"""Foundation checks without an external LLM or database."""

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from logi_scope.api import create_app
from logi_scope.config import Settings


async def test_health_does_not_require_external_services():
    settings = Settings(llm_base_url="http://127.0.0.1:1/v1")
    async with AsyncClient(
        transport=ASGITransport(app=create_app(settings)), base_url="http://test"
    ) as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_llm_connection_can_be_overridden_by_environment(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:1234/v1")
    monkeypatch.setenv("LLM_MODEL", "another-local-model")
    monkeypatch.setenv("LLM_REQUEST_TIMEOUT", "600")
    settings = Settings()
    assert str(settings.llm_base_url) == "http://localhost:1234/v1"
    assert settings.llm_model == "another-local-model"
    assert settings.llm_request_timeout == 600


@pytest.mark.parametrize("timeout", [0, -1, 1801])
def test_timeout_must_be_positive_and_bounded(timeout):
    with pytest.raises(ValidationError):
        Settings(llm_request_timeout=timeout)
