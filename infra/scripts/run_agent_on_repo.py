from __future__ import annotations

import argparse
import os
import uuid

from runloop_api_client import Runloop

from monorepo_cli.devbox_runner import (
    GitRepo,
    build_agent_command,
    create_devbox,
    ensure_api_key,
    run_agent_in_devbox,
    shutdown_devbox,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the dependency updater agent inside a Runloop devbox.")
    parser.add_argument("--repo", required=True, help="GitHub repository URL to mount, e.g. https://github.com/org/project")
    parser.add_argument("--branch-name", default="runloop/dependency-updates", help="Target branch for changes.")
    parser.add_argument("--blueprint-name", help="Blueprint name to launch devboxes from.")
    parser.add_argument("--blueprint-id", help="Explicit blueprint ID to use.")
    parser.add_argument("--devbox-name", help="Optional devbox name override.")
    parser.add_argument("--repo-path", help="Override the repo path inside the devbox (default /home/user/<repo>).")
    parser.add_argument("--no-dry-run", action="store_true", help="Allow the agent to push changes.")
    parser.add_argument("--cleanup", action="store_true", help="Shutdown the devbox after the agent finishes.")
    parser.add_argument("--llm-model", help="Override the LLM model passed to LangChain.")
    parser.add_argument("--quiet", action="store_true", help="Suppress streaming agent logs.")
    parser.add_argument(
        "--agent-install-path",
        required=True,
        help="Path inside the devbox where the agent repository lives (e.g. /home/user/langchain-dependency-agent).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo = GitRepo.from_url(args.repo)
    repo_path = args.repo_path or f"/home/user/{repo.name}"
    client = Runloop(bearer_token=ensure_api_key(os.environ.get))

    devbox_id = create_devbox(
        client=client,
        repo=repo,
        blueprint_id=args.blueprint_id,
        blueprint_name=args.blueprint_name,
        devbox_name=args.devbox_name or f"deps-agent-{uuid.uuid4().hex[:8]}",
    )
    try:
        run_agent_in_devbox(
            client=client,
            devbox_id=devbox_id,
            command=build_agent_command(
                repo_url=args.repo,
                repo_path=repo_path,
                branch_name=args.branch_name,
                dry_run=not args.no_dry_run,
                llm_model=args.llm_model,
                verbose=not args.quiet,
                agent_install_path=args.agent_install_path,
            ),
        )
    finally:
        if args.cleanup:
            shutdown_devbox(client, devbox_id)
        else:
            print(f"Devbox {devbox_id} left running (pass --cleanup to shut it down automatically).")


if __name__ == "__main__":
    main()
