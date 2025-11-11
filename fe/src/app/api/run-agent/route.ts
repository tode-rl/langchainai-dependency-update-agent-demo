import Runloop from '@runloop/api-client';

export const runtime = 'nodejs';

const AGENT_OPTIONS = new Set(['langchain-deps-agent', 'langchain-lint-agent']);
const MODEL_NAME = 'gpt-5-mini';
const BLUEPRINT_NAME = 'dependency-updater';
const DEFAULT_BRANCH = 'runloop/dependency-updates';
const AGENT_INSTALL_PATH = '/home/user/langchainai-dependency-update-agent-demo';

type StreamEvent =
  | { type: 'status'; message: string }
  | { type: 'chunk'; data: string }
  | { type: 'error'; message: string }
  | { type: 'done' };

interface RunAgentRequest {
  agent: string;
  repoUrl: string;
  model: string;
}

interface ParsedRepo {
  owner: string;
  name: string;
}

export async function POST(request: Request) {
  let payload: RunAgentRequest;
  try {
    payload = await request.json();
  } catch {
    return new Response(JSON.stringify({ error: 'Invalid JSON body' }), { status: 400 });
  }

  const { agent, repoUrl, model } = payload ?? {};
  if (!agent || !AGENT_OPTIONS.has(agent)) {
    return new Response(JSON.stringify({ error: 'Unsupported agent selection.' }), { status: 400 });
  }

  if (!repoUrl || typeof repoUrl !== 'string') {
    return new Response(JSON.stringify({ error: 'A public GitHub repository URL is required.' }), {
      status: 400,
    });
  }

  if (model !== MODEL_NAME) {
    return new Response(JSON.stringify({ error: `Model must be ${MODEL_NAME}.` }), {
      status: 400,
    });
  }

  let parsedRepo: ParsedRepo;
  try {
    parsedRepo = parseGitHubRepo(repoUrl);
  } catch (error) {
    return new Response(JSON.stringify({ error: (error as Error).message }), { status: 400 });
  }

  const apiKey = process.env.RUNLOOP_API_KEY;
  if (!apiKey) {
    return new Response(JSON.stringify({ error: 'RUNLOOP_API_KEY is not configured on the server.' }), {
      status: 500,
    });
  }

  const client = new Runloop({ bearerToken: apiKey });

  const stream = new ReadableStream({
    async start(controller) {
      const encoder = new TextEncoder();
      const send = (event: StreamEvent) => {
        controller.enqueue(encoder.encode(JSON.stringify(event) + '\n'));
      };

      let devboxId: string | undefined;
      let hadError = false;

      try {
        send({ type: 'status', message: 'Provisioning devbox...' });
        const devbox = await client.devboxes.createAndAwaitRunning({
          blueprint_name: BLUEPRINT_NAME,
          code_mounts: [
            {
              repo_owner: parsedRepo.owner,
              repo_name: parsedRepo.name,
            },
          ],
          name: `fe-session-${parsedRepo.name}`.slice(0, 63),
        });
        devboxId = devbox.id;

        send({ type: 'status', message: `Devbox ${devbox.id} is running.` });

        const repoPath = `/home/user/${parsedRepo.name}`;
        const command = buildAgentCommand({
          agent,
          repoPath,
          model,
        });

        send({ type: 'status', message: `Executing: ${command}` });

        const execution = await client.devboxes.executions.executeAsync(devbox.id, {
          command,
        });

        send({ type: 'status', message: 'Agent execution started.' });

        const stdoutStream = await client.devboxes.executions.streamStdoutUpdates(devbox.id, execution.execution_id);
        await forwardLogs(stdoutStream, send);

        const completed = await client.devboxes.executions.awaitCompleted(devbox.id, execution.execution_id);
        send({
          type: 'status',
          message: `Execution finished with exit status ${completed.exit_status ?? 'unknown'}.`,
        });
      } catch (error) {
        hadError = true;
        console.error('Failed to run agent', error);
        send({ type: 'error', message: formatError(error) });
      } finally {
        if (devboxId) {
          const message = hadError
            ? `Devbox ${devboxId} left running for debugging (manual shutdown required).`
            : `Devbox ${devboxId} left running for inspection. Remember to shut it down manually when done.`;
          send({ type: 'status', message });
        }
        send({ type: 'done' });
        controller.close();
      }
    },
  });

  return new Response(stream, {
    headers: {
      'Content-Type': 'application/x-ndjson',
      'Cache-Control': 'no-cache',
    },
  });
}

function parseGitHubRepo(url: string): ParsedRepo {
  const trimmed = url.trim();
  const pattern = /github\.com[:/](?<owner>[\w.-]+)\/(?<name>[\w.-]+?)(?:\.git|\/)?$/i;
  const match = pattern.exec(trimmed);
  if (!match || !match.groups?.owner || !match.groups?.name) {
    throw new Error('Unable to parse GitHub repository URL.');
  }
  return {
    owner: match.groups.owner,
    name: match.groups.name.replace(/\.git$/i, ''),
  };
}

function buildAgentCommand({
  agent,
  repoPath,
  model,
}: {
  agent: string;
  repoPath: string;
  model: string;
}): string {
  const args = [
    'uv',
    'run',
    agent,
    '--repo-path',
    repoPath,
    '--branch-name',
    DEFAULT_BRANCH,
    '--llm-model',
    model,
  ];
  const command = args.map(shellQuote).join(' ');
  return `cd ${shellQuote(AGENT_INSTALL_PATH)} && ${command}`;
}

function shellQuote(value: string): string {
  if (/^[\w@%+=:,./-]+$/u.test(value)) {
    return value;
  }
  return `'${value.replace(/'/g, `'\\''`)}'`;
}

function formatError(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  if (typeof error === 'object' && error !== null) {
    return JSON.stringify(error);
  }
  return 'Unknown error';
}

async function forwardLogs(stream: AsyncIterable<{ output: string }> , send: (event: StreamEvent) => void) {
  for await (const chunk of stream) {
    if (chunk?.output) {
      send({ type: 'chunk', data: chunk.output });
    }
  }
}
