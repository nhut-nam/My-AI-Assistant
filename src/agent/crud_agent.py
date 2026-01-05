from src.agent.base_agent import BaseAgent
from langchain_core.messages import HumanMessage, SystemMessage
from src.tools.base_tool import BaseTool
import json

BaseTool.auto_discover()


class CRUDAgent(BaseAgent):
    tools = BaseTool.list_tools()

    def __init__(
        self, llm, tools=None, name="CRUDAgent",
        description="Agent xử lý các công việc quản lý file",
        log_dir="logs"
    ):
        super().__init__(llm, tools, name, description, log_dir)


    def build_prompt(self, **kwargs):
        query = kwargs.get("query", "")
        params = kwargs.get("params", {})

        return [
            SystemMessage(
                content=(
                    "You are a File Management Assistant.\n"
                    "You can create, read, update, rename, copy and delete files.\n"
                    "If the user request requires using a tool, output VALID JSON with:\n"
                    "{ 'tool': '<tool_name>', 'params': {...} }\n"
                    "If no tool is needed (rare), you can reason directly."
                    "DO NOT EXPLAIN, just return JSON format like 'success': True/False. 'result': <your answer>."
                )
            ),
            HumanMessage(
                content=f"Task: {query}\nParameters: {params}"
            )
        ]

    async def invoke(self, **kwargs):
        query = kwargs.get("query", "")
        params = kwargs.get("params", {})

        self.info(f"[CRUDAgent] Invoking with query: {query}")

        prompt = self.build_prompt(query=query, params=params)

        output = await self.llm.ainvoke(prompt)
        raw = output.content.strip()

        self.info(f"[CRUDAgent] Raw output: {raw}")

        try:
            return json.loads(raw)
        except:
            return raw
