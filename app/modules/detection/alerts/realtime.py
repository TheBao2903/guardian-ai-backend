"""Read-only audio state feeds backed by Firestore, shared per user/process.

No local broadcast dependency: every instance observes the same durable state.
Callbacks only invalidate; responses are rebuilt through the existing service.
"""
import asyncio
from contextlib import asynccontextmanager
from threading import Lock
from anyio import CancelScope

from google.cloud.firestore import FieldFilter

from app.core.logging import logger
from .repository import key
from .service import get_alert_service


class AlertFeed:
    def __init__(self, user_id, service, *, reconcile_seconds=60):
        self.user_id = user_id
        self.service = service
        self.db = service.repository.store.db
        self.reconcile_seconds = reconcile_seconds
        self.loop = asyncio.get_running_loop()
        self.changed = asyncio.Event()
        self.subscribers = set()
        self.watches = {}
        self.latest = None
        self.has_latest = False
        self.closed = False
        self.task = None
        self.watch_lock = Lock()

    def invalidate(self, *args):
        if not self.closed:
            self.loop.call_soon_threadsafe(self.changed.set)

    def _watch(self, name, target, reference):
        current = self.watches.get(name)
        if current and current[0] == target and current[1].is_active:
            return
        if current:
            current[1].unsubscribe()
            del self.watches[name]
        if reference is not None:
            self.watches[name] = (target, reference.on_snapshot(self.invalidate))

    def _update_watches(self, alert):
        with self.watch_lock:
            if not self.closed:
                self._install_watches(alert)

    def _install_watches(self, alert):
        self._watch('pointer', self.user_id,
                    self.db.document(f'audio_alert_users/{key(self.user_id)}'))
        # Invalidation on account changes forces socket reauthorization before
        # any new data is sent, including an administrator disabling the user.
        self._watch('account', self.user_id, self.db.document(f'users/{self.user_id}'))
        alert_id = alert.alert_id if alert else None
        session_id = alert.emergency_session_id if alert else None
        self._watch('alert', alert_id,
                    self.db.document(f'audio_alerts/{alert_id}') if alert_id else None)
        self._watch('delivery', alert_id,
                    self.db.collection('audio_notification_outbox').where(
                        filter=FieldFilter('alert_id', '==', alert_id)) if alert_id else None)
        # Preserve the existing client's ability to observe a resolved SOS even
        # when the audio alert and its delivery summary no longer change.
        self._watch('session', session_id,
                    self.db.document(f'emergency_sessions/{session_id}') if session_id else None)

    def publish(self, value):
        self.latest, self.has_latest = value, True
        for queue in self.subscribers:
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(value)

    async def run(self):
        try:
            # Install pointer/account listeners before the first authoritative
            # read so a write during connection establishment is not lost.
            await asyncio.to_thread(self._update_watches, None)
            while True:
                self.changed.clear()
                alert = await self.service.current(self.user_id)
                await asyncio.to_thread(self._update_watches, alert)
                self.publish(alert.model_dump(mode='json') if alert else None)
                try:
                    await asyncio.wait_for(self.changed.wait(), self.reconcile_seconds)
                    # Coalesce initial snapshots and a transaction's changes.
                    await asyncio.sleep(.05)
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception('Audio state feed unavailable; clients will use HTTP fallback')
            self.publish(RuntimeError('Audio state feed unavailable'))

    async def close(self):
        self.closed = True
        with CancelScope(shield=True):
            if self.task:
                self.task.cancel()
                await asyncio.gather(self.task, return_exceptions=True)
            # Let any in-flight to_thread setup finish before detaching listeners.
            await asyncio.to_thread(self._close_watches)

    def _close_watches(self):
        with self.watch_lock:
            for _, watch in self.watches.values():
                watch.unsubscribe()
            self.watches.clear()


class AlertFeeds:
    def __init__(self, service_factory=get_alert_service):
        self.service_factory = service_factory
        self.feeds = {}

    @asynccontextmanager
    async def subscribe(self, user_id):
        # Dictionary/refcount changes happen only on the ASGI event loop.
        feed = self.feeds.get(user_id)
        if feed is None:
            feed = self.feeds[user_id] = AlertFeed(user_id, self.service_factory())
            feed.task = asyncio.create_task(feed.run())
        queue = asyncio.Queue(maxsize=1)
        feed.subscribers.add(queue)
        if feed.has_latest:
            queue.put_nowait(feed.latest)
        try:
            yield queue
        finally:
            feed.subscribers.discard(queue)
            if not feed.subscribers:
                self.feeds.pop(user_id, None)
                await feed.close()


alert_feeds = AlertFeeds()
