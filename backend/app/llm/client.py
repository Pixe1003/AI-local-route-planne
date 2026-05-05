import json
import re
from typing import Any

import httpx

from app.config import get_settings


class LlmClient:
    """OpenAI-compatible JSON boundary with deterministic fallback for demos."""

    def complete_json(self, prompt: str, fallback: dict[str, Any]) -> dict[str, Any]:
        settings = get_settings()
        if not settings.llm_api_key:
            return fallback
        try:
            response = httpx.post(
                f"{self._base_url(settings).rstrip('/')}/chat/completions",
                headers=self._headers(settings),
                json={
                    "model": settings.llm_model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "你是本地路线规划系统的需求理解模块。只输出一个合法 JSON 对象，"
                                "不要输出 Markdown、解释或路线安排。"
                            ),
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "max_completion_tokens": 1024,
                    "temperature": 0.2,
                    "top_p": 0.95,
                    "stream": False,
                    "stop": None,
                    "frequency_penalty": 0,
                    "presence_penalty": 0,
                },
                timeout=settings.llm_timeout_seconds,
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
            return self._parse_json_content(content, fallback)
        except Exception:
            return fallback

    def _base_url(self, settings) -> str:
        if settings.llm_base_url:
            return settings.llm_base_url
        if settings.llm_provider.lower() == "mimo":
            return "https://api.mimo-v2.com/v1"
        if settings.llm_provider.lower() == "deepseek":
            return "https://api.deepseek.com/v1"
        return "https://api.openai.com/v1"

    def _headers(self, settings) -> dict[str, str]:
        auth_header = settings.llm_auth_header
        if not auth_header:
            auth_header = "authorization"
        if auth_header.lower() in {"authorization", "bearer"}:
            return {"Authorization": f"Bearer {settings.llm_api_key}", "Content-Type": "application/json"}
        return {auth_header: settings.llm_api_key, "Content-Type": "application/json"}

    def _parse_json_content(self, content: str, fallback: dict[str, Any]) -> dict[str, Any]:
        text = content.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        if not text.startswith("{"):
            match = re.search(r"\{.*\}", text, flags=re.S)
            if match:
                text = match.group(0)
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else fallback
