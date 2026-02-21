from src.utils.logger import LoggerMixin
from src.agent.base_agent import BaseAgent
from src.agent.sop_agent import SOPAgent
from typing import List
from src.tools.base_tool import BaseTool
from src.handler.error_handler import ErrorHandler

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
        self.error_handler = ErrorHandler()

        self.info("dispatcher_initialized", agents=[agent.__class__.__name__ for agent in self.agents])

    async def build_sop(self, plan):
        """
        Nhận plan từ PlannerAgent để biết agent nào cung cấp tool descriptions.
        """
        try:
            if not plan:
                validation_error = self.error_handler.handle_validation_failure(
                    "Plan is None or invalid",
                    source="SOPStepDispatcher.build_sop"
                )
                self.error("dispatcher_no_plan", error=validation_error.message)
                return None

            agent_str = ""
            agent_str = "\n\n".join(
                BaseTool.get_tools_grouped_str_by_callables(
                    tools=agent.get_tools(), 
                    agent_name=agent.__class__.__name__
                ) for agent in self.agents
            )

            agent_dict = build_available_agents_dict(agents=self.agents)
            
            try:
                sop_result = await self.sop_agent.invoke(plan, agent_str, agent_dict)
            except Exception as e:
                agent_error = self.error_handler.handle_exception(
                    e,
                    source="SOPStepDispatcher.build_sop",
                    metadata={"plan_steps_count": len(plan.steps) if plan else 0}
                )
                self.error("dispatcher_sop_agent_failed", error=agent_error.message, error_type=agent_error.error_type.value)
                return None

            if not isinstance(sop_result, dict) or sop_result.get("success") is not True:
                error_msg = sop_result.get("error", "Unknown error") if isinstance(sop_result, dict) else "Invalid SOP result"
                validation_error = self.error_handler.handle_validation_failure(
                    f"SOP generation failed: {error_msg}",
                    source="SOPStepDispatcher.build_sop",
                    metadata={"sop_result": str(sop_result)[:200]}
                )
                self.error("dispatcher_sop_failed", error=validation_error.message)
                return None
            
            return sop_result.get("sop")
        except Exception as e:
            agent_error = self.error_handler.handle_exception(
                e,
                source="SOPStepDispatcher.build_sop",
                metadata={"agents_count": len(self.agents)}
            )
            self.error("dispatcher_exception", error=agent_error.message, error_type=agent_error.error_type.value)
            return None

