"""
Full LifeCycle graph (planner -> critic -> SOP -> executor -> HITL -> resume)
with the LLM parts replaced by fixed outputs. Executor, HITL middleware,
OpsAgent tools and the SQLite store are real.
"""
from unittest.mock import AsyncMock, Mock

import pytest

from src.business.store import OpsStore
from src.models.models import SOP, CriticFeedback, ExecutionState, Plan, StateSchema
from src.tools.group import business_ops


def step(n, tool, params, store_as=None):
    return {
        "step_number": n, "description": f"run {tool}", "agent_type": "OpsAgent",
        "execution_mode": "static", "action_type": {"agent": "OpsAgent", "tool": tool},
        "params": params, "conditions": [], "retry": 0,
        "store_result_as": store_as, "condition_to_jump_step": None,
    }


@pytest.fixture
def lifecycle(tmp_path, monkeypatch):
    monkeypatch.setenv("OPS_DB_PATH", str(tmp_path / "ops.db"))
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.chdir(tmp_path)  # logs / sandbox folders go to tmp
    from src.lifecycle.life_cycle import LifeCycle
    lc = LifeCycle()
    lc.planner.invoke = AsyncMock(return_value=Plan(steps=["look up", "act"]))
    lc.critic.invoke = AsyncMock(return_value={"feedback": CriticFeedback(score=100, issues=[], summary="pass")})
    lc.llm_prompt_critic.critique = Mock(return_value={})
    lc.llm_prompt_critic.apply_policy_if_needed = Mock()
    business_ops.CALL_LOG.clear()
    return lc


def use_sop(lc, steps):
    lc.dispatcher.build_sop = AsyncMock(return_value=SOP(steps=steps, final_target="done"))


async def resume(lc, state, decision):
    state.hitl_decision = decision
    state.is_resume = True
    return await lc.run(state)


def calls(tool):
    return [c for c in business_ops.CALL_LOG if c["tool"] == tool]


@pytest.mark.asyncio
async def test_write_pauses_then_runs_once_after_approve(lifecycle):
    use_sop(lifecycle, [
        step(1, "get_order", {"order_id": "ORD-1007"}, "order"),
        step(2, "update_order_status", {"order_id": "ORD-1007", "new_status": "shipped"}),
    ])
    state = await lifecycle.run(StateSchema(user_request="ship ORD-1007"))

    assert state.exec_result.state == ExecutionState.PENDING_HITL
    assert state.exec_result.tool_name == "update_order_status"
    assert OpsStore().get_order("ORD-1007")["status"] == "packed"   # nothing written yet

    state = await resume(lifecycle, state, "approve")

    assert state.exec_result.state == ExecutionState.DONE
    assert OpsStore().get_order("ORD-1007")["status"] == "shipped"
    assert len(calls("get_order")) == 1             # read step not re-run on resume
    assert len(OpsStore().audit_log()) == 1


@pytest.mark.asyncio
async def test_reject_means_no_write(lifecycle):
    use_sop(lifecycle, [step(1, "issue_refund", {"order_id": "ORD-1011", "amount": 200000, "reason": "damaged"})])
    state = await lifecycle.run(StateSchema(user_request="refund"))
    assert state.exec_result.state == ExecutionState.PENDING_HITL

    state = await resume(lifecycle, state, "reject")

    assert state.exec_result.state == ExecutionState.DONE
    assert calls("issue_refund") == []
    assert OpsStore().audit_log() == []


@pytest.mark.asyncio
async def test_approve_then_reject_does_not_repeat_first_write(lifecycle):
    use_sop(lifecycle, [
        step(1, "create_purchase_order", {"sku": "SKU-TEE-BLK", "quantity": 100}),
        step(2, "create_purchase_order", {"sku": "SKU-SOCK-3P", "quantity": 200}),
    ])
    state = await lifecycle.run(StateSchema(user_request="restock"))
    state = await resume(lifecycle, state, "approve")          # step 1 runs, step 2 pauses
    assert state.exec_result.state == ExecutionState.PENDING_HITL
    state = await resume(lifecycle, state, "reject")           # step 2 skipped

    assert state.exec_result.state == ExecutionState.DONE
    log = OpsStore().audit_log()
    assert [(e["action"], e["args"]["sku"]) for e in log] == [("create_purchase_order", "SKU-TEE-BLK")]


@pytest.mark.asyncio
async def test_approved_but_illegal_action_still_refused(lifecycle):
    use_sop(lifecycle, [step(1, "update_order_status", {"order_id": "ORD-1008", "new_status": "shipped"})])
    state = await lifecycle.run(StateSchema(user_request="ship cancelled order"))
    state = await resume(lifecycle, state, "approve")

    assert state.exec_result.steps[-1].success is False
    assert "cannot move" in state.exec_result.steps[-1].error
    assert OpsStore().get_order("ORD-1008")["status"] == "cancelled"
    assert OpsStore().audit_log() == []
