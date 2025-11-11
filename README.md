## LangChain Dependency Update Agent Mono-repo

This workspace contains the LangChain-based dependency updater agent plus the infrastructure scripts required to package and run it on Runloop.dev cloud devboxes.

### Repository Layout

- `agents/langchain-deps/` – agent package, LangChain tools, CLI entrypoints, and tests.
- `infra/runloop-blueprint/` – Runloop blueprint configuration, provisioning scripts, and orchestration helpers.
- `main.py` – repo-level CLI helpers for building devbox blueprints and launching remote runs.

### VSCode Development Environment

1. Install [uv](https://docs.astral.sh/uv/). Ensure it is on your `$PATH`.
2. Create one workspace venv at the repo root and install editable deps:
   ```bash
   uv venv
   source .venv/bin/activate
   uv pip install -e agents/langchain-deps -e infra/runloop-blueprint
   ```
3. Open the folder in VSCode (`code .`), then press `⌘⇧P`/`Ctrl+Shift+P` → **Python: Select Interpreter** → pick `<repo>/.venv/bin/python`. VSCode will activate the same environment for terminals, the language server, and test discovery.
4. (Optional) Set `"python.defaultInterpreterPath": "${workspaceFolder}/.venv/bin/python"` in `.vscode/settings.json` so teammates reuse the interpreter automatically.
5. Run tests or scripts through `uv run …` to ensure the correct environment is used even outside VSCode.

See the sub-directory READMEs for per-package commands that work seamlessly once the workspace venv is selected in VSCode.

### Frequently Used Commands

```bash
# Run the agent's unit tests from the repo root
uv run pytest agents/langchain-deps/tests

# Build or update the Runloop blueprint
uv run python infra/runloop-blueprint/build_blueprint.py --name dependency-updater --agent-repo langchainai/dependency-agent

# Launch the agent remotely via the CLI wrapper
uv run python main.py run-remote-agent --repo https://github.com/org/project
```

### Next Steps

- `agents/langchain-deps/README.md` – developing and testing the LangChain agent package (including VSCode tips).
- `infra/runloop-blueprint/README.md` – building Runloop blueprints and executing the agent on devboxes.
