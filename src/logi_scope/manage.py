"""Explicit management commands, never called by the runtime API."""

import argparse
import json
from datetime import datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from psycopg import sql
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL, create_engine, delete
from sqlalchemy.orm import Session

from logi_scope.db.models import Customer, DeliveryEvent, Inquiry, Shipment


class ManagementSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ADMIN_DATABASE_", extra="ignore")
    host: str = "db"
    port: int = 5432
    name: str = "logi_scope"
    user: str = "logi_scope_admin"
    password: SecretStr

    def engine(self):
        return create_engine(URL.create(
            "postgresql+psycopg", username=self.user,
            password=self.password.get_secret_value(), host=self.host,
            port=self.port, database=self.name,
        ), hide_parameters=True, connect_args={"connect_timeout": 5})


def initialize_database(reader_password: SecretStr, ingest_password: SecretStr) -> None:
    engine = ManagementSettings().engine()
    try:
        with engine.begin() as connection:
            config = Config("alembic.ini")
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
            # DDL only: identifiers and the secret are quoted by Psycopg.
            # Use the driver directly so password DDL cannot appear in SQLAlchemy logs.
            connection.connection.driver_connection.execute(sql.SQL(
                "ALTER ROLE logi_scope_reader PASSWORD {}"
            ).format(sql.Literal(reader_password.get_secret_value())))
            connection.connection.driver_connection.execute(sql.SQL(
                "ALTER ROLE logi_scope_ingest PASSWORD {}"
            ).format(sql.Literal(ingest_password.get_secret_value())))
            from logi_scope.delivery_updates import UpdateSettings
            connection.connection.driver_connection.execute(sql.SQL(
                "ALTER ROLE logi_scope_updater PASSWORD {}"
            ).format(sql.Literal(UpdateSettings().password.get_secret_value())))
    finally:
        engine.dispose()


def seed_business_data(session: Session, path: Path) -> None:
    data = json.loads(path.read_text())
    for key, model, dates in (
        ("customers", Customer, ()),
        ("shipments", Shipment, ("expected_delivery_at",)),
        ("delivery_events", DeliveryEvent, ("occurred_at",)),
        ("inquiries", Inquiry, ("created_at",)),
    ):
        for record in data[key]:
            row = dict(record)
            for field in dates:
                row[field] = datetime.fromisoformat(row[field])
            session.merge(model(**row))
        session.flush()


def main() -> None:
    parser = argparse.ArgumentParser(description="LogiScope database management")
    parser.add_argument("action", choices=["init", "seed", "updates-init", "updates-clear"])
    args = parser.parse_args()
    if args.action == "init":
        from logi_scope.config import Settings
        password = Settings().database_password
        if password is None:
            parser.error("DATABASE_PASSWORD must be configured")
        from logi_scope.rag.ingest import IngestSettings
        initialize_database(password, IngestSettings().password)
        print("Database migrations and reader/ingest credentials configured")
    else:
        engine = ManagementSettings().engine()
        try:
            with Session(engine) as session, session.begin():
                if args.action.startswith("updates-"):
                    session.execute(delete(DeliveryEvent).where(DeliveryEvent.shipment_id == "SHP-UPDATE-001"))
                    session.execute(delete(Shipment).where(Shipment.id == "SHP-UPDATE-001"))
                    session.execute(delete(Customer).where(Customer.id == 901))
                    if args.action == "updates-init":
                        seed_business_data(session, Path("seed/update-demo.json"))
                else:
                    seed_business_data(session, Path("seed/business.json"))
        finally:
            engine.dispose()
        print({"seed": "Fictional business seed applied", "updates-init": "Update demo initialized",
               "updates-clear": "Update demo removed"}[args.action])


if __name__ == "__main__":
    main()
