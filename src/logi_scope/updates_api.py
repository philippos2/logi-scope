"""Local-only event receiver; no LLM or reader/admin credentials."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Response
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from logi_scope.delivery_updates import DeliveryUpdates, EventRequest, EventResponse, UpdateRejected, UpdateSettings


def create_updates_app(*, service=None):
    @asynccontextmanager
    async def lifespan(app):
        if service is not None:
            yield
            return
        engine = UpdateSettings().engine()
        app.state.service = DeliveryUpdates(engine)
        try:
            yield
        finally:
            app.state.service = None
            await engine.dispose()

    app = FastAPI(title='LogiScope delivery update demo', lifespan=lifespan)
    app.state.service = service

    @app.get('/health')
    async def health():
        return {'status': 'ok'}

    @app.post('/shipments/{shipment_id}/events', response_model=EventResponse, status_code=201)
    async def register(shipment_id: str, request: EventRequest, response: Response):
        if app.state.service is None:
            raise HTTPException(503, detail={'code': 'updates_not_ready', 'message': '更新APIの準備ができていません。'})
        try:
            result = await app.state.service.register(shipment_id, request)
            response.status_code = 200 if result.replayed else 201
            return result
        except UpdateRejected as error:
            raise HTTPException(error.status, detail={'code': error.code, 'message': error.message}) from None
        except IntegrityError:
            raise HTTPException(409, detail={'code': 'event_conflict', 'message': 'イベントの登録が競合しました。内容を確認して再送してください。'}) from None
        except SQLAlchemyError:
            raise HTTPException(503, detail={'code': 'update_unavailable', 'message': '配送状態を更新できませんでした。'}) from None

    return app


app = create_updates_app()
