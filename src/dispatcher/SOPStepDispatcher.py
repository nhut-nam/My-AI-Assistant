from src.utils.logger import LoggerMixin
from src.agent.base_agent import BaseAgent
from src.agent.sop_agent import SOPAgent
from typing import List
from src.tools.base_tool import BaseTool

def build_available_agents_dict(agents) -> dict:
    """
    Build structure for validate_sop:
    {
        "CRUDAgent": {
            "tools": {
                "create_file": "...",
                ...
            }
        }
    }
    """
    result = {}

    for agent in agents:
        agent_name = agent.__class__.__name__
        tools = {}

        for tool in agent.get_tools():
            tools[tool.__name__] = tool.__doc__ or ""

        result[agent_name] = {
            "tools": tools
        }

    return result

class SOPStepDispatcher(LoggerMixin):
    """
    Dispatcher: Nhận vào (plan, group) → gọi SOPAgent để tạo SOP.
    """

    def __init__(self, sop_agent: SOPAgent, agents: List[BaseAgent], name=None, log_dir="logs"):
        super().__init__(name=name or "SOPStepDispatcher", log_dir=log_dir)
        self.sop_agent = sop_agent    
        self.agents = agents          

        self.info(f"[INIT] Dispatcher loaded with agents: {', '.join(agent.__class__.__name__ for agent in self.agents)}")

    async def build_sop(self, plan):
        """
        Nhận plan từ PlannerAgent để biết agent nào cung cấp tool descriptions.
        """
        agent_str = ""
        agent_str = "\n\n".join(BaseTool.get_tools_grouped_str_by_callables(tools=agent.get_tools(), agent_name=agent.__class__.__name__)for agent in self.agents)

        agent_dict = build_available_agents_dict(agents=self.agents)
        sop = await self.sop_agent.invoke(plan, agent_str, agent_dict)

        if sop["success"] is not True:
            self.error("[DISPATCH ERROR] SOPAgent returned None")
            return None
        return sop["sop"]

