from src.lifecycle.life_cycle import LifeCycle
from src.models.models import (
    ExecutionState,
    StateSchema,
    ConversationStatus,
    Message,
    ConversationSegment,
)


class GradChaining:
    def __init__(self):
        self.life_cycle = LifeCycle()
        self.segments: dict[str, ConversationSegment] = {}

    async def invoke(
        self,
        *,
        segment_id: str,
        user_request: str | None = None,
        hitl_decision: str | None = None,
    ):
        # -------------------------------------------------
        # INIT / GET SEGMENT
        # -------------------------------------------------
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

        # -------------------------------------------------
        # HITL RESUME
        # -------------------------------------------------
        if hitl_decision is not None:
            if not seg.pending_state:
                raise RuntimeError("No pending HITL in this segment")

            seg.messages.append(Message("user", hitl_decision))

            seg.pending_state.hitl_decision = hitl_decision
            seg.pending_state.is_resume = True
            seg.pending_state.segment_id = segment_id

            final_state = await self.life_cycle.run(seg.pending_state)
            seg.pending_state = None

        # -------------------------------------------------
        # FRESH USER REQUEST
        # -------------------------------------------------
        elif user_request is not None:
            state = StateSchema(
                user_request=user_request,
                segment_id=segment_id
            )
            final_state = await self.life_cycle.run(state)

        else:
            raise RuntimeError("Either user_request or hitl_decision must be provided")

        exec_result = final_state.exec_result

        # -------------------------------------------------
        # WAITING HITL
        # -------------------------------------------------
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

        # -------------------------------------------------
        # DONE
        # -------------------------------------------------
        if exec_result.state == ExecutionState.DONE:
            seg.status = ConversationStatus.DONE

            agent_response = None

            review = getattr(final_state, "post_execution_review", None)

            # 1️⃣ Priority: friendly user response from critic
            print("Final State:", final_state)
            print("Review:", review)
            if review:
                critic = review.get("critic", {})
                agent_response = critic.get("user_response")
            elif not agent_response and exec_result.result is not None:
                agent_response = str(exec_result.result)
            # 3️⃣ Last fallback
            elif not agent_response:
                agent_response = "✅ Task completed successfully."

            seg.messages.append(Message("agent", agent_response))
            return seg

        # -------------------------------------------------
        # CANCELLED
        # -------------------------------------------------
        if exec_result.state == ExecutionState.CANCELLED:
            seg.status = ConversationStatus.DONE
            seg.messages.append(
                Message("agent", "❌ Action was cancelled by user.")
            )
            return seg

        # -------------------------------------------------
        # FAILED
        # -------------------------------------------------
        seg.status = ConversationStatus.FAILED
        seg.messages.append(
            Message("agent", str(exec_result.error))
        )
        return seg
