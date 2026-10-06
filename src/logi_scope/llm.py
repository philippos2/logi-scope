"""Small OpenAI-compatible adapter; no raw responses or reasoning are logged."""

import json

import httpx
from pydantic import ValidationError

from logi_scope.agent import LLMError, LLMReply, ToolCall


class OpenAICompatibleClient:
    def __init__(self, http: httpx.AsyncClient, *, base_url: str, model: str,
                 timeout: float = 300, max_tokens: int = 1200, reasoning_effort: str | None = "none"):
        self.http = http
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.reasoning_effort = reasoning_effort

    async def complete(self, messages: list[dict], *, tools: list[dict], finalize: bool) -> LLMReply:
        payload = {"model": self.model, "messages": messages, "stream": False,
                   "temperature": 0, "max_tokens": self.max_tokens}
        if self.reasoning_effort is not None:
            payload["reasoning_effort"] = self.reasoning_effort
        if finalize:
            payload["response_format"] = {"type": "json_object"}
        elif tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        try:
            async with self.http.stream("POST", self.url, json=payload, timeout=self.timeout) as response:
                if response.status_code != 200:
                    raise LLMError("llm_http_error")
                data = bytearray()
                async for part in response.aiter_bytes():
                    data.extend(part)
                    if len(data) > 262144:
                        raise LLMError("llm_response_too_large")
            return parse_reply(json.loads(data))
        except httpx.TimeoutException:
            raise TimeoutError("llm_timeout") from None
        except httpx.HTTPError:
            raise LLMError("llm_connection_error") from None
        except (ValueError, KeyError, TypeError, AttributeError, IndexError, ValidationError):
            raise LLMError("llm_protocol_error") from None


def parse_reply(data: dict) -> LLMReply:
    choices = data["choices"]
    if not isinstance(choices, list) or len(choices) != 1:
        raise ValueError("one choice required")
    choice = choices[0]
    if choice.get("finish_reason") not in {"stop", "tool_calls"}:
        raise ValueError("incomplete response")
    message = choice["message"]
    if message.get("role") != "assistant":
        raise ValueError("assistant message required")
    content = message.get("content")
    if content is not None and (not isinstance(content, str) or len(content) > 32000
                                or "<think>" in content or "</think>" in content):
        raise ValueError("invalid public content")
    calls = message.get("tool_calls") or []
    if not isinstance(calls, list) or len(calls) > 12:
        raise ValueError("too many tool calls")
    extracted = []
    for call in calls:
        if call["type"] != "function":
            raise ValueError("function required")
        function = call["function"]
        if not isinstance(function["arguments"], str) or len(function["arguments"]) > 8000:
            raise ValueError("invalid arguments envelope")
        extracted.append(ToolCall(id=call["id"], name=function["name"], arguments=function["arguments"]))
    if len({c.id for c in extracted}) != len(extracted):
        raise ValueError("duplicate call IDs")
    # Drop reasoning/reasoning_content and all other provider-specific fields.
    return LLMReply(content=content, tool_calls=extracted)
