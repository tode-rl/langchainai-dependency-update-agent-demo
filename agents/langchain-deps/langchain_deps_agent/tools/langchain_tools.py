from __future__ import annotations

import json
from pathlib import Path
from typing import List

import httpx
from langchain.tools import StructuredTool
from pydantic import BaseModel, Field

from .github_repo_tool import RepoMetadata, RepoScannerTool


class DependencyListInput(BaseModel):
    include_optional: bool = Field(
        default=True,
        description="Set to false to omit optional dependency groups when summarizing the repo.",
    )


class LatestVersionInput(BaseModel):
    package_name: str = Field(
        ...,
        description="The PyPI package name to inspect.",
        examples=["langchain"],
    )


def build_dependency_tools(repo_path: Path) -> List[StructuredTool]:
    """Return LangChain tools for interacting with Python dependency manifests."""

    repo_metadata = RepoMetadata(repo_path=repo_path)
    repo_scanner = RepoScannerTool(manifests=["pyproject.toml"])

    def list_deps(include_optional: bool = True) -> str:
        metadata = repo_scanner.describe_repo(repo_metadata)
        dependencies = metadata.dependencies or []
        if not include_optional:
            dependencies = [d for d in dependencies if not d.source or not d.source.startswith("optional:")]
        payload = [
            {
                "name": dep.name,
                "specifier": dep.spec,
                "latest_version": dep.latest_version,
                "source": dep.source,
            }
            for dep in dependencies
        ]
        return json.dumps(payload, indent=2)

    def fetch_latest(package_name: str) -> str:
        url = f"https://pypi.org/pypi/{package_name}/json"
        resp = httpx.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        latest = data.get("info", {}).get("version")
        requires_python = data.get("info", {}).get("requires_python")
        return json.dumps(
            {
                "package_name": package_name,
                "latest_version": latest,
                "requires_python": requires_python,
            },
            indent=2,
        )

    dep_tool = StructuredTool.from_function(
        func=list_deps,
        name="list_python_dependencies",
        description=(
            "Inspect the pyproject.toml in the mounted repository and return all declared Python dependencies "
            "(including optional dependency groups when requested). Use this before planning upgrades."
        ),
        args_schema=DependencyListInput,
    )

    version_tool = StructuredTool.from_function(
        func=fetch_latest,
        name="fetch_latest_pypi_version",
        description=(
            "Query the PyPI JSON API for the latest published version and Python requirements of a single package."
        ),
        args_schema=LatestVersionInput,
    )

    return [dep_tool, version_tool]
