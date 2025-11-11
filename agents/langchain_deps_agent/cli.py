from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from .agent import DependencyUpdaterAgent, DependencyUpdateRequest
from .config import load_settings
from .tools.github_repo_tool import RepoMetadata, RepoScannerTool

app = typer.Typer(help="Run the LangChain dependency updater agent.")
console = Console()


@app.command()
def run(
    repo_path: Path = typer.Option(
        ..., "--repo-path", help="Path to the repository checked out on the Runloop devbox."
    ),
    repo_url: Optional[str] = typer.Option(None, "--repo-url", help="Original GitHub repository URL."),
    branch_name: str = typer.Option("runloop/dependency-updates", "--branch-name", help="Branch to push changes to."),
    dry_run: bool = typer.Option(True, "--dry-run/--no-dry-run", help="Disable pushes for local testing."),
    llm_model: Optional[str] = typer.Option(None, "--llm-model", help="Chat model for LangChain (defaults to gpt-5-mini)."),
    verbose: bool = typer.Option(True, "--verbose/--quiet", help="Stream the agent's thinking and tool calls."),
) -> None:
    """Entry point invoked inside the Runloop devbox."""

    settings = load_settings(
        repo_path=repo_path, branch_name=branch_name, dry_run=dry_run, llm_model=llm_model, verbose=verbose
    )
    repo_meta = RepoMetadata(repo_path=repo_path, repo_url=repo_url, default_branch="main")

    agent = DependencyUpdaterAgent(repo_tool=RepoScannerTool())
    result = agent.run(DependencyUpdateRequest(repo=repo_meta, settings=settings))

    console.print(f"[bold green]Completed dependency update workflow[/bold green]")
    for change in result.applied_changes:
        console.print(f"- {change}")
    console.print(f"Report stored at {result.report_path}")


if __name__ == "__main__":
    app()
