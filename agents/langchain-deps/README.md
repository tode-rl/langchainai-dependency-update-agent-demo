## LangChain Dependency Updater Agent

This package contains the LangChain-based agent that inspects a mounted repository, evaluates dependency upgrade paths, and produces pull requests.

### Key pieces

- `langchain_deps_agent/agent.py` – core orchestration logic for planning and applying updates.
- `langchain_deps_agent/tools/` – LangChain tool implementations (repo scanning, version resolution, git utilities).
- `langchain_deps_agent/cli.py` – local CLI to run the agent inside a Runloop devbox.

### Development

1. From the repo root, make sure `.venv` exists (`uv venv && source .venv/bin/activate`). Installing the workspace dependencies from the root ensures VSCode sees a single interpreter.
2. Install this package in editable mode (VSCode terminals inherit the interpreter you selected in the root README instructions):
   ```bash
   uv pip install -e agents/langchain-deps
   ```
3. Open the `agents/langchain-deps` folder in VSCode (or use a multi-root workspace) and confirm **Python: Select Interpreter** is still pointing at `<repo>/.venv/bin/python`. The language server will now resolve the agent modules and tests without extra configuration.
4. Run the CLI locally:
   ```bash
   uv run langchain-deps-agent --repo-path /mnt/repo --config ./config.example.yaml
   ```
