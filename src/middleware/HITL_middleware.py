from src.middleware.agent_middleware import AgentMiddleware
from src.models.models import HITLRequired

class HITL:
    def __init__(self, tools=None):
        self.tools = set(tools or [])

    def requires_hitl(self, tool_name: str) -> bool:
        return tool_name in self.tools


class HITLMiddleware(AgentMiddleware):
    priority = 10

    def __init__(self, hitl: HITL):
        self.hitl = hitl

    async def before_tool(self, step, tool_name, params, context):
        approved = context.get("hitl_approved")

        if approved:
            if (
                approved.get("tool") == tool_name
                and approved.get("step_number") == step.step_number
            ):
                print("HITL approved for tool:", tool_name)
                return
            
        skipped = context.get("hitl_skipped")

        if skipped:
            if (
                skipped["tool"] == tool_name
                and skipped["step_number"] == step.step_number
            ):
                return  
 

        if self.hitl.requires_hitl(tool_name):
            raise HITLRequired(
                tool_name=tool_name,
                params=params,
                reason="Human approval required"
            )

         