from src.utils.logger import LoggerMixin
from src.models.models import SOP, SOPStep, Condition, ToolResponse
from src.agent.base_agent import BaseAgent
from typing import Dict, Any
import re
from src.handler.error_handler import ErrorHandler, ErrorSeverity


class ExecutorAgent(LoggerMixin):

    OPERATORS = {
        "==": lambda a, b: a == b,
        "!=": lambda a, b: a != b,
        ">":  lambda a, b: a > b,
        "<":  lambda a, b: a < b,
        ">=": lambda a, b: a >= b,
        "<=": lambda a, b: a <= b,
    }

    def __init__(self, name="ExecutorAgent", log_dir="logs"):
        super().__init__(name, log_dir)
        self.agents: Dict[str, BaseAgent] = {}
        self.context: Dict[str, Any] = {}
        self.step_results: Dict[int, ToolResponse] = {}
        self.error_handler = ErrorHandler()
        self.max_visits_per_step = 10

    # ------------------------------------------------------------
    # REGISTER AGENT
    # ------------------------------------------------------------
    def register_agent(self, agent: BaseAgent):
        if not isinstance(agent, BaseAgent):
            raise ValueError("ExecutorAgent only accepts BaseAgent subclasses")
        self.agents[agent.__class__.__name__] = agent
        self.info(f"[REGISTER] Loaded Agent: {agent.__class__.__name__}")

    # ------------------------------------------------------------
    # PARAM RESOLVER
    # ------------------------------------------------------------
    def resolve_value(self, value):
        if not isinstance(value, str):
            return value

        match = re.match(r"^<([a-zA-Z_][a-zA-Z0-9_]*)>(?:\.(.+))?$", value)
        if not match:
            return value

        var_name = match.group(1)
        field_path = match.group(2)

        if var_name not in self.context:
            return None
        
        data = self.context[var_name]
        if field_path is None:
            return data
        
        current = data
        for p in field_path.split("."):
            if not isinstance(current, dict) or p not in current:
                return None
            current = current[p]

        return current

    def resolve_params(self, params: Dict[str, Any]):
        return {k: self.resolve_value(v) for k, v in params.items()}

    # ------------------------------------------------------------
    # CONDITION CHECKER
    # ------------------------------------------------------------
    def extract_field(self, resp: ToolResponse, field_expr: str):
        parts = field_expr.split(".")
        root = parts[0]

        if not hasattr(resp, root):
            return None

        current = getattr(resp, root)
        for p in parts[1:]:
            if not isinstance(current, dict) or p not in current:
                return None
            current = current[p]

        return current

    def check_conditions(self, conditions):
        for cond in conditions:
            prev = self.step_results.get(cond.step)
            if not prev:
                return False

            left = self.extract_field(prev, cond.field)
            right = cond.value

            op = self.OPERATORS[cond.operator]

            if not op(left, right):
                return False

        return True

    # ------------------------------------------------------------
    # EXECUTE ONE STEP
    # ------------------------------------------------------------
    async def execute_step(self, step: SOPStep):

        # 1) PRE-STEP CONDITIONS (SKIP LOGIC)
        if step.conditions and not self.check_conditions(step.conditions):
            resp = ToolResponse(success=True, output="SKIPPED", meta={"skipped": True})
            self.step_results[step.step_number] = resp
            return resp

        agent = self.agents.get(step.agent_type)
        if not agent:
            resp = ToolResponse(success=False, error=f"Agent '{step.agent_type}' not registered")
            self.step_results[step.step_number] = resp
            return resp

        params = self.resolve_params(step.params)

        # ---- STATIC EXECUTION ----
        if step.execution_mode == "static":

            tool = step.action_type["tool"]
            tool_fn = agent.get_tool(tool)

            if not tool_fn:
                resp = ToolResponse(success=False, error=f"Tool '{tool}' not found")
                self.step_results[step.step_number] = resp
                return resp

            last_exc = None
            for _ in range((step.retry or 0) + 1):
                try:
                    out = tool_fn(**params)
                    resp = ToolResponse(success=True, output=out)
                    break
                except Exception as e:
                    err = self.error_handler.handle_exception(e, "ExecutorAgent.execute_step")
                    last_exc = err
                    if err.severity != ErrorSeverity.RECOVERABLE:
                        resp = ToolResponse(success=False, error=err.message)
                        break
                    resp = ToolResponse(success=False, error=str(e))

            if step.store_result_as:
                self.context[step.store_result_as] = resp.output
            self.step_results[step.step_number] = resp
            return resp

        # ---- DYNAMIC EXECUTION ----
        else:
            last_exc = None
            for _ in range((step.retry or 0) + 1):
                try:
                    raw = await agent.invoke(query=step.description, params=params)
                    out = raw.get("result") if isinstance(raw, dict) else raw
                    resp = ToolResponse(success=True, output=out)
                    break
                except Exception as e:
                    last_exc = e
                    resp = ToolResponse(success=False, error=str(e))

            if step.store_result_as:
                self.context[step.store_result_as] = resp.output

            self.step_results[step.step_number] = resp
            return resp

    # ------------------------------------------------------------
    # RUN SOP — OFFICIAL VERSION (NO next_step_on_success/failure)
    # ------------------------------------------------------------
    async def run_sop(self, sop: SOP):

        steps = {s.step_number: s for s in sop.steps}
        ordered = [s.step_number for s in sop.steps]

        cur_idx = 0
        visits = {k: 0 for k in ordered}
        results = []

        while 0 <= cur_idx < len(ordered):

            step_num = ordered[cur_idx]
            step = steps[step_num]

            visits[step_num] += 1
            if visits[step_num] > self.max_visits_per_step:
                return {"success": False, "error": f"Step {step_num} exceeded max visits"}

            resp = await self.execute_step(step)
            results.append(resp)

            # -------------------------------
            # POST-STEP JUMP LOGIC
            # -------------------------------
            jumped = False

            if step.condition_to_jump_step:
                for cond in step.condition_to_jump_step:

                    prev = self.step_results.get(cond.step)
                    if not prev:
                        continue

                    left = self.extract_field(prev, cond.field)
                    right = cond.value
                    op = self.OPERATORS[cond.operator]

                    cond_result = op(left, right)

                    # decide target
                    target = cond.jump_to_step_on_success if cond_result else cond.jump_to_step_on_failure

                    # -1 => terminate SOP
                    if target == -1:
                        return {
                            "success": True,
                            "final_target": sop.final_target,
                            "steps": [r.dict() for r in results],
                            "context": self.context
                        }

                    # valid jump
                    if target is not None:
                        if target in steps:
                            cur_idx = ordered.index(target)
                            jumped = True
                            break
                        else:
                            return {
                                "success": False,
                                "error": f"Invalid jump target {target}",
                                "steps": [r.dict() for r in results],
                                "context": self.context
                            }

            if jumped:
                continue

            # -------------------------------
            # DEFAULT SEQUENTIAL FLOW
            # -------------------------------
            cur_idx += 1

        # ------------------------------------------------------
        # SOP finished normally
        # ------------------------------------------------------
        return {
            "success": True,
            "final_target": sop.final_target,
            "steps": [r.dict() for r in results],
            "context": self.context,
        }
