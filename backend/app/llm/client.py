from typing import Any

from app.config import get_settings


class LlmClient:
    """DeepSeek-compatible boundary with deterministic fallback for demos."""

    def complete_json(self, prompt: str, fallback: dict[str, Any]) -> dict[str, Any]:
        settings = get_settings()
        if not settings.llm_api_key:
            return fallback
        return fallback
