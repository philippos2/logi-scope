"""Application shell. The investigation endpoint is not implemented yet."""

from fastapi import FastAPI
from pydantic import BaseModel

from logi_scope.config import Settings


class HealthResponse(BaseModel):
    status: str


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="LogiScope", version="0.1.0")
    app.state.settings = settings if settings is not None else Settings()

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        # Liveness only; this does not claim DB/LLM readiness.
        return HealthResponse(status="ok")

    return app


app = create_app()
