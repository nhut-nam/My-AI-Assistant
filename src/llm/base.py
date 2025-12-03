from abc import ABC, abstractmethod
from src.utils.logger import LoggerMixin
from src.constants.constants import MODEL_CONFIG
from dotenv import load_dotenv
import os

load_dotenv()

class BaseClient(LoggerMixin, ABC):
    """Base class for all LLM providers."""

    def __init__(self, provider_key: str):
        """
        provider_key: tên trong MODEL_CONFIG (vd: 'groq', 'openai', 'gemini')
        """
        super().__init__(self.__class__.__name__)

        if provider_key not in MODEL_CONFIG:
            raise ValueError(f"Provider '{provider_key}' not found in MODEL_CONFIG")

        self.config = MODEL_CONFIG[provider_key]  # metadata của model
        self.model_name = self.config.get("model_name")

        # API key không lấy từ YAML — lấy từ ENV
        self.api_key = os.getenv(f"{provider_key.upper()}_API_KEY")
        if not self.api_key and not provider_key.__eq__("ollama"):
            raise ValueError(f"Missing environment variable: {provider_key.upper()}_API_KEY")

        # Khởi tạo client thật của LLM provider
        self.client = self._create_client()

        self.info(f"Initialized LLM Client for provider: {provider_key}, model: {self.model_name}")

    @abstractmethod
    def _create_client(self):
        """Khởi tạo client provider cụ thể."""
        raise NotImplementedError

    @abstractmethod
    def invoke(self, query: str):
        """Gọi LLM."""
        raise NotImplementedError
