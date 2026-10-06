"""Update API contract and controlled failures without external services."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from logi_scope.delivery_updates import EventResponse, UpdateRejected
from logi_scope.updates_api import create_updates_app


class Service:
    def __init__(self, replay=False, error=None):
        self.replay, self.error, self.calls = replay, error, 0

    async def register(self, shipment_id, request):
        self.calls += 1
        if self.error:
            raise self.error
        return EventResponse(shipment_id=shipment_id, event_id=1000000,
            status=request.status, occurred_at=request.occurred_at, replayed=self.replay)


def payload():
    return {'event_key': str(uuid4()), 'status': 'delivered', 'occurred_at': '2026-10-04T09:00:00+09:00'}


@pytest.mark.parametrize('replay,expected', [(False, 201), (True, 200)])
async def test_new_event_and_replay(replay, expected):
    service = Service(replay)
    async with AsyncClient(transport=ASGITransport(app=create_updates_app(service=service)), base_url='http://test') as client:
        response = await client.post('/shipments/SHP-UPDATE-001/events', json=payload())
    assert response.status_code == expected
    assert response.json()['replayed'] is replay
    assert service.calls == 1


@pytest.mark.parametrize('patch', [
    {'event_key': 'invalid'}, {'status': 'lost'}, {'occurred_at': '2026-10-04T09:00:00'},
    {'occurred_at': True}, {'extra': 'unknown'},
    {'occurred_at': (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()},
])
async def test_invalid_input_never_reaches_writer(patch):
    service = Service()
    async with AsyncClient(transport=ASGITransport(app=create_updates_app(service=service)), base_url='http://test') as client:
        response = await client.post('/shipments/SHP-UPDATE-001/events', json=payload() | patch)
    assert response.status_code == 422 and service.calls == 0


@pytest.mark.parametrize('error,status,code', [
    (UpdateRejected(409, 'out_of_order', '時刻を確認してください。'), 409, 'out_of_order'),
    (IntegrityError('SECRET SQL', {}, Exception('SECRET')), 409, 'event_conflict'),
    (SQLAlchemyError('SECRET PASSWORD'), 503, 'update_unavailable'),
])
async def test_failures_do_not_expose_internal_details(error, status, code):
    async with AsyncClient(transport=ASGITransport(app=create_updates_app(service=Service(error=error))), base_url='http://test') as client:
        response = await client.post('/shipments/SHP-UPDATE-001/events', json=payload())
    assert response.status_code == status
    assert response.json()['detail']['code'] == code
    assert 'SECRET' not in response.text
