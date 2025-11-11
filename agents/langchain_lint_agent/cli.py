from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from .agent import LintAgent, LintRequest
from .config import load_settings

app = typer.Typer(help="Run the LangChain linting agent using Ruff.")
console = Console()


@app.command()
def run(
    repo_path: Path = typer.Option(
        ..., "--repo-path", help="Path to the repository to lint."
    ),
    branch_name: str = typer.Option(
        "runloop/lint-fixes", "--branch-name", help="Branch to push changes to."
    ),
    dry_run: bool = typer.Option(
        True, "--dry-run/--no-dry-run", help="Disable pushes for local testing."
    ),
    auto_fix: bool = typer.Option(
        True, "--auto-fix/--no-auto-fix", help="Automatically fix safe linting issues."
    ),
    format_code: bool = typer.Option(
        True, "--format/--no-format", help="Apply code formatting."
    ),
    llm_model: Optional[str] = typer.Option(
        None, "--llm-model", help="Chat model for LangChain (defaults to gpt-4o-mini)."
    ),
    verbose: bool = typer.Option(
        True, "--verbose/--quiet", help="Stream the agent's thinking and tool calls."
    ),
) -> None:
    """Entry point to run the linting agent on a repository."""

    settings = load_settings(
        repo_path=repo_path,
        branch_name=branch_name,
        dry_run=dry_run,
        auto_fix=auto_fix,
        format_code=format_code,
        llm_model=llm_model,
        verbose=verbose,
    )

    agent = LintAgent()
    result = agent.run(LintRequest(repo_path=repo_path, settings=settings))

    console.print("\n[bold green]Completed linting workflow[/bold green]")
    console.print(f"Files analyzed: {result.files_analyzed}")
    console.print(f"Issues fixed: {result.issues_fixed}")
    console.print(f"Issues remaining: {result.issues_remaining}")
    console.print(f"Code formatted: {'Yes' if result.formatted else 'No'}")

    if result.config_suggestions:
        console.print("\n[bold yellow]Configuration Suggestions:[/bold yellow]")
        for category, rules in result.config_suggestions.items():
            if rules:
                console.print(
                    f"  {category}: {', '.join(rules) if isinstance(rules, list) else rules}"
                )

    console.print(f"\nFull report saved at: {result.report_path}")


if __name__ == "__main__":
    app()
