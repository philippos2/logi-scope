"""Business tools run with the actual restricted PostgreSQL role."""

import os

import pytest

from logi_scope.config import Settings
from logi_scope.db.session import create_reader_engine
from logi_scope.tools import BusinessTools

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.environ.get("LOGISCOPE_DB_TESTS") != "1", reason="real DB tests are opt-in"),
]


@pytest.fixture
async def tools():
    engine = create_reader_engine(Settings())
    yield BusinessTools(engine)
    assert engine.pool.checkedout() == 0
    await engine.dispose()


async def test_customer_candidates_are_preserved_and_can_be_disambiguated(tools):
    result = await tools.execute("search_customers", {"customer_name": "双葉"})
    assert {r["id"] for r in result.records} == {201, 202}
    assert {s.id for s in result.sources} == {"customer:201", "customer:202"}
    result = await tools.execute("search_customers", {"customer_name": "双葉", "branch": "架空北営業所"})
    assert [r["id"] for r in result.records] == [201]


async def test_customer_search_escapes_sql_wildcards(tools):
    for name in ("%", "_", "' OR 1=1 --"):
        assert not (await tools.execute("search_customers", {"customer_name": name})).records


async def test_result_limit_reports_hidden_candidates(tools):
    result = await tools.execute("search_customers", {"customer_name": "双葉", "limit": 1})
    assert len(result.records) == len(result.sources) == 1
    assert result.truncated is True


async def test_multistage_ids_and_incident_reference(tools):
    customers = await tools.execute("search_customers", {"customer_name": "青空"})
    shipments = await tools.execute("search_shipments", {"customer_id": customers.records[0]["id"]})
    details = await tools.execute("get_shipment_details", {"shipment_id": shipments.records[0]["id"]})
    assert details.records[0]["status"] == "delayed"
    assert details.records[0]["events"][0]["incident_id"] == "INC-DEMO-001"
    assert {s.id for s in details.sources} == {"shipment:SHP-DEMO-001", "delivery_event:1001", "delivery_event:1002"}


async def test_simple_shipment_status_and_combined_filters(tools):
    result = await tools.execute("search_shipments", {"shipment_id": "SHP-DEMO-002"})
    assert result.records[0]["status"] == "delivered"
    assert result.sources[0].id == "shipment:SHP-DEMO-002"
    mismatch = await tools.execute("search_shipments", {"shipment_id": "SHP-DEMO-002", "customer_id": 101})
    assert mismatch.records == mismatch.sources == []


async def test_event_limit_reports_omission(tools):
    result = await tools.execute("get_shipment_details", {"shipment_id": "SHP-DEMO-001", "event_limit": 1})
    assert len(result.records[0]["events"]) == 1 and result.truncated
    assert result.sources[-1].id == "delivery_event:1002"


async def test_inquiry_original_includes_resolution(tools):
    result = await tools.execute("get_inquiry", {"inquiry_id": 501})
    assert result.records[0]["shipment_id"] == "SHP-DEMO-002"
    assert "11時15分" in result.records[0]["resolution"]
    assert result.sources[0].id == "inquiry:501"


@pytest.mark.parametrize("name,args", [
    ("search_customers", {"customer_name": "不存在の架空顧客"}),
    ("search_shipments", {"shipment_id": "SHP-NOT-FOUND"}),
    ("get_shipment_details", {"shipment_id": "SHP-NOT-FOUND"}),
    ("get_inquiry", {"inquiry_id": 999999}),
])
async def test_no_match_is_a_successful_empty_result(tools, name, args):
    result = await tools.execute(name, args)
    assert result.records == result.sources == []
    assert result.truncated is False


async def test_delivery_timestamps_are_returned_in_japanese_time(tools):
    result = await tools.execute("get_shipment_details", {"shipment_id": "SHP-DEMO-002"})
    assert result.records[0]["events"][0]["occurred_at"] == "2026-10-02T11:15:00+09:00"
    assert result.records[0]["expected_delivery_at"].endswith("+09:00")
    inquiry = await tools.execute("get_inquiry", {"inquiry_id": 501})
    assert inquiry.records[0]["created_at"].endswith("+09:00")


async def test_status_search_does_not_require_an_individual_target(tools):
    result = await tools.execute("search_shipments", {"status": "missing"})
    assert {r["id"] for r in result.records} == {"SHP-EXTRA-011", "SHP-EXTRA-014"}
    assert all(r["status"] == "missing" for r in result.records)
    assert not result.truncated
    for row in result.records:
        details = await tools.execute("get_shipment_details", {"shipment_id": row["id"]})
        assert any("所在不明として登録" in e["description"] for e in details.records[0]["events"])


async def test_status_conditions_combine_and_preserve_truncation(tools):
    narrowed = await tools.execute("search_shipments", {"customer_id": 304, "status": "missing"})
    assert [r["id"] for r in narrowed.records] == ["SHP-EXTRA-011"]
    empty = await tools.execute("search_shipments", {"customer_id": 101, "status": "missing"})
    assert empty.records == empty.sources == [] and not empty.truncated
    conflicting = await tools.execute("search_shipments", {"shipment_id": "SHP-DEMO-002", "status": "missing"})
    assert conflicting.records == []
    delayed = await tools.execute("search_shipments", {"status": "delayed"})
    assert {r["id"] for r in delayed.records} == {"SHP-DEMO-001", "SHP-EXTRA-005", "SHP-EXTRA-008", "SHP-EXTRA-017"}
    limited = await tools.execute("search_shipments", {"status": "in_transit", "limit": 2})
    assert len(limited.records) == 2 and limited.truncated
