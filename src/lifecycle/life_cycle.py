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
from src.models.models import StateSchema
from src.models.models import CriticFeedback

class LifeCycle(LoggerMixin):

    MAX_PLAN_RETRY = 3

    def __init__(self):
        super().__init__("LifeCycle")
        self.info("[LifeCycle] Initializing...")

        # Shared LLMs
        self.llm = GroqClient()
        self.llm_ollama = OllamaClient()

        # AGENTS
        self.planner = PlannerAgent(llm=self.llm)
        self.critic = PlanCriticAgent(llm=self.llm)
        self.sop_agent = SOPAgent(llm=self.llm)

        # TOOLS + EXECUTOR
        self.base_tool = BaseTool()
        self.base_tool.auto_discover("src.tools.group")

        self.crud = CRUDAgent(llm=self.llm_ollama)
        self.crud.register_tool(self.base_tool.get_tools_by_group("file"))

        self.math = SimpleMathAgent(llm=self.llm_ollama)
        self.math.register_tool(self.base_tool.get_tools_by_group("math"))

        self.dispatcher = SOPStepDispatcher(sop_agent=self.sop_agent, agents=[self.crud, self.math])

        self.executor = ExecutorAgent()
        self.executor.register_agent(self.crud)
        self.executor.register_agent(self.math)

        # BUILD THE GRAPH
        self.workflow = self._build_graph()

    # ───────────────────────────────────────────────────────────
    # BUILD LANGGRAPH
    # ───────────────────────────────────────────────────────────
    def _build_graph(self):

        graph = StateGraph(state_schema=StateSchema)

        # -----------------------------------------------------
        # NODE 1 — Planner
        # -----------------------------------------------------
        async def planner_node(state: StateSchema):
            plan = await self.planner.invoke(state.user_request)
            state.plan = plan
            return state

        # -----------------------------------------------------
        # NODE 2 — Critic Plan
        # -----------------------------------------------------
        async def critic_node(state: StateSchema):
            critic_resp = await self.critic.invoke(plan=state.plan, query=state.user_request)

            critic_obj = critic_resp.get("feedback")   # CriticFeedback object hoặc None

            # Convert object → dict (LangGraph yêu cầu JSON-safe state)
            if critic_obj:
                critic = critic_obj.model_dump()
            else:
                critic = {}

            state.critic = critic
            return state


        # -----------------------------------------------------
        # ROUTER — Retry if score < 100
        # -----------------------------------------------------
        def route_planning(state: StateSchema):
            critic = state.critic        # critic is ALWAYS a dict now
            retry = state.retry

            # critic must be a dict
            if not isinstance(critic, dict):
                return "planner"

            score = critic.get("score", 0)

            if score == 100:
                return "sop_dispatch"

            if retry + 1 >= self.MAX_PLAN_RETRY:
                return "stop"

            state.retry += 1
            return "planner"

        # -----------------------------------------------------
        # NODE 3 — SOP Dispatcher
        # -----------------------------------------------------
        async def sop_dispatch_node(state: StateSchema):
            sop = await self.dispatcher.build_sop(state.plan)
            state.sop = sop
            return state

        # -----------------------------------------------------
        # NODE 5 — Executor
        # -----------------------------------------------------
        async def executor_node(state: StateSchema):
            result = await self.executor.run_sop(state.sop)
            state.exec_result = result or {}     # FIXED
            return state

        # -----------------------------------------------------
        # STOP NODE
        # -----------------------------------------------------
        def stop_node(state: StateSchema):
            self.error("[LifeCycle] Stopped due to planning failure.")
            return state

        # -----------------------------------------------------
        # GRAPH CONNECTIONS
        # -----------------------------------------------------
        graph.add_node("planner", planner_node)
        graph.add_node("critic", critic_node)
        graph.add_node("sop_dispatch", sop_dispatch_node)
        graph.add_node("executor", executor_node)
        graph.add_node("stop", stop_node)

        graph.add_edge(START, "planner")
        graph.add_edge("planner", "critic")

        graph.add_conditional_edges(
            "critic",
            route_planning,
            {
                "planner": "planner",
                "sop_dispatch": "sop_dispatch",
                "stop": "stop"
            }
        )

        graph.add_edge("sop_dispatch", "executor")
        graph.add_edge("executor", END)

        return graph.compile()


    # ───────────────────────────────────────────────────────────
    async def run(self, user_request: str):

        final_state = await self.workflow.ainvoke({"user_request": user_request})
        return final_state
