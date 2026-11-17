"""
SQLite store for a small demo business: orders, customers, inventory,
purchase orders and refunds.

Design notes
- Every write runs in one transaction and appends a row to `audit_log`,
  so evaluations (and humans) can see exactly what the agent changed.
- Business rules live HERE, not in prompts. Even if the LLM produces a
  bad plan and a human approves it by mistake, the store still refuses
  invalid actions (illegal status change, over-refund, huge PO, ...).
- "Today" is fixed by the seed (`meta.as_of`) or the OPS_TODAY env var,
  so results are reproducible.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SEED_PATH = REPO_ROOT / "data" / "ops_seed.json"
DEFAULT_DB_PATH = REPO_ROOT / "data" / "ops.db"

ORDER_STATUSES = (
    "pending_payment", "paid", "packed", "on_hold",
    "shipped", "delivered", "cancelled", "refunded",
)

# Allowed manual status changes. "refunded" is only reached through issue_refund.
ORDER_TRANSITIONS: dict[str, set[str]] = {
    "pending_payment": {"paid", "cancelled"},
    "paid": {"packed", "on_hold", "cancelled"},
    "packed": {"shipped", "on_hold", "cancelled"},
    "on_hold": {"packed", "cancelled"},
    "shipped": {"delivered"},
    "delivered": set(),
    "cancelled": set(),
    "refunded": set(),
}

REFUNDABLE_STATUSES = {"paid", "packed", "on_hold", "shipped", "delivered", "cancelled"}
DEFAULT_TRANSIT_DAYS = 3

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS suppliers (
    supplier_id TEXT PRIMARY KEY, name TEXT NOT NULL,
    lead_time_days INTEGER NOT NULL, email TEXT
);
CREATE TABLE IF NOT EXISTS products (
    sku TEXT PRIMARY KEY, name TEXT NOT NULL,
    on_hand INTEGER NOT NULL, reserved INTEGER NOT NULL,
    reorder_point INTEGER NOT NULL, reorder_qty INTEGER NOT NULL,
    unit_cost INTEGER NOT NULL, price INTEGER NOT NULL,
    supplier_id TEXT REFERENCES suppliers(supplier_id)
);
CREATE TABLE IF NOT EXISTS customers (
    customer_id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT, tier TEXT
);
CREATE TABLE IF NOT EXISTS orders (
    order_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(customer_id),
    status TEXT NOT NULL, created_at TEXT NOT NULL,
    paid_amount INTEGER NOT NULL, refunded_amount INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS order_items (
    order_id TEXT NOT NULL REFERENCES orders(order_id),
    sku TEXT NOT NULL REFERENCES products(sku),
    qty INTEGER NOT NULL, unit_price INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS shipments (
    order_id TEXT PRIMARY KEY REFERENCES orders(order_id),
    carrier TEXT, tracking TEXT, shipped_at TEXT,
    expected_delivery TEXT, delivered_at TEXT
);
CREATE TABLE IF NOT EXISTS purchase_orders (
    po_id TEXT PRIMARY KEY, sku TEXT NOT NULL, supplier_id TEXT NOT NULL,
    quantity INTEGER NOT NULL, unit_cost INTEGER NOT NULL, total_cost INTEGER NOT NULL,
    status TEXT NOT NULL, expected_arrival TEXT, created_at TEXT NOT NULL, note TEXT
);
CREATE TABLE IF NOT EXISTS refunds (
    refund_id TEXT PRIMARY KEY, order_id TEXT NOT NULL,
    amount INTEGER NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS order_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, order_id TEXT NOT NULL,
    from_status TEXT, to_status TEXT, note TEXT, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT NOT NULL,
    action TEXT NOT NULL, args_json TEXT NOT NULL, result_json TEXT NOT NULL
);
"""


class BusinessRuleError(Exception):
    """An action was refused by a business rule. Not retried by the executor."""


class NotFoundError(BusinessRuleError):
    """The referenced order / customer / product does not exist."""


def _to_int(value: Any, field: str) -> int:
    """Accept 200000, 200000.0, "200000", "200,000", "200.000 VND"; refuse anything ambiguous."""
    if isinstance(value, bool):
        raise BusinessRuleError(f"'{field}' must be a whole number")
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        s = value.strip()
        for suffix in ("VND", "vnd", "đ"):
            s = s.removesuffix(suffix).strip()
        if re.fullmatch(r"-?\d{1,3}([.,]\d{3})+", s):   # thousands separators: 200,000 / 200.000
            return int(re.sub(r"[.,]", "", s))
        if re.fullmatch(r"-?\d+(\.0+)?", s):             # 200000 / 200000.0
            return int(float(s))
    raise BusinessRuleError(f"'{field}' must be a whole number, got {value!r}")


class OpsStore:
    def __init__(self, db_path: str | os.PathLike | None = None,
                 seed_path: str | os.PathLike | None = None):
        self.db_path = Path(db_path or os.getenv("OPS_DB_PATH") or DEFAULT_DB_PATH)
        self.seed_path = Path(seed_path or os.getenv("OPS_SEED_PATH") or DEFAULT_SEED_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_ready()

    # ------------------------------------------------------------------
    # setup
    # ------------------------------------------------------------------
    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _ensure_ready(self) -> None:
        with self._conn() as c:
            c.executescript(SCHEMA)
            seeded = c.execute("SELECT value FROM meta WHERE key='seeded'").fetchone()
        if not seeded:
            self._load_seed()

    def reset(self) -> None:
        """Drop all data and reload the seed. Used by tests and the eval runner."""
        with self._conn() as c:
            tables = [r["name"] for r in c.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            c.execute("PRAGMA foreign_keys = OFF")
            for t in tables:
                c.execute(f"DROP TABLE {t}")
        self._ensure_ready()

    def _load_seed(self) -> None:
        seed = json.loads(self.seed_path.read_text(encoding="utf-8"))
        with self._conn() as c:
            for k, v in seed["meta"].items():
                c.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (k, json.dumps(v)))
            for s in seed["suppliers"]:
                c.execute("INSERT INTO suppliers VALUES (:supplier_id, :name, :lead_time_days, :email)", s)
            for p in seed["products"]:
                c.execute("""INSERT INTO products VALUES (:sku, :name, :on_hand, :reserved,
                             :reorder_point, :reorder_qty, :unit_cost, :price, :supplier_id)""", p)
            for cu in seed["customers"]:
                c.execute("INSERT INTO customers VALUES (:customer_id, :name, :email, :tier)", cu)
            for o in seed["orders"]:
                c.execute("""INSERT INTO orders VALUES (:order_id, :customer_id, :status,
                             :created_at, :paid_amount, :refunded_amount)""", o)
                for it in o["items"]:
                    c.execute("INSERT INTO order_items VALUES (?, ?, ?, ?)",
                              (o["order_id"], it["sku"], it["qty"], it["unit_price"]))
                if o.get("shipment"):
                    sh = o["shipment"]
                    c.execute("INSERT INTO shipments VALUES (?, ?, ?, ?, ?, ?)",
                              (o["order_id"], sh["carrier"], sh["tracking"], sh["shipped_at"],
                               sh["expected_delivery"], sh["delivered_at"]))
            c.execute("INSERT OR REPLACE INTO meta VALUES ('seeded', 'true')")

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _meta(self, key: str, default: Any = None) -> Any:
        with self._conn() as c:
            row = c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return json.loads(row["value"]) if row else default

    def today(self) -> date:
        raw = os.getenv("OPS_TODAY") or self._meta("as_of")
        return date.fromisoformat(raw) if raw else date.today()

    @property
    def currency(self) -> str:
        return self._meta("currency", "VND")

    @staticmethod
    def _days_between(a: str, b: date) -> int:
        return (b - date.fromisoformat(a)).days

    def _audit(self, c: sqlite3.Connection, action: str, args: dict, result: dict) -> None:
        c.execute("INSERT INTO audit_log (ts, action, args_json, result_json) VALUES (?, ?, ?, ?)",
                  (datetime.now().isoformat(timespec="seconds"), action,
                   json.dumps(args, ensure_ascii=False), json.dumps(result, ensure_ascii=False)))

    def _next_id(self, c: sqlite3.Connection, table: str, column: str, prefix: str) -> str:
        n = c.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]
        return f"{prefix}-{n + 1:04d}"

    def _order_row(self, c: sqlite3.Connection, order_id: str) -> sqlite3.Row:
        row = c.execute("SELECT * FROM orders WHERE order_id=?", (str(order_id).strip().upper(),)).fetchone()
        if row is None:
            raise NotFoundError(f"Order '{order_id}' does not exist")
        return row

    def _product_row(self, c: sqlite3.Connection, sku: str) -> sqlite3.Row:
        row = c.execute("SELECT * FROM products WHERE sku=?", (str(sku).strip().upper(),)).fetchone()
        if row is None:
            raise NotFoundError(f"Product '{sku}' does not exist")
        return row

    # ------------------------------------------------------------------
    # READS
    # ------------------------------------------------------------------
    def get_order(self, order_id: str) -> dict:
        with self._conn() as c:
            o = self._order_row(c, order_id)
            items = [dict(r) for r in c.execute(
                """SELECT i.sku, p.name, i.qty, i.unit_price, i.qty * i.unit_price AS line_total
                   FROM order_items i JOIN products p USING (sku) WHERE order_id=?""", (o["order_id"],))]
            cust = c.execute("SELECT customer_id, name, tier FROM customers WHERE customer_id=?",
                             (o["customer_id"],)).fetchone()
            sh = c.execute("SELECT carrier, tracking, shipped_at, expected_delivery, delivered_at "
                           "FROM shipments WHERE order_id=?", (o["order_id"],)).fetchone()
        return {
            "order_id": o["order_id"],
            "status": o["status"],
            "created_at": o["created_at"],
            "days_since_created": self._days_between(o["created_at"], self.today()),
            "customer": dict(cust) if cust else None,
            "items": items,
            "order_total": sum(i["line_total"] for i in items),
            "paid_amount": o["paid_amount"],
            "refunded_amount": o["refunded_amount"],
            "refundable_amount": max(0, o["paid_amount"] - o["refunded_amount"]),
            "shipment": dict(sh) if sh else None,
            "allowed_next_statuses": sorted(ORDER_TRANSITIONS.get(o["status"], set())),
            "currency": self.currency,
        }

    def list_orders(self, status: str | None = None, customer_id: str | None = None) -> list[dict]:
        sql, args = "SELECT * FROM orders WHERE 1=1", []
        if status:
            status = status.strip().lower()
            if status not in ORDER_STATUSES:
                raise BusinessRuleError(f"Unknown status '{status}'. Valid: {', '.join(ORDER_STATUSES)}")
            sql += " AND status=?"; args.append(status)
        if customer_id:
            sql += " AND customer_id=?"; args.append(customer_id.strip().upper())
        sql += " ORDER BY created_at, order_id"
        with self._conn() as c:
            rows = [dict(r) for r in c.execute(sql, args)]
        return [{k: r[k] for k in ("order_id", "customer_id", "status", "created_at", "paid_amount")}
                for r in rows]

    def get_customer(self, customer_id: str) -> dict:
        with self._conn() as c:
            cu = c.execute("SELECT * FROM customers WHERE customer_id=?",
                           (str(customer_id).strip().upper(),)).fetchone()
            if cu is None:
                raise NotFoundError(f"Customer '{customer_id}' does not exist")
            orders = [dict(r) for r in c.execute(
                "SELECT order_id, status, created_at, paid_amount, refunded_amount FROM orders "
                "WHERE customer_id=? ORDER BY created_at", (cu["customer_id"],))]
        return {
            **dict(cu),
            "orders": orders,
            "order_count": len(orders),
            "net_spend": sum(o["paid_amount"] - o["refunded_amount"] for o in orders),
            "currency": self.currency,
        }

    def check_stock(self, sku: str) -> dict:
        with self._conn() as c:
            p = self._product_row(c, sku)
            sup = c.execute("SELECT * FROM suppliers WHERE supplier_id=?", (p["supplier_id"],)).fetchone()
            open_pos = [dict(r) for r in c.execute(
                "SELECT po_id, quantity, status, expected_arrival FROM purchase_orders WHERE sku=?",
                (p["sku"],))]
        available = p["on_hand"] - p["reserved"]
        return {
            "sku": p["sku"], "name": p["name"],
            "on_hand": p["on_hand"], "reserved": p["reserved"], "available": available,
            "reorder_point": p["reorder_point"], "reorder_qty": p["reorder_qty"],
            "is_low": available <= p["reorder_point"],
            "supplier": dict(sup) if sup else None,
            "open_purchase_orders": open_pos,
        }

    def find_low_stock(self) -> list[dict]:
        with self._conn() as c:
            rows = [dict(r) for r in c.execute(
                """SELECT p.sku, p.name, p.on_hand, p.reserved, p.on_hand - p.reserved AS available,
                          p.reorder_point, p.reorder_qty, p.supplier_id, s.name AS supplier_name,
                          s.lead_time_days,
                          (SELECT COUNT(*) FROM purchase_orders po WHERE po.sku = p.sku) AS open_purchase_orders
                   FROM products p JOIN suppliers s USING (supplier_id)
                   WHERE p.on_hand - p.reserved <= p.reorder_point
                   ORDER BY available""")]
        return rows

    def find_delayed_orders(self) -> dict:
        today = self.today()
        sla = int(self._meta("fulfillment_sla_days", 3))
        with self._conn() as c:
            late = [dict(r) for r in c.execute(
                """SELECT o.order_id, o.customer_id, s.carrier, s.tracking, s.shipped_at, s.expected_delivery
                   FROM orders o JOIN shipments s USING (order_id)
                   WHERE o.status='shipped' AND s.delivered_at IS NULL AND s.expected_delivery < ?
                   ORDER BY s.expected_delivery""", (today.isoformat(),))]
            waiting = [dict(r) for r in c.execute(
                """SELECT order_id, customer_id, status, created_at FROM orders
                   WHERE status IN ('paid', 'packed', 'on_hold') ORDER BY created_at""")]
        for r in late:
            r["days_late"] = self._days_between(r["expected_delivery"], today)
        unshipped = []
        for r in waiting:
            r["days_waiting"] = self._days_between(r["created_at"], today)
            if r["days_waiting"] > sla:
                unshipped.append(r)
        return {
            "as_of": today.isoformat(),
            "fulfillment_sla_days": sla,
            "late_deliveries": late,
            "unshipped_past_sla": unshipped,
        }

    def operations_summary(self) -> dict:
        with self._conn() as c:
            counts = {r["status"]: r["n"] for r in c.execute(
                "SELECT status, COUNT(*) AS n FROM orders GROUP BY status")}
            net = c.execute("SELECT COALESCE(SUM(paid_amount - refunded_amount), 0) AS v FROM orders").fetchone()["v"]
            pos = c.execute("SELECT COUNT(*) AS n FROM purchase_orders").fetchone()["n"]
        delayed = self.find_delayed_orders()
        low = self.find_low_stock()
        return {
            "as_of": self.today().isoformat(),
            "orders_by_status": counts,
            "net_revenue": net,
            "currency": self.currency,
            "late_deliveries": [r["order_id"] for r in delayed["late_deliveries"]],
            "unshipped_past_sla": [r["order_id"] for r in delayed["unshipped_past_sla"]],
            "low_stock_skus": [r["sku"] for r in low],
            "purchase_orders": pos,
        }

    def audit_log(self) -> list[dict]:
        with self._conn() as c:
            rows = [dict(r) for r in c.execute("SELECT * FROM audit_log ORDER BY id")]
        for r in rows:
            r["args"] = json.loads(r.pop("args_json"))
            r["result"] = json.loads(r.pop("result_json"))
        return rows

    # ------------------------------------------------------------------
    # WRITES (each one: validate -> change -> audit, in one transaction)
    # ------------------------------------------------------------------
    def update_order_status(self, order_id: str, new_status: str, note: str = "") -> dict:
        new_status = str(new_status).strip().lower()
        if new_status not in ORDER_STATUSES:
            raise BusinessRuleError(f"Unknown status '{new_status}'. Valid: {', '.join(ORDER_STATUSES)}")
        today = self.today().isoformat()
        with self._conn() as c:
            o = self._order_row(c, order_id)
            current = o["status"]
            allowed = ORDER_TRANSITIONS.get(current, set())
            if new_status not in allowed:
                hint = ", ".join(sorted(allowed)) or "none (final status)"
                raise BusinessRuleError(
                    f"Order {o['order_id']} is '{current}'; it cannot move to '{new_status}'. Allowed: {hint}")
            c.execute("UPDATE orders SET status=? WHERE order_id=?", (new_status, o["order_id"]))
            if new_status == "shipped":
                expected = (self.today() + timedelta(days=DEFAULT_TRANSIT_DAYS)).isoformat()
                c.execute("""INSERT INTO shipments (order_id, carrier, tracking, shipped_at, expected_delivery, delivered_at)
                             VALUES (?, NULL, NULL, ?, ?, NULL)
                             ON CONFLICT(order_id) DO UPDATE SET shipped_at=excluded.shipped_at,
                                                               expected_delivery=excluded.expected_delivery""",
                          (o["order_id"], today, expected))
            if new_status == "delivered":
                c.execute("UPDATE shipments SET delivered_at=? WHERE order_id=?", (today, o["order_id"]))
            c.execute("INSERT INTO order_events (order_id, from_status, to_status, note, created_at) VALUES (?, ?, ?, ?, ?)",
                      (o["order_id"], current, new_status, note, today))
            result = {"order_id": o["order_id"], "from_status": current, "to_status": new_status}
            if new_status == "cancelled" and o["paid_amount"] - o["refunded_amount"] > 0:
                result["warning"] = "Order was paid; issue a refund separately if needed."
            self._audit(c, "update_order_status",
                        {"order_id": o["order_id"], "new_status": new_status, "note": note}, result)
        return result

    def create_purchase_order(self, sku: str, quantity: Any, note: str = "") -> dict:
        qty = _to_int(quantity, "quantity")
        max_qty = int(self._meta("max_po_quantity", 1000))
        if qty <= 0:
            raise BusinessRuleError("quantity must be greater than 0")
        if qty > max_qty:
            raise BusinessRuleError(f"quantity {qty} is above the per-order limit of {max_qty}")
        with self._conn() as c:
            p = self._product_row(c, sku)
            sup = c.execute("SELECT * FROM suppliers WHERE supplier_id=?", (p["supplier_id"],)).fetchone()
            po_id = self._next_id(c, "purchase_orders", "po_id", "PO")
            arrival = (self.today() + timedelta(days=sup["lead_time_days"])).isoformat()
            total = qty * p["unit_cost"]
            c.execute("""INSERT INTO purchase_orders VALUES (?, ?, ?, ?, ?, ?, 'draft', ?, ?, ?)""",
                      (po_id, p["sku"], sup["supplier_id"], qty, p["unit_cost"], total,
                       arrival, self.today().isoformat(), note))
            result = {"po_id": po_id, "sku": p["sku"], "quantity": qty, "supplier": sup["name"],
                      "total_cost": total, "currency": self.currency, "status": "draft",
                      "expected_arrival": arrival}
            self._audit(c, "create_purchase_order", {"sku": p["sku"], "quantity": qty, "note": note}, result)
        return result

    def issue_refund(self, order_id: str, amount: Any, reason: str) -> dict:
        amt = _to_int(amount, "amount")
        if amt <= 0:
            raise BusinessRuleError("amount must be greater than 0")
        if not reason or not str(reason).strip():
            raise BusinessRuleError("a refund reason is required")
        with self._conn() as c:
            o = self._order_row(c, order_id)
            if o["status"] not in REFUNDABLE_STATUSES:
                raise BusinessRuleError(f"Order {o['order_id']} is '{o['status']}' and cannot be refunded")
            refundable = o["paid_amount"] - o["refunded_amount"]
            if refundable <= 0:
                raise BusinessRuleError(f"Order {o['order_id']} has nothing left to refund")
            if amt > refundable:
                raise BusinessRuleError(
                    f"amount {amt} is more than the refundable amount {refundable} for order {o['order_id']}")
            refund_id = self._next_id(c, "refunds", "refund_id", "RF")
            today = self.today().isoformat()
            c.execute("INSERT INTO refunds VALUES (?, ?, ?, ?, ?)", (refund_id, o["order_id"], amt, reason, today))
            new_refunded = o["refunded_amount"] + amt
            c.execute("UPDATE orders SET refunded_amount=? WHERE order_id=?", (new_refunded, o["order_id"]))
            new_status = o["status"]
            if new_refunded == o["paid_amount"]:
                new_status = "refunded"
                c.execute("UPDATE orders SET status='refunded' WHERE order_id=?", (o["order_id"],))
                c.execute("INSERT INTO order_events (order_id, from_status, to_status, note, created_at) "
                          "VALUES (?, ?, 'refunded', ?, ?)", (o["order_id"], o["status"], reason, today))
            result = {"refund_id": refund_id, "order_id": o["order_id"], "amount": amt,
                      "currency": self.currency, "total_refunded": new_refunded,
                      "remaining_refundable": o["paid_amount"] - new_refunded, "order_status": new_status}
            self._audit(c, "issue_refund", {"order_id": o["order_id"], "amount": amt, "reason": reason}, result)
        return result
