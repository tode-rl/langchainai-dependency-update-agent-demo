from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


class AgentSettings(BaseModel):
    """Runtime configuration for the dependency updater agent."""

    repo_path: Path = Field(..., description="Path to the mounted repository to update.")
    branch_name: str = Field(
        default="runloop/dependency-updates",
        description="Branch to create or fast-forward when committing changes.",
    )
    max_steps: int = Field(
        default=25,
        description="Maximum reasoning steps (graph recursion limit) before aborting.",
    )
    verbose: bool = Field(
        default=False,
        description="Enable verbose AgentExecutor logging during runs.",
    )
    dry_run: bool = Field(
        default=True,
        description="When true, skip committing or pushing changes.",
    )
    github_token_env: Optional[str] = Field(
        default="GITHUB_TOKEN",
        description="Environment variable that holds a GitHub token, if available.",
    )
    llm_model: Optional[str] = Field(
        default=None,
        description="Chat model identifier passed to LangChain (defaults to gpt-5-mini if unset).",
    )


def load_settings(repo_path: str | Path, **overrides: object) -> AgentSettings:
    """Create an AgentSettings instance with optional overrides."""

    payload = {"repo_path": Path(repo_path)}
    payload.update(overrides)
    return AgentSettings(**payload)
