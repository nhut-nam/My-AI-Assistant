from src.utils.logger import LoggerMixin
from src.models.models import SOP, SOPStep, Condition, ToolResponse
from src.agent.base_agent import BaseAgent
from typing import Dict, Any, Optional
import operator
import re
from langgraph.graph import StateGraph, START, END  # for interoperability / visualization


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

        # graph runner tunables
        self.max_visits_per_step = 10  # avoid infinite loops
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
        # keep None values if unresolved
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
            self.debug(f"Checking condition: left={left_value} op={cond.operator} right={right_value}")
            if not op(left_value, right_value):
                self.info(
                    f"[SKIP] Condition failed: {left_value} {cond.operator} {right_value}"
                )
                return False

        return True

    # --------------------------------------------------
    # EXECUTE ONE STEP (unchanged behavior)
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

        params = self.resolve_params(step.params or {})

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
            last_exc = None
            for _ in range((step.retry or 0) + 1):
                try:
                    raw_output = tool_func(**params)  # raw dict from tool
                    resp = ToolResponse(success=True, output=raw_output)
                    break
                except Exception as e:
                    last_exc = e
                    resp = ToolResponse(success=False, error=str(e))

            if last_exc and not resp.success:
                self.error(f"[STEP {step.step_number}] Exception: {last_exc}")

            # save context
            if step.store_result_as:
                self.context[step.store_result_as] = resp.output

            self.step_results[step.step_number] = resp
            return resp

        # ---------- DYNAMIC ----------
        else:
            self.info(f"[EXECUTE] Step {step.step_number} (dynamic)...")

            last_exc = None
            for _ in range((step.retry or 0) + 1):
                try:
                    # keep compatibility: agent.invoke may expect (query, params) or (params, query)
                    # here we try both patterns safely
                    try:
                        raw_output = await agent.invoke(params=params, query=step.description)
                    except TypeError:
                        raw_output = await agent.invoke(step.description, params)
                    # expect agent.invoke returns dict with key "result" or raw output
                    out = raw_output.get("result") if isinstance(raw_output, dict) and "result" in raw_output else raw_output
                    resp = ToolResponse(success=True, output=out)
                    break
                except Exception as e:
                    last_exc = e
                    resp = ToolResponse(success=False, error=str(e))

            if last_exc and not resp.success:
                self.error(f"[STEP {step.step_number}] Exception: {last_exc}")

            if step.store_result_as:
                self.context[step.store_result_as] = resp.output

            self.step_results[step.step_number] = resp
            return resp

    # --------------------------------------------------
    # CONVERT SOP -> StateGraph (structure for visualization/interoperability)
    # --------------------------------------------------
    def sop_to_stategraph(self, sop: SOP) -> StateGraph:
        """
        Build a StateGraph structure representing the SOP.
        This does not execute; it builds nodes and edges so it can be inspected or used by external graph engines.
        """
        graph = StateGraph(name="sop_graph")
        # create a mapping step_number -> node_id
        node_map = {}
        for step in sop.steps:
            node_name = f"step_{step.step_number}"
            node_map[step.step_number] = graph.add_node(node_name, payload={"step": step})
        # create edges according to next_step_on_success / next_step_on_failure or sequential default
        for i, step in enumerate(sop.steps):
            src = node_map[step.step_number]
            # determine default next sequential
            default_next = sop.steps[i+1].step_number if i + 1 < len(sop.steps) else None
            # define success target
            success_target = None
            if getattr(step, "next_step_on_success", None):
                success_target = int(step.next_step_on_success)
            elif step.params and step.params.get("next_step_on_success"):
                success_target = int(step.params.get("next_step_on_success"))
            else:
                success_target = default_next
            if success_target:
                tgt = node_map.get(success_target)
                if tgt:
                    graph.add_edge(src, tgt, condition="success")
            else:
                graph.add_edge(src, graph.node(END), condition="success")

            # define failure target
            failure_target = None
            if getattr(step, "next_step_on_failure", None):
                failure_target = int(step.next_step_on_failure)
            elif step.params and step.params.get("next_step_on_failure"):
                failure_target = int(step.params.get("next_step_on_failure"))
            if failure_target:
                tgt = node_map.get(failure_target)
                if tgt:
                    graph.add_edge(src, tgt, condition="failure")
            else:
                # default on failure: terminate / go to END with failure marker
                graph.add_edge(src, graph.node(END), condition="failure")
        return graph

    # --------------------------------------------------
    # GRAPH-STYLE RUNNER (supports jump, back-step, loops)
    # --------------------------------------------------
    async def run_sop_as_graph(self, sop: SOP):
        """
        Execute the SOP using graph semantics:
        - honor next_step_on_success and next_step_on_failure
        - honor fields in step.params: "retry_step" (optional)
        - prevent infinite loops with visit counts
        """
        # map step_number -> SOPStep and build index sequence
        steps_map: Dict[int, SOPStep] = {s.step_number: s for s in sop.steps}
        ordered_step_numbers = [s.step_number for s in sop.steps]
        if not ordered_step_numbers:
            return {"success": True, "final_target": sop.final_target, "steps": [], "context": self.context}

        # visit counters to avoid infinite loops
        visits: Dict[int, int] = {num: 0 for num in ordered_step_numbers}

        # start at first step
        current_idx = 0
        results = []
        # use while loop for jumps/back-steps
        while 0 <= current_idx < len(ordered_step_numbers):
            step_num = ordered_step_numbers[current_idx]
            step = steps_map[step_num]

            visits[step_num] += 1
            if visits[step_num] > self.max_visits_per_step:
                err = f"Step {step_num} exceeded max visits ({self.max_visits_per_step}). Potential infinite loop."
                self.error(err)
                return {"success": False, "error": err, "steps": [r.dict() for r in results], "context": self.context}

            self.info(f"[GRAPH RUN] Executing step {step_num} (index {current_idx})")
            resp = await self.execute_step(step)
            results.append(resp)

            # if step failed, check next_step_on_failure (either direct attribute or in params)
            if not resp.success:
                target = None
                if getattr(step, "next_step_on_failure", None):
                    target = int(step.next_step_on_failure)
                elif step.params and step.params.get("next_step_on_failure"):
                    try:
                        target = int(step.params.get("next_step_on_failure"))
                    except Exception:
                        target = None

                # support retry_step (reflection loop)
                if step.params and step.params.get("retry_step"):
                    try:
                        retry_target = int(step.params.get("retry_step"))
                        target = retry_target
                    except Exception:
                        pass

                if target is not None and target in steps_map:
                    # jump to that target
                    new_idx = ordered_step_numbers.index(target)
                    self.info(f"[GRAPH RUN] Step {step_num} failed -> jumping to {target}")
                    current_idx = new_idx
                    continue
                else:
                    # default: abort and return failure + trace
                    self.error(f"[GRAPH RUN] Step {step_num} failed and no failure transition; aborting.")
                    return {
                        "success": False,
                        "error": resp.error or "step failure",
                        "steps": [r.dict() for r in results],
                        "context": self.context
                    }

            # success path: check next_step_on_success override
            success_target = None
            if getattr(step, "next_step_on_success", None):
                success_target = int(step.next_step_on_success)
            elif step.params and step.params.get("next_step_on_success"):
                try:
                    success_target = int(step.params.get("next_step_on_success"))
                except Exception:
                    success_target = None

            if success_target is not None and success_target in steps_map:
                self.info(f"[GRAPH RUN] Step {step_num} success -> jumping to {success_target}")
                current_idx = ordered_step_numbers.index(success_target)
                continue

            # default sequential: go to next step
            current_idx += 1

        # finished loop successfully
        return {
            "success": True,
            "final_target": sop.final_target,
            "steps": [r.dict() for r in results],
            "context": self.context
        }

    # --------------------------------------------------
    # RUN FULL SOP (auto-detect graph needs)
    # --------------------------------------------------
    async def run_sop(self, sop: SOP):
        """
        Auto-detect: if any step defines next_step_on_success/next_step_on_failure or
        if step.params contains retry_step/next_step_on_* then use graph runner.
        Otherwise fallback to linear runner (backwards-compatible).
        """
        # quick detection of graphy SOP
        needs_graph = False
        for step in sop.steps:
            if getattr(step, "next_step_on_success", None) is not None or getattr(step, "next_step_on_failure", None) is not None:
                needs_graph = True
                break
            if step.params and any(k in step.params for k in ("next_step_on_success", "next_step_on_failure", "retry_step")):
                needs_graph = True
                break

        if needs_graph:
            self.info("[RUN SOP] Detected graph-like SOP -> using graph runner")
            # build a StateGraph object for inspection (optional)
            try:
                sg = self.sop_to_stategraph(sop)
                self.debug(f"[RUN SOP] Generated StateGraph: {sg}")
            except Exception as e:
                # non-fatal if graph building fails; proceed with execution
                self.warning(f"[RUN SOP] Failed to build StateGraph: {e}")

            return await self.run_sop_as_graph(sop)

        # fallback: linear runner (existing behavior)
        self.info("[RUN SOP] Using linear runner")
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
                    "context": self.context,
                }

        return {
            "success": True,
            "final_target": sop.final_target,
            "steps": [r.dict() for r in results],
            "context": self.context,
        }
