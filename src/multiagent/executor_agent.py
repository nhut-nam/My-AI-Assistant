from src.utils.logger import LoggerMixin
from src.models.models import SOP, SOPStep, Condition, ToolResponse, HITLRequired, ExecutionStatus, ExecutionState
from src.agent.base_agent import BaseAgent
from typing import Dict, Any
import re
from src.handler.error_handler import ErrorHandler, ErrorSeverity
from src.middleware.middleware_manager import MiddlewareManager

class ExecutorAgent(LoggerMixin):

    OPERATORS = {
        "==": lambda a, b: a == b,
        "!=": lambda a, b: a != b,
        ">":  lambda a, b: a > b,
        "<":  lambda a, b: a < b,
        ">=": lambda a, b: a >= b,
        "<=": lambda a, b: a <= b,
    }

    def __init__(self, name="ExecutorAgent", log_dir="logs", middleware=None):
        super().__init__(name, log_dir)
        self.agents: Dict[str, BaseAgent] = {}
        self.context: Dict[str, Any] = {}
        self.step_results: Dict[int, ToolResponse] = {}
        self.error_handler = ErrorHandler()
        self.max_visits_per_step = 10
        
        self.middleware = MiddlewareManager(middleware or [])

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

            await self.middleware.dispatch(
                "before_tool",
                step,
                tool,
                params,
                self.context
            )
            
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

            await self.middleware.dispatch(
                "after_tool",
                step,
                tool,
                resp,
                self.context
            )
            
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
        
    def resolve_template(self, template: str) -> str:
        """
        Resolve templates like:
        'The area is <area_result>.result square centimeters.'
        """

        if not isinstance(template, str):
            return template

        pattern = r"<([a-zA-Z_][a-zA-Z0-9_]*)(?:\.(.+?))?>"

        def replacer(match):
            var_name = match.group(1)
            field_path = match.group(2)

            if var_name not in self.context:
                return ""

            value = self.context[var_name]

            if field_path is None:
                return str(value)

            current = value
            for part in field_path.split("."):
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    return ""

            return str(current)

        return re.sub(pattern, replacer, template)
    

    async def run_sop(
        self,
        sop: SOP,
        resume_context: dict | None = None,
        resume_step_results: list[ToolResponse] | None = None,
    ) -> ExecutionStatus:

        steps = {s.step_number: s for s in sop.steps}
        ordered = [s.step_number for s in sop.steps]
        print("SOP Steps Order:", ordered)

        if resume_context is not None and resume_step_results is not None:
            self.context = resume_context

            self.step_results = {
                step_num: resp
                for step_num, resp in zip(ordered, resume_step_results)
            }

            results = list(resume_step_results)

            if "hitl_approved" in resume_context:
                step_num = resume_context["hitl_approved"]["step_number"]
                cur_idx = ordered.index(step_num)
                print("Resuming from approved HITL at step:", cur_idx)

            elif "hitl_skipped" in resume_context:
                resp = ToolResponse(
                    success=False,
                    output=None,
                    meta={"skipped": True}
                )
                step_num = resume_context["hitl_skipped"]["step_number"]
                self.step_results[step_num] = resp
                cur_idx = ordered.index(step_num) + 1
                print("Resuming from skipped HITL at step:", cur_idx)

            else:
                cur_idx = 0

        else:
            self.context = {}
            self.step_results = {}
            results = []
            cur_idx = 0

        await self.middleware.dispatch("before_run", self.context)

        visits = {k: 0 for k in ordered}

        while 0 <= cur_idx < len(ordered):
            self.info(f"[Executor] Executing step index: {cur_idx}")
            step_number = ordered[cur_idx]
            step = steps[step_number]

            await self.middleware.dispatch("before_step", step, self.context)

            visits[step_number] += 1
            if visits[step_number] > self.max_visits_per_step:
                return ExecutionStatus(
                    state=ExecutionState.FAILED,
                    error=f"Step {step_number} exceeded max visits",
                    steps=results,
                    context=self.context,
                )

            try:
                resp = await self.execute_step(step)

            except HITLRequired as hitl:
                return ExecutionStatus(
                    state=ExecutionState.PENDING_HITL,
                    tool_name=hitl.tool_name,
                    params=hitl.params,
                    reason=hitl.reason,
                    current_step_idx=cur_idx, 
                    steps=results,
                    context=self.context,
                )

            await self.middleware.dispatch("after_step", step, resp, self.context)

            self.step_results[step_number] = resp
            results.append(resp)

            jumped = False
            if step.condition_to_jump_step:
                for cond in step.condition_to_jump_step:
                    prev = self.step_results.get(cond.step)
                    if not prev:
                        continue

                    left = self.extract_field(prev, cond.field)
                    right = cond.value
                    op = self.OPERATORS[cond.operator]

                    target = (
                        cond.jump_to_step_on_success
                        if op(left, right)
                        else cond.jump_to_step_on_failure
                    )

                    if target == -1:
                        resolved = self.resolve_template(sop.final_target)
                        await self.middleware.dispatch("after_run", self.context, resolved)
                        return ExecutionStatus(
                            state=ExecutionState.DONE,
                            result=resolved,
                            steps=results,
                            context=self.context,
                        )

                    if target in steps:
                        cur_idx = ordered.index(target)
                        jumped = True
                        break

                    if target is not None:
                        return ExecutionStatus(
                            state=ExecutionState.FAILED,
                            error=f"Invalid jump target {target}",
                            steps=results,
                            context=self.context,
                        )

            if not jumped:
                cur_idx += 1

        resolved = self.resolve_template(sop.final_target)
        await self.middleware.dispatch("after_run", self.context, resolved)

        return ExecutionStatus(
            state=ExecutionState.DONE,
            result=resolved,
            steps=results,
            context=self.context,
        )

