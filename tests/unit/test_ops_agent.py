"""OpsAgent dynamic mode: may read, must never write."""
import json
from unittest.mock import AsyncMock, Mock

import pytest

from src.agent.ops_agent import OpsAgent, WriteNotAllowedError
from src.business.store import OpsStore
from src.tools.base_tool import BaseTool
from src.tools.group import business_ops

BaseTool.auto_discover("src.tools.group")


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "ops.db"
    monkeypatch.setenv("OPS_DB_PATH", str(path))
    business_ops.CALL_LOG.clear()
    return OpsStore(db_path=path)


def make_agent(llm_reply: str) -> OpsAgent:
    chat = Mock()
    chat.ainvoke = AsyncMock(return_value=Mock(content=llm_reply))
    client = Mock()
    client._create_client = Mock(return_value=chat)
    agent = OpsAgent(llm=client)
    agent.register_tool(BaseTool.get_tools_by_group("business"))
    return agent


@pytest.mark.asyncio
async def test_reads_with_tool_chosen_by_llm(db):
    agent = make_agent(json.dumps({"tool": "get_order", "params": {"order_id": "ORD-1005"}}))
    out = await agent.invoke(query="When will ORD-1005 arrive?", params={})
    assert out["result"]["shipment"]["expected_delivery"] == "2026-11-17"
    assert business_ops.CALL_LOG == [{"tool": "get_order", "params": {"order_id": "ORD-1005"}}]


@pytest.mark.asyncio
async def test_answer_without_tool(db):
    agent = make_agent('```json\n{"tool": null, "result": "3 SKUs are low"}\n```')
    out = await agent.invoke(query="Summarize", params={"low": ["a", "b", "c"]})
    assert out == {"success": True, "result": "3 SKUs are low"}


@pytest.mark.asyncio
@pytest.mark.parametrize("tool,params", [
    ("issue_refund", {"order_id": "ORD-1011", "amount": 1000, "reason": "x"}),
    ("update_order_status", {"order_id": "ORD-1007", "new_status": "shipped"}),
    ("create_purchase_order", {"sku": "SKU-TEE-BLK", "quantity": 10}),
])
async def test_write_tools_blocked_in_dynamic_mode(db, tool, params):
    agent = make_agent(json.dumps({"tool": tool, "params": params}))
    with pytest.raises(WriteNotAllowedError):
        await agent.invoke(query="do it", params={})
    assert db.audit_log() == []
    assert business_ops.CALL_LOG == []  # the tool function was never called


@pytest.mark.asyncio
@pytest.mark.parametrize("reply", [
    '{"tool": "delete_everything", "params": {}}',
    '{"tool": "get_order", "params": {"order": "ORD-1"}}',
    "I think the order is late.",
])
async def test_bad_llm_output_rejected(db, reply):
    agent = make_agent(reply)
    with pytest.raises(ValueError):
        await agent.invoke(query="x", params={})
