from src.utils.logger import LoggerMixin
from src.models.models import SOP, SOPStep, Condition, ToolResponse
from src.agent.base_agent import BaseAgent
from typing import Dict, Any
import operator
import re


class ExecutorAgent(LoggerMixin):

    OPERATORS = {
        "==": operator.eq,
        "!=": operator.ne,
        ">": operator.gt,
        "<": operator.lt,
        ">=": operator.ge,
        "<=": operator.le,
    }

    def __init__(self, name="ExecutorAgent", log_dir="logs"):
        super().__init__(name, log_dir)

        self.agents: Dict[str, BaseAgent] = {}
        self.context: Dict[str, Any] = {}            # store_result_as → output
        self.step_results: Dict[int, ToolResponse] = {}  # step_number → ToolResponse

        self.info("[INIT] ExecutorAgent initialized")

    # --------------------------------------------------
    # REGISTER AGENTS
    # --------------------------------------------------
    def register_agent(self, agent: BaseAgent):
        if not isinstance(agent, BaseAgent):
            raise ValueError("ExecutorAgent only accepts BaseAgent subclasses")

        name = agent.__class__.__name__
        self.agents[name] = agent

        self.info(f"[REGISTER] Loaded Agent: {name}")

    # --------------------------------------------------
    # PARAM RESOLVER (NEW SYNTAX)
    # --------------------------------------------------
    def resolve_value(self, value: Any):
        """
        Hỗ trợ:
            "<store>"
            "<store>.field"
            "<store>.field.subfield"
        """
        if not isinstance(value, str):
            return value

        # pattern for variable reference: <var> or <var>.x.y
        match = re.match(r"^<([a-zA-Z_][a-zA-Z0-9_]*)>(?:\.(.+))?$", value)
        if not match:
            return value  # literal string

        var_name = match.group(1)
        field_path = match.group(2)  # may be None

        if var_name not in self.context:
            return None

        data = self.context[var_name]  # this is output dict from previous ToolResponse

        if field_path is None:
            return data  # return whole dict

        # drill down nested fields
        parts = field_path.split(".")
        current = data

        for p in parts:
            if not isinstance(current, dict):
                return None
            if p not in current:
                return None
            current = current[p]

        return current

    def resolve_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {k: self.resolve_value(v) for k, v in params.items()}

    # --------------------------------------------------
    # CONDITION CHECKER (supports "output.xxx.y")
    # --------------------------------------------------
    def extract_field_from_toolresponse(self, resp: ToolResponse, field_expr: str):
        """
        field_expr:
            "success"
            "error"
            "output"
            "output.exists"
            "output.info.size"
            "meta.action"
        """
        parts = field_expr.split(".")

        # root is a ToolResponse attribute ("success", "error", "output", "meta")
        root = parts[0]
        if not hasattr(resp, root):
            return None

        current = getattr(resp, root)

        # drill deeper if needed
        for p in parts[1:]:
            if not isinstance(current, dict):
                return None
            if p not in current:
                return None
            current = current[p]

        return current

    def check_conditions(self, conditions: list[Condition]) -> bool:
        for cond in conditions:
            prev = self.step_results.get(cond.step)
            if not prev:
                return False

            left_value = self.extract_field_from_toolresponse(prev, cond.field)
            op = self.OPERATORS[cond.operator]
            right_value = cond.value
            print(f"Checking condition: {left_value} {cond.operator} {right_value}")
            if not op(left_value, right_value):
                self.info(
                    f"[SKIP] Condition failed: {left_value} {cond.operator} {right_value}"
                )
                return False

        return True

    # --------------------------------------------------
    # EXECUTE ONE STEP
    # --------------------------------------------------
    async def execute_step(self, step: SOPStep) -> ToolResponse:

        # ----- CONDITIONS -----
        if step.conditions and not self.check_conditions(step.conditions):
            self.info(f"[STEP {step.step_number}] Skipped due to condition")
            resp = ToolResponse(
                success=True,
                output="SKIPPED",
                meta={"skipped": True}
            )
            self.step_results[step.step_number] = resp
            return resp

        agent = self.agents.get(step.agent_type)
        if not agent:
            resp = ToolResponse(
                success=False,
                error=f"Agent '{step.agent_type}' not registered"
            )
            self.step_results[step.step_number] = resp
            return resp

        params = self.resolve_params(step.params)

        # ---------- STATIC ----------
        if step.execution_mode == "static":
            tool_name = step.action_type["tool"]
            tool_func = agent.get_tool(tool_name)

            if not tool_func:
                resp = ToolResponse(
                    success=False,
                    error=f"Tool '{tool_name}' not found in agent '{step.agent_type}'"
                )
                self.step_results[step.step_number] = resp
                return resp

            self.info(
                f"[EXECUTE] Step {step.step_number}: "
                f"{step.agent_type}.{tool_name} params={params}"
            )

            # retry logic
            for _ in range(step.retry + 1):
                try:
                    raw_output = tool_func(**params)  # raw dict from tool
                    resp = ToolResponse(success=True, output=raw_output)
                    break
                except Exception as e:
                    resp = ToolResponse(success=False, error=str(e))

            # save context
            if step.store_result_as:
                self.context[step.store_result_as] = resp.output

            self.step_results[step.step_number] = resp
            return resp

        # ---------- DYNAMIC ----------
        else:
            self.info(f"[EXECUTE] Step {step.step_number} (dynamic)...")

            for _ in range(step.retry + 1):
                try:
                    raw_output = await agent.invoke(params=params, query=step.description)
                    resp = ToolResponse(success=True, output=raw_output["result"])
                    break
                except Exception as e:
                    resp = ToolResponse(success=False, error=str(e))

            if step.store_result_as:
                self.context[step.store_result_as] = resp.output

            self.step_results[step.step_number] = resp
            return resp

    # --------------------------------------------------
    # RUN FULL SOP
    # --------------------------------------------------
    async def run_sop(self, sop: SOP):
        results = []

        for step in sop.steps:
            self.info(f"[RUN SOP] Step {step.step_number}")
            resp = await self.execute_step(step)
            results.append(resp)

            if not resp.success:
                return {
                    "success": False,
                    "error": resp.error,
                    "steps": [r.dict() for r in results],
                }

        return {
            "success": True,
            "final_target": sop.final_target,
            "steps": [r.dict() for r in results],
            "context": self.context,
        }
