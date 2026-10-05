"""Runtime connections always authenticate as the restricted reader role."""

from sqlalchemy import URL
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from logi_scope.config import Settings


def create_reader_engine(settings: Settings) -> AsyncEngine:
    if settings.database_password is None:
        raise ValueError("DATABASE_PASSWORD is required for business tools")
    url = URL.create(
        "postgresql+psycopg", username="logi_scope_reader",
        password=settings.database_password.get_secret_value(),
        host=settings.database_host, port=settings.database_port,
        database=settings.database_name,
    )
    return create_async_engine(
        url, pool_pre_ping=True, hide_parameters=True,
        connect_args={"connect_timeout": 5, "options": "-c statement_timeout=10000"},
    )
