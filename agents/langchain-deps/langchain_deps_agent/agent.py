from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from .config import AgentSettings
from .tools.github_repo_tool import RepoMetadata, RepoScannerTool
from .tools.langchain_tools import build_dependency_tools


@dataclass
class DependencyUpdateRequest:
    """Input payload for the agent."""

    repo: RepoMetadata
    settings: AgentSettings


@dataclass
class DependencyUpdateResult:
    """High-level summary of an agent run."""

    applied_changes: List[str]
    pr_branch: str
    report_path: Path
    plan: Dict[str, Any]


class DependencyUpdaterAgent:
    """LangChain-powered agent that coordinates repo scanning and upgrade planning."""

    def __init__(self, repo_tool: RepoScannerTool, llm: Optional[BaseChatModel] = None) -> None:
        self.repo_tool = repo_tool
        self._llm = llm

    def run(self, request: DependencyUpdateRequest) -> DependencyUpdateResult:
        """Analyze the repo and generate an upgrade plan."""

        repo_summary = self.repo_tool.describe_repo(request.repo)
        executor = self._build_executor(request.settings, repo_summary)
        prompt_input = self._build_prompt_input(request, repo_summary)
        raw_response = executor.invoke({"input": prompt_input})
        plan = self._normalize_plan(raw_response.get("output", ""), repo_summary)
        report_path = self._write_report(plan, request.settings.repo_path)
        applied = [f"Generated dependency upgrade plan with {len(plan.get('upgrades', []))} suggestions."]
        return DependencyUpdateResult(
            applied_changes=applied,
            pr_branch=request.settings.branch_name,
            report_path=report_path,
            plan=plan,
        )

    def _build_executor(self, settings: AgentSettings, repo_summary: RepoMetadata) -> AgentExecutor:
        tools = build_dependency_tools(repo_summary.repo_path)
        llm = self._resolve_llm(settings)

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    (
                        "You are a release engineering agent that proposes safe dependency upgrades for Python projects. "
                        "Use the available tools to inspect pyproject.toml and PyPI metadata before recommending changes. "
                        "Return JSON with keys 'upgrades' (list) and 'notes' (string). Repository context:\n{repo_snapshot}"
                    ),
                ),
                ("human", "{input}"),
                MessagesPlaceholder(variable_name="agent_scratchpad"),
            ]
        ).partial(repo_snapshot=self._format_repo_snapshot(repo_summary))

        agent = create_tool_calling_agent(llm, tools, prompt)
        return AgentExecutor(
            agent=agent,
            tools=tools,
            max_iterations=settings.max_steps,
            verbose=settings.verbose,
        )

    def _build_prompt_input(self, request: DependencyUpdateRequest, repo_summary: RepoMetadata) -> str:
        repo_path = request.settings.repo_path
        return (
            "Analyze the Python dependencies declared in the repository located at "
            f"{repo_path}. Identify outdated packages and propose compatible upgrades based on the "
            "current specifiers. Prioritize security patches and minor releases unless the specifier "
            "allows breaking updates. Produce detailed reasoning for each proposed change in the JSON response."
        )

    def _format_repo_snapshot(self, repo_summary: RepoMetadata) -> str:
        dependencies = repo_summary.dependencies or []
        snapshot = [
            {
                "name": dep.name,
                "specifier": dep.spec,
                "latest_version": dep.latest_version,
                "source": dep.source,
            }
            for dep in dependencies
        ]
        return json.dumps(snapshot, indent=2)

    def _normalize_plan(self, raw_output: str, repo_summary: RepoMetadata) -> Dict[str, Any]:
        try:
            plan = json.loads(raw_output)
            if isinstance(plan, dict):
                plan.setdefault("repo_url", repo_summary.repo_url)
                return plan
        except json.JSONDecodeError:
            pass
        return {
            "repo_url": repo_summary.repo_url,
            "upgrades": [],
            "notes": raw_output.strip(),
        }

    def _write_report(self, plan: Dict[str, Any], repo_path: Path) -> Path:
        reports_dir = repo_path / ".runloop"
        reports_dir.mkdir(exist_ok=True)
        plan_path = reports_dir / "dependency_plan.json"
        plan_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
        return plan_path

    def _resolve_llm(self, settings: AgentSettings) -> BaseChatModel:
        if self._llm:
            return self._llm

        model_name = settings.llm_model or os.getenv("OPENAI_MODEL", "gpt-5-mini")
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY environment variable is required for ChatOpenAI.")

        return ChatOpenAI(model=model_name, temperature=0)
