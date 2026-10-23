import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI, WebSocketDisconnect
from fastapi.testclient import TestClient

from app.core.exceptions import UnauthorizedException
from app.modules.detection.alerts.realtime import AlertFeed, AlertFeeds
from app.modules.detection.alerts.repository import key
from app.modules.detection.alerts.schemas import AlertResponse
from app.modules.detection.alerts import stream


class Reference:
    def __init__(self):
        self.listeners = []

    def on_snapshot(self, callback):
        watch = SimpleNamespace(is_active=True)
        def unsubscribe():
            watch.is_active = False
        watch.unsubscribe = Mock(side_effect=unsubscribe)
        self.listeners.append((watch, callback))
        return watch

    def notify(self):
        for watch, callback in self.listeners:
            if watch.is_active:
                callback([], [], None)

    def where(self, **kwargs):
        return self


class Database:
    def __init__(self):
        self.references = {}

    def document(self, path):
        return self.references.setdefault(path, Reference())

    def collection(self, path):
        return self.document(path)


def alert(status='PENDING', alert_id='a' * 40, session_id=None):
    now = datetime.now(timezone.utc)
    return AlertResponse(alert_id=alert_id, status=status, created_at=now,
        deadline_at=now + timedelta(seconds=10), server_time=now,
        emergency_session_id=session_id)


def service(db=None):
    return SimpleNamespace(repository=SimpleNamespace(store=SimpleNamespace(db=db or Database())),
                           current=AsyncMock(return_value=None))


def test_same_user_devices_share_feed_and_release_last_subscription():
    async def run():
        svc = service()
        feeds = AlertFeeds(lambda: svc)
        async with feeds.subscribe('u') as first:
            assert await asyncio.wait_for(first.get(), 1) is None
            feed = feeds.feeds['u']
            async with feeds.subscribe('u') as second:
                assert feeds.feeds['u'] is feed
                assert await asyncio.wait_for(second.get(), 1) is None
                assert len(feed.watches) == 2  # pointer and account, no broad collection watch
                assert svc.current.await_count == 1
                svc.current.return_value = alert()
                svc.repository.store.db.document(f'audio_alert_users/{key("u")}').notify()
                assert (await asyncio.wait_for(first.get(), 1))['status'] == 'PENDING'
                assert (await asyncio.wait_for(second.get(), 1))['status'] == 'PENDING'
                assert 'alert' in feed.watches and 'delivery' in feed.watches
            assert 'u' in feeds.feeds
        assert feeds.feeds == {}
        assert feed.closed and feed.watches == {}
        assert all(not watch.is_active for ref in svc.repository.store.db.references.values()
                   for watch, _ in ref.listeners)
    asyncio.run(run())


def test_independent_instances_receive_same_firestore_changes():
    async def run():
        db = Database()
        first, second = service(db), service(db)
        feeds_a, feeds_b = AlertFeeds(lambda: first), AlertFeeds(lambda: second)
        async with feeds_a.subscribe('u') as queue_a, feeds_b.subscribe('u') as queue_b:
            await asyncio.wait_for(queue_a.get(), 1)
            await asyncio.wait_for(queue_b.get(), 1)
            first.current.return_value = second.current.return_value = alert('CANCELLED')
            db.document(f'audio_alert_users/{key("u")}').notify()
            assert (await asyncio.wait_for(queue_a.get(), 1))['status'] == 'CANCELLED'
            assert (await asyncio.wait_for(queue_b.get(), 1))['status'] == 'CANCELLED'
    asyncio.run(run())


def test_session_changes_refresh_audio_delivery_without_running_safety_checks():
    async def run():
        svc = service()
        svc.current.return_value = alert('SOS_CREATED', session_id='sos-session')
        feeds = AlertFeeds(lambda: svc)
        async with feeds.subscribe('u') as queue:
            await asyncio.wait_for(queue.get(), 1)
            feed = feeds.feeds['u']
            assert feed.watches['session'][0] == 'sos-session'
            svc.repository.store.db.document('emergency_sessions/sos-session').notify()
            assert (await asyncio.wait_for(queue.get(), 1))['emergency_session_id'] == 'sos-session'
            assert svc.current.await_count == 2
            assert not any('safety_check' in path for path in svc.repository.store.db.references)
    asyncio.run(run())


def test_broken_watch_reconnects_during_reconciliation_and_refreshes_state():
    async def run():
        svc = service()
        feed = AlertFeed('u', svc, reconcile_seconds=.02)
        queue = asyncio.Queue(maxsize=1)
        feed.subscribers.add(queue)
        feed.task = asyncio.create_task(feed.run())
        await asyncio.wait_for(queue.get(), 1)
        old_watch = feed.watches['pointer'][1]
        old_watch.is_active = False
        svc.current.return_value = alert()
        assert (await asyncio.wait_for(queue.get(), 1))['status'] == 'PENDING'
        assert feed.watches['pointer'][1] is not old_watch
        await feed.close()
    asyncio.run(run())


def test_feed_error_reaches_subscribers_to_enable_http_fallback():
    async def run():
        svc = service()
        svc.current.side_effect = RuntimeError('database unavailable')
        feeds = AlertFeeds(lambda: svc)
        async with feeds.subscribe('u') as queue:
            assert isinstance(await asyncio.wait_for(queue.get(), 1), Exception)
    asyncio.run(run())


def test_latest_queue_is_bounded_for_slow_device():
    async def run():
        feed = AlertFeed('u', service())
        queue = asyncio.Queue(maxsize=1)
        feed.subscribers.add(queue)
        for number in range(100):
            feed.publish({'version': number})
        assert queue.qsize() == 1
        assert (await queue.get())['version'] == 99
        await feed.close()
    asyncio.run(run())


def socket_app(monkeypatch, svc, authorize):
    feeds = AlertFeeds(lambda: svc)
    monkeypatch.setattr(stream, 'alert_feeds', feeds)
    monkeypatch.setattr(stream, 'get_current_user', authorize)
    app = FastAPI()
    app.include_router(stream.router)
    return app, feeds


def test_socket_auth_snapshot_ping_and_cleanup(monkeypatch):
    svc = service()
    old = datetime.now(timezone.utc) - timedelta(hours=1)
    state = alert()
    state.server_time = old
    svc.current.return_value = state
    authorize = AsyncMock(return_value=SimpleNamespace(uid='authenticated-user'))
    app, feeds = socket_app(monkeypatch, svc, authorize)
    with TestClient(app) as client:
        with client.websocket_connect('/alerts/stream') as socket:
            socket.send_json({'type': 'AUTH', 'token': 'access-token', 'user_id': 'ignored-attacker-id'})
            message = socket.receive_json()
            assert message['type'] == 'AUDIO_ALERT'
            assert datetime.fromisoformat(message['data']['server_time']) > old + timedelta(minutes=59)
            assert set(feeds.feeds) == {'authenticated-user'}
            socket.send_json({'type': 'PING'})
            assert socket.receive_json() == {'type': 'PONG'}
        client.portal.call(asyncio.sleep, .01)
        assert feeds.feeds == {}


@pytest.mark.parametrize('message', [[], {'type': 'AUTH'}, {'type': 'AUTH', 'token': 42},
                                    {'type': 'CONFIRM', 'alert_id': 'a' * 40}])
def test_socket_rejects_missing_or_invalid_auth_before_subscribing(monkeypatch, message):
    authorize = AsyncMock(return_value=SimpleNamespace(uid='u'))
    app, feeds = socket_app(monkeypatch, service(), authorize)
    with TestClient(app) as client:
        with client.websocket_connect('/alerts/stream') as socket:
            socket.send_json(message)
            with pytest.raises(WebSocketDisconnect) as error:
                socket.receive_json()
            assert error.value.code == 4401
    assert feeds.feeds == {}
    authorize.assert_not_awaited()


def test_expired_or_disabled_user_gets_no_state(monkeypatch):
    authorize = AsyncMock(side_effect=UnauthorizedException('disabled or expired'))
    app, feeds = socket_app(monkeypatch, service(), authorize)
    with TestClient(app) as client:
        with client.websocket_connect('/alerts/stream') as socket:
            socket.send_json({'type': 'AUTH', 'token': 'expired'})
            with pytest.raises(WebSocketDisconnect) as error:
                socket.receive_json()
            assert error.value.code == 4401
    assert feeds.feeds == {}


def test_account_disabled_during_connection_closes_before_next_state(monkeypatch):
    svc = service()
    allowed = [True]
    async def authorize(credentials):
        if not allowed[0]:
            raise UnauthorizedException('disabled')
        return SimpleNamespace(uid='u')
    app, _ = socket_app(monkeypatch, svc, authorize)
    with TestClient(app) as client:
        with client.websocket_connect('/alerts/stream') as socket:
            socket.send_json({'type': 'AUTH', 'token': 'token'})
            assert socket.receive_json()['type'] == 'AUDIO_ALERT'
            allowed[0] = False
            svc.repository.store.db.document('users/u').notify()
            with pytest.raises(WebSocketDisconnect) as error:
                socket.receive_json()
            assert error.value.code == 4401


def test_socket_cannot_confirm_cancel_or_modify_safety_checks(monkeypatch):
    app, _ = socket_app(monkeypatch, service(), AsyncMock(return_value=SimpleNamespace(uid='u')))
    with TestClient(app) as client:
        with client.websocket_connect('/alerts/stream') as socket:
            socket.send_json({'type': 'AUTH', 'token': 'token'})
            socket.receive_json()
            socket.send_json({'type': 'CONFIRM', 'safety_check_instance_id': 'check'})
            with pytest.raises(WebSocketDisconnect) as error:
                socket.receive_json()
            assert error.value.code == 4400
