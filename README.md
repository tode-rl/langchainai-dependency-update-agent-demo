## LangChain Dependency Update Agent Mono-repo

This workspace contains the LangChain-based dependency updater agent plus the infrastructure scripts required to package and run it on Runloop.dev cloud devboxes.

### Structure

- `agents/langchain-deps/` – agent package, LangChain tools, CLI entrypoints, and tests.
- `infra/runloop-blueprint/` – Runloop blueprint configuration, provisioning scripts, and orchestration helpers.

### Getting Started

1. Install [uv](https://docs.astral.sh/uv/) and run `uv venv && source .venv/bin/activate`.
2. Install dependencies with `uv pip install -e agents/langchain-deps`.
3. See `infra/runloop-blueprint/README.md` for building and publishing the Runloop blueprint with `runloop_api_client`.
4. Use `infra/runloop-blueprint/run_agent_on_repo.py --blueprint-name <name> --repo https://github.com/org/repo` to launch a devbox and run the agent remotely.
