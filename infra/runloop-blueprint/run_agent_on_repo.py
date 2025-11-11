from __future__ import annotations

import argparse
import os
import re
import sys
import uuid
from dataclasses import dataclass

from runloop_api_client import Runloop
from runloop_api_client.types.shared_params.code_mount_parameters import CodeMountParameters


@dataclass
class RepoSlug:
    owner: str
    name: str

    @classmethod
    def from_url(cls, url: str) -> "RepoSlug":
        pattern = re.compile(r"(?:github\\.com[:/])(?P<owner>[\\w.-]+)/(?P<name>[\\w.-]+)(?:\\.git)?")
        match = pattern.search(url)
        if not match:
            raise ValueError(f"Unable to parse GitHub URL: {url}")
        return cls(owner=match.group("owner"), name=match.group("name"))


def ensure_api_key() -> str:
    api_key = os.environ.get("RUNLOOP_API_KEY")
    if not api_key:
        raise RuntimeError("RUNLOOP_API_KEY environment variable is required.")
    return api_key


def create_devbox(
    client: Runloop,
    blueprint_name: str | None,
    blueprint_id: str | None,
    repo: RepoSlug,
    devbox_name: str,
) -> str:
    if not blueprint_name and not blueprint_id:
        raise ValueError("Either blueprint_name or blueprint_id must be provided.")

    kwargs = {"name": devbox_name, "code_mounts": [CodeMountParameters(repo_owner=repo.owner, repo_name=repo.name)]}
    if blueprint_id:
        kwargs["blueprint_id"] = blueprint_id
    if blueprint_name:
        kwargs["blueprint_name"] = blueprint_name

    devbox = client.devboxes.create_and_await_running(**kwargs)
    return devbox.id


def run_agent(
    client: Runloop,
    devbox_id: str,
    repo_url: str,
    repo_path: str,
    branch_name: str,
    dry_run: bool,
    llm_model: str | None,
    verbose: bool,
) -> None:
    command_parts = [
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
        command_parts.append("--no-dry-run")
    if llm_model:
        command_parts.extend(["--llm-model", llm_model])
    if verbose:
        command_parts.append("--verbose")

    command = " ".join(command_parts)
    execution = client.devboxes.execute_and_await_completion(devbox_id, command=command)
    logs = getattr(execution, "logs", None) or []
    for chunk in logs:
        sys.stdout.write(chunk)
    if not logs and getattr(execution, "output", None):
        sys.stdout.write(execution.output)
    sys.stdout.flush()


def shutdown_devbox(client: Runloop, devbox_id: str) -> None:
    client.devboxes.shutdown(devbox_id)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the dependency updater agent inside a Runloop devbox.")
    parser.add_argument("--repo", required=True, help="GitHub repository URL to mount, e.g. https://github.com/org/project")
    parser.add_argument("--branch-name", default="runloop/dependency-updates", help="Target branch for changes.")
    parser.add_argument("--blueprint-name", help="Blueprint name to launch devboxes from.")
    parser.add_argument("--blueprint-id", help="Explicit blueprint ID to use.")
    parser.add_argument("--devbox-name", help="Optional devbox name override.")
    parser.add_argument("--repo-path", help="Override the repo path inside the devbox (default /home/user/<repo>).")
    parser.add_argument("--no-dry-run", action="store_true", help="Allow the agent to push changes.")
    parser.add_argument("--keep", action="store_true", help="Keep the devbox running after the agent finishes.")
    parser.add_argument("--llm-model", help="Override the LLM model passed to LangChain.")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose agent logging.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    repo = RepoSlug.from_url(args.repo)
    repo_path = args.repo_path or f"/home/user/{repo.name}"
    devbox_name = args.devbox_name or f"deps-agent-{uuid.uuid4().hex[:8]}"
    client = Runloop(bearer_token=ensure_api_key())

    devbox_id = create_devbox(
        client=client,
        blueprint_name=args.blueprint_name,
        blueprint_id=args.blueprint_id,
        repo=repo,
        devbox_name=devbox_name,
    )
    try:
        run_agent(
            client=client,
            devbox_id=devbox_id,
            repo_url=args.repo,
            repo_path=repo_path,
            branch_name=args.branch_name,
            dry_run=not args.no_dry_run,
            llm_model=args.llm_model,
            verbose=args.verbose,
        )
    finally:
        if not args.keep:
            shutdown_devbox(client, devbox_id)


if __name__ == "__main__":
    main()
