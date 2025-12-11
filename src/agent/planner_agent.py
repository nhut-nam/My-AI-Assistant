from src.agent.base_agent import BaseAgent
from src.models.models import Plan
from src.prompt_engineering.templates import PLANNER_PROMPT
from langchain_core.prompts import ChatPromptTemplate
from src.handler.error_handler import ErrorSeverity
from src.agent.plan_critic import PlanCriticAgent

class PlannerAgent(BaseAgent):
    """
    Planner Agent:
    - tạo kế hoạch (Plan)
    """
    MAX_RETRY = 3

    def __init__(self, llm, tools=None, name=None, description="", log_dir="logs"):
        super().__init__(llm, tools, name, description, log_dir)
        self.planner_prompt = PLANNER_PROMPT
        self.critic_agent = PlanCriticAgent(llm=llm)

    # ------------------------------------------------------------
    # BUILD PROMPT — thêm biến {error_message} & {attempt}
    # ------------------------------------------------------------
    def build_prompt(self):
        """
        Build template chuẩn SYSTEM + placeholder messages.
        Cho phép truyền biến attempt và error_message vào hệ thống.
        """
        return ChatPromptTemplate.from_messages(
            [
                ("system", self.planner_prompt),
                ("human", "{messages}"),
            ]
        )

    def chain(self):
        """Prompt → LLM → Structured Plan."""
        prompt = self.build_prompt()
        return prompt | self.llm.with_structured_output(Plan)

    # ------------------------------------------------------------
    # INVOKE
    # ------------------------------------------------------------
    async def invoke(self, query: str):
        self.debug(f"[PlannerAgent] Generating plan for: {query}")

        chain = self.chain()
        last_error_message = "None"

        for attempt in range(1, self.MAX_RETRY + 1):   # bắt đầu từ 1
            try:
                self.debug(f"[PlannerAgent] Attempt {attempt}/{self.MAX_RETRY}")

                # --------------------------------------------------------
                # 1) TẠO THÔNG ĐIỆP ĐẦU VÀO CHO PLANNER_PROMPT
                # --------------------------------------------------------
                system_vars = {
                    "attempt": attempt,
                    "error_message": last_error_message
                }

                # 2) GENERATE PLAN với biến attempt + error_message
                result = await chain.ainvoke({
                    "messages": [("user", query)],
                    **system_vars
                })
                print("Generated Plan: ", result)
                return result

            except Exception as e:
                agent_error = self.error_handler.handle_exception(
                    e, source="PlannerAgent.invoke"
                )

                last_error_message = f"{agent_error.error_type}: {agent_error.message}"

                self.warning(
                    f"[PlannerAgent] Attempt {attempt} failed: {last_error_message}"
                )

                if agent_error.severity != ErrorSeverity.RECOVERABLE:
                    break

        # --------------------------------------------------------
        # 5) FAIL SAU NHIỀU LẦN THỬ
        # --------------------------------------------------------
        self.error(f"[PlannerAgent] Failed after {self.MAX_RETRY} attempts.")
        return last_error_message
