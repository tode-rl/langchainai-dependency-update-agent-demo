from __future__ import annotations

import json
import operator
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import ToolNode

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


class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]


class DependencyUpdaterAgent:
    """LangChain-powered agent that coordinates repo scanning and upgrade planning."""

    def __init__(
        self, repo_tool: RepoScannerTool, llm: Optional[BaseChatModel] = None
    ) -> None:
        self.repo_tool = repo_tool
        self._llm = llm

    def run(self, request: DependencyUpdateRequest) -> DependencyUpdateResult:
        """Analyze the repo and generate an upgrade plan."""

        repo_summary = self.repo_tool.describe_repo(request.repo)
        tools = build_dependency_tools(repo_summary.repo_path)
        llm = self._resolve_llm(request.settings).bind_tools(tools)
        graph = self._create_graph(llm, tools, verbose=request.settings.verbose)

        prompt_input = self._build_prompt_input(request, repo_summary)
        initial_messages = self._build_initial_messages(prompt_input, repo_summary)
        if request.settings.verbose:
            self._log("agent", "Starting dependency analysis run.")
        final_state: Optional[AgentState] = None
        for state in graph.stream(
            {"messages": initial_messages},
            config={"recursion_limit": request.settings.max_steps},
            stream_mode="values",
        ):
            final_state = state
        if not final_state:
            raise RuntimeError("Agent graph returned no state.")
        raw_output = self._extract_response_text(final_state.get("messages", []))
        plan = self._normalize_plan(raw_output, repo_summary)
        report_path = self._write_report(plan, request.settings.repo_path)
        applied = [
            f"Generated dependency upgrade plan with {len(plan.get('upgrades', []))} suggestions."
        ]
        if request.settings.verbose:
            self._log(
                "agent",
                f"Plan generated with {len(plan.get('upgrades', []))} suggestions.",
            )
        return DependencyUpdateResult(
            applied_changes=applied,
            pr_branch=request.settings.branch_name,
            report_path=report_path,
            plan=plan,
        )

    def _build_prompt_input(
        self, request: DependencyUpdateRequest, repo_summary: RepoMetadata
    ) -> str:
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

    def _build_initial_messages(
        self, prompt_input: str, repo_summary: RepoMetadata
    ) -> List[BaseMessage]:
        system_prompt = (
            "You are a release engineering agent that proposes safe dependency upgrades for Python projects. "
            "Use the available tools to inspect pyproject.toml and PyPI metadata before recommending changes. "
            "Return JSON with keys 'upgrades' (list) and 'notes' (string). Repository context:\n"
            f"{self._format_repo_snapshot(repo_summary)}"
        )
        return [
            SystemMessage(content=system_prompt),
            HumanMessage(content=prompt_input),
        ]

    def _extract_response_text(self, messages: List[BaseMessage]) -> str:
        for message in reversed(messages):
            if isinstance(message, AIMessage):
                return self._render_message_content(message.content)
        raise RuntimeError("Agent graph did not produce a final AIMessage response.")

    def _normalize_plan(
        self, raw_output: str, repo_summary: RepoMetadata
    ) -> Dict[str, Any]:
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
        plan_path = repo_path / "dependency_plan.json"
        plan_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
        return plan_path

    def _resolve_llm(self, settings: AgentSettings) -> BaseChatModel:
        if self._llm:
            return self._llm

        model_name = settings.llm_model or os.getenv("OPENAI_MODEL", "gpt-5-mini")
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY environment variable is required for ChatOpenAI."
            )

        return ChatOpenAI(model=model_name, temperature=0)

    def _create_graph(
        self, llm: BaseChatModel, tools: List[Any], verbose: bool = False
    ):
        tool_node = ToolNode(tools)

        def call_model(state: AgentState) -> AgentState:
            response = llm.invoke(state["messages"])
            if verbose and isinstance(response, AIMessage):
                tool_calls = getattr(response, "tool_calls", None)
                if tool_calls:
                    for call in tool_calls:
                        name = call.get("name")
                        args = call.get("args")
                        self._log("agent", f"Calling tool '{name}' with args {args}")
                else:
                    self._log("agent", self._render_message_content(response.content))
            return {"messages": [response]}

        def invoke_tools(state: AgentState) -> AgentState:
            result = tool_node.invoke(state)
            if verbose:
                message = result["messages"][-1]
                label = getattr(message, "name", None) or getattr(
                    message, "tool_call_id", "tool"
                )
                self._log(
                    f"tool:{label}", self._render_message_content(message.content)
                )
            return result

        def should_continue(state: AgentState):
            last_message = state["messages"][-1]
            if isinstance(last_message, AIMessage) and getattr(
                last_message, "tool_calls", None
            ):
                return "tools"
            return END

        workflow = StateGraph(AgentState)
        workflow.add_node("agent", call_model)
        workflow.add_node("tools", invoke_tools)
        workflow.set_entry_point("agent")
        workflow.add_conditional_edges(
            "agent", should_continue, {"tools": "tools", END: END}
        )
        workflow.add_edge("tools", "agent")
        return workflow.compile()

    def _render_message_content(self, content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            chunks: List[str] = []
            for part in content:
                if isinstance(part, dict):
                    if part.get("type") == "tool_call":
                        continue
                    text = part.get("text")
                    if text:
                        chunks.append(text)
                else:
                    chunks.append(str(part))
            if chunks:
                return "".join(chunks).strip()
        return json.dumps(content)

    def _log(self, source: str, message: str) -> None:
        print(f"[{source}] {message}", flush=True)
