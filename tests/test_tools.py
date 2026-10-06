"""Input/dispatch/error tests independent of PostgreSQL and the LLM."""

import asyncio
from contextlib import asynccontextmanager

import pytest
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from logi_scope.tools import BusinessTools, ToolExecutionError, UnknownTool, tool_definitions


@pytest.mark.parametrize("name,arguments", [
    ("search_customers", {"customer_name": "   "}),
    ("search_customers", {"customer_name": 123}),
    ("search_customers", {"customer_name": "青空", "sql": "anything"}),
    ("search_customers", {"customer_name": "青空", "limit": 21}),
    ("search_shipments", {}),
    ("search_shipments", {"customer_id": "101"}),
    ("search_shipments", {"customer_id": True}),
    ("search_shipments", {"customer_id": -1}),
    ("search_shipments", {"status": "lost"}),
    ("search_shipments", {"status": ""}),
    ("search_shipments", {"status": 1}),
    ("get_shipment_details", {"shipment_id": ""}),
    ("get_shipment_details", {"shipment_id": "SHP-DEMO-001", "event_limit": 0}),
    ("get_inquiry", {"inquiry_id": 0}),
    ("search_knowledge", {"query": " "}),
    ("search_knowledge", {"query": "遅延", "kind": "anything"}),
])
async def test_invalid_input_is_rejected_before_database_access(name, arguments):
    tools = BusinessTools(None)
    with pytest.raises(ValidationError):
        await tools.execute(name, arguments)


async def test_unknown_tool_is_not_dispatched():
    with pytest.raises(UnknownTool, match="unknown_tool"):
        await BusinessTools(None).execute("execute_sql", {"query": "anything"})


def test_normalized_arguments_and_exposed_schema():
    args = BusinessTools(None).validate("search_customers", {"customer_name": " 青空 "})
    assert args.customer_name == "青空"
    definitions = tool_definitions()
    assert {d["function"]["name"] for d in definitions} == {
        "search_customers", "search_shipments", "get_shipment_details", "get_inquiry",
    }
    assert all(d["function"]["parameters"]["additionalProperties"] is False for d in definitions)


async def test_database_error_is_sanitized():
    tools = BusinessTools(None)

    @asynccontextmanager
    async def failing_session():
        raise SQLAlchemyError("private database detail")
        yield

    tools.sessions = failing_session
    with pytest.raises(ToolExecutionError) as error:
        await tools.execute("get_inquiry", {"inquiry_id": 501})
    assert str(error.value) == "database_error"
    assert error.value.__suppress_context__


async def test_timeout_cancels_query_and_closes_session():
    tools = BusinessTools(None, timeout=0.01)
    closed = []

    class SlowSession:
        async def get(self, *_):
            await asyncio.sleep(10)

    @asynccontextmanager
    async def slow_session():
        try:
            yield SlowSession()
        finally:
            closed.append(True)

    tools.sessions = slow_session
    with pytest.raises(ToolExecutionError, match="timeout"):
        await tools.execute("get_inquiry", {"inquiry_id": 501})
    assert closed == [True]
