from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import List

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field


class ScanRepoInput(BaseModel):
    """Input for scanning repository for Python files."""

    pass


class CheckLintInput(BaseModel):
    """Input for checking linting issues."""

    auto_fix: bool = Field(
        default=False,
        description="Automatically fix safe issues using ruff --fix.",
    )


class FormatCodeInput(BaseModel):
    """Input for formatting code."""

    check_only: bool = Field(
        default=False,
        description="Only check if code would be reformatted without making changes.",
    )


class AnalyzeCodebaseInput(BaseModel):
    """Input for analyzing codebase patterns."""

    pass


def build_linting_tools(repo_path: Path) -> List[StructuredTool]:
    """Return LangChain tools for linting operations with Ruff."""

    def scan_repo() -> str:
        """Scan the repository for Python files and existing Ruff configuration."""
        py_files = list(repo_path.rglob("*.py"))
        # Filter out common non-source directories
        py_files = [
            f
            for f in py_files
            if not any(
                part in f.parts
                for part in [
                    ".venv",
                    "venv",
                    "__pycache__",
                    ".git",
                    "node_modules",
                    ".tox",
                ]
            )
        ]

        # Check for existing Ruff config
        config_locations = [
            repo_path / "pyproject.toml",
            repo_path / "ruff.toml",
            repo_path / ".ruff.toml",
        ]
        config_found = None
        ruff_config_exists = False

        for config_file in config_locations:
            if config_file.exists():
                content = config_file.read_text()
                if "[tool.ruff]" in content or "# Ruff" in content:
                    config_found = str(config_file.relative_to(repo_path))
                    ruff_config_exists = True
                    break
                elif config_file.name in ["ruff.toml", ".ruff.toml"]:
                    config_found = str(config_file.relative_to(repo_path))
                    ruff_config_exists = True
                    break

        result = {
            "total_python_files": len(py_files),
            "python_files": [
                str(f.relative_to(repo_path)) for f in py_files[:50]
            ],  # Limit for brevity
            "has_ruff_config": ruff_config_exists,
            "config_location": config_found,
        }

        if len(py_files) > 50:
            result["note"] = f"Showing first 50 of {len(py_files)} Python files"

        return json.dumps(result, indent=2)

    def check_lint(auto_fix: bool = False) -> str:
        """Run ruff check to find linting issues, optionally auto-fixing safe issues."""
        cmd = ["ruff", "check", str(repo_path), "--output-format=json"]

        if auto_fix:
            cmd.append("--fix")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=repo_path,
            )

            # Ruff returns JSON output even on errors
            if result.stdout:
                issues = json.loads(result.stdout)
            else:
                issues = []

            summary = {
                "total_issues": len(issues),
                "auto_fixed": auto_fix,
                "issues_by_file": {},
                "issues_by_code": {},
            }

            for issue in issues:
                file_path = issue.get("filename", "unknown")
                code = issue.get("code", "unknown")

                if file_path not in summary["issues_by_file"]:
                    summary["issues_by_file"][file_path] = 0
                summary["issues_by_file"][file_path] += 1

                if code not in summary["issues_by_code"]:
                    summary["issues_by_code"][code] = 0
                summary["issues_by_code"][code] += 1

            # Include sample issues (first 10)
            summary["sample_issues"] = issues[:10]

            return json.dumps(summary, indent=2)

        except subprocess.CalledProcessError as e:
            return json.dumps(
                {"error": "Failed to run ruff check", "stderr": e.stderr}, indent=2
            )
        except json.JSONDecodeError:
            return json.dumps(
                {
                    "error": "Failed to parse ruff output",
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                },
                indent=2,
            )

    def format_code(check_only: bool = False) -> str:
        """Format code using ruff format."""
        cmd = ["ruff", "format", str(repo_path)]

        if check_only:
            cmd.append("--check")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=repo_path,
            )

            if check_only:
                # In check mode, non-zero exit means files would be reformatted
                if result.returncode == 0:
                    status = "All files already formatted"
                else:
                    status = "Some files would be reformatted"
            else:
                status = (
                    "Files formatted successfully"
                    if result.returncode == 0
                    else "Formatting completed with warnings"
                )

            return json.dumps(
                {
                    "status": status,
                    "check_only": check_only,
                    "stdout": result.stdout.strip(),
                    "stderr": result.stderr.strip(),
                },
                indent=2,
            )

        except subprocess.CalledProcessError as e:
            return json.dumps(
                {"error": "Failed to run ruff format", "stderr": e.stderr}, indent=2
            )

    def analyze_codebase() -> str:
        """Analyze codebase patterns to suggest appropriate Ruff rules."""
        # Run ruff with all rules enabled to see what violations exist
        cmd = ["ruff", "check", str(repo_path), "--select=ALL", "--output-format=json"]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=repo_path,
            )

            if result.stdout:
                issues = json.loads(result.stdout)
            else:
                issues = []

            # Categorize issues by rule category
            categories = {}
            for issue in issues:
                code = issue.get("code", "unknown")
                # Extract category (first letter(s) before numbers)
                category = "".join([c for c in code if not c.isdigit()])

                if category not in categories:
                    categories[category] = {
                        "count": 0,
                        "codes": set(),
                        "description": _get_category_description(category),
                    }

                categories[category]["count"] += 1
                categories[category]["codes"].add(code)

            # Convert sets to lists for JSON serialization
            for cat in categories.values():
                cat["codes"] = sorted(list(cat["codes"]))

            suggestions = _generate_rule_suggestions(categories)

            return json.dumps(
                {
                    "total_potential_issues": len(issues),
                    "categories": categories,
                    "suggested_rules": suggestions,
                    "note": "These are suggestions based on common patterns. Review before applying.",
                },
                indent=2,
            )

        except subprocess.CalledProcessError as e:
            return json.dumps(
                {"error": "Failed to analyze codebase", "stderr": e.stderr}, indent=2
            )
        except json.JSONDecodeError:
            return json.dumps(
                {"error": "Failed to parse ruff output", "raw": result.stdout}, indent=2
            )

    scan_tool = StructuredTool.from_function(
        func=scan_repo,
        name="scan_repository",
        description=(
            "Scan the repository for Python files and check for existing Ruff configuration. "
            "Use this first to understand the repository structure."
        ),
        args_schema=ScanRepoInput,
    )

    check_tool = StructuredTool.from_function(
        func=check_lint,
        name="check_linting_issues",
        description=(
            "Run ruff check to identify linting issues. Can optionally auto-fix safe issues "
            "by setting auto_fix=True. Returns a summary of issues found."
        ),
        args_schema=CheckLintInput,
    )

    format_tool = StructuredTool.from_function(
        func=format_code,
        name="format_code",
        description=(
            "Format code using ruff format. Can check if formatting is needed without making changes "
            "by setting check_only=True."
        ),
        args_schema=FormatCodeInput,
    )

    analyze_tool = StructuredTool.from_function(
        func=analyze_codebase,
        name="analyze_codebase_patterns",
        description=(
            "Analyze the codebase to identify common patterns and suggest appropriate Ruff rules. "
            "This helps recommend configuration improvements based on actual code patterns."
        ),
        args_schema=AnalyzeCodebaseInput,
    )

    return [scan_tool, check_tool, format_tool, analyze_tool]


def _get_category_description(category: str) -> str:
    """Get human-readable description for rule category."""
    descriptions = {
        "E": "pycodestyle errors",
        "W": "pycodestyle warnings",
        "F": "Pyflakes",
        "C": "mccabe complexity",
        "I": "isort imports",
        "N": "pep8-naming",
        "D": "pydocstyle documentation",
        "UP": "pyupgrade",
        "S": "flake8-bandit security",
        "B": "flake8-bugbear",
        "A": "flake8-builtins",
        "COM": "flake8-commas",
        "T": "flake8-print",
        "Q": "flake8-quotes",
        "RET": "flake8-return",
        "SIM": "flake8-simplify",
        "ARG": "flake8-unused-arguments",
        "PTH": "flake8-use-pathlib",
        "PD": "pandas-vet",
        "PL": "Pylint",
        "RUF": "Ruff-specific rules",
    }
    return descriptions.get(category, f"{category} rules")


def _generate_rule_suggestions(categories: dict) -> dict:
    """Generate suggestions for which rules to enable based on violations found."""
    suggestions = {
        "essential": ["E", "F", "W"],  # Core PEP 8 and Pyflakes
        "recommended": [],
        "optional": [],
    }

    # Recommend enabling rules if they have significant violations
    for category, data in categories.items():
        count = data["count"]

        # If there are many violations, it's a good candidate for fixing
        if category in ["I", "UP", "B", "SIM"]:  # Common useful categories
            if count > 5:
                suggestions["recommended"].append(category)
            elif count > 0:
                suggestions["optional"].append(category)
        elif category in ["D", "S", "N"]:  # Documentation, security, naming
            suggestions["optional"].append(category)

    return suggestions
