"""Actual writer privileges, concurrent delivery events and atomicity."""

import asyncio
import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from logi_scope.config import Settings
from logi_scope.db.models import Customer, DeliveryEvent, Shipment
from logi_scope.db.session import create_reader_engine
from logi_scope.delivery_updates import DeliveryUpdates, EventRequest, UpdateRejected, UpdateSettings
from logi_scope.manage import ManagementSettings

pytestmark = [pytest.mark.integration,
    pytest.mark.skipif(os.environ.get('LOGISCOPE_DB_TESTS') != '1', reason='real DB tests are opt-in')]
T0 = datetime(2026, 10, 4, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
async def demo():
    admin = ManagementSettings().engine()
    writer = UpdateSettings().engine()
    reader = create_reader_engine(Settings())
    shipment_id = 'SHP-UPDATE-TEST-' + uuid4().hex
    with Session(admin) as session, session.begin():
        session.add(Customer(id=899001, name='デモ更新テスト商店', branch='架空更新テスト営業所'))
        session.flush()
        session.add(Shipment(id=shipment_id, customer_id=899001, status='in_transit',
            destination='架空更新テスト地区', expected_delivery_at=T0 + timedelta(days=1)))
        session.flush()
        session.add(DeliveryEvent(shipment_id=shipment_id, occurred_at=T0, location='架空更新テスト営業所', description='受付'))
    yield DeliveryUpdates(writer), shipment_id, reader, writer
    with Session(admin) as session, session.begin():
        session.execute(delete(DeliveryEvent).where(DeliveryEvent.shipment_id == shipment_id))
        session.execute(delete(Shipment).where(Shipment.id == shipment_id))
        session.execute(delete(Customer).where(Customer.id == 899001))
    await writer.dispose()
    await reader.dispose()
    admin.dispose()


def event(status='delivered', minutes=1, key=None):
    return EventRequest(event_key=key or uuid4(), status=status, occurred_at=T0 + timedelta(minutes=minutes))


async def state(reader, shipment_id):
    async with AsyncSession(reader) as session:
        shipment = await session.get(Shipment, shipment_id)
        events = list((await session.scalars(select(DeliveryEvent).where(DeliveryEvent.shipment_id == shipment_id))).all())
        return shipment.status, events


async def test_update_and_replay_visible_to_reader(demo):
    service, shipment_id, reader, _ = demo
    request = event()
    created = await service.register(shipment_id, request)
    replay = await service.register(shipment_id, request)
    assert not created.replayed and replay.replayed and created.event_id == replay.event_id
    status, events = await state(reader, shipment_id)
    assert status == 'delivered' and len(events) == 2
    assert next(e for e in events if e.id == created.event_id).reported_status == 'delivered'


async def test_duplicate_concurrent_send_is_one_event(demo):
    service, shipment_id, reader, _ = demo
    request = event()
    results = await asyncio.gather(service.register(shipment_id, request), service.register(shipment_id, request))
    assert sorted(r.replayed for r in results) == [False, True]
    assert len((await state(reader, shipment_id))[1]) == 2


async def test_conflicting_replay_rolls_back(demo):
    service, shipment_id, reader, _ = demo
    request = event('delayed')
    await service.register(shipment_id, request)
    with pytest.raises(UpdateRejected) as error:
        await service.register(shipment_id, event('missing', minutes=2, key=request.event_key))
    assert error.value.code == 'event_key_conflict'
    status, events = await state(reader, shipment_id)
    assert status == 'delayed' and len(events) == 2


async def test_old_event_and_terminal_transition_leave_no_partial_write(demo):
    service, shipment_id, reader, _ = demo
    with pytest.raises(UpdateRejected) as error:
        await service.register(shipment_id, event(minutes=0))
    assert error.value.code == 'out_of_order'
    assert (await state(reader, shipment_id))[0] == 'in_transit'
    await service.register(shipment_id, event())
    with pytest.raises(UpdateRejected) as error:
        await service.register(shipment_id, event('in_transit', minutes=2))
    assert error.value.code == 'invalid_transition'
    assert len((await state(reader, shipment_id))[1]) == 2


async def test_missing_recovery_and_restricted_targets(demo):
    service, shipment_id, reader, _ = demo
    await service.register(shipment_id, event('missing'))
    with pytest.raises(UpdateRejected):
        await service.register(shipment_id, event('delivered', minutes=2))
    await service.register(shipment_id, event('in_transit', minutes=2))
    assert (await state(reader, shipment_id))[0] == 'in_transit'
    for target, code in [('SHP-DEMO-001', 'fixed_demo_data'), ('SHP-UPDATE-ABSENT', 'shipment_not_found')]:
        with pytest.raises(UpdateRejected) as error:
            await service.register(target, event())
        assert error.value.code == code


async def test_reader_cannot_update_and_writer_cannot_change_other_columns(demo):
    _, shipment_id, reader, writer = demo
    for engine, statement in [
        (reader, update(Shipment).where(Shipment.id == shipment_id).values(status='delivered')),
        (writer, update(Shipment).where(Shipment.id == shipment_id).values(destination='不正な変更')),
        (writer, delete(DeliveryEvent).where(DeliveryEvent.shipment_id == shipment_id)),
    ]:
        async with engine.connect() as connection:
            with pytest.raises(DBAPIError):
                async with connection.begin():
                    await connection.execute(text('SET LOCAL transaction_read_only = off'))
                    await connection.execute(statement)


async def test_distinct_concurrent_updates_keep_newest_state(demo):
    service, shipment_id, reader, _ = demo
    requests = [event('delayed', minutes=1), event('delivered', minutes=2)]
    results = await asyncio.gather(*(service.register(shipment_id, r) for r in requests), return_exceptions=True)
    assert not isinstance(results[1], Exception)
    if isinstance(results[0], Exception):
        assert isinstance(results[0], UpdateRejected) and results[0].code == 'out_of_order'
    status, events = await state(reader, shipment_id)
    assert status == 'delivered'
    assert max(e.occurred_at for e in events) == requests[1].occurred_at
    assert len(events) == 1 + sum(not isinstance(r, Exception) for r in results)


async def test_failure_after_flush_rolls_back_event_and_shipment(demo, monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError

    service, shipment_id, reader, _ = demo
    original = AsyncSession.flush

    async def failing_flush(session, *args, **kwargs):
        await original(session, *args, **kwargs)
        raise SQLAlchemyError('simulated failure after writes')

    monkeypatch.setattr(AsyncSession, 'flush', failing_flush)
    with pytest.raises(SQLAlchemyError):
        await service.register(shipment_id, event())
    monkeypatch.setattr(AsyncSession, 'flush', original)
    status, events = await state(reader, shipment_id)
    assert status == 'in_transit' and len(events) == 1
