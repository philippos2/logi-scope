"""Runtime configuration, independent of administrative DB credentials."""

from typing import Literal

from pydantic import Field, HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Compose supplies environment variables. Do not load the host's admin .env.
    model_config = SettingsConfigDict(extra="ignore")

    llm_base_url: HttpUrl = "http://host.docker.internal:11434/v1"
    llm_model: str = Field(default="logiscope-qwen30-probe", min_length=1)
    llm_request_timeout: float = Field(default=300, gt=0, le=1800)
    llm_max_tokens: int = Field(default=1200, ge=100, le=4000)
    llm_reasoning_effort: Literal["none", "low", "medium", "high", "omit"] | None = "none"
    agent_max_llm_calls: int = Field(default=8, ge=1, le=100)
    agent_max_tool_attempts: int = Field(default=12, ge=1, le=100)
    agent_total_timeout: float = Field(default=900, gt=0, le=3600)
    database_host: str = "db"
    database_port: int = Field(default=5432, gt=0, le=65535)
    database_name: str = "logi_scope"
    database_password: SecretStr | None = None
