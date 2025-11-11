from __future__ import annotations

import argparse
import os
from dataclasses import dataclass

from runloop_api_client import Runloop
from runloop_api_client.types.shared_params.code_mount_parameters import CodeMountParameters


@dataclass
class RepoSlug:
    owner: str
    name: str

    @classmethod
    def parse(cls, slug: str) -> "RepoSlug":
        if "/" not in slug:
            raise ValueError("Repo slug must be in the format owner/name")
        owner, name = slug.split("/", 1)
        return cls(owner=owner, name=name)


def build_blueprint(name: str, agent_repo: RepoSlug, api_key: str, dockerfile: str, install_command: str) -> str:
    client = Runloop(bearer_token=api_key)
    code_mounts = [
        CodeMountParameters(
            repo_owner=agent_repo.owner,
            repo_name=agent_repo.name,
            install_command=install_command,
        )
    ]

    setup_commands = [
        "set -euo pipefail",
        "python3 -m pip install --upgrade pip uv",
        f"cd /home/user/{agent_repo.name} && {install_command}",
    ]

    blueprint = client.blueprints.create_and_await_build_complete(
        name=name,
        dockerfile=dockerfile,
        code_mounts=code_mounts,
        system_setup_commands=setup_commands,
        metadata={"agent_repo": f"{agent_repo.owner}/{agent_repo.name}"},
    )
    return blueprint.id


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build and publish the Runloop blueprint for the dependency agent.")
    parser.add_argument("--name", required=True, help="Blueprint name, e.g. dependency-updater")
    parser.add_argument(
        "--agent-repo",
        required=True,
        help="GitHub slug containing the agent code, e.g. langchainai/dependency-agent.",
    )
    parser.add_argument(
        "--install-command",
        default="uv pip install -e .",
        help="Command executed in the agent repo to install the package.",
    )
    parser.add_argument(
        "--dockerfile",
        default="FROM runloophq/devbox-python:3.12\nENV UV_SYSTEM_PYTHON=1\nRUN pip install --upgrade pip uv",
        help="Dockerfile contents for the blueprint base image.",
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
        dockerfile=args.dockerfile,
        install_command=args.install_command,
    )
    print(f"Blueprint build started. ID: {blueprint_id}")


if __name__ == "__main__":
    main()
