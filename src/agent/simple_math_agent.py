from src.agent.base_agent import BaseAgent
from langchain_core.messages import HumanMessage, SystemMessage
from src.tools.base_tool import BaseTool
import json
from src.models.models import Response

BaseTool.auto_discover()


class SimpleMathAgent(BaseAgent):
    tools = BaseTool.list_tools()

    def __init__(
        self, llm, tools=None, name="SimpleMathAgent",
        description="Agent xử lý các phép toán đơn giản", log_dir="logs"
    ):
        super().__init__(llm, tools, name, description, log_dir)

    # ----------------------------------------------------------
    # PROMPT ENGINEERING
    # ----------------------------------------------------------
    def build_prompt(self, **kwargs):
        """
        Chuẩn hoá prompt phù hợp với quy trình dynamic tool selection.
        Executor sẽ dùng LLM này để trả về JSON hoặc text cho reasoning.
        """
        query = kwargs.get("query", "")
        params = kwargs.get("params", {})

        return [
            SystemMessage(
                content=(
                    "You are a Math Assistant AI.\n"
                    "Your job is to solve the math problem step-by-step.\n"
                    "If the task requires arithmetic operations, return the tool name and parameters.\n"
                    "If the calculation is simple, you can compute it directly.\n"
                    "Always return valid JSON when specifying a tool."
                    "DO NOT EXPLAIN, just return JSON format like 'success': True/False. 'result': <your answer>."
                )
            ),
            HumanMessage(
                content=f"Task description: {query}\nParameters: {params}"
            ),
        ]

    # ----------------------------------------------------------
    # LLM REASONING
    # ----------------------------------------------------------
    async def invoke(self, **kwargs):
        """
        Hàm này chạy khi SOP step ở chế độ 'dynamic',
        dùng LLM để quyết định cách xử lý.
        """
        query = kwargs.get("query", "")
        params = kwargs.get("params", {})

        self.info(f"[SimpleMathAgent] Running reasoning for query: {query}")

        prompt = self.build_prompt(query=query, params=params)

        # Gọi LLM
        output = await self.llm.ainvoke(prompt)
        raw_content = output.content.strip()

        self.info(f"[SimpleMathAgent] Raw output: {raw_content}")

        # Nếu LLM trả JSON → parse
        try:
            raw_content_json = json.loads(raw_content)
            return {"message": "success", "result": raw_content_json['result']}
        except:
            return {"message": "fail", "result": None}