import json
import re
from typing import Any

import httpx

from app.config import get_settings
from app.llm import cache as llm_cache
from app.observability.metrics import CACHE_HIT_RATE, LLM_TOKENS
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
        cacheable: bool = False,
    ) -> dict[str, Any]:
        settings = get_settings()
        if not settings.llm_api_key:
            return fallback
        system_content = get_agent_skill_registry().build_system_prompt(
            agent_name,
            system_prompt or self.BASE_SYSTEM_PROMPT,
        )
        key = llm_cache.cache_key(prompt, [], system_content, model=settings.llm_model)
        if cacheable:
            cached = llm_cache.get(key)
            if cached is not None:
                CACHE_HIT_RATE.labels(cache_name="llm_json", result="hit").inc()
                return cached
            CACHE_HIT_RATE.labels(cache_name="llm_json", result="miss").inc()
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
            payload = response.json()
            self._record_usage(settings, payload.get("usage", {}))
            content = payload["choices"][0]["message"]["content"]
            result = self._parse_json_content(content, fallback)
            if cacheable and result != fallback:
                llm_cache.put(key, result)
            return result
        except Exception:
            return fallback

    def complete_tool_call(
        self,
        prompt: str,
        *,
        tools: list[dict[str, Any]],
        fallback: dict[str, Any],
    ) -> dict[str, Any]:
        settings = get_settings()
        if not settings.llm_api_key:
            return fallback
        system_prompt = "Choose exactly one tool. Return only a tool call."
        key = llm_cache.cache_key(prompt, tools, system_prompt, model=settings.llm_model)
        cached = llm_cache.get(key)
        if cached is not None:
            CACHE_HIT_RATE.labels(cache_name="llm_tool_call", result="hit").inc()
            return {**cached, "_tokens_used": 0}
        CACHE_HIT_RATE.labels(cache_name="llm_tool_call", result="miss").inc()
        try:
            response = httpx.post(
                f"{self._base_url(settings).rstrip('/')}/chat/completions",
                headers=self._headers(settings),
                json={
                    "model": settings.llm_model,
                    "messages": [
                        {
                            "role": "system",
                            "content": system_prompt,
                        },
                        {"role": "user", "content": prompt},
                    ],
                    "tools": [
                        {
                            "type": "function",
                            "function": {
                                "name": tool["name"],
                                "description": tool.get("description", ""),
                                "parameters": tool.get("parameters", {"type": "object"}),
                            },
                        }
                        for tool in tools
                    ],
                    "tool_choice": "auto",
                    "temperature": 0.0,
                    "stream": False,
                },
                timeout=settings.llm_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            self._record_usage(settings, payload.get("usage", {}))
            message = payload["choices"][0]["message"]
            usage = payload.get("usage", {})
            tool_calls = message.get("tool_calls") or []
            if not tool_calls:
                return fallback
            function = tool_calls[0].get("function") or {}
            tool_name = function.get("name")
            raw_args = function.get("arguments") or "{}"
            args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            if isinstance(tool_name, str) and isinstance(args, dict):
                result = {
                    "tool": tool_name,
                    "args": args,
                }
                llm_cache.put(key, result)
                return {**result, "_tokens_used": int(usage.get("total_tokens", 0) or 0)}
        except Exception:
            return fallback
        return fallback

    def _base_url(self, settings) -> str:
        if settings.llm_base_url:
            return str(settings.llm_base_url)
        provider = self._provider(settings)
        if provider == "longcat":
            return "https://api.longcat.ai/v1"
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
        return str(getattr(settings, "llm_provider", "")).lower()

    def _headers(self, settings) -> dict[str, str]:
        auth_header = settings.llm_auth_header
        if not auth_header:
            auth_header = "authorization"
        if auth_header.lower() in {"authorization", "bearer"}:
            return {"Authorization": f"Bearer {settings.llm_api_key}", "Content-Type": "application/json"}
        return {auth_header: settings.llm_api_key, "Content-Type": "application/json"}

    def _record_usage(self, settings, usage: dict[str, Any]) -> None:
        if not usage:
            return
        provider = getattr(settings, "llm_provider", "") or self._provider(settings) or "unknown"
        model = getattr(settings, "llm_model", "unknown") or "unknown"
        token_fields = {
            "input": usage.get("prompt_tokens", 0),
            "output": usage.get("completion_tokens", 0),
            "total": usage.get("total_tokens", 0),
        }
        for kind, value in token_fields.items():
            if value:
                LLM_TOKENS.labels(provider=provider, model=model, kind=kind).inc(int(value))

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
