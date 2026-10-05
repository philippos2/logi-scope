"""Alembic uses management credentials, not runtime configuration."""

from alembic import context

from logi_scope.db.models import Base
from logi_scope.manage import ManagementSettings


def migrate(connection):
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError("Use an online management connection for role/extension migration")
else:
    connection = context.config.attributes.get("connection")
    if connection is not None:
        migrate(connection)
    else:
        engine = ManagementSettings().engine()
        try:
            with engine.connect() as connection:
                migrate(connection)
        finally:
            engine.dispose()
