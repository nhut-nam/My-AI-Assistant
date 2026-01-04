from src.lifecycle.life_cycle import LifeCycle
from src.models.models import ExecutionState, StateSchema, ConversationStatus, Message, ConversationSegment

class GradChaining:
    def __init__(self):
        self.life_cycle = LifeCycle()
        
        self.segments: dict[str, ConversationSegment] = {}
        
    def _start_segment(self, user_text: str):
        seg = ConversationSegment(
            intent=user_text,
            status=ConversationStatus.RUNNING
        )
        seg.messages.append(Message("user", user_text))
        self.segments.append(seg)
        self.current_segment = seg


    def _agent_say(self, text: str):
        self.current_segment.messages.append(
            Message("agent", text)
        )

    async def invoke(
        self,
        *,
        segment_id: str,
        user_request: str | None = None,
        hitl_decision: str | None = None,
    ):
        if segment_id not in self.segments:
            if not user_request:
                raise RuntimeError("Cannot create segment without user_request")

            seg = ConversationSegment(
                segment_id=segment_id,
                intent=user_request,
                status=ConversationStatus.RUNNING
            )
            seg.messages.append(Message("user", user_request))
            self.segments[segment_id] = seg
        else:
            seg = self.segments[segment_id]

        if hitl_decision is not None:
            if not seg.pending_state:
                raise RuntimeError("No pending HITL in this segment")

            seg.messages.append(Message("user", hitl_decision))
            seg.pending_state.hitl_decision = hitl_decision
            seg.pending_state.is_resume = True
            final_state = await self.life_cycle.run(seg.pending_state)
            seg.pending_state = None

        elif user_request is not None:
            state = StateSchema(user_request=user_request)
            final_state = await self.life_cycle.run(state)

        else:
            raise RuntimeError("Either user_request or hitl_decision must be provided")

        exec_result = final_state.exec_result

        if exec_result.state == ExecutionState.PENDING_HITL:
            seg.status = ConversationStatus.WAITING_HITL
            seg.pending_state = final_state

            msg = (
                f"⚠️ Action requires approval\n"
                f"Tool: {exec_result.tool_name}\n"
                f"Reason: {exec_result.reason}\n"
                f"Type 'approve' or 'reject'."
            )
            seg.messages.append(Message("agent", msg))
            return seg
        
        if exec_result.state == ExecutionState.CANCELLED:
            seg.status = ConversationStatus.DONE
            self._agent_say(f"❌ Action was cancelled by user.")

        if exec_result.state == ExecutionState.DONE:
            seg.status = ConversationStatus.DONE
            seg.messages.append(Message("agent", str(exec_result.result)))
            return seg

        seg.status = ConversationStatus.FAILED
        seg.messages.append(Message("agent", exec_result.error))
        return seg



