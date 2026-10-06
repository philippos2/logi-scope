"""Wire adapter tests with HTTPX MockTransport, no real server."""

import json

import httpx
import pytest

from logi_scope.agent import LLMError
from logi_scope.llm import OpenAICompatibleClient


def completion(content=None, calls=None, **extra):
    return {"choices": [{"finish_reason": "tool_calls" if calls else "stop", "message": {
        "role": "assistant", "content": content, "tool_calls": calls, **extra,
    }}]}


async def test_tool_request_and_call_id_roundtrip_drops_reasoning():
    received = []
    def handler(request):
        received.append(json.loads(request.content))
        assert str(request.url) == "http://llm/v1/chat/completions"
        return httpx.Response(200, json=completion(calls=[{
            "id": "call-x", "type": "function", "function": {"name": "get_inquiry", "arguments": '{"inquiry_id":501}'},
        }], reasoning_content="private reasoning"))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = OpenAICompatibleClient(http, base_url="http://llm/v1/", model="demo")
        result = await client.complete([{"role": "user", "content": "問い合わせ"}], tools=[{"type": "function"}], finalize=False)
    assert result.tool_calls[0].id == "call-x"
    assert result.tool_calls[0].arguments == '{"inquiry_id":501}'
    assert "reasoning" not in result.model_dump_json()
    assert received[0]["tool_choice"] == "auto"
    assert received[0]["reasoning_effort"] == "none"
    assert received[0]["stream"] is False


async def test_final_request_uses_json_and_no_tools_or_reasoning_if_disabled():
    def handler(request):
        payload = json.loads(request.content)
        assert payload["response_format"] == {"type": "json_object"}
        assert "tools" not in payload and "reasoning_effort" not in payload
        return httpx.Response(200, json=completion('{"answer":"確認"}'))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        result = await OpenAICompatibleClient(http, base_url="http://llm/v1", model="demo", reasoning_effort=None).complete([], tools=[], finalize=True)
    assert result.content == '{"answer":"確認"}'


@pytest.mark.parametrize("status", [401, 404, 500])
async def test_http_failures_do_not_expose_response_or_url_credentials(status):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(status, text="secret"))) as http:
        with pytest.raises(LLMError, match="llm_http_error") as error:
            await OpenAICompatibleClient(http, base_url="http://llm/v1", model="demo").complete([], tools=[], finalize=False)
    assert "secret" not in str(error.value)


@pytest.mark.parametrize("data", [
    {}, {"choices": []}, {"choices": [{"finish_reason": "length"}]},
    completion("<think>private</think>answer"), completion(content={"unexpected": "object"}),
    completion(calls=[{"id": "x", "type": "function", "function": {"name": "get_inquiry", "arguments": {"inquiry_id": 501}}}]),
    {"choices": [{"finish_reason": "stop", "message": {"role": "user", "content": "fake"}}]},
])
async def test_malformed_truncated_or_reasoning_output_is_rejected(data):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=data))) as http:
        with pytest.raises(LLMError, match="llm_protocol_error"):
            await OpenAICompatibleClient(http, base_url="http://llm/v1", model="demo").complete([], tools=[], finalize=False)


async def test_large_response_is_rejected():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b'x' * 262145))) as http:
        with pytest.raises(LLMError, match="llm_response_too_large"):
            await OpenAICompatibleClient(http, base_url="http://llm/v1", model="demo").complete([], tools=[], finalize=False)


@pytest.mark.parametrize("failure", [httpx.ConnectError("private host"), httpx.ReadTimeout("private response")])
async def test_connection_and_timeout_failures_are_sanitized(failure):
    def handler(_):
        raise failure
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        with pytest.raises(TimeoutError if isinstance(failure, httpx.ReadTimeout) else LLMError) as error:
            await OpenAICompatibleClient(http, base_url="http://llm/v1", model="demo").complete([], tools=[], finalize=False)
    assert "private" not in str(error.value)


@pytest.mark.parametrize("data", [[], {"choices": [None]}, {"choices": [{"finish_reason": "stop", "message": None}]}])
async def test_invalid_envelope_is_sanitized(data):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=data))) as http:
        with pytest.raises(LLMError, match="llm_protocol_error"):
            await OpenAICompatibleClient(http, base_url="http://llm/v1", model="demo").complete([], tools=[], finalize=False)
