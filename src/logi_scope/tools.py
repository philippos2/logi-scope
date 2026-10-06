"""Registered, validated, read-only business tools. No LLM orchestration here."""

import asyncio
from datetime import timezone, timedelta
from typing import Annotated, Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from logi_scope.db.models import Customer, DeliveryEvent, Inquiry, Shipment

JAPAN_TIME = timezone(timedelta(hours=9))


SearchText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
PositiveId = Annotated[int, Field(gt=0)]
ResultLimit = Annotated[int, Field(ge=1, le=20)]
ShipmentStatus = Literal["in_transit", "delayed", "delivered", "missing"]


class Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class CustomerSearch(Arguments):
    customer_name: SearchText
    branch: SearchText | None = None
    limit: ResultLimit = 10


class ShipmentSearch(Arguments):
    customer_id: PositiveId | None = None
    shipment_id: Identifier | None = None
    status: ShipmentStatus | None = None
    scope: Literal["all"] | None = None
    limit: ResultLimit = 10

    @model_validator(mode="after")
    def require_search_condition(self):
        has_filter = self.customer_id is not None or self.shipment_id is not None or self.status is not None
        if self.scope == "all" and has_filter:
            raise ValueError("scope=all cannot be combined with filters")
        if not has_filter and self.scope != "all":
            raise ValueError("customer_id, shipment_id, status or explicit scope=all is required")
        return self


class ShipmentDetails(Arguments):
    shipment_id: Identifier
    event_limit: ResultLimit = 20


class InquiryLookup(Arguments):
    inquiry_id: PositiveId


class KnowledgeSearch(Arguments):
    query: SearchText
    kind: Literal["document", "inquiry"] | None = None
    reference_id: Identifier | None = None
    limit: ResultLimit = 5


class Source(BaseModel):
    id: str
    kind: Literal["customer", "shipment", "delivery_event", "inquiry", "chunk"]
    record_id: int | str | None = None
    path: str | None = None
    chunk_id: str | None = None
    origin_id: str | None = None
    source_revision: str | None = None


class ToolResult(BaseModel):
    records: list[dict[str, Any]]
    sources: list[Source]
    truncated: bool = False
    total_count: int | None = Field(default=None, ge=0)
    status_counts: dict[ShipmentStatus, int] | None = None


TOOLS = {
    "search_customers": (CustomerSearch, "顧客名の部分一致で候補を検索する。同名候補を保持し、営業所で絞り込める。"),
    "search_shipments": (ShipmentSearch, "顧客ID・荷物ID・配送状態で検索する。複数条件はAND。statusはin_transit=配送中、delayed=遅延、delivered=配達完了、missing=所在不明として登録済み。状態別の一覧・有無の質問ではID不要。全体の概要・内訳はscope=allで検索し、他の条件と併用しない。遅延だけで所在不明とは判断しない。total_countは条件に一致するDB上の総件数、scope=allのstatus_countsは状態別の総件数。recordsは取得上限までの例。truncated=trueでも件数は集計値を使い、例を全件とは扱わない。"),
    "get_shipment_details": (ShipmentDetails, "荷物IDで配送状況と配送イベントを取得する。障害IDを関連文書の検索に使える。"),
    "get_inquiry": (InquiryLookup, "問い合わせIDでDB上の正本を取得する。検索チャンクとは異なる。"),
    "search_knowledge": (KnowledgeSearch, "文書・過去問い合わせの派生チャンクを検索する。kindで種類、reference_idで荷物・障害IDを絞れる。問い合わせの正本は返されたinquiry_idでget_inquiryを使って取得する。類似度は事実の確定を意味しない。"),
}


def tool_definitions(*, include_knowledge: bool = False) -> list[dict]:
    return [{"type": "function", "function": {
        "name": name, "description": description, "parameters": model.model_json_schema(),
    }} for name, (model, description) in TOOLS.items() if include_knowledge or name != "search_knowledge"]


class UnknownTool(ValueError):
    pass


class ToolExecutionError(RuntimeError):
    """Contains only a public error code, never a DB exception message."""


def reference(kind: str, record_id: int | str) -> Source:
    return Source(id=f"{kind}:{record_id}", kind=kind, record_id=record_id)


def shipment_record(row: Shipment) -> dict:
    return {"id": row.id, "customer_id": row.customer_id, "status": row.status,
            "destination": row.destination, "expected_delivery_at": row.expected_delivery_at.astimezone(JAPAN_TIME).isoformat()}


class BusinessTools:
    def __init__(self, engine: AsyncEngine, timeout: float = 15, *, embedder=None):
        if not 0 < timeout <= 60:
            raise ValueError("tool timeout must be between 0 and 60 seconds")
        self.sessions = async_sessionmaker(engine, expire_on_commit=False)
        self.timeout = timeout
        self.embedder = embedder

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
        except ValueError as error:
            code = "embedding_index_mismatch" if str(error) == "embedding_index_mismatch" else "embedding_error"
            raise ToolExecutionError(code) from None

    async def _query(self, name: str, args: Arguments) -> ToolResult:
        if name == "search_knowledge":
            if self.embedder is None:
                raise ToolExecutionError("knowledge_unavailable")
            from logi_scope.rag.retrieve import retrieve
            records, truncated = await retrieve(self.sessions, self.embedder, args)
            return ToolResult(records=records, truncated=truncated, sources=[
                Source(id=f"chunk:{r['chunk_id']}", kind="chunk", chunk_id=r["chunk_id"],
                    path=r["document_path"], origin_id=r["source_key"], source_revision=r["source_revision"])
                for r in records
            ])
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
                # The count and examples share one statement and one DB snapshot.
                query = select(Shipment, func.count().over().label("total_count"))
                statuses = get_args(ShipmentStatus)
                if args.scope == "all":
                    query = query.add_columns(*[
                        func.count().filter(Shipment.status == status).over().label(f"count_{status}")
                        for status in statuses
                    ])
                if args.customer_id is not None:
                    query = query.where(Shipment.customer_id == args.customer_id)
                if args.shipment_id is not None:
                    query = query.where(Shipment.id == args.shipment_id)
                if args.status is not None:
                    query = query.where(Shipment.status == args.status)
                rows = (await session.execute(query.order_by(Shipment.id).limit(args.limit))).all()
                total_count = rows[0].total_count if rows else 0
                status_counts = ({status: rows[0]._mapping[f"count_{status}"] if rows else 0 for status in statuses}
                                 if args.scope == "all" else None)
                return ToolResult(records=[shipment_record(row[0]) for row in rows],
                                  sources=[reference("shipment", row[0].id) for row in rows],
                                  truncated=total_count > args.limit, total_count=total_count,
                                  status_counts=status_counts)
            if name == "get_shipment_details":
                shipment = await session.get(Shipment, args.shipment_id)
                if shipment is None:
                    return ToolResult(records=[], sources=[])
                events = (await session.scalars(select(DeliveryEvent).where(
                    DeliveryEvent.shipment_id == shipment.id
                ).order_by(DeliveryEvent.occurred_at.desc(), DeliveryEvent.id.desc()).limit(args.event_limit + 1))).all()
                visible = events[:args.event_limit]
                record = shipment_record(shipment)
                record["events"] = [{"id": e.id, "occurred_at": e.occurred_at.astimezone(JAPAN_TIME).isoformat(),
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
                    "shipment_id": row.shipment_id, "created_at": row.created_at.astimezone(JAPAN_TIME).isoformat(),
                    "subject": row.subject, "body": row.body[:2000], "resolution": row.resolution[:2000]}],
                    sources=[reference("inquiry", row.id)], truncated=len(row.body) > 2000 or len(row.resolution) > 2000)
            raise UnknownTool("unknown_tool")
