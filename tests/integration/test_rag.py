"""PostgreSQL/pgvector behavior with deterministic vectors, separate from E5 eval."""

import os
from pathlib import Path

import pytest
from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.orm import Session

from logi_scope.config import Settings
from logi_scope.db.models import Chunk, Inquiry
from logi_scope.db.session import create_reader_engine
from logi_scope.manage import ManagementSettings
from logi_scope.rag.documents import SourceDocument
from logi_scope.rag.embeddings import DIMENSIONS
from logi_scope.rag.ingest import IngestSettings, load_sources, prepare_index, replace_index
from logi_scope.tools import BusinessTools

pytestmark = [pytest.mark.integration, pytest.mark.skipif(
    os.environ.get("LOGISCOPE_DB_TESTS") != "1", reason="real DB tests are opt-in")]


class FakeEmbedder:
    def encode(self, texts, *, query=False):
        return [[1.0] + [0.0] * (DIMENSIONS - 1) for _ in texts]


@pytest.fixture
def admin_engine():
    engine = ManagementSettings().engine()
    yield engine
    engine.dispose()


def test_loads_inquiry_originals_and_file_sources(admin_engine):
    docs = load_sources(admin_engine, Path("."))
    assert {d.inquiry_id for d in docs if d.kind == "inquiry"} == {501, 502, *range(601, 611), *range(701, 709)}
    assert len([d for d in docs if d.kind == "document"]) == 13


def test_regeneration_removes_deleted_sources_and_does_not_duplicate(admin_engine):
    docs = [SourceDocument(kind="inquiry", title="架空", text="対応内容", inquiry_id=501)]
    with admin_engine.connect() as connection, connection.begin() as transaction:
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            replace_index(session, prepare_index(docs, FakeEmbedder()))
            replace_index(session, prepare_index(docs, FakeEmbedder()))
            assert session.scalar(select(func.count()).select_from(Chunk)) == 1
            assert session.scalar(select(Chunk.inquiry_id)) == 501
            replace_index(session, [])
            assert session.scalar(select(func.count()).select_from(Chunk)) == 0
        transaction.rollback()


def test_failed_replacement_rolls_back_to_previous_index(admin_engine):
    with admin_engine.connect() as connection, connection.begin() as transaction:
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            before = set(session.scalars(select(Chunk.id)))
            invalid = prepare_index([SourceDocument(kind="inquiry", title="架空", text="本文", inquiry_id=999999)], FakeEmbedder())
            with pytest.raises(IntegrityError):
                with session.begin_nested():
                    replace_index(session, invalid)
            assert set(session.scalars(select(Chunk.id))) == before
        transaction.rollback()


async def test_vector_search_preserves_origin_for_original_lookup():
    # Real reader connection, deterministic query vector; no semantic quality claim.
    engine = create_reader_engine(Settings())
    try:
        tools = BusinessTools(engine, embedder=FakeEmbedder())
        result = await tools.execute("search_knowledge", {"query": "架空問い合わせ", "kind": "inquiry", "reference_id": "SHP-DEMO-002", "limit": 20})
        assert {r["inquiry_id"] for r in result.records} == {501}
        assert all(s.kind == "chunk" and s.origin_id.startswith("inquiry:") for s in result.sources)
        original = await tools.execute("get_inquiry", {"inquiry_id": result.records[0]["inquiry_id"]})
        assert original.sources[0].kind == "inquiry"
        assert engine.pool.checkedout() == 0
    finally:
        await engine.dispose()


async def test_exact_incident_filter_and_unknown_reference():
    engine = create_reader_engine(Settings())
    try:
        tools = BusinessTools(engine, embedder=FakeEmbedder())
        result = await tools.execute("search_knowledge", {"query": "遅延原因", "kind": "document", "reference_id": "INC-DEMO-001"})
        assert result.records
        assert all(r["document_path"] in ("seed/docs/incident-demo-001.md", "seed/docs/delay-demo-001.md") for r in result.records)
        missing = await tools.execute("search_knowledge", {"query": "遅延", "reference_id": "INC-NOT-FOUND"})
        assert missing.records == missing.sources == []
    finally:
        await engine.dispose()


@pytest.mark.parametrize("operation", [update(Inquiry).values(subject="変更不可"), text("CREATE TABLE public.ingest_must_not_create (id integer)")])
def test_ingest_role_cannot_write_business_data_or_ddl(operation):
    engine = IngestSettings().engine()
    try:
        with engine.connect() as connection:
            with pytest.raises(DBAPIError) as error:
                connection.execute(operation)
            assert error.value.orig.sqlstate == "42501"
            connection.rollback()
    finally:
        engine.dispose()


async def test_reader_cannot_delete_derived_index():
    engine: AsyncEngine = create_reader_engine(Settings())
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SET LOCAL transaction_read_only = off"))
            with pytest.raises(DBAPIError) as error:
                await connection.execute(delete(Chunk))
            assert error.value.orig.sqlstate == "42501"
            await connection.rollback()
    finally:
        await engine.dispose()


@pytest.mark.parametrize("reference,path", [
    ("INC-EXPAND-001", "seed/docs/incident-expand-001.md"),
    ("INC-EXPAND-002", "seed/docs/incident-expand-002.md"),
])
async def test_added_reports_are_isolated_by_business_reference(reference, path):
    engine = create_reader_engine(Settings())
    try:
        result = await BusinessTools(engine, embedder=FakeEmbedder()).execute(
            "search_knowledge", {"query": "遅延原因", "kind": "document", "reference_id": reference})
        assert result.records
        assert {r["document_path"] for r in result.records} == {path}
    finally:
        await engine.dispose()


async def test_shipment_without_inquiry_is_still_queryable():
    engine = create_reader_engine(Settings())
    try:
        tools = BusinessTools(engine, embedder=FakeEmbedder())
        result = await tools.execute("get_shipment_details", {"shipment_id": "SHP-EXPAND-053"})
        assert result.records[0]["status"] == "delivered"
        inquiry = await tools.execute("search_knowledge", {
            "query": "状況確認", "kind": "inquiry", "reference_id": "SHP-EXPAND-053"})
        assert inquiry.records == inquiry.sources == []
    finally:
        await engine.dispose()
