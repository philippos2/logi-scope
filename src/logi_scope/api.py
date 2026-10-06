"""HTTP API and lifecycle for the read-only investigation service."""

import asyncio
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import StringConstraints
from typing import Annotated

from logi_scope.agent import AgentLoop, AgentResponse, AgentUnavailable, Limits, StrictModel
from logi_scope.config import Settings
from logi_scope.db.session import create_reader_engine
from logi_scope.llm import OpenAICompatibleClient
from logi_scope.tools import BusinessTools


class HealthResponse(StrictModel):
    status: str


class AgentRequest(StrictModel):
    question: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]


def create_app(settings: Settings | None = None, *, agent=None) -> FastAPI:
    settings = settings if settings is not None else Settings()

    @asynccontextmanager
    async def lifespan(app):
        if agent is not None or settings.database_password is None:
            yield
            return
        from logi_scope.rag.embeddings import E5Embedder
        engine = create_reader_engine(settings)
        try:
            async with httpx.AsyncClient(trust_env=False) as http:
                embedder = await asyncio.to_thread(E5Embedder)
                client = OpenAICompatibleClient(
                    http, base_url=str(settings.llm_base_url), model=settings.llm_model,
                    timeout=settings.llm_request_timeout, max_tokens=settings.llm_max_tokens,
                    reasoning_effort=None if settings.llm_reasoning_effort == "omit" else settings.llm_reasoning_effort,
                )
                app.state.agent = AgentLoop(client, BusinessTools(engine, embedder=embedder), limits=Limits(
                    max_llm_calls=settings.agent_max_llm_calls,
                    max_tool_attempts=settings.agent_max_tool_attempts,
                    total_timeout=settings.agent_total_timeout,
                    llm_timeout=settings.llm_request_timeout,
                ))
                yield
                app.state.agent = None
        finally:
            app.state.agent = None
            await engine.dispose()

    app = FastAPI(title="LogiScope", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.agent = agent
    app.state.investigation_lock = asyncio.Lock()

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        # Liveness only; this does not claim DB/LLM readiness.
        return HealthResponse(status="ok")

    @app.post("/agent", response_model=AgentResponse, response_model_exclude_none=True)
    async def investigate(request: AgentRequest) -> AgentResponse:
        runner = app.state.agent
        if runner is None:
            raise HTTPException(503, detail={"code": "agent_not_ready", "message": "Agentの準備ができていません。"})
        if app.state.investigation_lock.locked():
            raise HTTPException(503, detail={"code": "agent_busy", "message": "別の調査を実行中です。"})
        async with app.state.investigation_lock:
            try:
                return await runner.run(request.question)
            except AgentUnavailable as error:
                timeout = str(error) == "timeout"
                raise HTTPException(504 if timeout else 502, detail={
                    "code": "llm_timeout" if timeout else "llm_unavailable",
                    "message": "LLMから回答を取得できませんでした。",
                }) from None

    return app


app = create_app()
