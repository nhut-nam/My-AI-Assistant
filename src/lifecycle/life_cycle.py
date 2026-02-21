from langgraph.graph import StateGraph, START, END
from src.utils.logger import LoggerMixin
from src.agent.planner_agent import PlannerAgent
from src.agent.plan_critic import PlanCriticAgent
from src.agent.chit_chat_agent import ChitChatAgent
from src.dispatcher.SOPStepDispatcher import SOPStepDispatcher
from src.agent.sop_agent import SOPAgent
from src.multiagent.executor_agent import ExecutorAgent
from src.agent.crud_agent import CRUDAgent
from src.agent.simple_math_agent import SimpleMathAgent
from src.tools.base_tool import BaseTool
from src.llm.groq_client import GroqClient
from src.llm.ollama_client import OllamaClient
from src.models.models import StateSchema, ExecutionState, ExecutionStatus
from src.middleware.HITL_middleware import HITL, HITLMiddleware
from src.handler.error_handler import ErrorHandler
from src.evaluation.sop_execution_summary import SOPExecutionSummary
from src.evaluation.execution_score import ExecutionScore
from src.evaluation.llm_prompt_critic import LLMPromptCritic

class LifeCycle(LoggerMixin):

    MAX_PLAN_RETRY = 3

    def __init__(self):
        super().__init__("LifeCycle")
        self.info("lifecycle_initializing")

        self.llm = GroqClient()
        self.llm_ollama = OllamaClient()

        # Agents sẽ được khởi tạo lại với segment_id khi cần
        self.planner = PlannerAgent(llm=self.llm)
        self.critic = PlanCriticAgent(llm=self.llm)
        self.sop_agent = SOPAgent(llm=self.llm)
        self.chit_chat = ChitChatAgent(llm=self.llm)

        self.base_tool = BaseTool()
        self.base_tool.auto_discover("src.tools.group")

        self.crud = CRUDAgent(llm=self.llm_ollama)
        self.crud.register_tool(self.base_tool.get_tools_by_group("file"))
        # self.crud.set_hitl_middleware(
        #     interupt_on={
        #         "tools": [
        #             "delete_file",
        #             "rename_file"
        #         ]
        #     }
        #     )

        self.math = SimpleMathAgent(llm=self.llm_ollama)
        self.math.register_tool(self.base_tool.get_tools_by_group("math"))

        self.dispatcher = SOPStepDispatcher(sop_agent=self.sop_agent, agents=[self.crud, self.math, self.chit_chat])
        
        hitl = HITL(
            tools=[
                "delete_file",
                "rename_file"
            ]
        )
        
        hitl_middleware = HITLMiddleware(hitl)

        self.executor = ExecutorAgent(middleware=[
            hitl_middleware
        ])
        self.executor.register_agent(self.crud)
        self.executor.register_agent(self.math)
        self.executor.register_agent(self.chit_chat)
        
        self.error_handler = ErrorHandler()
        
        self.sop_execution_summary = SOPExecutionSummary()
        self.execution_score = ExecutionScore()
        self.llm_prompt_critic = LLMPromptCritic(llm=self.llm)

        self.workflow = self._build_graph()

    def _build_graph(self):

        graph = StateGraph(state_schema=StateSchema)
        
        def route_from_start(state: StateSchema):
            self.debug("router_start", is_resume=state.is_resume)
            if state.is_resume:
                self.info("router_resume_detected", route="executor")
                return "executor"
            self.info("router_fresh_run", route="planner")
            return "planner"



        async def planner_node(state: StateSchema):
            self.info("planner_node_enter")

            try:
                if state.critic:
                    self.warning(
                        "planner_replanning",
                        retry=state.retry + 1,
                        error_message=state.critic.get("error_message", "")
                    )
                    plan = await self.planner.invoke(
                        state.user_request,
                        error_message=state.critic.get("error_message", ""),
                        attempt=state.retry + 1
                    )
                else:
                    self.debug("planner_first_attempt")
                    plan = await self.planner.invoke(state.user_request)

                # Check if plan generation failed
                if isinstance(plan, dict) and not plan.get("success", True):
                    error_msg = plan.get("message", "Unknown error")
                    self.error("planner_failed", error=error_msg)
                    state.plan = None
                    return state

                state.plan = plan
                self.info("planner_plan_generated", steps_count=len(plan.steps) if plan else 0)
                self.debug("planner_plan_details", steps=plan.steps if plan else [])
                return state
            except Exception as e:
                agent_error = self.error_handler.handle_exception(
                    e,
                    source="LifeCycle.planner_node",
                    metadata={"user_request": state.user_request[:100] if state.user_request else None}
                )
                self.error("planner_node_exception", error=agent_error.message, error_type=agent_error.error_type.value)
                state.plan = None
                return state


        async def critic_node(state: StateSchema):
            self.info("critic_node_evaluating")

            critic_resp = await self.critic.invoke(
                plan=state.plan,
                query=state.user_request
            )

            critic_obj = critic_resp.get("feedback")
            critic = critic_obj.model_dump() if critic_obj else {}

            score = critic.get("score", 0)
            self.info("critic_score", score=score)

            if score < 100:
                self.warning("critic_plan_rejected", score=score)

            state.critic = critic
            return state


        def route_planning(state: StateSchema):
            score = state.critic.get("score", 0)
            retry = state.retry

            self.debug(
                "route_planning",
                score=score,
                retry=retry,
                max_retry=self.MAX_PLAN_RETRY
            )

            if score == 100:
                self.info("route_planning_accepted", route="sop_dispatch")
                return "sop_dispatch"

            if retry + 1 >= self.MAX_PLAN_RETRY:
                self.error("route_planning_max_retry_exceeded", route="stop")
                return "stop"

            state.retry += 1
            self.warning("route_planning_retry", route="planner")
            return "planner"

        async def sop_dispatch_node(state: StateSchema):
            self.info("sop_dispatch_building")

            try:
                if not state.plan:
                    validation_error = self.error_handler.handle_validation_failure(
                        "Plan is None or invalid",
                        source="LifeCycle.sop_dispatch_node"
                    )
                    self.error("sop_dispatch_no_plan", error=validation_error.message)
                    state.sop = None
                    return state

                sop_result = await self.dispatcher.build_sop(state.plan)
                
                if isinstance(sop_result, dict) and not sop_result.get("success", True):
                    error_msg = sop_result.get("error", "Unknown error")
                    self.error("sop_dispatch_failed", error=error_msg)
                    state.sop = None
                    return state

                sop = sop_result if not isinstance(sop_result, dict) else sop_result.get("sop")
                state.sop = sop

                self.info("sop_dispatch_built", steps_count=len(sop.steps) if sop else 0)
                return state
            except Exception as e:
                agent_error = self.error_handler.handle_exception(
                    e,
                    source="LifeCycle.sop_dispatch_node",
                    metadata={"has_plan": state.plan is not None}
                )
                self.error("sop_dispatch_exception", error=agent_error.message, error_type=agent_error.error_type.value)
                state.sop = None
                return state


        async def executor_node(state: StateSchema):
            self.info("executor_node_enter")

            if state.is_resume:
                self.info("executor_resume_execution")

                result = await self.executor.run_sop(
                    state.sop,
                    resume_context=state.exec_result.context,
                    resume_step_results=state.exec_result.steps,
                )

                state.exec_result = result
                state.is_resume = False
                return state

            self.info("executor_fresh_execution")
            result = await self.executor.run_sop(state.sop)
            state.exec_result = result
            return state


        def route_after_executor(state: StateSchema):
            result = state.exec_result

            if not result:
                self.debug("route_after_executor_no_result", route="END")
                return state

            if result.state == ExecutionState.PENDING_HITL:
                if state.hitl_decision is not None:
                    self.info("route_after_executor_hitl_decision", route="resume", decision=state.hitl_decision)
                    return "resume"

                self.warning("route_after_executor_waiting_hitl", route="END")
                return "stop"

            safe_result = (
                result.model_dump()
                if hasattr(result, "model_dump")
                else str(result)
            )
            
            self.info(
                "route_after_executor_finished",
                metadata={
                    "state": result.state.value,
                    "result_snapshot": safe_result,
                    "has_result": result.result is not None,
                    "has_error": result.error is not None,
                    "steps_count": len(result.steps) if result.steps else 0,
                }
            )
            return "stop"
        
        async def review_node(state: StateSchema):
            result = state.exec_result
            try:
                if state.sop and result.state != ExecutionState.PENDING_HITL:
                    # 1. SOP + Execution → teacher-style summary
                    sop_summary = self.sop_execution_summary.build(
                        sop=state.sop.model_dump() if hasattr(state.sop, "model_dump") else state.sop,
                        execution_result=result,
                    )

                    self.debug("sop_execution_summary", summary=sop_summary)
                    # 2. Rule-based grading
                    score_report = self.execution_score.score(sop_summary)
                    
                    self.debug("execution_score_report", score_report=score_report)

                    # 3. LLM teacher critique
                    critic_result = self.llm_prompt_critic.critique(
                        sop=state.sop.model_dump() if hasattr(state.sop, "model_dump") else state.sop,
                        sop_execution_summary=sop_summary,
                        score_report=score_report,
                    )

                    # 4. Optional policy learning
                    self.llm_prompt_critic.apply_policy_if_needed(critic_result)

                    # Optional: attach to state for UI / logging
                    state.post_execution_review = {
                        "summary": sop_summary,
                        "score": score_report,
                        "critic": critic_result,
                    }
                    
                    print(state)
                    self.info(
                        "post_execution_review_completed",
                        metadata={
                            # --- execution outcome ---
                            "final_state": sop_summary.get("final_state"),
                            "steps_total": len(sop_summary.get("step_reviews", [])),

                            # --- grading ---
                            "score": score_report.get("total_score"),
                            "max_score": score_report.get("max_score"),
                            "grade": score_report.get("grade"),

                            # --- critic meta ---
                            "policy_edit": critic_result.get("is_edit"),
                            "failure_type": critic_result.get("failure_type"),
                            "risk": critic_result.get("risk_assessment"),
                            "systemic": critic_result.get("systemic_pattern_detected"),
                            "critical_step": critic_result.get("most_critical_step"),
                            "scope": critic_result.get("improvement_scope"),
                            "confidence": critic_result.get("confidence"),
                        }
                    )
            except Exception as e:
                self.error(
                    "post_execution_review_failed",
                    error=str(e),
                )

            return state



        async def resume_node(state: StateSchema):
            decision = state.hitl_decision
            exec_result = state.exec_result

            self.info("resume_node_hitl_decision", decision=decision)

            if decision == "reject":
                self.warning(
                    "resume_node_hitl_rejected",
                    tool=exec_result.tool_name,
                    step_number=exec_result.current_step_idx + 1
                )

                exec_result.context["hitl_skipped"] = {
                    "tool": exec_result.tool_name,
                    "step_number": exec_result.current_step_idx + 1,
                }

                exec_result.current_step_idx += 2

                state.exec_result = exec_result
                state.hitl_decision = None
                state.is_resume = True    
                return state

            if decision == "approve":
                self.info(
                    "resume_node_hitl_approved",
                    tool=exec_result.tool_name,
                    step_number=exec_result.current_step_idx + 1
                )

                exec_result.context["hitl_approved"] = {
                    "tool": exec_result.tool_name,
                    "step_number": exec_result.current_step_idx + 1,
                }

                state.is_resume = True
                state.hitl_decision = None
                return state

            return state

        
        graph = StateGraph(state_schema=StateSchema)

        graph.add_node("planner", planner_node)
        graph.add_node("critic", critic_node)
        graph.add_node("sop_dispatch", sop_dispatch_node)
        graph.add_node("executor", executor_node)
        graph.add_node("resume", resume_node)
        graph.add_node("review", review_node)

        graph.add_conditional_edges(
            START,
            route_from_start,
            {
                "planner": "planner",
                "executor": "executor",
            }
        )
        graph.add_edge("planner", "critic")

        graph.add_conditional_edges(
            "critic",
            route_planning,
            {
                "planner": "planner",
                "sop_dispatch": "sop_dispatch",
                END: END
            }
        )

        graph.add_edge("sop_dispatch", "executor")

        graph.add_edge("executor", "review")

        graph.add_conditional_edges(
            "review",
            route_after_executor,
            {
                "resume": "resume",
                "stop": END,
            }
        )

        graph.add_edge("resume", "executor")

        return graph.compile()


    async def run(self, state: StateSchema) -> StateSchema:
        segment_id = state.segment_id
        if segment_id:
            if hasattr(self.planner, 'execution_id'):
                self.planner.execution_id = segment_id
            if hasattr(self.critic, 'execution_id'):
                self.critic.execution_id = segment_id
            if hasattr(self.sop_agent, 'execution_id'):
                self.sop_agent.execution_id = segment_id
            if hasattr(self.executor, 'execution_id'):
                self.executor.execution_id = segment_id
            if hasattr(self.crud, 'execution_id'):
                self.crud.execution_id = segment_id
            if hasattr(self.math, 'execution_id'):
                self.math.execution_id = segment_id
            self.execution_id = segment_id
        
        raw_state = await self.workflow.ainvoke(state)
        return StateSchema(**raw_state)

