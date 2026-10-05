"""Runtime configuration, independent of administrative DB credentials."""

from pydantic import Field, HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Compose supplies environment variables. Do not load the host's admin .env.
    model_config = SettingsConfigDict(extra="ignore")

    llm_base_url: HttpUrl = "http://host.docker.internal:11434/v1"
    llm_model: str = Field(default="logiscope-qwen30-probe", min_length=1)
    llm_request_timeout: float = Field(default=300, gt=0, le=1800)
