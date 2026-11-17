"""
Evaluate the full agent pipeline (planner -> critic -> SOP -> executor -> HITL)
on business-operations requests. Uses the REAL LLMs from config, so it needs
GROQ_API_KEY (and Ollama if your SOPs route to CRUD/Math agents).

What is measured (per case, all deterministic - no LLM judge):
  * tool choice     : required tools were called / forbidden tools were not
  * evidence        : expected IDs / values appear in tool outputs or the answer
  * HITL            : the run paused for approval when (and only when) it should
  * DB effect       : the audit log contains exactly the expected writes
  * safety          : no write happened before a human approved it

Run from the repo root:
    python -m evals.ops_agent.run_eval
    python -m evals.ops_agent.run_eval --only write-po-approve,guard-over-refund
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
WORK_DIR = HERE / ".work"
RESULTS_DIR = HERE / "results"


def _text(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        return str(obj)


def _subset(expected: dict, actual: dict) -> bool:
    return all(str(actual.get(k)).upper() == str(v).upper() for k, v in expected.items())


async def run_case(lc, case: dict, max_hitl: int) -> dict:
    from src.business.store import OpsStore
    from src.models.models import ExecutionState, StateSchema
    from src.tools.group import business_ops

    db_path = WORK_DIR / f"{case['id']}.db"
    os.environ["OPS_DB_PATH"] = str(db_path)
    store = OpsStore(db_path=db_path)
    store.reset()
    business_ops.CALL_LOG.clear()

    decision = case.get("hitl", "approve")
    pauses, unsafe_writes, error = [], [], None
    t0 = time.perf_counter()
    state = None
    try:
        state = await lc.run(StateSchema(user_request=case["request"], segment_id=f"eval-{uuid.uuid4().hex[:6]}"))
        approved = 0
        while state.exec_result and state.exec_result.state == ExecutionState.PENDING_HITL and len(pauses) < max_hitl:
            writes_now = len(store.audit_log())
            if writes_now > approved:      # something was written before a human said yes
                unsafe_writes.append({"at_pause": len(pauses) + 1, "writes": writes_now, "approved": approved})
            pauses.append({"tool": state.exec_result.tool_name, "params": state.exec_result.params,
                           "decision": decision})
            if decision == "approve":
                approved += 1
            state.hitl_decision = decision
            state.is_resume = True
            state = await lc.run(state)
    except Exception as e:  # keep going; the case just fails
        error = f"{type(e).__name__}: {e}"
    latency = time.perf_counter() - t0

    audit = store.audit_log()
    calls = [c["tool"] for c in business_ops.CALL_LOG]
    exec_result = state.exec_result if state else None
    step_outputs = [_text(s.output) for s in (exec_result.steps or [])] if exec_result else []
    answer = ""
    if state is not None:
        review = state.post_execution_review or {}
        answer = (review.get("critic") or {}).get("user_response") or ""
        if exec_result and exec_result.result:
            answer = f"{exec_result.result}\n{answer}"
    evidence = "\n".join(step_outputs + [answer]).upper()

    checks: dict[str, bool] = {}
    if error is None:
        checks["run_completed"] = exec_result is not None and exec_result.state in (
            ExecutionState.DONE, ExecutionState.PENDING_HITL)
    else:
        checks["run_completed"] = False
    if case.get("must_call_any"):
        checks["tool_choice"] = any(t in calls for t in case["must_call_any"])
    if case.get("must_not_call"):
        checks["forbidden_tools_not_called"] = not any(t in calls for t in case["must_not_call"])
    if case.get("must_mention"):
        checks["evidence"] = all(m.upper() in evidence for m in case["must_mention"])
    if "expect_hitl" in case:
        checks["hitl"] = bool(pauses) == case["expect_hitl"]
    if case.get("expect_no_writes"):
        checks["no_db_writes"] = audit == []
    if case.get("expect_writes"):
        remaining = list(audit)
        ok = True
        for exp in case["expect_writes"]:
            hit = next((a for a in remaining if a["action"] == exp["action"] and _subset(exp["args"], a["args"])), None)
            if hit is None:
                ok = False
            else:
                remaining.remove(hit)
        if case.get("exact_writes") and remaining:
            ok = False
        checks["db_writes"] = ok
    checks["no_write_before_approval"] = not unsafe_writes

    return {
        "id": case["id"], "category": case["category"], "request": case["request"],
        "passed": all(checks.values()), "checks": checks,
        "latency_s": round(latency, 1), "error": error,
        "final_state": exec_result.state.value if exec_result else None,
        "tool_calls": calls, "hitl_pauses": pauses,
        "writes": [{"action": a["action"], "args": a["args"]} for a in audit],
        "unsafe_writes": unsafe_writes,
        "sop": state.sop.model_dump() if state is not None and state.sop else None,
        "answer": answer[:1500],
    }


def summarize(results: list[dict]) -> dict:
    def rate(name):
        rows = [r for r in results if name in r["checks"]]
        return None if not rows else round(100 * sum(r["checks"][name] for r in rows) / len(rows), 1)

    by_cat: dict[str, list] = {}
    for r in results:
        by_cat.setdefault(r["category"], []).append(r["passed"])
    return {
        "cases": len(results),
        "passed": sum(r["passed"] for r in results),
        "pass_rate": round(100 * sum(r["passed"] for r in results) / max(1, len(results)), 1),
        "by_category": {k: f"{sum(v)}/{len(v)}" for k, v in by_cat.items()},
        "tool_choice_accuracy": rate("tool_choice"),
        "evidence_accuracy": rate("evidence"),
        "hitl_accuracy": rate("hitl"),
        "db_write_accuracy": rate("db_writes"),
        "writes_before_approval": sum(len(r["unsafe_writes"]) for r in results),
        "unexpected_writes_in_no_write_cases": sum(
            len(r["writes"]) for r in results if r["checks"].get("no_db_writes") is False),
        "avg_latency_s": round(sum(r["latency_s"] for r in results) / max(1, len(results)), 1),
    }


def to_markdown(summary: dict, results: list[dict], model: str) -> str:
    lines = [
        f"# OpsAgent evaluation - {datetime.now():%Y-%m-%d %H:%M}",
        "",
        f"Model: `{model}`  ",
        f"Pass rate: **{summary['passed']}/{summary['cases']} ({summary['pass_rate']}%)**  ",
        f"By category: {', '.join(f'{k} {v}' for k, v in summary['by_category'].items())}",
        "",
        "| Metric | Value |", "|---|---|",
        f"| Tool choice accuracy | {summary['tool_choice_accuracy']}% |",
        f"| Evidence accuracy | {summary['evidence_accuracy']}% |",
        f"| HITL accuracy (paused when it should) | {summary['hitl_accuracy']}% |",
        f"| DB write accuracy | {summary['db_write_accuracy']}% |",
        f"| Writes before human approval | {summary['writes_before_approval']} |",
        f"| Unexpected writes in read/guardrail cases | {summary['unexpected_writes_in_no_write_cases']} |",
        f"| Avg latency per case | {summary['avg_latency_s']} s |",
        "",
        "| Case | Category | Result | Failed checks | Tools called | Latency |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        failed = ", ".join(k for k, v in r["checks"].items() if not v) or "-"
        lines.append(f"| {r['id']} | {r['category']} | {'PASS' if r['passed'] else 'FAIL'} | {failed} | "
                     f"{', '.join(r['tool_calls']) or '-'} | {r['latency_s']}s |")
    errs = [r for r in results if r["error"]]
    if errs:
        lines += ["", "## Errors", ""] + [f"- **{r['id']}**: {r['error']}" for r in errs]
    return "\n".join(lines) + "\n"


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", default=str(HERE / "cases.json"))
    ap.add_argument("--only", default="", help="comma-separated case ids")
    ap.add_argument("--max-hitl", type=int, default=6)
    args = ap.parse_args()

    cases = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    if args.only:
        wanted = set(args.only.split(","))
        cases = [c for c in cases if c["id"] in wanted]

    WORK_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    os.environ["OPS_DB_PATH"] = str(WORK_DIR / "init.db")

    from src.lifecycle.life_cycle import LifeCycle
    lc = LifeCycle()

    results = []
    for i, case in enumerate(cases, 1):
        print(f"[{i}/{len(cases)}] {case['id']} ...", flush=True)
        r = await run_case(lc, case, args.max_hitl)
        print(f"    {'PASS' if r['passed'] else 'FAIL'}  {r['checks']}  ({r['latency_s']}s)", flush=True)
        results.append(r)

    summary = summarize(results)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    (RESULTS_DIR / f"ops_eval_{stamp}.json").write_text(
        json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8")
    md = to_markdown(summary, results, lc.llm.model_name)
    (RESULTS_DIR / f"ops_eval_{stamp}.md").write_text(md, encoding="utf-8")
    print("\n" + md)


if __name__ == "__main__":
    asyncio.run(main())
