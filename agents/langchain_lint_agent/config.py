from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class LintAgentSettings(BaseModel):
    """Runtime configuration for the linting agent."""

    repo_path: Path = Field(..., description="Path to the repository to lint.")
    branch_name: str = Field(
        default="runloop/lint-fixes",
        description="Branch to create or fast-forward when committing changes.",
    )
    max_steps: int = Field(
        default=25,
        description="Maximum reasoning steps (graph recursion limit) before aborting.",
    )
    verbose: bool = Field(
        default=True,
        description="Stream the agent's intermediate reasoning and tool calls to stdout.",
    )
    dry_run: bool = Field(
        default=True,
        description="When true, skip committing or pushing changes.",
    )
    auto_fix: bool = Field(
        default=True,
        description="Automatically fix safe linting issues using ruff --fix.",
    )
    format_code: bool = Field(
        default=True,
        description="Apply code formatting using ruff format.",
    )
    llm_model: Optional[str] = Field(
        default=None,
        description="Chat model identifier passed to LangChain (defaults to gpt-5-mini if unset).",
    )


def load_settings(repo_path: str | Path, **overrides: object) -> LintAgentSettings:
    """Create a LintAgentSettings instance with optional overrides."""

    payload = {"repo_path": Path(repo_path)}
    payload.update(overrides)
    return LintAgentSettings(**payload)
