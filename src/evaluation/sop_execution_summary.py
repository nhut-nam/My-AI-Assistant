from typing import Dict, Any
from src.utils.logger import LoggerMixin


class SOPExecutionSummary(LoggerMixin):
    """
    Behavior-aware execution summary.
    Designed for policy learning + LLM meta critique.
    """

    def __init__(self):
        super().__init__("SOPExecutionSummary")

    def build(self, *, sop: Dict[str, Any], execution_result: Any) -> Dict[str, Any]:

        sop_steps = sop.get("steps", [])
        exec_steps = execution_result.steps or []

        step_summaries = []

        for sop_step in sop_steps:
            exec_step = self._find_exec_step(exec_steps, sop_step["step_number"])
            step_summaries.append(
                self._summarize_step(sop_step, exec_step)
            )

        summary = {
            "final_state": execution_result.state.value,
            "final_target": sop.get("final_target"),
            "step_reviews": step_summaries,
        }

        return summary

    # --------------------------------------------------

    def _find_exec_step(self, exec_steps, step_number):
        for s in exec_steps:
            if (s.meta or {}).get("step_number") == step_number:
                return s
        return None

    # --------------------------------------------------

    def _summarize_step(self, sop_step: Dict[str, Any], exec_step):

        question = {
            "description": sop_step["description"],
            "agent_type": sop_step["agent_type"],
            "execution_mode": sop_step["execution_mode"],
            "expected_tool": (
                sop_step["action_type"]["tool"]
                if sop_step["action_type"]
                else None
            ),
            "retry_limit": sop_step["retry"],
            "store_result_as": sop_step.get("store_result_as"),
        }

        if exec_step is None:
            return {
                "step_number": sop_step["step_number"],
                "question": question,
                "answer": None,
                "analysis": {
                    "step_status": "NOT_EXECUTED",
                    "reasoning": ["Step defined but never executed."],
                    "deviation": ["STEP_NOT_EXECUTED"],
                    "execution_trace": None,
                    "behavioral_interpretation": {
                        "intent_alignment": "unknown",
                        "tool_selection_quality": "unknown",
                        "execution_stability": "unknown",
                    },
                    "impact_assessment": {
                        "affects_final_target": True,
                        "severity": "critical",
                    }
                }
            }

        meta = exec_step.meta or {}

        answer = {
            "used_tool": meta.get("tool_name"),
            "success": exec_step.success,
            "retry": meta.get("retry_count", 0),
            "hitl": meta.get("hitl", False),
            "error": exec_step.error,
        }

        issues = []
        reasoning_notes = []

        if question["expected_tool"] and answer["used_tool"] != question["expected_tool"]:
            issues.append("WRONG_TOOL_USED")
            reasoning_notes.append(
                f"Expected tool '{question['expected_tool']}' but used '{answer['used_tool']}'"
            )

        if answer["retry"] > question["retry_limit"]:
            issues.append("RETRY_LIMIT_EXCEEDED")
            reasoning_notes.append(
                f"Retry {answer['retry']} exceeds limit {question['retry_limit']}"
            )

        if not answer["success"]:
            issues.append("STEP_FAILED")
            reasoning_notes.append("Step execution failed.")

        step_status = "CORRECT" if not issues else "INCORRECT"

        behavioral = {
            "intent_alignment": "aligned" if "WRONG_TOOL_USED" not in issues else "misaligned",
            "tool_selection_quality": "correct" if "WRONG_TOOL_USED" not in issues else "incorrect",
            "execution_stability": (
                "stable"
                if answer["retry"] <= question["retry_limit"]
                else "excessive_retry"
            ),
        }

        impact = {
            "affects_final_target": True if issues else False,
            "severity": self._map_severity(issues)
        }

        return {
            "step_number": sop_step["step_number"],
            "question": question,
            "answer": answer,
            "analysis": {
                "step_status": step_status,
                "reasoning": reasoning_notes,
                "deviation": issues,
                "execution_trace": {
                    "params_used": meta.get("params"),
                    "output_preview": str(exec_step.output)[:200] if hasattr(exec_step, "output") else None,
                    "error": exec_step.error,
                },
                "behavioral_interpretation": behavioral,
                "impact_assessment": impact,
            }
        }

    # --------------------------------------------------

    def _map_severity(self, issues):
        if "STEP_NOT_EXECUTED" in issues:
            return "critical"
        if "STEP_FAILED" in issues:
            return "high"
        if "WRONG_TOOL_USED" in issues:
            return "medium"
        if "RETRY_LIMIT_EXCEEDED" in issues:
            return "low"
        return "none"
