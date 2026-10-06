"""Transactional local-demo updates, separate from the agent's tools."""

from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL, func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from logi_scope.agent import StrictModel
from logi_scope.db.models import DeliveryEvent, Shipment

Status = Literal['in_transit', 'delayed', 'missing', 'delivered']
TRANSITIONS = {
    'in_transit': {'in_transit', 'delayed', 'missing', 'delivered'},
    'delayed': {'in_transit', 'delayed', 'missing', 'delivered'},
    'missing': {'missing', 'in_transit'},
    'delivered': set(),
}
LABELS = {'in_transit': '配送中', 'delayed': '遅延', 'missing': '所在不明', 'delivered': '配達完了'}


class UpdateSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix='UPDATE_DATABASE_', extra='ignore')
    host: str = 'db'
    port: int = 5432
    name: str = 'logi_scope'
    password: SecretStr

    def engine(self):
        return create_async_engine(URL.create('postgresql+psycopg', username='logi_scope_updater',
            password=self.password.get_secret_value(), host=self.host, port=self.port, database=self.name),
            hide_parameters=True, pool_pre_ping=True,
            connect_args={'connect_timeout': 5, 'options': '-c statement_timeout=10000 -c lock_timeout=5000'})


class EventRequest(StrictModel):
    event_key: UUID = Field(strict=False)
    status: Status
    occurred_at: AwareDatetime = Field(strict=False)

    @field_validator('occurred_at', mode='before')
    @classmethod
    def timestamp_type(cls, value):
        if not isinstance(value, (str, datetime)):
            raise ValueError('タイムゾーン付き日時を指定してください。')
        return value

    @field_validator('occurred_at')
    @classmethod
    def not_future(cls, value):
        if value > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise ValueError('未来の時刻は登録できません。')
        return value


class EventResponse(StrictModel):
    shipment_id: str
    event_id: int
    status: Status
    occurred_at: datetime
    replayed: bool


class UpdateRejected(Exception):
    def __init__(self, status, code, message):
        self.status, self.code, self.message = status, code, message


class DeliveryUpdates:
    def __init__(self, engine):
        self.engine = engine

    async def register(self, shipment_id: str, request: EventRequest) -> EventResponse:
        if not shipment_id.startswith('SHP-UPDATE-'):
            raise UpdateRejected(403, 'fixed_demo_data', '更新用のデモ荷物だけを更新できます。')
        async with AsyncSession(self.engine) as session, session.begin():
            shipment = await session.scalar(select(Shipment).where(Shipment.id == shipment_id).with_for_update())
            if shipment is None:
                raise UpdateRejected(404, 'shipment_not_found', '更新対象の荷物がありません。')
            prior = await session.scalar(select(DeliveryEvent).where(DeliveryEvent.event_key == str(request.event_key)))
            if prior is not None:
                if (prior.shipment_id, prior.reported_status, prior.occurred_at) != (shipment_id, request.status, request.occurred_at):
                    raise UpdateRejected(409, 'event_key_conflict', '同じイベントキーで異なる内容が送信されました。')
                return self.response(prior, True)
            latest = await session.scalar(select(func.max(DeliveryEvent.occurred_at)).where(DeliveryEvent.shipment_id == shipment_id))
            if latest is not None and request.occurred_at <= latest:
                raise UpdateRejected(409, 'out_of_order', '最新イベントより後の時刻を指定してください。')
            if request.status not in TRANSITIONS[shipment.status]:
                raise UpdateRejected(409, 'invalid_transition', 'この配送状態への変更はできません。')
            event = DeliveryEvent(shipment_id=shipment_id, event_key=str(request.event_key),
                reported_status=request.status, occurred_at=request.occurred_at,
                location='架空更新デモ営業所', description=f'更新デモから{LABELS[request.status]}として報告された。')
            session.add(event)
            shipment.status = request.status
            await session.flush()
            return self.response(event, False)

    @staticmethod
    def response(event, replayed):
        return EventResponse(shipment_id=event.shipment_id, event_id=event.id,
            status=event.reported_status, occurred_at=event.occurred_at, replayed=replayed)
