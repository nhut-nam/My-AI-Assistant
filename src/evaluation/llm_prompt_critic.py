from typing import Dict, Any
from src.utils.logger import LoggerMixin
from src.utils.helper import edit_yaml
from src.constants.config_path import POLICY_PATH
from src.prompt_engineering.templates import POLICY_PROMPT


class LLMPromptCritic(LoggerMixin):
    """
    Meta-level execution reviewer.

    Produces:
    - developer_analysis (technical explanation)
    - user_response (friendly assistant reply)

    Also:
    - Diagnoses failure type
    - Detects systemic weakness
    - Decides whether policy refinement is required
    - NEVER overrides rule-based score
    """

    def __init__(self, llm):
        super().__init__("LLMPromptCritic")
        self.llm = llm

    # ======================================================
    # MAIN ENTRY
    # ======================================================

    def critique(
        self,
        *,
        sop: Dict[str, Any],
        sop_execution_summary: Dict[str, Any],
        score_report: Dict[str, Any],
    ) -> Dict[str, Any]:

        prompt = self._build_prompt(
            sop=sop,
            summary=sop_execution_summary,
            score=score_report,
        )

        raw = self.llm.invoke(prompt)

        from src.serializer.serializer import SmartSerializer
        response = SmartSerializer.extract_json(raw)

        if not isinstance(response, dict):
            raise ValueError("LLM did not return valid JSON")

        result = {
            # ---------------------------
            # Two-layer explanation
            # ---------------------------
            "developer_analysis": response.get("developer_analysis"),
            "user_response": response.get("user_response"),

            # ---------------------------
            # Policy decision
            # ---------------------------
            "is_edit": bool(response.get("is_edit", False)),
            "reason": response.get("reason"),
            "improved_policy": response.get("improved_policy"),

            # ---------------------------
            # Classification
            # ---------------------------
            "failure_type": response.get("failure_type"),
            "most_critical_step": response.get("most_critical_step"),
            "systemic_pattern_detected": response.get("systemic_pattern_detected", False),
            "risk_assessment": response.get("risk_assessment"),
            "improvement_scope": response.get("improvement_scope"),

            "confidence": response.get("confidence", "medium"),
        }

        self.info(
            "llm_prompt_critic_completed",
            is_edit=result["is_edit"],
            failure_type=result["failure_type"],
            risk=result["risk_assessment"],
            confidence=result["confidence"],
        )

        return result

    # ======================================================
    # APPLY POLICY IF NEEDED
    # ======================================================

    def apply_policy_if_needed(self, critic_result: Dict[str, Any]) -> None:

        if not critic_result.get("is_edit"):
            self.info("policy_update_skipped", reason="is_edit_false")
            return

        if not critic_result.get("improved_policy"):
            self.warning(
                "policy_update_skipped",
                reason="missing_improved_policy"
            )
            return

        edit_yaml(
            POLICY_PATH,
            {"sop_policy_prompt": critic_result["improved_policy"]}
        )

        self.info(
            "policy_updated",
            path=POLICY_PATH,
            confidence=critic_result.get("confidence"),
            scope=critic_result.get("improvement_scope"),
        )

    # ======================================================
    # PROMPT BUILDER
    # ======================================================

    def _build_prompt(
        self,
        *,
        sop: Dict[str, Any],
        summary: Dict[str, Any],
        score: Dict[str, Any],
    ) -> str:

        return f"""
You are an AI Assistant reviewing an execution result.

You must produce TWO different explanations:

--------------------------------------------------
CURRENT SOP POLICY:
{POLICY_PROMPT}
--------------------------------------------------

CURRENT SOP:
{sop}

EXECUTION SUMMARY:
{summary}

RULE-BASED SCORE:
Total Score: {score["total_score"]}/{score["max_score"]}
Grade: {score["grade"]}
Per-step: {score["per_step"]}

--------------------------------------------------

YOUR TASK:

1) developer_analysis:
   - Detailed technical explanation.
   - May reference execution logic, step status, severity.
   - Intended for developers.
   - Can be structured and analytical.

2) user_response:
   - Friendly assistant-style explanation.
   - Speak directly to the user.
   - Avoid internal technical terms like:
     "execution engine", "orchestration layer", "severity mapping".
   - Explain what happened in simple language.
   - If something failed, explain what will happen next.
   - Tone: calm, helpful, reassuring.
   - Keep it concise and natural.

Then also:

3) Classify failure type:
   - execution
   - policy
   - mixed
   - environment
   - planning

4) Identify the most critical step.

5) Decide whether the mistake is systemic.
   - systemic_pattern_detected = true only if likely to recur.

6) Decide if SOP policy needs refinement.
   - Only set is_edit = true if:
       - systemic
       - AND policy-level weakness exists.
   - If editing:
       - Explain the causal policy gap.
       - Preserve schema.
       - Preserve task intent.

7) Assess overall risk level:
   - low | medium | high | critical

IMPORTANT:
- Do NOT change rule-based score.
- Do NOT modify SOP schema.
- Do NOT invent tools.
- Do NOT hallucinate missing data.

Return ONLY JSON:

{{
  "developer_analysis": "...",
  "user_response": "...",

  "is_edit": true | false,
  "reason": "...",
  "improved_policy": "...",

  "failure_type": "execution | policy | mixed | environment | planning",
  "most_critical_step": <int>,
  "systemic_pattern_detected": true | false,
  "risk_assessment": "low | medium | high | critical",
  "improvement_scope": "...",

  "confidence": "low | medium | high"
}}
"""
