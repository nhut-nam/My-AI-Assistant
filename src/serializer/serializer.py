import json
import re
from typing import Any, Type
from pydantic import BaseModel, ValidationError


class SmartSerializer:
    """
    Bộ serializer/deserializer cho LLM JSON.
    - extract JSON từ text
    - sanitize
    - parse JSON
    - map dict → Pydantic model
    """

    # --------------------
    # CLEAN META TAG
    # --------------------
    @staticmethod
    def remove_meta(text: str) -> str:
        return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)

    # --------------------
    # REMOVE CODE FENCES
    # --------------------
    @staticmethod
    def strip_code_fences(text: str) -> str:
        if "```" not in text:
            return text

        cleaned = re.sub(r"```[a-zA-Z]*", "", text)
        cleaned = cleaned.replace("```", "")
        return cleaned

    # --------------------
    # TRY DIRECT JSON PARSE
    # --------------------
    @staticmethod
    def try_parse_json(text: str):
        text = text.strip()
        try:
            return json.loads(text)
        except:
            return None

    # --------------------
    # STACK-BASED JSON EXTRACT
    # --------------------
    @staticmethod
    def extract_first_json_object(text: str):
        start = text.find("{")
        if start == -1:
            return None

        stack = 0
        buf = ""
        in_json = False

        for ch in text[start:]:
            if ch == "{":
                stack += 1
                in_json = True

            if in_json:
                buf += ch

            if ch == "}":
                stack -= 1
                if stack == 0:
                    try:
                        return json.loads(buf)
                    except:
                        return None

        return None

    # --------------------
    # NULL / BOOLEAN SANITIZER
    # --------------------
    @staticmethod
    def sanitize(data):
        """
        Recursively convert:
        - "null"  -> None
        - "None"  -> None
        - "true"  -> True
        - "false" -> False
        """
        if isinstance(data, dict):
            return {k: SmartSerializer.sanitize(v) for k, v in data.items()}

        if isinstance(data, list):
            return [SmartSerializer.sanitize(x) for x in data]

        if isinstance(data, str):
            lowered = data.strip().lower()
            if lowered == "null":
                return None
            if lowered == "none":
                return None
            if lowered == "true":
                return True
            if lowered == "false":
                return False

        return data

    # --------------------
    # MAIN ENTRY
    # --------------------
    @staticmethod
    def extract_json(text: str):
        """
        Steps:
        1. Remove <think>
        2. Remove code fences
        3. Try direct JSON
        4. Try stack-based extraction
        5. Sanitize "null"/"None"/boolean strings
        """
        if not text or not isinstance(text, str):
            return None

        # Step 1
        clean = SmartSerializer.remove_meta(text)

        # Step 2
        clean = SmartSerializer.strip_code_fences(clean)

        # Step 3
        parsed = SmartSerializer.try_parse_json(clean)
        if parsed is not None:
            return SmartSerializer.sanitize(parsed)

        # Step 4
        parsed = SmartSerializer.extract_first_json_object(clean)
        if parsed is not None:
            return SmartSerializer.sanitize(parsed)

        return None

    @staticmethod
    def to_model(model: Type[BaseModel], data: dict) -> BaseModel | None:
        """
        Convert dict → Pydantic model.
        Return None nếu dict không valid.
        """
        if not isinstance(data, dict):
            return None

        try:
            return model(**data)
        except ValidationError as e:
            print(f"Validation error: {e}")
            return None


    @classmethod
    def parse_model(cls, model: Type[BaseModel], data: dict) -> BaseModel | None:
        """
        Nhận trực tiếp dict → validate → trả về model instance.
        KHÔNG còn xử lý raw_text hay JSON string.
        """
        if not isinstance(data, dict):
            return None

        return cls.to_model(model, data)

