from __future__ import annotations

from dataclasses import dataclass
from textwrap import dedent

from runloop_api_client import Runloop


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


def render_setup_script(agent_repo: RepoSlug, install_command: str) -> str:
    repo_url = f"https://github.com/{agent_repo.owner}/{agent_repo.name}.git"
    target_dir = f"/home/user/src/{agent_repo.name}"
    return dedent(
        f"""
        set -euo pipefail
        export PATH="$HOME/.local/bin:$PATH"
        mkdir -p /home/user/src
        if ! command -v uv >/dev/null 2>&1; then
            curl -LsSf https://astral.sh/uv/install.sh | sh
        fi
        rm -rf "{target_dir}"
        git clone "{repo_url}" "{target_dir}"
        cd "{target_dir}"
        {install_command}
        """
    ).strip()


def build_blueprint(name: str, agent_repo: RepoSlug, api_key: str, install_command: str) -> str:
    client = Runloop(bearer_token=api_key)
    setup_script = render_setup_script(agent_repo, install_command)
    blueprint = client.blueprints.create_and_await_build_complete(
        name=name,
        system_setup_commands=[setup_script],
        metadata={
            "agent_repo": f"{agent_repo.owner}/{agent_repo.name}",
            "install_command": install_command,
        },
    )
    return blueprint.id


__all__ = ["RepoSlug", "render_setup_script", "build_blueprint"]
