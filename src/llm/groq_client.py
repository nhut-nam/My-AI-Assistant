from langchain_groq import ChatGroq
from src.llm.base import BaseClient

class GroqClient(BaseClient):

    def __init__(self):
        super().__init__("groq") 

    def _create_client(self):
        return ChatGroq(
            model=self.model_name,
            groq_api_key=self.api_key,
            temperature=self.config.get("temperature", 0.2),
            max_tokens=self.config.get("max_tokens", 2048)
        )

    def invoke(self, query: str) -> str:
        response = self.client.invoke(query)
        content = response.content
        self.info(f"Groq Response: {content}")
        return content
