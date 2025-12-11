from src.agent.base_agent import BaseAgent
from langchain_core.prompts import ChatPromptTemplate
from src.models.models import SynthesizedCriticReport
from typing import Any, Dict


# -------------------------------------------------------------
# CRITIC SYNTHESIZER
# -------------------------------------------------------------
class CriticSynthesizerAgent(BaseAgent):
    """
    Agent chuyên để tổng hợp thông tin từ:
        - input_text (user request gốc)
        - sop_result (SOP object mà hệ thống tạo ra)
        - execution_result (kết quả thực thi thật)

    → Trả về synthesized critic report, ví dụ:
        - Những lỗi chính
        - Gợi ý sửa SOP/Plan
        - Mức độ rủi ro
    """

    def __init__(self, llm, name="CriticSynthesizerAgent", log_dir="logs"):
        super().__init__(llm, None, name, "", log_dir)

    # -------------------------------------------------------------
    # Prompt generator
    # -------------------------------------------------------------
    def build_prompt(self, input_text: str, sop_result: Any, execution_result: Any):
        """
        Build prompt cho LLM: tổng hợp dữ liệu vào 1 prompt.
        """
        system_prompt = """
        You are a Critic Synthesizer Agent.
        Your job is to analyze:
        1. The original user request
        2. The generated SOP
        3. The execution result (success/failure/output)

        Your goals:
        - Identify failures and problematic logic
        - Summarize execution problems
        - Infer systemic issues in SOP design
        - Provide actionable improvement recommendations
        - Assess risk level (low / medium / high / critical)

        You MUST return JSON strictly matching this model:
        {
            "summary": "...",
            "key_failures": ["...", "..."],
            "improvement_advice": ["...", "..."],
            "risk_level": "low | medium | high | critical"
        }
        """

        # Build ChatPromptTemplate cho LLM
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("human", 
                f"User request:\n{input_text}\n\n"
                f"SOP generated:\n{sop_result}\n\n"
                f"Execution result:\n{execution_result}\n\n"
                "Generate the JSON report now."
            )
        ])

        return prompt

    # -------------------------------------------------------------
    # Chain: prompt → structured output
    # -------------------------------------------------------------
    def chain(self, prompt):
        return prompt | self.llm.with_structured_output(SynthesizedCriticReport)

    # -------------------------------------------------------------
    # Invoke (async hoặc sync tùy backend)
    # -------------------------------------------------------------
    async def invoke(self, input_text: str, sop_result: Dict, execution_result: Dict):
        """
        Chạy Synthesizer → trả JSON structured.
        """

        self.info("[CriticSynthesizer] Building prompt...")

        prompt = self.build_prompt(input_text, sop_result, execution_result)
        chain = self.chain(prompt)

        try:
            self.info("[CriticSynthesizer] Invoking LLM...")
            result = await chain.ainvoke({})
            self.info("[CriticSynthesizer] Done.")
            return result
        except Exception as e:
            self.error(f"[CriticSynthesizer] Error: {e}")
            return {
                "summary": "Failed to generate critic synthesis.",
                "key_failures": [str(e)],
                "improvement_advice": [],
                "risk_level": "high"
            }
