from langchain_ollama import ChatOllama
from src.llm.base import BaseClient

class OllamaClient(BaseClient):

    def __init__(self):
        super().__init__("ollama") 

    def _create_client(self):
        return ChatOllama(
            model=self.model_name,
            temperature=self.config.get("temperature", 0.2)
        )

    def invoke(self, query: str) -> str:
        response = self.client.invoke(query)
        content = response.content
        self.info(f"Ollama Response: {content}")
        return content
