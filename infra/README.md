## Runloop Blueprint Toolkit

This module contains helper scripts to package the LangChain dependency updater agent into a Runloop blueprint and trigger remote executions using the official [`runloop_api_client`](https://pypi.org/project/runloop_api_client/) primitives.

### VSCode-Friendly Setup

From the repository root:

```bash
uv venv
source .venv/bin/activate
uv pip install -e infra
```

Open the repo in VSCode, run **Python: Select Interpreter** and choose `<repo>/.venv/bin/python` so the editor reuses the shared environment. Terminals inside VSCode will now have `runloop_api_client` (and its dependencies) on the path, and scripts in this directory can be launched with `uv run python infra/scripts/<script>.py ...`.

### Files

- `scripts/build_blueprint.py` – orchestrates `runloop blueprint build` / `push` commands using the repo as a code mount.
- `scripts/run_agent_on_repo.py` – bootstraps a devbox from a blueprint, mounts a public GitHub repo, and runs the agent.

### Usage

```bash
# 1. Build the blueprint from your agent repo (requires RUNLOOP_API_KEY)
python scripts/build_blueprint.py --name dependency-updater --agent-repo your-org/langchain-deps-agent

# 2. Run the agent against a repo using the newly built blueprint
python scripts/run_agent_on_repo.py --blueprint-name dependency-updater \
    --agent-install-path /home/user/langchainai-dependency-update-agent-demo \
    --repo https://github.com/org/project \
    --llm-model gpt-5-mini
```

Every successful build stores the latest `blueprint_id` in `~/.cache/langchain-deps-agent/blueprints.json`. The repo-level CLI (see `main.py`) reads the same cache so you can launch devboxes without copying IDs around manually.
