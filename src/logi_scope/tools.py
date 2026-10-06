"""Registered, validated, read-only business tools. No LLM orchestration here."""

import asyncio
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from logi_scope.db.models import Customer, DeliveryEvent, Inquiry, Shipment

SearchText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
PositiveId = Annotated[int, Field(gt=0)]
ResultLimit = Annotated[int, Field(ge=1, le=20)]


class Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class CustomerSearch(Arguments):
    customer_name: SearchText
    branch: SearchText | None = None
    limit: ResultLimit = 10


class ShipmentSearch(Arguments):
    customer_id: PositiveId | None = None
    shipment_id: Identifier | None = None
    limit: ResultLimit = 10

    @model_validator(mode="after")
    def require_search_condition(self):
        if self.customer_id is None and self.shipment_id is None:
            raise ValueError("customer_id or shipment_id is required")
        return self


class ShipmentDetails(Arguments):
    shipment_id: Identifier
    event_limit: ResultLimit = 20


class InquiryLookup(Arguments):
    inquiry_id: PositiveId


class Source(BaseModel):
    id: str
    kind: Literal["customer", "shipment", "delivery_event", "inquiry"]
    record_id: int | str


class ToolResult(BaseModel):
    records: list[dict[str, Any]]
    sources: list[Source]
    truncated: bool = False


TOOLS = {
    "search_customers": (CustomerSearch, "顧客名の部分一致で候補を検索する。同名候補を保持し、営業所で絞り込める。"),
    "search_shipments": (ShipmentSearch, "顧客IDまたは荷物IDで荷物を検索する。両方指定すると両条件で絞り込む。"),
    "get_shipment_details": (ShipmentDetails, "荷物IDで配送状況と配送イベントを取得する。障害IDを関連文書の検索に使える。"),
    "get_inquiry": (InquiryLookup, "問い合わせIDでDB上の正本を取得する。検索チャンクとは異なる。"),
}


def tool_definitions() -> list[dict]:
    return [{"type": "function", "function": {
        "name": name, "description": description, "parameters": model.model_json_schema(),
    }} for name, (model, description) in TOOLS.items()]


class UnknownTool(ValueError):
    pass


class ToolExecutionError(RuntimeError):
    """Contains only a public error code, never a DB exception message."""


def reference(kind: str, record_id: int | str) -> Source:
    return Source(id=f"{kind}:{record_id}", kind=kind, record_id=record_id)


def shipment_record(row: Shipment) -> dict:
    return {"id": row.id, "customer_id": row.customer_id, "status": row.status,
            "destination": row.destination, "expected_delivery_at": row.expected_delivery_at.isoformat()}


class BusinessTools:
    def __init__(self, engine: AsyncEngine, timeout: float = 15):
        if not 0 < timeout <= 60:
            raise ValueError("tool timeout must be between 0 and 60 seconds")
        self.sessions = async_sessionmaker(engine, expire_on_commit=False)
        self.timeout = timeout

    def validate(self, name: str, arguments: dict) -> Arguments:
        if name not in TOOLS:
            raise UnknownTool("unknown_tool")
        return TOOLS[name][0].model_validate(arguments)

    async def execute(self, name: str, arguments: dict) -> ToolResult:
        validated = self.validate(name, arguments)
        try:
            return await asyncio.wait_for(self._query(name, validated), timeout=self.timeout)
        except TimeoutError:
            raise ToolExecutionError("timeout") from None
        except SQLAlchemyError:
            raise ToolExecutionError("database_error") from None

    async def _query(self, name: str, args: Arguments) -> ToolResult:
        # Session/transaction closes before returning a result to an Agent/LLM.
        async with self.sessions() as session:
            if name == "search_customers":
                query = select(Customer).where(Customer.name.contains(args.customer_name, autoescape=True))
                if args.branch is not None:
                    query = query.where(Customer.branch == args.branch)
                rows = (await session.scalars(query.order_by(Customer.id).limit(args.limit + 1))).all()
                return ToolResult(
                    records=[{"id": r.id, "name": r.name, "branch": r.branch} for r in rows[:args.limit]],
                    sources=[reference("customer", r.id) for r in rows[:args.limit]],
                    truncated=len(rows) > args.limit,
                )
            if name == "search_shipments":
                query = select(Shipment)
                if args.customer_id is not None:
                    query = query.where(Shipment.customer_id == args.customer_id)
                if args.shipment_id is not None:
                    query = query.where(Shipment.id == args.shipment_id)
                rows = (await session.scalars(query.order_by(Shipment.id).limit(args.limit + 1))).all()
                return ToolResult(records=[shipment_record(r) for r in rows[:args.limit]],
                                  sources=[reference("shipment", r.id) for r in rows[:args.limit]],
                                  truncated=len(rows) > args.limit)
            if name == "get_shipment_details":
                shipment = await session.get(Shipment, args.shipment_id)
                if shipment is None:
                    return ToolResult(records=[], sources=[])
                events = (await session.scalars(select(DeliveryEvent).where(
                    DeliveryEvent.shipment_id == shipment.id
                ).order_by(DeliveryEvent.occurred_at.desc(), DeliveryEvent.id.desc()).limit(args.event_limit + 1))).all()
                visible = events[:args.event_limit]
                record = shipment_record(shipment)
                record["events"] = [{"id": e.id, "occurred_at": e.occurred_at.isoformat(),
                    "location": e.location, "description": e.description[:2000], "incident_id": e.incident_id}
                    for e in visible]
                return ToolResult(records=[record], sources=[reference("shipment", shipment.id)] +
                    [reference("delivery_event", e.id) for e in visible],
                    truncated=len(events) > args.event_limit or any(len(e.description) > 2000 for e in visible))
            if name == "get_inquiry":
                row = await session.get(Inquiry, args.inquiry_id)
                if row is None:
                    return ToolResult(records=[], sources=[])
                return ToolResult(records=[{"id": row.id, "customer_id": row.customer_id,
                    "shipment_id": row.shipment_id, "created_at": row.created_at.isoformat(),
                    "subject": row.subject, "body": row.body[:2000], "resolution": row.resolution[:2000]}],
                    sources=[reference("inquiry", row.id)], truncated=len(row.body) > 2000 or len(row.resolution) > 2000)
            raise UnknownTool("unknown_tool")
