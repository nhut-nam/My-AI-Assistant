"""Business rules of the demo store. No LLM involved."""
import pytest

from src.business.store import BusinessRuleError, NotFoundError, OpsStore


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.delenv("OPS_TODAY", raising=False)
    return OpsStore(db_path=tmp_path / "ops.db")


def test_seed_loaded_and_today_fixed(store):
    assert store.today().isoformat() == "2026-11-15"
    assert store.get_order("ORD-1005")["status"] == "shipped"


def test_low_stock_uses_available_not_on_hand(store):
    skus = {r["sku"] for r in store.find_low_stock()}
    assert skus == {"SKU-TEE-BLK", "SKU-HOOD-GRY", "SKU-SOCK-3P"}
    assert "SKU-JEAN-32" not in skus  # available 22 > reorder point 20


def test_delayed_orders(store):
    d = store.find_delayed_orders()
    assert {r["order_id"] for r in d["late_deliveries"]} == {"ORD-1002", "ORD-1009"}
    assert {r["order_id"] for r in d["unshipped_past_sla"]} == {"ORD-1003"}


def test_valid_status_change_is_audited(store):
    r = store.update_order_status("ORD-1007", "shipped", note="handed to GHN")
    assert r == {"order_id": "ORD-1007", "from_status": "packed", "to_status": "shipped"}
    assert store.get_order("ORD-1007")["shipment"]["shipped_at"] == "2026-11-15"
    log = store.audit_log()
    assert [e["action"] for e in log] == ["update_order_status"]


@pytest.mark.parametrize("order_id,new_status", [
    ("ORD-1008", "shipped"),     # cancelled is final
    ("ORD-1004", "shipped"),     # cannot skip payment
    ("ORD-1001", "cancelled"),   # delivered is final
    ("ORD-1007", "teleported"),  # unknown status
])
def test_illegal_status_change_refused_and_not_written(store, order_id, new_status):
    before = store.get_order(order_id)["status"]
    with pytest.raises(BusinessRuleError):
        store.update_order_status(order_id, new_status)
    assert store.get_order(order_id)["status"] == before
    assert store.audit_log() == []


def test_unknown_order(store):
    with pytest.raises(NotFoundError):
        store.get_order("ORD-9999")


def test_refund_partial_then_full(store):
    r1 = store.issue_refund("ORD-1011", "200,000", "item damaged")
    assert r1["amount"] == 200000 and r1["remaining_refundable"] == 299000
    assert store.get_order("ORD-1011")["status"] == "delivered"
    r2 = store.issue_refund("ORD-1011", 299000, "customer returned item")
    assert r2["order_status"] == "refunded"
    assert len(store.audit_log()) == 2


@pytest.mark.parametrize("order_id,amount,reason", [
    ("ORD-1001", 99_000_000, "too much"),   # more than paid
    ("ORD-1004", 1000, "unpaid order"),      # pending_payment
    ("ORD-1012", 1000, "already refunded"),  # nothing left
    ("ORD-1011", 0, "zero"),
    ("ORD-1011", 1000, "   "),               # reason required
])
def test_refund_guardrails(store, order_id, amount, reason):
    with pytest.raises(BusinessRuleError):
        store.issue_refund(order_id, amount, reason)
    assert store.audit_log() == []


def test_purchase_order_and_limits(store):
    po = store.create_purchase_order("sku-tee-blk", 100)
    assert po["sku"] == "SKU-TEE-BLK" and po["status"] == "draft"
    assert po["total_cost"] == 100 * 60000
    assert po["expected_arrival"] == "2026-11-22"   # supplier lead time 7 days
    for bad in (0, -5, 5000, "lots"):
        with pytest.raises(BusinessRuleError):
            store.create_purchase_order("SKU-TEE-BLK", bad)
    assert len(store.audit_log()) == 1


def test_reset_restores_seed(store):
    store.update_order_status("ORD-1007", "shipped")
    store.reset()
    assert store.get_order("ORD-1007")["status"] == "packed"
    assert store.audit_log() == []
