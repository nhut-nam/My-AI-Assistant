from langgraph.graph import StateGraph, START, END
from src.utils.logger import LoggerMixin
from src.agent.planner_agent import PlannerAgent
from src.agent.plan_critic import PlanCriticAgent
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

class LifeCycle(LoggerMixin):

    MAX_PLAN_RETRY = 3

    def __init__(self):
        super().__init__("LifeCycle")
        self.info("[LifeCycle] Initializing...")

        self.llm = GroqClient()
        self.llm_ollama = OllamaClient()

        self.planner = PlannerAgent(llm=self.llm)
        self.critic = PlanCriticAgent(llm=self.llm)
        self.sop_agent = SOPAgent(llm=self.llm)

        self.base_tool = BaseTool()
        self.base_tool.auto_discover("src.tools.group")

        self.crud = CRUDAgent(llm=self.llm_ollama)
        self.crud.register_tool(self.base_tool.get_tools_by_group("file"))

        self.math = SimpleMathAgent(llm=self.llm_ollama)
        self.math.register_tool(self.base_tool.get_tools_by_group("math"))

        self.dispatcher = SOPStepDispatcher(sop_agent=self.sop_agent, agents=[self.crud, self.math])
        
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

        self.workflow = self._build_graph()

    def _build_graph(self):

        graph = StateGraph(state_schema=StateSchema)
        
        def route_from_start(state: StateSchema):
            self.debug(f"[Router] START is_resume={state.is_resume}")
            if state.is_resume:
                self.info("[Router] Resume detected → executor")
                return "executor"
            self.info("[Router] Fresh run → planner")
            return "planner"



        async def planner_node(state: StateSchema):
            self.info("[PlannerNode] Enter")

            if state.critic:
                self.warning(
                    f"[PlannerNode] Re-planning due to critic. retry={state.retry + 1}"
                )
                plan = await self.planner.invoke(
                    state.user_request,
                    error_message=state.critic.get("error_message", ""),
                    attempt=state.retry + 1
                )
            else:
                self.debug("[PlannerNode] First planning attempt")
                plan = await self.planner.invoke(state.user_request)

            state.plan = plan
            self.info("[PlannerNode] Plan generated")
            self.debug(f"[PlannerNode] Plan steps={len(plan.steps)}")
            return state


        async def critic_node(state: StateSchema):
            self.info("[CriticNode] Evaluating plan")

            critic_resp = await self.critic.invoke(
                plan=state.plan,
                query=state.user_request
            )

            critic_obj = critic_resp.get("feedback")
            critic = critic_obj.model_dump() if critic_obj else {}

            score = critic.get("score", 0)
            self.info(f"[CriticNode] Score={score}")

            if score < 100:
                self.warning("[CriticNode] Plan rejected")

            state.critic = critic
            return state


        def route_planning(state: StateSchema):
            score = state.critic.get("score", 0)
            retry = state.retry

            self.debug(
                f"[RoutePlanning] score={score}, retry={retry}/{self.MAX_PLAN_RETRY}"
            )

            if score == 100:
                self.info("[RoutePlanning] Plan accepted → SOP")
                return "sop_dispatch"

            if retry + 1 >= self.MAX_PLAN_RETRY:
                self.error("[RoutePlanning] Max retry exceeded → STOP")
                return "stop"

            state.retry += 1
            self.warning("[RoutePlanning] Retry planner")
            return "planner"

        async def sop_dispatch_node(state: StateSchema):
            self.info("[SOPDispatch] Building SOP from plan")

            sop = await self.dispatcher.build_sop(state.plan)
            state.sop = sop

            self.info(f"[SOPDispatch] SOP built with {len(sop.steps)} steps")
            return state


        async def executor_node(state: StateSchema):
            self.info("[ExecutorNode] Enter")

            if state.is_resume:
                self.info("[ExecutorNode] Resume execution")

                result = await self.executor.run_sop(
                    state.sop,
                    resume_context=state.exec_result.context,
                    resume_step_results=state.exec_result.steps,
                )

                state.exec_result = result
                state.is_resume = False
                return state

            self.info("[ExecutorNode] Fresh execution")
            result = await self.executor.run_sop(state.sop)
            state.exec_result = result
            return state


        def route_after_executor(state: StateSchema):
            result = state.exec_result

            if not result:
                self.debug("[RouteAfterExec] No result → END")
                return END

            if result.state == ExecutionState.PENDING_HITL:
                if state.hitl_decision is not None:
                    self.info("[RouteAfterExec] HITL decision received → resume")
                    return "resume"

                self.warning("[RouteAfterExec] Waiting for HITL decision")
                return END

            self.info("[RouteAfterExec] Execution finished")
            return END

        async def resume_node(state: StateSchema):
            decision = state.hitl_decision
            exec_result = state.exec_result

            self.info(f"[ResumeNode] HITL decision={decision}")

            if decision == "reject":
                self.warning("[ResumeNode] HITL rejected → skip step")

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
                self.info("[ResumeNode] HITL approved")

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

        graph.add_conditional_edges(
            "executor",
            route_after_executor,
            {
                "resume": "resume",
                END: END
            }
        )

        graph.add_edge("resume", "executor")

        return graph.compile()


    async def run(self, state: StateSchema) -> StateSchema:
        raw_state = await self.workflow.ainvoke(state)
        return StateSchema(**raw_state)

