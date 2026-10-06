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
        assert not (await tools.execute("search_customers", {"customer_name": "デモ", "branch": name})).records


async def test_partial_branch_preserves_multiple_candidates(tools):
    unique = await tools.execute("search_customers", {"customer_name": "銀河", "branch": "第2営業所"})
    assert [r["id"] for r in unique.records] == [402]
    ambiguous = await tools.execute("search_customers", {"customer_name": "銀河", "branch": "営業所"})
    assert {r["id"] for r in ambiguous.records} == {401, 402}


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
    assert result.records[0]["expected_delivery_basis"] == "registered_schedule"
    inquiry = await tools.execute("get_inquiry", {"inquiry_id": 501})
    assert inquiry.records[0]["created_at"].endswith("+09:00")


@pytest.mark.parametrize("shipment_id", ["SHP-DEMO-001", "SHP-EXPAND-021"])
async def test_disrupted_shipment_schedule_is_not_a_revised_arrival_estimate(tools, shipment_id):
    listing = await tools.execute("search_shipments", {"shipment_id": shipment_id})
    details = await tools.execute("get_shipment_details", {"shipment_id": shipment_id})
    assert listing.records[0]["expected_delivery_basis"] == "original_schedule"
    assert details.records[0]["expected_delivery_basis"] == "original_schedule"
    assert "expected_delivery_at" not in listing.records[0]
    assert "expected_delivery_at" not in details.records[0]
    assert listing.records[0]["original_expected_delivery_at"] == details.records[0]["original_expected_delivery_at"]


async def test_status_search_does_not_require_an_individual_target(tools):
    result = await tools.execute("search_shipments", {"status": "missing"})
    assert {r["id"] for r in result.records} == {"SHP-EXTRA-011", "SHP-EXTRA-014", "SHP-EXPAND-021", "SHP-EXPAND-024"}
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
    assert {r["id"] for r in delayed.records} == {"SHP-DEMO-001", "SHP-EXTRA-005", "SHP-EXTRA-008", "SHP-EXTRA-017",
        "SHP-EXPAND-003", "SHP-EXPAND-006", "SHP-EXPAND-009",
        "SHP-EXPAND-012", "SHP-EXPAND-015", "SHP-EXPAND-018"}
    limited = await tools.execute("search_shipments", {"status": "in_transit", "limit": 2})
    assert len(limited.records) == 2 and limited.truncated


@pytest.mark.parametrize("status,total", [
    ("in_transit", 49), ("delayed", 10), ("delivered", 27), ("missing", 4),
])
async def test_shipment_total_count_is_independent_of_example_limit(tools, status, total):
    limited = await tools.execute("search_shipments", {"status": status, "limit": 1})
    default = await tools.execute("search_shipments", {"status": status})
    assert limited.total_count == default.total_count == total
    assert len(limited.records) == 1 and limited.truncated
    assert len(default.records) == min(10, total)
    assert default.truncated == (total > 10)
    assert len(default.sources) == len(default.records)


async def test_shipment_counts_apply_all_search_conditions(tools):
    all_customer_shipments = await tools.execute("search_shipments", {"customer_id": 304, "limit": 1})
    assert all_customer_shipments.total_count == 3 and all_customer_shipments.truncated
    one = await tools.execute("search_shipments", {"customer_id": 304, "status": "missing"})
    assert one.total_count == 1 and not one.truncated
    empty = await tools.execute("search_shipments", {"customer_id": 101, "status": "missing"})
    assert empty.total_count == 0 and empty.records == [] and not empty.truncated
    mismatch = await tools.execute("search_shipments", {
        "customer_id": 101, "shipment_id": "SHP-DEMO-002", "status": "delivered",
    })
    assert mismatch.total_count == 0 and mismatch.records == []


async def test_whole_collection_counts_include_rows_beyond_examples(tools):
    result = await tools.execute("search_shipments", {"scope": "all", "limit": 1})
    assert len(result.records) == len(result.sources) == 1 and result.truncated
    assert result.total_count == 90
    assert result.status_counts == {"in_transit": 49, "delayed": 10, "delivered": 27, "missing": 4}
    assert sum(result.status_counts.values()) == result.total_count
    # The one displayed delayed example does not define the entire distribution.
    assert result.records[0]["status"] == "delayed"


@pytest.mark.parametrize("name,ids,branch", [
    ("デモ銀河資材", {401, 402}, "架空拡充分第2営業所"),
    ("デモ霞色商会", {403, 404}, "架空拡充分第4営業所"),
])
async def test_new_names_can_be_resolved_by_branch(tools, name, ids, branch):
    candidates = await tools.execute("search_customers", {"customer_name": name})
    assert {r["id"] for r in candidates.records} == ids
    selected = await tools.execute("search_customers", {"customer_name": name, "branch": branch})
    assert len(selected.records) == 1
    customer_id = selected.records[0]["id"]
    shipments = await tools.execute("search_shipments", {"customer_id": customer_id})
    assert shipments.total_count == 3
    assert {r["status"] for r in shipments.records} == {"delivered", "in_transit", "delayed"}
    assert all(r["customer_id"] == customer_id for r in shipments.records)


@pytest.mark.parametrize("shipment_id,incident_id,inquiry_id", [
    ("SHP-EXPAND-003", "INC-EXPAND-001", 701),
    ("SHP-EXPAND-012", "INC-EXPAND-002", 704),
])
async def test_added_delay_events_and_original_inquiries_agree(tools, shipment_id, incident_id, inquiry_id):
    details = await tools.execute("get_shipment_details", {"shipment_id": shipment_id})
    assert details.records[0]["status"] == "delayed"
    assert details.records[0]["events"][0]["incident_id"] == incident_id
    original = await tools.execute("get_inquiry", {"inquiry_id": inquiry_id})
    assert original.records[0]["shipment_id"] == shipment_id
    assert incident_id in original.records[0]["resolution"]


async def test_added_customer_filters_return_empty_without_reclassifying_delays(tools):
    result = await tools.execute("search_shipments", {"customer_id": 401, "status": "missing"})
    assert result.total_count == 0 and result.records == result.sources == []
    delivered = await tools.execute("search_shipments", {"customer_id": 416, "status": "delivered"})
    assert delivered.total_count == 1
    assert delivered.records[0]["id"] == "SHP-EXPAND-053"
