from src.agent.base_agent import BaseAgent
from src.models.models import Plan
from src.prompt_engineering.templates import PLANNER_PROMPT
from langchain_core.prompts import ChatPromptTemplate


class PlannerAgent(BaseAgent):
    """
    Planner Agent:
    - tạo kế hoạch (Plan)
    """

    def __init__(self, llm, tools = None, name = None, description="", log_dir = "logs"):
        super().__init__(llm, tools, name, description, log_dir)
        self.planner_prompt = PLANNER_PROMPT

    def build_prompt(self):
        """Build template chuẩn SYSTEM + placeholder messages."""
        return ChatPromptTemplate.from_messages(
            [
                ("system", self.planner_prompt),
                ("placeholder", "{messages}")
            ]
        )

    def chain(self):
        """Prompt → LLM → Structured Plan."""
        prompt = self.build_prompt()
        return prompt | self.llm.with_structured_output(Plan)

    async def invoke(self, query: str):
        """Trả về dict {'plan': [...]} đúng spec LangGraph."""
        self.debug(f"[PlannerAgent] Generating plan for: {query}")

        chain = self.chain()
        result = await chain.ainvoke({"messages": [("user", query)]})

        self.info(f"[PlannerAgent] Plan generated: {result.steps}")

        return result
