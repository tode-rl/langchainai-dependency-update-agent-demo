from __future__ import annotations
from dataclasses import dataclass
from runloop_api_client import Runloop
from runloop_api_client.types.shared.launch_parameters import (
    LaunchParameters,
    UserParameters,
)
import os

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


def render_setup_script(agent_repo: RepoSlug) -> list[str]:
    repo_url = f"https://github.com/{agent_repo.owner}/{agent_repo.name}.git"
    target_dir = f"/home/user/{agent_repo.name}"
    return [
        "wget -qO- https://astral.sh/uv/install.sh | sh",
        f'git clone "{repo_url}" "{target_dir}"',
        f'cd "{target_dir}" && uv sync && uv pip install -e agents -e infra',
        f'echo "export OPENAI_API_KEY={os.environ.get("OPENAI_API_KEY", "")}" >> /home/user/.bashrc',
        f'echo "export OPENAI_API_KEY={os.environ.get("OPENAI_API_KEY", "")}" >> /root/.bashrc',
    ]


def build_blueprint(name: str, agent_repo: RepoSlug, api_key: str) -> str:
    client = Runloop(bearer_token=api_key)
    setup_script = render_setup_script(agent_repo)
    blueprint = client.blueprints.create_and_await_build_complete(
        name=name,
        system_setup_commands=setup_script,
        launch_parameters=LaunchParameters(
            user_parameters=UserParameters(
                uid=0,
                username="root",
            )
        ),
    )
    return blueprint.id


__all__ = ["RepoSlug", "render_setup_script", "build_blueprint"]
