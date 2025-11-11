from __future__ import annotations

import argparse
import os

from monorepo_cli import BlueprintMemory
from monorepo_cli.blueprint_build import RepoSlug, build_blueprint


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and publish the Runloop blueprint for the dependency agent.")
    parser.add_argument("--name", required=True, help="Blueprint name, e.g. dependency-updater")
    parser.add_argument(
        "--agent-repo",
        required=True,
        help="GitHub slug containing the agent code, e.g. langchainai/dependency-agent.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    api_key = os.environ.get("RUNLOOP_API_KEY")
    if not api_key:
        raise RuntimeError("RUNLOOP_API_KEY environment variable is required to call the Runloop API.")
    repo = RepoSlug.parse(args.agent_repo)
    blueprint_id = build_blueprint(
        name=args.name,
        agent_repo=repo,
        api_key=api_key,
    )
    BlueprintMemory().remember(name=args.name, blueprint_id=blueprint_id)
    print(f"Blueprint build complete. ID: {blueprint_id}")


if __name__ == "__main__":
    main()
