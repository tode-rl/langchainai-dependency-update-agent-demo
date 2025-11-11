'use client';

import { FormEvent, useCallback, useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Separator } from '@/components/ui/separator';

const MODEL_NAME = 'gpt-5-mini';
const BLUEPRINT_NAME = 'dependency-updater';

const AGENT_OPTIONS = [
  { value: 'langchain-deps-agent', label: 'LangChain Deps Agent' },
  { value: 'langchain-lint-agent', label: 'LangChain Lint Agent' },
];

type SessionStatus = 'pending' | 'provisioning' | 'running' | 'completed' | 'error';

type StreamEvent =
  | { type: 'status'; message: string }
  | { type: 'chunk'; data: string }
  | { type: 'error'; message: string }
  | { type: 'done' };

interface SessionEvent {
  id: string;
  message: string;
  timestamp: number;
  variant: 'status' | 'error';
}

interface Session {
  id: string;
  agent: string;
  repoUrl: string;
  model: string;
  startedAt: number;
  status: SessionStatus;
  logs: string;
  events: SessionEvent[];
  error?: string;
}

export default function HomePage() {
  const [repoUrl, setRepoUrl] = useState('');
  const [agent, setAgent] = useState(AGENT_OPTIONS[0]!.value);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [isLaunching, setIsLaunching] = useState(false);

  const mutateSession = useCallback((sessionId: string, updater: (session: Session) => Session) => {
    setSessions((prev) => prev.map((session) => (session.id === sessionId ? updater(session) : session)));
  }, []);

  const appendEvent = useCallback(
    (sessionId: string, message: string, variant: 'status' | 'error' = 'status') => {
      mutateSession(sessionId, (session) => ({
        ...session,
        events: [
          ...session.events,
          {
            id: createId(),
            message,
            timestamp: Date.now(),
            variant,
          },
        ],
      }));
    },
    [mutateSession],
  );

  const appendLog = useCallback(
    (sessionId: string, chunk: string) => {
      mutateSession(sessionId, (session) => ({
        ...session,
        logs: session.logs + chunk,
      }));
    },
    [mutateSession],
  );

  const setStatus = useCallback(
    (sessionId: string, status: SessionStatus, error?: string) => {
      mutateSession(sessionId, (session) => ({
        ...session,
        status,
        error,
      }));
    },
    [mutateSession],
  );

  const handleStreamEvent = useCallback(
    (event: StreamEvent, sessionId: string) => {
      switch (event.type) {
        case 'status':
          appendEvent(sessionId, event.message);
          if (event.message.toLowerCase().includes('executing')) {
            setStatus(sessionId, 'running');
          }
          break;
        case 'chunk':
          setStatus(sessionId, 'running');
          appendLog(sessionId, event.data);
          break;
        case 'error':
          appendEvent(sessionId, event.message, 'error');
          appendLog(sessionId, `\n[error] ${event.message}\n`);
          setStatus(sessionId, 'error', event.message);
          break;
        case 'done':
          mutateSession(sessionId, (session) => {
            if (session.status === 'error') {
              return session;
            }
            return {
              ...session,
              status: 'completed',
            };
          });
          appendEvent(sessionId, 'Session finished.');
          break;
        default:
          break;
      }
    },
    [appendEvent, appendLog, mutateSession, setStatus],
  );

  const startRun = useCallback(
    async (session: Session) => {
      setIsLaunching(false);
      setStatus(session.id, 'provisioning');
      appendEvent(session.id, 'Provisioning devbox...');

      try {
        const response = await fetch('/api/run-agent', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            agent: session.agent,
            repoUrl: session.repoUrl,
            model: session.model,
          }),
        });

        if (!response.ok || !response.body) {
          const message = await readErrorMessage(response);
          throw new Error(message);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
          const { value, done } = await reader.read();
          buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });

          buffer = processBuffer(buffer, (line) => {
            try {
              const event = JSON.parse(line) as StreamEvent;
              handleStreamEvent(event, session.id);
            } catch (error) {
              console.error('Unable to parse stream chunk', error);
            }
          });

          if (done) {
            if (buffer.trim()) {
              try {
                const event = JSON.parse(buffer.trim()) as StreamEvent;
                handleStreamEvent(event, session.id);
              } catch (error) {
                console.error('Unable to parse trailing chunk', error);
              }
            }
            break;
          }
        }
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Unexpected error';
        appendEvent(session.id, message, 'error');
        appendLog(session.id, `\n[error] ${message}\n`);
        setStatus(session.id, 'error', message);
      }
    },
    [appendEvent, appendLog, handleStreamEvent, setStatus],
  );

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!repoUrl.trim() || isLaunching) {
      return;
    }

    setIsLaunching(true);
    const session: Session = {
      id: createId(),
      agent,
      repoUrl: repoUrl.trim(),
      model: MODEL_NAME,
      startedAt: Date.now(),
      status: 'pending',
      logs: '',
      events: [
        {
          id: createId(),
          message: 'Session created.',
          timestamp: Date.now(),
          variant: 'status',
        },
      ],
    };

    setSessions((prev) => [session, ...prev]);
    setRepoUrl('');
    startRun(session);
  };

  const hasSessions = sessions.length > 0;

  return (
    <div className="min-h-screen bg-muted/40">
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-4 py-10 sm:px-6 lg:px-8">
        <header className="space-y-1">
          <p className="text-sm font-semibold text-primary">Runloop Blueprint · {BLUEPRINT_NAME}</p>
          <h1 className="text-3xl font-semibold text-foreground">Stream agent runs in a devbox</h1>
          <p className="text-sm text-muted-foreground">
            Launch a session by mounting a public GitHub repo, then watch the output of{' '}
            <code className="rounded bg-muted px-1.5 py-0.5 text-xs font-mono">{`uv run <agent>`}</code> stream
            back in real time.
          </p>
        </header>

        <Card>
          <CardHeader className="pb-4">
            <CardTitle>New agent chat</CardTitle>
            <CardDescription>Provide a repo and choose which built-in agent should handle it.</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2 md:col-span-2">
                <Label htmlFor="repo-url">Public repository URL</Label>
                <Input
                  id="repo-url"
                  placeholder="https://github.com/langchain-ai/langchain"
                  value={repoUrl}
                  onChange={(event) => setRepoUrl(event.target.value)}
                  required
                  autoComplete="off"
                />
              </div>
              <div className="space-y-2">
                <Label>Agent</Label>
                <Select value={agent} onValueChange={setAgent}>
                  <SelectTrigger>
                    <SelectValue placeholder="Choose agent" />
                  </SelectTrigger>
                  <SelectContent>
                    {AGENT_OPTIONS.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Model</Label>
                <Select value={MODEL_NAME} disabled>
                  <SelectTrigger>
                    <SelectValue placeholder={MODEL_NAME} />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={MODEL_NAME}>{MODEL_NAME} (locked)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="md:col-span-2">
                <Button type="submit" className="w-full md:w-auto" disabled={isLaunching}>
                  {isLaunching ? 'Starting session…' : 'Start chat'}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>

        <Separator />

        <section className="space-y-3">
          <div>
            <h2 className="text-xl font-semibold">Active chats</h2>
            <p className="text-sm text-muted-foreground">
              Each run executes inside a Runloop devbox provisioned from the dependency-updater blueprint.
            </p>
          </div>

          {!hasSessions ? (
            <Card className="border-dashed text-center text-sm text-muted-foreground">
              <CardContent className="py-10">
                Launch your first session to see live logs here.
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-4">
              {sessions.map((session) => (
                <SessionCard key={session.id} session={session} />
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );

  async function readErrorMessage(response: Response): Promise<string> {
    try {
      const data = await response.json();
      return data?.error ?? 'Failed to start agent run';
    } catch {
      return 'Failed to start agent run';
    }
  }

  function processBuffer(buffer: string, onLine: (line: string) => void) {
    const lines = buffer.split('\n');
    const trailing = lines.pop() ?? '';
    for (const line of lines) {
      if (line.trim().length === 0) continue;
      onLine(line.trim());
    }
    return trailing;
  }
}

function SessionCard({ session }: { session: Session }) {
  return (
    <Card>
      <CardHeader className="space-y-2">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <CardTitle className="text-lg">{session.repoUrl}</CardTitle>
            <CardDescription>
              {session.agent} · Model {session.model} · Started {formatTimestamp(session.startedAt)}
            </CardDescription>
          </div>
          <StatusBadge status={session.status} />
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <ScrollArea className="h-64 rounded-md border bg-muted/50">
          <pre className="h-full whitespace-pre-wrap p-4 font-mono text-sm leading-relaxed">
            {session.logs.trim().length > 0 ? (
              session.logs
            ) : (
              <span className="text-muted-foreground">Waiting for output…</span>
            )}
          </pre>
        </ScrollArea>
        <div className="space-y-2">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Events</p>
          <ul className="space-y-1 text-sm">
            {session.events.map((event) => (
              <li
                key={event.id}
                className="flex items-center justify-between rounded border bg-background px-2 py-1"
              >
                <span className={event.variant === 'error' ? 'text-destructive' : ''}>{event.message}</span>
                <span className="text-xs text-muted-foreground">{formatTimestamp(event.timestamp)}</span>
              </li>
            ))}
          </ul>
        </div>
      </CardContent>
    </Card>
  );
}

function StatusBadge({ status }: { status: SessionStatus }) {
  const label = useMemo(() => {
    switch (status) {
      case 'pending':
        return 'Pending';
      case 'provisioning':
        return 'Provisioning';
      case 'running':
        return 'Running';
      case 'completed':
        return 'Completed';
      case 'error':
        return 'Error';
      default:
        return status;
    }
  }, [status]);

  const variants: Record<SessionStatus, string> = {
    pending: 'bg-muted text-foreground',
    provisioning: 'bg-amber-100 text-amber-900',
    running: 'bg-blue-100 text-blue-900',
    completed: 'bg-emerald-100 text-emerald-900',
    error: 'bg-rose-100 text-rose-900',
  };

  return (
    <span className={`rounded-full px-3 py-1 text-xs font-semibold tracking-wide ${variants[status]}`}>
      {label}
    </span>
  );
}

function createId() {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : Math.random().toString(36).slice(2);
}

function formatTimestamp(timestamp: number) {
  return new Intl.DateTimeFormat('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  }).format(new Date(timestamp));
}
