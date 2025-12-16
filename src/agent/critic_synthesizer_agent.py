from src.agent.base_agent import BaseAgent
from langchain_core.prompts import ChatPromptTemplate
from src.models.models import SynthesizedCriticReport
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough
from typing import Any, Dict


class CriticSynthesizerAgent(BaseAgent):
    """
    Reflection-style synthesizer:
    Gathers:
        - original user request
        - generated SOP
        - execution result
    And produces:
        - consolidated summary
        - discovered failure patterns
        - improvement strategies
    """

    def __init__(self, llm, name="CriticSynthesizerAgent", log_dir="logs"):
        super().__init__(llm, None, name, "", log_dir)
        
    def build_prompt(self, **kwargs):
        return super().build_prompt(**kwargs)

    def _review_chain(self):
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """
            You are a Review Agent.
            Your job is to evaluate the SOP and Execution result.
            Focus on:
            - What went wrong
            - Why it happened
            - What parts of the SOP may have caused it
            Write a structured critique in plain text.
                        """,
                ),
                (
                    "human",
                    """
            User Request:
            {user_request}

            SOP:
            {sop}

            Execution Output after running the SOPw:
            {execution}

            Write your detailed critique now.
                        """,
                ),
            ]
        )
        return prompt | self.llm | StrOutputParser()

    def _analysis_chain(self):
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """
                    You are an Analysis Agent.
                    Given a critique, extract:
                    - Key failure points
                    - Root causes
                    - Logical issues from SOP design
                    """,
                ),
                ("user", "Critique:\n{critique}\n\nExtract the insights."),
            ]
        )
        return prompt | self.llm | StrOutputParser()

    def _synthesis_chain(self):
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """
                    You are a Critic Synthesizer Agent.
                    Combine:
                    - Original request
                    - SOP
                    - Execution result
                    - Extracted insights

                    Produce a JSON strictly following this structure:

                    {{
                    "summary": "...",
                    "key_failures": ["...", "..."],
                    "improvement_advice": ["...", "..."],
                    "risk_level": "low | medium | high | critical"
                    }}
                                """,
                                    ),
                                    (
                                        "user",
                                        """
                    User request:
                    {user_request}

                    Extracted insights:
                    {insights}

                    Generate the JSON now.
                    """,
                ),
            ]
        )

        return prompt | self.llm.with_structured_output(SynthesizedCriticReport)

    def build_full_chain(self):
        return (
            RunnablePassthrough.assign(critique=self._review_chain())
            | RunnablePassthrough.assign(insights=self._analysis_chain())
            | self._synthesis_chain()
        )

    async def invoke(self, input_text: str, sop_result: Dict, execution_result: Dict):
        self.info("[CriticSynthesizer] Running reflection pipeline...")

        chain = self.build_full_chain()

        final = await chain.ainvoke(
            {
                "user_request": input_text,
                "sop": sop_result,
                "execution": execution_result,
            }
        )

        self.info("[CriticSynthesizer] Done.")
        print(type(final))
        return final
