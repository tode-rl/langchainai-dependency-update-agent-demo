## Runloop Blueprint Toolkit

This module contains helper scripts to package the LangChain dependency updater agent into a Runloop blueprint and trigger remote executions using the official [`runloop_api_client`](https://pypi.org/project/runloop_api_client/) primitives.

### Files

- `build_blueprint.py` – orchestrates `runloop blueprint build` / `push` commands using the repo as a code mount.
- `run_agent_on_repo.py` – bootstraps a devbox from a blueprint, mounts a public GitHub repo, and runs the agent.
- `blueprint_manifest.example.yaml` – sample manifest describing mounts, startup commands, and env vars.

### Usage

```bash
# 1. Build the blueprint from your agent repo (requires RUNLOOP_API_KEY)
python build_blueprint.py --name dependency-updater --agent-repo your-org/langchain-deps-agent

# 2. Run the agent against a repo using the newly built blueprint
python run_agent_on_repo.py --blueprint-name dependency-updater \
    --repo https://github.com/org/project \
    --llm-model gpt-4o-mini
```
