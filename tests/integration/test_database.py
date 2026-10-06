"""Real PostgreSQL checks; no SQLite substitute and no external LLM."""

import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import delete, func, insert, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session, selectinload

from logi_scope.config import Settings
from logi_scope.db.models import Customer, DeliveryEvent, Inquiry, Shipment
from logi_scope.db.session import create_reader_engine
from logi_scope.manage import ManagementSettings, seed_business_data

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("LOGISCOPE_DB_TESTS") != "1", reason="real DB tests are opt-in"),
]


@pytest.fixture
def admin_engine():
    engine = ManagementSettings().engine()
    yield engine
    engine.dispose()


@pytest.fixture
async def reader_engine():
    engine = create_reader_engine(Settings())
    yield engine
    await engine.dispose()


async def test_reader_follows_customer_shipment_event_and_inquiry(reader_engine):
    from sqlalchemy.ext.asyncio import AsyncSession

    async with AsyncSession(reader_engine) as session:
        customer = await session.scalar(select(Customer).where(Customer.id == 101).options(
            selectinload(Customer.shipments).selectinload(Shipment.events),
            selectinload(Customer.inquiries),
        ))
        assert customer.name == "デモ青空商店"
        shipment = customer.shipments[0]
        assert shipment.id == "SHP-DEMO-001" and shipment.status == "delayed"
        incident = next(e for e in shipment.events if e.incident_id)
        assert incident.incident_id == "INC-DEMO-001"
        assert incident.occurred_at.astimezone(timezone.utc).hour == 23
        report = Path("seed/docs/incident-demo-001.md").read_text()
        assert incident.incident_id in report and shipment.id in report
        inquiry = next(i for i in customer.inquiries if i.id == 502)
        assert "センサー故障" in inquiry.resolution


async def test_reader_preserves_ambiguity_and_missing_data(reader_engine):
    from sqlalchemy.ext.asyncio import AsyncSession

    async with AsyncSession(reader_engine) as session:
        candidates = (await session.scalars(select(Customer).where(Customer.name == "デモ双葉商会"))).all()
        assert {c.id for c in candidates} == {201, 202}
        assert len({c.branch for c in candidates}) == 2
        assert await session.get(Shipment, "SHP-NOT-FOUND") is None


@pytest.mark.parametrize("operation", [
    insert(Customer).values(id=900001, name="権限テスト", branch="架空"),
    update(Customer).where(Customer.id == 101).values(name="変更不可"),
    delete(Customer).where(Customer.id == 101),
    text("CREATE TABLE public.reader_must_not_create (id integer)"),
])
async def test_db_permissions_reject_writes_even_without_readonly_default(reader_engine, operation):
    async with reader_engine.connect() as connection:
        transaction = await connection.begin()
        try:
            # Prove actual ACLs enforce read-only, independent of transaction default.
            await connection.execute(text("SET LOCAL transaction_read_only = off"))
            with pytest.raises(DBAPIError) as error:
                await connection.execute(operation)
            assert error.value.orig.sqlstate == "42501"
        finally:
            await transaction.rollback()


def test_seed_can_be_reapplied_without_duplicate_records(admin_engine):
    with admin_engine.connect() as connection:
        transaction = connection.begin()
        try:
            with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
                seed_business_data(session, Path("seed/business.json"))
                seed_business_data(session, Path("seed/business.json"))
                assert session.scalar(select(func.count()).select_from(Customer).where(
                    Customer.id.in_([101, 102, 201, 202]))) == 4
                assert session.scalar(select(func.count()).select_from(Shipment).where(
                    Shipment.id.like("SHP-DEMO-%"))) == 4
                assert session.scalar(select(func.count()).select_from(DeliveryEvent).where(
                    DeliveryEvent.id.between(1001, 1005))) == 5
                assert session.scalar(select(func.count()).select_from(Inquiry).where(
                    Inquiry.id.in_([501, 502]))) == 2
                assert session.scalar(select(func.count()).select_from(Customer).where(
                    Customer.id.between(301, 310))) == 10
                assert session.scalar(select(func.count()).select_from(Shipment).where(
                    Shipment.id.like("SHP-EXTRA-%"))) == 30
                assert session.scalar(select(func.count()).select_from(DeliveryEvent).where(
                    DeliveryEvent.id.between(2002, 2061))) == 60
                assert session.scalar(select(func.count()).select_from(Inquiry).where(
                    Inquiry.id.between(601, 610))) == 10
        finally:
            transaction.rollback()


def test_foreign_key_rejects_unknown_customer(admin_engine):
    with Session(admin_engine) as session:
        session.add(Shipment(
            id="SHP-FK-TEST", customer_id=900001, status="in_transit",
            destination="架空", expected_delivery_at=datetime.now(timezone.utc),
        ))
        with pytest.raises(IntegrityError) as error:
            session.flush()
        assert error.value.orig.sqlstate == "23503"
        session.rollback()


def test_pgvector_and_restricted_role_are_configured(admin_engine):
    with admin_engine.connect() as connection:
        version = connection.scalar(text("SELECT extversion FROM pg_extension WHERE extname = 'vector'"))
        assert version
        role = connection.execute(text(
            "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls "
            "FROM pg_roles WHERE rolname = 'logi_scope_reader'"
        )).one()
        assert not any(role)
        assert connection.scalar(text(
            "SELECT count(*) FROM pg_auth_members WHERE member = "
            "(SELECT oid FROM pg_roles WHERE rolname = 'logi_scope_reader')"
        )) == 0


async def test_runtime_authenticates_as_reader(reader_engine):
    async with reader_engine.connect() as connection:
        assert await connection.scalar(text("SELECT current_user")) == "logi_scope_reader"
        assert await connection.scalar(text("SHOW transaction_read_only")) == "on"


def test_migration_downgrade_preserves_missing_shipments(admin_engine):
    from alembic import command
    from alembic.config import Config

    with admin_engine.connect() as connection, connection.begin() as transaction:
        config = Config("alembic.ini")
        config.attributes["connection"] = connection
        with pytest.raises(RuntimeError, match="Resolve missing shipment records"):
            command.downgrade(config, "0002_search_chunks")
        assert connection.scalar(select(func.count()).select_from(Shipment).where(
            Shipment.status == "missing")) == 2
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0003_missing_shipments"
        transaction.rollback()


def test_status_migration_can_round_trip_without_missing_records(admin_engine):
    from alembic import command
    from alembic.config import Config

    with admin_engine.connect() as connection, connection.begin() as transaction:
        # Changes are confined to this rolled-back test transaction.
        connection.execute(update(Shipment).where(Shipment.status == "missing").values(status="delayed"))
        config = Config("alembic.ini")
        config.attributes["connection"] = connection
        command.downgrade(config, "0002_search_chunks")
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0002_search_chunks"
        command.upgrade(config, "head")
        connection.execute(update(Shipment).where(Shipment.id == "SHP-EXTRA-011").values(status="missing"))
        assert connection.scalar(select(Shipment.status).where(Shipment.id == "SHP-EXTRA-011")) == "missing"
        transaction.rollback()
