## LangChain Dependency Updater Agent

This package contains the LangChain-based agent that inspects a mounted repository, evaluates dependency upgrade paths, and produces pull requests.

### Key pieces

- `langchain_deps_agent/agent.py` – core orchestration logic for planning and applying updates.
- `langchain_deps_agent/tools/` – LangChain tool implementations (repo scanning, version resolution, git utilities).
- `langchain_deps_agent/cli.py` – local CLI to run the agent inside a Runloop devbox.

### Development

```bash
uv pip install -e .
langchain-deps-agent --repo-path /mnt/repo --config ./config.example.yaml
```
