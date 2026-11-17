from src.agent.base_agent import BaseAgent
from langchain_core.messages import HumanMessage, SystemMessage
import json


class ChitChatAgent(BaseAgent):
    """
    ChitChatAgent:
    - Xử lý hội thoại tự nhiên
    - Không sử dụng tool
    - Trả về phản hồi trực tiếp từ LLM
    """

    def __init__(
        self,
        llm,
        tools=None,
        name="ChitChatAgent",
        description="Agent xử lý hội thoại tự nhiên (casual conversation)",
        log_dir="logs"
    ):
        super().__init__(llm, tools, name, description, log_dir)

    # ----------------------------------------------------------
    # PROMPT ENGINEERING
    # ----------------------------------------------------------
    def build_prompt(self, **kwargs):
        """
        Chuẩn hoá prompt cho hội thoại.
        Không dùng tool.
        """

        query = kwargs.get("query", "")
        context = kwargs.get("context", "")

        return [
            SystemMessage(
                content=(
                    "You are a friendly conversational AI assistant.\n"
                    "Your job is to respond naturally and helpfully.\n"
                    "Do NOT call any tools.\n"
                    "Always return JSON in this format:\n"
                    "{ 'success': True/False, 'result': '<your reply>' }\n"
                    "Do not explain anything outside JSON."
                )
            ),
            HumanMessage(
                content=f"User message: {query}\nContext: {context}"
            ),
        ]

    # ----------------------------------------------------------
    # INVOKE (Dynamic reasoning giống SimpleMathAgent)
    # ----------------------------------------------------------
    async def invoke(self, **kwargs):
        """
        Dùng LLM để trả lời trực tiếp.
        """

        query = kwargs.get("query", "")
        context = kwargs.get("context", "")

        self.info(f"[ChitChatAgent] Running conversation for: {query}")

        prompt = self.build_prompt(query=query, context=context)

        output = await self.llm.ainvoke(prompt)
        raw_content = output.content.strip()

        self.info(f"[ChitChatAgent] Raw output: {raw_content}")

        try:
            parsed = json.loads(raw_content)
            return parsed
        except:
            # fallback nếu LLM không trả JSON chuẩn
            return {
                "success": True,
                "result": raw_content
            }
