from src.utils.logger import LoggerMixin
from src.agent.base_agent import BaseAgent
from src.agent.sop_agent import SOPAgent
from typing import List

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
        agent_str = "\n\n".join(agent.to_string() for agent in self.agents)

        sop = await self.sop_agent.invoke(plan, agent_str)

        if sop["success"] is not True:
            self.error("[DISPATCH ERROR] SOPAgent returned None")
            return None
        return sop["sop"]

