from __future__ import annotations

import re
import shlex
import sys
import uuid
from dataclasses import dataclass
from typing import Iterable, Optional

from runloop_api_client import Runloop
from runloop_api_client.types.shared_params.code_mount_parameters import CodeMountParameters


@dataclass
class GitRepo:
    owner: str
    name: str

    @classmethod
    def from_url(cls, url: str) -> "GitRepo":
        pattern = re.compile(r"(?:github\.com[:/])(?P<owner>[\w.-]+)/(?P<name>[\w.-]+)(?:\.git)?")
        match = pattern.search(url)
        if not match:
            raise ValueError(f"Unable to parse GitHub URL: {url}")
        return cls(owner=match.group("owner"), name=match.group("name"))


def ensure_api_key(env_lookup) -> str:
    api_key = env_lookup("RUNLOOP_API_KEY")
    if not api_key:
        raise RuntimeError("RUNLOOP_API_KEY environment variable is required.")
    return api_key


def create_devbox(
    client: Runloop,
    repo: GitRepo,
    blueprint_id: Optional[str],
    blueprint_name: Optional[str],
    devbox_name: Optional[str] = None,
) -> str:
    if not blueprint_id and not blueprint_name:
        raise ValueError("Either blueprint_id or blueprint_name must be provided.")
    params = {
        "name": devbox_name or f"deps-agent-{uuid.uuid4().hex[:8]}",
        "code_mounts": [CodeMountParameters(repo_owner=repo.owner, repo_name=repo.name)],
    }
    if blueprint_name:
        params["blueprint_name"] = blueprint_name
    elif blueprint_id:
        params["blueprint_id"] = blueprint_id

    devbox = client.devboxes.create_and_await_running(**params)
    return devbox.id


def build_agent_command(
    repo_url: str,
    repo_path: str,
    branch_name: str,
    dry_run: bool,
    llm_model: Optional[str],
    verbose: bool,
) -> str:
    parts = [
        "langchain-deps-agent",
        "run",
        "--repo-path",
        repo_path,
        "--repo-url",
        repo_url,
        "--branch-name",
        branch_name,
    ]
    if not dry_run:
        parts.append("--no-dry-run")
    if llm_model:
        parts.extend(["--llm-model", llm_model])
    if verbose:
        parts.append("--verbose")
    return " ".join(parts)


def stream_execution_logs(logs: Iterable[str]) -> None:
    for chunk in logs:
        sys.stdout.write(chunk)
    sys.stdout.flush()


def run_agent_in_devbox(
    client: Runloop,
    devbox_id: str,
    command: str,
) -> None:
    execution = client.devboxes.execute_and_await_completion(devbox_id, command=command)
    logs = getattr(execution, "logs", None) or []
    if logs:
        stream_execution_logs(logs)
    elif getattr(execution, "output", None):
        sys.stdout.write(execution.output)
        sys.stdout.flush()


def shutdown_devbox(client: Runloop, devbox_id: str) -> None:
    client.devboxes.shutdown(devbox_id)


__all__ = [
    "GitRepo",
    "ensure_api_key",
    "create_devbox",
    "build_agent_command",
    "run_agent_in_devbox",
    "shutdown_devbox",
]
