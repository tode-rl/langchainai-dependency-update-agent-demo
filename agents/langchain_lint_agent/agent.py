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

from .config import LintAgentSettings
from .tools.linting_tools import build_linting_tools


@dataclass
class LintRequest:
    """Input payload for the linting agent."""

    repo_path: Path
    settings: LintAgentSettings


@dataclass
class LintResult:
    """High-level summary of a linting run."""

    files_analyzed: int
    issues_fixed: int
    issues_remaining: int
    formatted: bool
    report_path: Path
    config_suggestions: Dict[str, Any]


class AgentState(TypedDict):
    messages: Annotated[List[BaseMessage], operator.add]


class LintAgent:
    """LangChain-powered agent that coordinates code linting and formatting using Ruff."""

    def __init__(self, llm: Optional[BaseChatModel] = None) -> None:
        self._llm = llm

    def run(self, request: LintRequest) -> LintResult:
        """Analyze the repository and apply linting fixes."""

        tools = build_linting_tools(request.settings.repo_path)
        llm = self._resolve_llm(request.settings).bind_tools(tools)
        graph = self._create_graph(llm, tools, verbose=request.settings.verbose)

        initial_messages = self._build_initial_messages(request)
        if request.settings.verbose:
            self._log("agent", "Starting linting analysis run.")

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
        report = self._normalize_report(raw_output, request.settings.repo_path)
        report_path = self._write_report(report, request.settings.repo_path)

        if request.settings.verbose:
            self._log("agent", f"Linting completed. Report saved to {report_path}")

        return LintResult(
            files_analyzed=report.get("files_analyzed", 0),
            issues_fixed=report.get("issues_fixed", 0),
            issues_remaining=report.get("issues_remaining", 0),
            formatted=report.get("formatted", False),
            report_path=report_path,
            config_suggestions=report.get("config_suggestions", {}),
        )

    def _build_initial_messages(self, request: LintRequest) -> List[BaseMessage]:
        """Build the initial system and user messages for the agent."""
        system_prompt = (
            "You are a Python code quality agent that uses Ruff to lint and format code. "
            "Your workflow:\n"
            "1. Scan the repository to understand its structure\n"
            "2. Analyze the codebase patterns to suggest appropriate linting rules\n"
            "3. Check for linting issues (use auto_fix=True to fix safe issues automatically)\n"
            "4. Format the code using ruff format\n"
            "5. Generate a final report with:\n"
            "   - Summary of files analyzed\n"
            "   - Issues fixed automatically\n"
            "   - Issues remaining that need manual intervention\n"
            "   - Suggested configuration improvements\n\n"
            "Return your final response as JSON with these keys:\n"
            "- files_analyzed (int)\n"
            "- issues_fixed (int)\n"
            "- issues_remaining (int)\n"
            "- formatted (bool)\n"
            "- config_suggestions (dict with 'essential', 'recommended', 'optional' rule categories)\n"
            "- summary (string with human-readable summary)\n"
        )

        user_prompt = (
            f"Analyze and lint the Python repository at {request.settings.repo_path}. "
        )

        if request.settings.auto_fix:
            user_prompt += "Auto-fix safe linting issues. "

        if request.settings.format_code:
            user_prompt += "Format the code. "

        user_prompt += "Provide config suggestions based on codebase patterns."

        return [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ]

    def _extract_response_text(self, messages: List[BaseMessage]) -> str:
        """Extract the final text response from the agent's messages."""
        for message in reversed(messages):
            if isinstance(message, AIMessage):
                return self._render_message_content(message.content)
        raise RuntimeError("Agent graph did not produce a final AIMessage response.")

    def _normalize_report(self, raw_output: str, repo_path: Path) -> Dict[str, Any]:
        """Parse and normalize the agent's output into a structured report."""
        # Try to parse as-is first
        try:
            report = json.loads(raw_output)
            if isinstance(report, dict):
                report.setdefault("repo_path", str(repo_path))
                return report
        except json.JSONDecodeError:
            pass

        # Try to extract JSON from markdown code blocks
        import re

        json_match = re.search(r"```(?:json)?\s*\n(.*?)\n```", raw_output, re.DOTALL)
        if json_match:
            try:
                report = json.loads(json_match.group(1))
                if isinstance(report, dict):
                    report.setdefault("repo_path", str(repo_path))
                    return report
            except json.JSONDecodeError:
                pass

        # If parsing fails, create a basic report
        return {
            "repo_path": str(repo_path),
            "files_analyzed": 0,
            "issues_fixed": 0,
            "issues_remaining": 0,
            "formatted": False,
            "config_suggestions": {},
            "summary": raw_output.strip(),
        }

    def _write_report(self, report: Dict[str, Any], repo_path: Path) -> Path:
        """Write the linting report to a JSON file."""
        report_path = repo_path / "lint_report.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report_path

    def _resolve_llm(self, settings: LintAgentSettings) -> BaseChatModel:
        """Resolve the LLM to use for the agent."""
        if self._llm:
            return self._llm

        model_name = settings.llm_model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY environment variable is required for ChatOpenAI."
            )

        return ChatOpenAI(model=model_name, temperature=0)

    def _create_graph(
        self, llm: BaseChatModel, tools: List[Any], verbose: bool = False
    ):
        """Create the LangGraph workflow for the linting agent."""
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
                    content = self._render_message_content(response.content)
                    if content and content.strip():
                        self._log("agent", content)
            return {"messages": [response]}

        def invoke_tools(state: AgentState) -> AgentState:
            result = tool_node.invoke(state)
            if verbose:
                message = result["messages"][-1]
                label = getattr(message, "name", None) or getattr(
                    message, "tool_call_id", "tool"
                )
                content = self._render_message_content(message.content)
                self._log(f"tool:{label}", content)
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
        """Render message content as a string."""
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
        """Log a message with a source label."""
        print(f"[{source}] {message}", flush=True)
