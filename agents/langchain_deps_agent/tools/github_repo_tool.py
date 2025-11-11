from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import httpx
from packaging.requirements import Requirement


@dataclass
class DependencyInfo:
    name: str
    spec: str
    latest_version: Optional[str] = None
    source: str | None = None

    def to_json(self) -> str:
        return json.dumps(
            {
                "name": self.name,
                "specifier": self.spec,
                "latest_version": self.latest_version,
                "source": self.source,
            },
            indent=2,
        )


@dataclass
class RepoMetadata:
    repo_path: Path
    repo_url: str | None = None
    default_branch: str = "main"
    dependencies: List[DependencyInfo] | None = None


class RepoScannerTool:
    """Inspect a Python repository for dependency manifests and metadata."""

    def __init__(
        self,
        manifests: list[str] | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.manifests = manifests or ["pyproject.toml"]
        self.http_client = http_client or httpx.Client(timeout=10)

    def describe_repo(self, repo: RepoMetadata) -> RepoMetadata:
        """Populate dependency metadata from supported manifest files."""

        dependencies: list[DependencyInfo] = []
        for manifest in self.manifests:
            manifest_path = repo.repo_path / manifest
            if not manifest_path.exists():
                continue
            if manifest_path.name == "pyproject.toml":
                dependencies.extend(self._parse_pyproject(manifest_path))
        return RepoMetadata(
            repo_path=repo.repo_path,
            repo_url=repo.repo_url,
            default_branch=repo.default_branch,
            dependencies=dependencies,
        )

    def _parse_pyproject(self, path: Path) -> list[DependencyInfo]:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        project_section = data.get("project", {})
        deps = project_section.get("dependencies", []) or []
        optional = project_section.get("optional-dependencies", {})

        results: list[DependencyInfo] = []
        for dep in deps:
            info = self._build_dependency(dep, source="default")
            if info:
                results.append(info)

        for group, extras in optional.items():
            for dep in extras:
                info = self._build_dependency(dep, source=f"optional:{group}")
                if info:
                    results.append(info)
        return results

    def _build_dependency(self, raw: str, source: str) -> DependencyInfo | None:
        try:
            requirement = Requirement(raw)
        except Exception:
            return None

        spec = str(requirement.specifier) or "*"
        latest = self._fetch_latest_version(requirement.name)
        return DependencyInfo(
            name=requirement.name, spec=spec, latest_version=latest, source=source
        )

    def _fetch_latest_version(self, package: str) -> Optional[str]:
        url = f"https://pypi.org/pypi/{package}/json"
        try:
            response = self.http_client.get(url)
            response.raise_for_status()
            data = response.json()
            return data.get("info", {}).get("version")
        except Exception:
            return None
