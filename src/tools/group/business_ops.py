"""
Business operations tools for OpsAgent (category: "business").

READ tools  : safe, the agent may call them on its own (static or dynamic steps).
WRITE tools : change business data. They are listed in WRITE_TOOLS and
              - are intercepted by HITLMiddleware (human must approve), and
              - are refused by OpsAgent in dynamic mode, so a write can only
                happen as an explicit, validated, approved SOP step.
Business rules (allowed status changes, refund limits, PO limits) are
enforced in src/business/store.py, not in prompts.
"""
from __future__ import annotations

from typing import Any, Optional

from src.business.store import OpsStore
from src.tools.base_tool import BaseTool

WRITE_TOOLS: tuple[str, ...] = ("update_order_status", "create_purchase_order", "issue_refund")
READ_TOOLS: tuple[str, ...] = (
    "get_operations_summary", "list_orders", "get_order", "get_customer",
    "check_stock", "find_low_stock", "find_delayed_orders",
)

# Every call is recorded here so tests and the eval runner can see which tools ran.
CALL_LOG: list[dict[str, Any]] = []


def _store() -> OpsStore:
    # New instance per call so OPS_DB_PATH changes (tests / eval) take effect immediately.
    return OpsStore()


def _record(tool: str, **params: Any) -> None:
    CALL_LOG.append({"tool": tool, "params": params})


class BusinessOps(BaseTool):

    # ------------------------------------------------------------------
    # READ
    # ------------------------------------------------------------------
    @BaseTool.register_tool(category="business", description=(
        "[READ] Snapshot of operations today: order counts by status, net revenue, "
        "late deliveries, orders past the fulfillment SLA and low-stock SKUs."))
    @staticmethod
    def get_operations_summary() -> dict:
        _record("get_operations_summary")
        return _store().operations_summary()

    @BaseTool.register_tool(category="business", description=(
        "[READ] List orders, optionally filtered by status (pending_payment, paid, packed, "
        "on_hold, shipped, delivered, cancelled, refunded) and/or customer_id (e.g. CUS-002)."))
    @staticmethod
    def list_orders(status: Optional[str] = None, customer_id: Optional[str] = None) -> dict:
        _record("list_orders", status=status, customer_id=customer_id)
        orders = _store().list_orders(status=status, customer_id=customer_id)
        return {"count": len(orders), "orders": orders}

    @BaseTool.register_tool(category="business", description=(
        "[READ] Full details of one order (e.g. ORD-1005): status, items, customer, payment, "
        "refundable amount, shipment / expected delivery and allowed next statuses."))
    @staticmethod
    def get_order(order_id: str) -> dict:
        _record("get_order", order_id=order_id)
        return _store().get_order(order_id)

    @BaseTool.register_tool(category="business", description=(
        "[READ] Customer profile (e.g. CUS-002) with tier, all their orders and net spend."))
    @staticmethod
    def get_customer(customer_id: str) -> dict:
        _record("get_customer", customer_id=customer_id)
        return _store().get_customer(customer_id)

    @BaseTool.register_tool(category="business", description=(
        "[READ] Stock level of one SKU (e.g. SKU-TEE-BLK): on hand, reserved, available, "
        "reorder point / quantity, supplier and existing purchase orders."))
    @staticmethod
    def check_stock(sku: str) -> dict:
        _record("check_stock", sku=sku)
        return _store().check_stock(sku)

    @BaseTool.register_tool(category="business", description=(
        "[READ] All SKUs whose available stock is at or below the reorder point, "
        "with suggested reorder quantity and supplier."))
    @staticmethod
    def find_low_stock() -> dict:
        _record("find_low_stock")
        items = _store().find_low_stock()
        return {"count": len(items), "items": items, "skus": [i["sku"] for i in items]}

    @BaseTool.register_tool(category="business", description=(
        "[READ] Delayed orders: shipped orders past their expected delivery date, and paid/packed "
        "orders not shipped within the fulfillment SLA."))
    @staticmethod
    def find_delayed_orders() -> dict:
        _record("find_delayed_orders")
        data = _store().find_delayed_orders()
        data["order_ids"] = ([r["order_id"] for r in data["late_deliveries"]]
                             + [r["order_id"] for r in data["unshipped_past_sla"]])
        return data

    # ------------------------------------------------------------------
    # WRITE  (human approval required; static SOP steps only)
    # ------------------------------------------------------------------
    @BaseTool.register_tool(category="business", description=(
        "[WRITE - needs human approval, use only in a static step] Change an order's status "
        "(e.g. packed -> shipped). Illegal changes are refused."))
    @staticmethod
    def update_order_status(order_id: str, new_status: str, note: str = "") -> dict:
        _record("update_order_status", order_id=order_id, new_status=new_status, note=note)
        return _store().update_order_status(order_id, new_status, note)

    @BaseTool.register_tool(category="business", description=(
        "[WRITE - needs human approval, use only in a static step] Create a DRAFT purchase order "
        "to restock a SKU from its supplier. quantity must be 1..1000."))
    @staticmethod
    def create_purchase_order(sku: str, quantity: int, note: str = "") -> dict:
        _record("create_purchase_order", sku=sku, quantity=quantity, note=note)
        return _store().create_purchase_order(sku, quantity, note)

    @BaseTool.register_tool(category="business", description=(
        "[WRITE - needs human approval, use only in a static step] Refund part or all of a paid "
        "order. amount in VND, cannot exceed the refundable amount; reason is required."))
    @staticmethod
    def issue_refund(order_id: str, amount: int, reason: str) -> dict:
        _record("issue_refund", order_id=order_id, amount=amount, reason=reason)
        return _store().issue_refund(order_id, amount, reason)
