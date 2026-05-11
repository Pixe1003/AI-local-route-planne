import json
import re
from typing import Any

import httpx

from app.config import get_settings
from app.services.agent_skill_registry import get_agent_skill_registry


class LlmClient:
    """OpenAI-compatible JSON boundary with deterministic fallback for demos."""

    BASE_SYSTEM_PROMPT = (
        "你是本地路线规划系统的需求理解模块。只输出一个合法 JSON 对象，"
        "不要输出 Markdown、解释或路线安排。"
    )

    def complete_json(
        self,
        prompt: str,
        fallback: dict[str, Any],
        *,
        agent_name: str | None = None,
        system_prompt: str | None = None,
    ) -> dict[str, Any]:
        settings = get_settings()
        if not settings.llm_api_key:
            return fallback
        system_content = get_agent_skill_registry().build_system_prompt(
            agent_name,
            system_prompt or self.BASE_SYSTEM_PROMPT,
        )
        try:
            payload = {
                "model": settings.llm_model,
                "messages": [
                    {
                        "role": "system",
                        "content": system_content,
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.2,
                "top_p": 0.95,
                "stream": False,
                "stop": None,
                "frequency_penalty": 0,
                "presence_penalty": 0,
            }
            payload[self._max_tokens_field(settings)] = 1024
            response = httpx.post(
                f"{self._base_url(settings).rstrip('/')}/chat/completions",
                headers=self._headers(settings),
                json=payload,
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
        provider = self._provider(settings)
        if provider == "longcat":
            return "https://api.longcat.chat/openai/v1"
        if provider == "mimo":
            return "https://api.mimo-v2.com/v1"
        if provider == "deepseek":
            return "https://api.deepseek.com/v1"
        return "https://api.openai.com/v1"

    def _max_tokens_field(self, settings) -> str:
        if self._provider(settings) == "longcat":
            return "max_tokens"
        return "max_completion_tokens"

    def _provider(self, settings) -> str:
        return getattr(settings, "llm_provider", "").lower()

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
