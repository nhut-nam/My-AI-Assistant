from src.agent.base_agent import BaseAgent
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import HumanMessage
from src.tools.base_tool import BaseTool

BaseTool.auto_discover()

class CRUDAgent(BaseAgent):
    tools = BaseTool.list_tools()

    def __init__(self, llm, tools = None, name = "CRUDAgent", description="Agent xử lý các công việc quản lý file", log_dir = "logs"):
        super().__init__(llm, tools, name, description, log_dir)

    def build_prompt(self, **kwargs):
        """Tạo prompt LLM."""
        return [
            HumanMessage(
                content=f"You are a file management assistant. Task: {kwargs['query']}"
            )
        ]
    
    def execute_step(self, step, context):
        return super().execute_step(step, context)
    
    def invoke(self, **kwargs):
        return super().invoke(**kwargs)
