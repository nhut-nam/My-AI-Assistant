from typing import Dict, Any
from src.utils.logger import LoggerMixin


class ExecutionScore(LoggerMixin):

    SEVERITY_WEIGHT = {
        "critical": 10,
        "high": 7,
        "medium": 5,
        "low": 2,
        "none": 0
    }

    def __init__(self):
        super().__init__("ExecutionScore")

    def score(self, summary: Dict[str, Any]) -> Dict[str, Any]:

        step_reviews = summary["step_reviews"]

        per_step_scores = []
        total_score = 0
        max_score = len(step_reviews) * 10

        for review in step_reviews:
            step_score = self._score_step(review)
            per_step_scores.append(step_score)
            total_score += step_score["score"]

        return {
            "total_score": total_score,
            "max_score": max_score,
            "grade": self._grade(total_score, max_score),
            "per_step": per_step_scores,
        }

    # --------------------------------------------------

    def _score_step(self, review: Dict[str, Any]) -> Dict[str, Any]:

        base = 10
        severity = review["analysis"]["impact_assessment"]["severity"]

        deduction = self.SEVERITY_WEIGHT.get(severity, 0)
        score = max(base - deduction, 0)

        return {
            "step_number": review["step_number"],
            "score": score,
            "max_score": 10,
            "severity": severity,
            "issues": review["analysis"]["deviation"],
        }

    # --------------------------------------------------

    def _grade(self, total: int, max_score: int) -> str:
        ratio = total / max_score if max_score else 0

        if ratio >= 0.9:
            return "EXCELLENT"
        if ratio >= 0.7:
            return "PASS"
        if ratio >= 0.5:
            return "WEAK"
        return "FAIL"
