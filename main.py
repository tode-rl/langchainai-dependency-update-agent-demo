from __future__ import annotations

import argparse
import os

from runloop_api_client import Runloop

from monorepo_cli import BlueprintMemory, DEFAULT_STATE_FILE, AGENT_INSTALL_PATH
from monorepo_cli.blueprint_build import RepoSlug, build_blueprint
from monorepo_cli.devbox_runner import (
    GitRepo,
    build_agent_command,
    create_devbox,
    ensure_api_key,
    run_agent_in_devbox,
    shutdown_devbox,
)


def build_blueprint_command(args: argparse.Namespace) -> None:
    repo = RepoSlug.parse(args.agent_repo)
    api_key = ensure_api_key(os.environ.get)
    blueprint_id = build_blueprint(
        name=args.name,
        agent_repo=repo,
        api_key=api_key,
    )
    record = BlueprintMemory().remember(args.name, blueprint_id)
    print(
        f"Blueprint '{record.name}' built successfully.\n"
        f"  ID: {record.blueprint_id}\n"
        f"  Cached at: {DEFAULT_STATE_FILE}"
    )


def _resolve_blueprint(args: argparse.Namespace, memory: BlueprintMemory):
    blueprint_id = args.blueprint_id
    blueprint_name = args.blueprint_name

    if blueprint_name:
        record = memory.recall(blueprint_name)
        if not record:
            raise RuntimeError(f"No cached blueprint named '{blueprint_name}' was found.")
        if not blueprint_id:
            blueprint_id = record.blueprint_id
    elif not blueprint_id:
        record = memory.recall()
        if record:
            blueprint_id = record.blueprint_id
            blueprint_name = record.name

    if not blueprint_id:
        raise RuntimeError(
            "A blueprint ID is required to launch a devbox. "
            "Pass --blueprint-id or run build-blueprint first."
        )
    return blueprint_id, blueprint_name, AGENT_INSTALL_PATH


def run_remote_agent_command(args: argparse.Namespace) -> None:
    memory = BlueprintMemory()
    blueprint_id, blueprint_name, agent_path = _resolve_blueprint(args, memory)
    repo = GitRepo.from_url(args.repo)
    repo_path = args.repo_path or f"/home/user/{repo.name}"
    api_key = ensure_api_key(os.environ.get)
    client = Runloop(bearer_token=api_key)

    devbox_id = create_devbox(
        client=client,
        repo=repo,
        blueprint_id=blueprint_id,
        blueprint_name=blueprint_name,
        devbox_name=args.devbox_name,
    )
    print(f"Devbox {devbox_id} is running. Streaming agent output...\n")
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
                agent_install_path=agent_path,
            ),
        )
    finally:
        if args.cleanup:
            shutdown_devbox(client, devbox_id)
        else:
            print(f"Devbox {devbox_id} left running (pass --cleanup to shut it down automatically).")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LangChain dependency agent toolbox.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build-blueprint", help="Build and cache a Runloop blueprint for the agent.")
    build_parser.add_argument("--name", required=True, help="Blueprint name, e.g. dependency-updater.")
    build_parser.add_argument(
        "--agent-repo",
        required=True,
        help="GitHub slug containing the agent code, e.g. langchainai/dependency-agent.",
    )
    build_parser.set_defaults(func=build_blueprint_command)

    run_parser = subparsers.add_parser(
        "run-remote-agent", help="Launch a devbox from a blueprint and stream the agent output."
    )
    run_parser.add_argument("--repo", required=True, help="GitHub repository URL to mount.")
    run_parser.add_argument("--branch-name", default="runloop/dependency-updates", help="Branch to push updates to.")
    run_parser.add_argument("--blueprint-name", help="Blueprint name override.")
    run_parser.add_argument("--blueprint-id", help="Explicit blueprint ID override.")
    run_parser.add_argument("--devbox-name", help="Optional devbox name override.")
    run_parser.add_argument("--repo-path", help="Override repo path inside the devbox.")
    run_parser.add_argument("--llm-model", help="LLM model override for the agent.")
    run_parser.add_argument("--no-dry-run", action="store_true", help="Allow the agent to push changes.")
    run_parser.add_argument("--cleanup", action="store_true", help="Shutdown the devbox after execution.")
    run_parser.add_argument("--quiet", action="store_true", help="Suppress streaming agent logs.")
    run_parser.set_defaults(func=run_remote_agent_command)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
