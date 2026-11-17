"""
OpsAgent: answers questions and runs actions on business data
(orders, customers, inventory, purchasing, refunds).

Safety rule
-----------
* static steps  -> ExecutorAgent calls the tool directly. Write tools go through
                   HITLMiddleware first, so a human approves every change.
* dynamic steps -> the LLM may only pick READ tools (or answer from the given
                   params without a tool). If it picks a WRITE tool, OpsAgent
                   refuses: writes must be explicit in the validated SOP so they
                   can be reviewed and approved.
"""
from __future__ import annotations

import inspect
import json
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from src.agent.base_agent import BaseAgent
from src.serializer.serializer import SmartSerializer
from src.tools.base_tool import BaseTool
from src.tools.group.business_ops import READ_TOOLS, WRITE_TOOLS


class WriteNotAllowedError(PermissionError):
    """A write tool was requested outside an approved static step."""


class OpsAgent(BaseAgent):

    def __init__(
        self, llm, tools=None, name="OpsAgent",
        description="Agent for business operations data: orders, customers, inventory, purchase orders, refunds",
        log_dir="logs",
    ):
        super().__init__(llm, tools, name, description, log_dir)

    # ------------------------------------------------------------------
    def _read_tools(self) -> list:
        return [t for t in self.get_tools() if t.__name__ in READ_TOOLS]

    def build_prompt(self, **kwargs):
        query = kwargs.get("query", "")
        params = kwargs.get("params", {})
        tools_str = BaseTool.get_tools_grouped_str_by_callables(
            tools=self._read_tools(), agent_name="OpsAgent read-only tools")

        system = (
            "You are an operations analyst for a small online shop.\n"
            "You can ONLY use these read-only tools:\n"
            f"{tools_str}\n\n"
            "Rules:\n"
            "- To look something up, return JSON: {\"tool\": \"<tool_name>\", \"params\": {...}}\n"
            "- If PARAMETERS already contain the data needed, answer without a tool:\n"
            "  {\"tool\": null, \"result\": <your answer as a string or JSON>}\n"
            "- Never invent order IDs, SKUs, amounts or dates. Use only data from tools or PARAMETERS.\n"
            "- You cannot change data. Do not try to update orders, create purchase orders or refund.\n"
            "Return ONE JSON object only. No explanation, no code fences."
        )
        human = (
            f"TASK: {query}\n"
            f"PARAMETERS: {json.dumps(params, ensure_ascii=False, default=str)}"
        )
        return [SystemMessage(content=system), HumanMessage(content=human)]

    # ------------------------------------------------------------------
    async def invoke(self, **kwargs) -> dict[str, Any]:
        query = kwargs.get("query", "")
        params = kwargs.get("params", {}) or {}

        self.info("ops_agent_invoke", query=query)
        output = await self.llm.ainvoke(self.build_prompt(query=query, params=params))
        raw = (output.content or "").strip()
        self.debug("ops_agent_raw_output", raw=raw[:500])

        decision = SmartSerializer.extract_json(raw)
        if not isinstance(decision, dict):
            raise ValueError(f"OpsAgent expected a JSON object, got: {raw[:200]}")

        tool_name = decision.get("tool")
        if not tool_name:
            return {"success": True, "result": decision.get("result")}

        return {"success": True, "result": self.run_read_tool(tool_name, decision.get("params") or {})}

    # ------------------------------------------------------------------
    def run_read_tool(self, tool_name: str, tool_params: dict) -> Any:
        """Validate the LLM's tool choice, then run it. Only read tools are allowed here."""
        if tool_name in WRITE_TOOLS:
            self.warning("ops_agent_write_blocked", tool=tool_name)
            raise WriteNotAllowedError(
                f"'{tool_name}' changes business data and is not allowed in a dynamic step. "
                "It must be an explicit static SOP step so a human can approve it.")

        fn = self.get_tool(tool_name)
        if fn is None or tool_name not in READ_TOOLS:
            raise ValueError(f"Unknown tool '{tool_name}'. Allowed: {', '.join(READ_TOOLS)}")
        if not isinstance(tool_params, dict):
            raise ValueError(f"params for '{tool_name}' must be an object")

        try:
            inspect.signature(fn).bind(**tool_params)
        except TypeError as e:
            raise ValueError(f"Bad params for '{tool_name}': {e}") from e

        self.info("ops_agent_tool_call", tool=tool_name, params=tool_params)
        return fn(**tool_params)
