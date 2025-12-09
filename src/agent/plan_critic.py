from __future__ import annotations
from src.agent.base_agent import BaseAgent
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field
import json


# ============================================================
# MODELS
# ============================================================

class CriticIssue(BaseModel):
    description: str = Field(..., description="Mô tả vấn đề phát hiện trong plan")
    severity: str = Field(
        ...,
        description="Mức độ nghiêm trọng: none | low | medium | high | critical"
    )
    impact: str = Field(
        ...,
        description="Hậu quả hoặc rủi ro tiềm năng nếu vấn đề không được xử lý"
    )


class CriticFeedback(BaseModel):
    score: int = Field(..., description="Điểm đánh giá tổng thể (0–100)")
    issues: list[CriticIssue] = Field(..., description="Danh sách vấn đề được phát hiện")
    summary: str = Field(..., description="Tóm tắt đánh giá + Pass/Fail")


# ============================================================
# PLAN CRITIC AGENT
# ============================================================

class PlanCriticAgent(BaseAgent):
    """
    PlanCriticAgent:
    - Đánh giá Plan từ PlannerAgent
    - Chấm điểm theo tiêu chí chất lượng: correctness, completeness, safety, clarity, feasibility
    - Để đảm bảo an toàn tuyệt đối: score MUST be 100 to PASS
    """

    MAX_RETRY = 3

    def __init__(self, llm, tools=None, name="PlanCriticAgent", description="", log_dir="logs"):
        super().__init__(llm, tools, name, description, log_dir)

    # ------------------------------------------------------------
    # BUILD PROMPT
    # ------------------------------------------------------------
    def build_prompt(self, plan, query=None):

        plan_str = "\n".join(f"{i+1}. {s}" for i, s in enumerate(plan.steps))

        system_prompt = (
            """You are a Plan Completeness Checker.

            User request (task to achieve):
            {query}

            Your task:
            - Evaluate whether the plan contains ALL necessary steps to achieve the goal.
            - Check if the order of steps is logically correct.
            - Identify if the plan is missing any essential step. Example: if user wants to stop execution upon condition, plan must include that check.
            - Do NOT evaluate edge cases such as file permissions, read-only files, or runtime exceptions.
            - Do NOT require error handling, safety guards, or robustness features.
            - Only check: "Does this plan contain all required steps to successfully perform the described task?"

            Scoring rules:
            - 100 = Plan has all required steps in correct logical order.
            - < 100 = Plan is missing at least one essential step OR steps are out of logical order.

            You MUST return JSON:
            {{
            "score": <0-100>,
            "issues": [
                {{
                "description": "<missing or wrong step>",
                "severity": "<low|medium|high>",
                "impact": "<short explanation>"
                }}
            ],
            "summary": "<PASS if score == 100 else FAIL>"
            }}
            """
        )

        return ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                ("human", "Evaluate the following plan:\n" + plan_str)
            ]
        ).partial(query=query)


    # ------------------------------------------------------------
    # CHAIN
    # ------------------------------------------------------------
    def chain(self, plan, query=None):
        prompt = self.build_prompt(plan, query)
        # LLM output mapped directly to CriticFeedback Pydantic model
        return prompt | self.llm.with_structured_output(CriticFeedback)

    # ------------------------------------------------------------
    # INVOKE (retry + structured validate)
    # ------------------------------------------------------------
    async def invoke(self, plan, query=None):

        for attempt in range(1, self.MAX_RETRY + 1):
            self.info(f"[PlanCritic] Attempt {attempt}")

            try:
                chain = self.chain(plan, query)
                feedback = await chain.ainvoke({"messages": []})

                self.info("[PlanCritic] Structured output received")
                return {"success": True, "feedback": feedback}

            except Exception as e:
                self.warning(f"[PlanCritic] Error: {e}")
                continue

        return {
            "success": False,
            "error": "Could not produce valid CriticFeedback after retries."
        }
