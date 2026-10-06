"""API contract with injected runner; no DB, model or network required."""

import asyncio

import httpx
import pytest

from logi_scope.agent import AgentResponse, AgentUnavailable, Step, Unresolved
from logi_scope.api import create_app
from logi_scope.config import Settings
from logi_scope.tools import reference


class Runner:
    def __init__(self, response=None, error=None):
        self.questions = []
        self.response = response or AgentResponse(answer="配達完了です。", sources=[reference("shipment", "SHP-1")],
            steps=[Step(tool="search_shipments", args={"shipment_id": "SHP-1"}, ok=True)], unresolved=[])
        self.error = error

    async def run(self, question):
        self.questions.append(question)
        if self.error:
            raise self.error
        return self.response


async def request(runner, data):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=create_app(Settings(), agent=runner)), base_url="http://test") as http:
        return await http.post("/agent", json=data)


async def test_success_returns_public_four_field_contract():
    runner = Runner()
    response = await request(runner, {"question": " SHP-1の状態は？ "})
    assert response.status_code == 200
    assert set(response.json()) == {"answer", "sources", "steps", "unresolved"}
    assert runner.questions == ["SHP-1の状態は？"]
    assert response.json()["steps"][0] == {"tool": "search_shipments", "args": {"shipment_id": "SHP-1"}, "ok": True}


@pytest.mark.parametrize("data", [{}, {"question": " "}, {"question": 1}, {"question": "x" * 4001}, {"question": "調査", "tools": []}])
async def test_invalid_input_never_runs_agent(data):
    runner = Runner()
    response = await request(runner, data)
    assert response.status_code == 422
    assert runner.questions == []


@pytest.mark.parametrize("code", ["not_found", "ambiguous_target", "step_limit", "timeout"])
async def test_controlled_incomplete_investigations_are_http_200(code):
    result = AgentResponse(answer="確認できませんでした。", sources=[], steps=[], unresolved=[Unresolved(code=code, message="未解決")])
    response = await request(Runner(result), {"question": "調査"})
    assert response.status_code == 200
    assert response.json()["unresolved"][0]["code"] == code


@pytest.mark.parametrize("failure,status,code", [("llm_error", 502, "llm_unavailable"), ("timeout", 504, "llm_timeout")])
async def test_initial_connection_failures_are_5xx(failure, status, code):
    response = await request(Runner(error=AgentUnavailable(failure)), {"question": "調査"})
    assert response.status_code == status
    assert response.json()["detail"]["code"] == code


async def test_uninitialized_agent_is_503_but_health_is_available():
    app = create_app(Settings(database_password=None))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        assert (await http.get("/health")).status_code == 200
        assert (await http.post("/agent", json={"question": "調査"})).status_code == 503


async def test_concurrent_request_is_rejected_and_lock_released():
    started, release = asyncio.Event(), asyncio.Event()
    class BlockingRunner(Runner):
        async def run(self, question):
            started.set()
            await release.wait()
            return await super().run(question)
    app = create_app(Settings(), agent=BlockingRunner())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
        first = asyncio.create_task(http.post("/agent", json={"question": "最初"}))
        await asyncio.wait_for(started.wait(), 1)
        busy = await http.post("/agent", json={"question": "同時"})
        assert busy.status_code == 503 and busy.json()["detail"]["code"] == "agent_busy"
        release.set()
        assert (await first).status_code == 200
        assert (await http.post("/agent", json={"question": "次"})).status_code == 200


async def test_lifespan_builds_real_loop_and_releases_runtime_resources(monkeypatch):
    import logi_scope.api as api
    import logi_scope.rag.embeddings as embeddings
    from logi_scope.agent import LLMReply, ToolCall
    from logi_scope.tools import BusinessTools, ToolResult
    import json
    disposed = []
    embedded = object()
    class Engine:
        async def dispose(self):
            disposed.append(True)
    class Client:
        def __init__(self, *args, **kwargs):
            assert kwargs["reasoning_effort"] is None
            self.calls = 0
        async def complete(self, messages, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return LLMReply(tool_calls=[ToolCall(id="lookup", name="search_shipments", arguments='{"shipment_id":"SHP-1"}')])
            return LLMReply(content=json.dumps({"answer": "配達完了", "sources": ["shipment:SHP-1"], "unresolved": []}))
    class Tools:
        def __init__(self, engine, *, embedder):
            assert embedder is embedded
        def validate(self, name, args):
            return BusinessTools(None).validate(name, args)
        async def execute(self, name, args):
            return ToolResult(records=[{"id": "SHP-1", "status": "delivered"}], sources=[reference("shipment", "SHP-1")])
    monkeypatch.setattr(api, "create_reader_engine", lambda _: Engine())
    monkeypatch.setattr(api, "OpenAICompatibleClient", Client)
    monkeypatch.setattr(api, "BusinessTools", Tools)
    monkeypatch.setattr(embeddings, "E5Embedder", lambda: embedded)
    app = create_app(Settings(database_password="test-only", llm_reasoning_effort="omit"))
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http:
            response = await http.post("/agent", json={"question": "SHP-1の状態は？"})
        assert response.status_code == 200
        assert response.json()["steps"][0]["tool"] == "search_shipments"
        assert "test-only" not in response.text
    assert disposed == [True] and app.state.agent is None
