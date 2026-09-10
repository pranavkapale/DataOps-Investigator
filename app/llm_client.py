import json
import logging
from typing import Any, Type, TypeVar

import requests
from pydantic import BaseModel, ValidationError

from app.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

class LLMClientError(RuntimeError):
    """Raised when an LLM request fails or returns an unparseable response."""

class LLMClient:
    """A minimal client for interacting with OpenAI-compatible endpoints."""
    
    def __init__(
        self, 
        api_base: str = settings.llm_api_base, 
        api_key: str = settings.llm_api_key, 
        model: str = settings.llm_model
    ):
        self.api_base = api_base
        self.api_key = api_key
        self.model = model

    def generate_structured(self, system_prompt: str, user_prompt: str, response_model: Type[T]) -> T:
        """
        Requests a structured JSON response from the LLM and parses it into the provided Pydantic model.
        """
        url: str = f"{self.api_base}/chat/completions"
        headers: dict[str, str] = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        # Append instructions for the model to return JSON
        enhanced_system_prompt = (
            f"{system_prompt}\n\n"
            "You MUST return ONLY valid JSON matching the exact required schema. "
            "Do NOT wrap the JSON in Markdown backticks (e.g., ```json). "
            "Return the raw JSON object directly."
        )

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": enhanced_system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=60)
            resp.raise_for_status()
        except requests.RequestException as e:
            raise LLMClientError(f"LLM API request failed: {e}") from e

        response_data: Any = resp.json()
        choices: Any = response_data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise LLMClientError("LLM response did not include any choices.")

        first_choice: Any = choices[0]
        message: Any = first_choice.get("message", {})
        content = message.get("content")
        
        if not content or not isinstance(content, str):
            raise LLMClientError("LLM response content was empty or not a string.")

        try:
            parsed_json = json.loads(content)
            return response_model.model_validate(parsed_json)
        except json.JSONDecodeError as e:
            raise LLMClientError(f"Failed to parse LLM response as JSON: {content}") from e
        except ValidationError as e:
            raise LLMClientError(f"LLM response JSON failed schema validation: {e}") from e
