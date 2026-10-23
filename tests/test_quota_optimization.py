"""Offline regressions: no credentials, production reads or notifications."""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from google.api_core.exceptions import ResourceExhausted

from app.infrastructure.firestore.watched_query import WatchedQuery
from app.infrastructure.firestore import client
from app.modules.detection.alerts.repository import AlertRepository
from app.modules.detection.alerts.schemas import AlertCandidate
from app.modules.detection.alerts.service import AlertService, AlertWorker
from app.modules.emergency.repository import EmergencyRepository
from app.modules.emergency.safety_check.repository import SafetyCheckRepository
from app.modules.notifications.schemas import NotificationResult
from app.shared.enums.contact import NotificationChannel


def document(doc_id, **data):
    return SimpleNamespace(id=doc_id, to_dict=lambda: deepcopy(data))


class FakeQuery:
    def __init__(self, documents=()):
        self.documents = list(documents)
        self.watch = SimpleNamespace(is_active=True, unsubscribe=Mock())
        self.on_snapshot = Mock(side_effect=self.subscribe)
        self.stream = Mock(side_effect=lambda **kwargs: iter(self.documents))

    def subscribe(self, callback):
        self.callback = callback
        self.watch = SimpleNamespace(is_active=True, unsubscribe=Mock())
        return self.watch

    def publish(self, documents):
        self.documents = list(documents)
        self.callback(self.documents, [], None)


def test_idle_worker_does_not_query_every_tick_and_reconciles():
    clock = [0]
    query = FakeQuery()
    watched = WatchedQuery(query, clock=lambda: clock[0])
    for _ in range(1000):
        assert watched.read() == []
    assert query.stream.call_count == 1
    query.stream.assert_called_with(retry=None, timeout=3)
    clock[0] = 60
    watched.read()
    assert query.stream.call_count == 2


def test_live_add_change_remove_and_copy_isolation():
    query = FakeQuery()
    watched = WatchedQuery(query)
    watched.read()
    query.publish([document('a', status='PENDING')])
    rows = watched.read()
    assert rows[0]['status'] == 'PENDING'
    rows[0]['status'] = 'LOCAL_MUTATION'
    assert watched.read()[0]['status'] == 'PENDING'
    query.publish([document('a', status='DISPATCHING')])
    assert watched.read()[0]['status'] == 'DISPATCHING'
    query.publish([])
    assert watched.read() == []
    assert query.stream.call_count == 1


def test_dead_listener_reloads_persisted_work_and_closes():
    query = FakeQuery()
    watched = WatchedQuery(query, clock=lambda: 100)
    watched.read()
    old_watch = query.watch
    old_watch.is_active = False
    query.documents = [document('persisted', status='DISPATCHING')]
    watched._next_connect = 0
    assert watched.read()[0]['_document_id'] == 'persisted'
    old_watch.unsubscribe.assert_called_once()
    assert query.on_snapshot.call_count == 2
    watched.close()
    query.watch.unsubscribe.assert_called_once()


def test_listener_setup_failure_uses_authoritative_reads():
    query = FakeQuery([document('a', status='PENDING')])
    query.on_snapshot.side_effect = RuntimeError('listener unavailable')
    watched = WatchedQuery(query, clock=lambda: 0)
    assert watched.read()[0]['status'] == 'PENDING'
    query.documents = []
    assert watched.read() == []
    assert query.on_snapshot.call_count == 1  # reconnect has backoff
    assert query.stream.call_count == 2


def test_snapshot_during_reconciliation_is_not_overwritten():
    query = FakeQuery()
    watched = WatchedQuery(query)
    def stream(**kwargs):
        query.publish([document('new', status='PENDING')])
        return iter([document('old', status='PENDING')])
    query.stream.side_effect = stream
    assert watched.read()[0]['_document_id'] == 'new'


def test_reconcile_failure_is_not_hidden_by_cache():
    clock = [0]
    query = FakeQuery()
    watched = WatchedQuery(query, clock=lambda: clock[0])
    watched.read()
    clock[0] = 61
    query.stream.side_effect = ResourceExhausted('quota')
    with pytest.raises(ResourceExhausted):
        watched.read()


class MemoryStore:
    def __init__(self):
        self.rows = {}
        self.writes = {}

    def atomic(self, callback):
        self.writes = {}
        result = callback(self)
        self.rows.update(self.writes)
        return deepcopy(result)

    def get(self, path):
        return deepcopy(self.writes.get(path, self.rows.get(path)))

    read = get

    def set(self, path, row):
        self.writes[path] = deepcopy(row)

    def scan(self, collection, filters=()):
        rows = [deepcopy(row) for path, row in self.rows.items()
                if path.startswith(collection + '/')]
        for field, op, value in filters:
            rows = [row for row in rows if
                    (row.get(field) in value if op == 'in' else row.get(field) == value)]
        return rows

    query = scan
    work_scan = scan


def new_alert():
    store = MemoryStore()
    repo = AlertRepository(store)
    now = datetime.now(timezone.utc)
    candidate = AlertCandidate(monitoring_session_id='monitor', idempotency_key='candidate',
                               captured_at=now, confidence=.9)
    row = repo.create('u', candidate, now)
    return store, repo, now, candidate, row


def test_countdown_idempotency_cancel_and_expiry_unchanged():
    store, repo, now, candidate, row = new_alert()
    assert row['deadline_at'] == now + timedelta(seconds=10)
    assert repo.create('u', candidate, now)['alert_id'] == row['alert_id']
    assert repo.work(now + timedelta(seconds=9.9)) == []
    assert len(repo.work(now + timedelta(seconds=10))) == 1
    cancelled = repo.decide('u', row['alert_id'], 'cancel', now + timedelta(seconds=9))
    assert cancelled['status'] == 'CANCELLED'
    assert repo.work(now + timedelta(seconds=11)) == []
    assert repo.decide('u', row['alert_id'], 'confirm', now)['status'] == 'CANCELLED'


def test_confirm_restart_and_dispatch_lease_recovery():
    store, repo, now, _, row = new_alert()
    repo.decide('u', row['alert_id'], 'confirm', now)
    assert len(repo.work(now)) == 1
    assert repo.claim_dispatch(row['alert_id'], now, 'worker-1')
    recovered = AlertRepository(store)  # new worker, persisted state
    assert recovered.work(now + timedelta(seconds=29)) == []
    assert len(recovered.work(now + timedelta(seconds=30))) == 1
    assert recovered.claim_dispatch(row['alert_id'], now, 'worker-2') is None
    assert recovered.claim_dispatch(row['alert_id'], now + timedelta(seconds=30), 'worker-2')


def test_cancel_at_deadline_still_dispatches_and_checks_ownership():
    _, repo, now, _, row = new_alert()
    with pytest.raises(Exception):
        repo.decide('other-user', row['alert_id'], 'cancel', now)
    assert repo.decide('u', row['alert_id'], 'cancel',
                       now + timedelta(seconds=10))['status'] == 'DISPATCHING'


def test_not_due_jobs_skip_transaction_but_due_jobs_are_still_claimed():
    now = datetime.now(timezone.utc)
    repo = SimpleNamespace(jobs=Mock(return_value=[
        dict(job_id='later', next_attempt_at=now + timedelta(seconds=5), lease_until=now),
        dict(job_id='leased', next_attempt_at=now, lease_until=now + timedelta(seconds=30)),
        dict(job_id='due', next_attempt_at=now, lease_until=now),
    ]), claim_job=Mock(return_value=None))
    service = AlertService(repo, None, None, None, now=lambda: now)
    asyncio.run(service.tick_deliveries())
    assert repo.claim_job.call_count == 1
    assert repo.claim_job.call_args.args[0] == 'due'


def test_materialize_restart_retry_and_end_session_keep_durable_rules():
    store, repo, now, _, alert = new_alert()
    alert_id = alert['alert_id']
    repo.decide('u', alert_id, 'confirm', now)
    repo.claim_dispatch(alert_id, now, 'dispatch-token')
    recipients = [dict(contact_id='c', chat_id='123')]
    repo.materialize(alert_id, 'dispatch-token', recipients, {'user_name': 'User'}, now)
    # A stale cached candidate cannot recreate the SOS or its outbox.
    assert repo.claim_dispatch(alert_id, now, 'stale-token') is None
    assert repo.get('u', alert_id)['status'] == 'SOS_CREATED'
    jobs = repo.jobs(alert_id)
    assert len(jobs) == 1
    job_id = jobs[0]['job_id']
    assert repo.claim_job(job_id, now, 'send-1')['attempts'] == 1
    assert repo.claim_job(job_id, now, 'duplicate') is None
    failed = NotificationResult(success=False, channel=NotificationChannel.TELEGRAM,
        recipient='123', retryable=True, retry_after_seconds=10)
    repo.finish_job(job_id, 'send-1', failed, now)
    assert repo.claim_job(job_id, now + timedelta(seconds=9), 'too-soon') is None
    restarted = AlertRepository(store)
    assert restarted.claim_job(job_id, now + timedelta(seconds=10), 'send-2')['attempts'] == 2
    success = NotificationResult(success=True, channel=NotificationChannel.TELEGRAM,
        recipient='123', message_id='message')
    restarted.finish_job(job_id, 'wrong-token', success, now)
    assert restarted.jobs(alert_id)[0]['status'] == 'SENDING'
    restarted.finish_job(job_id, 'send-2', success, now)
    assert restarted.jobs(alert_id)[0]['status'] == 'SENT'
    assert restarted.jobs() == []


def test_ended_sos_prevents_notification_even_with_stale_work_snapshot():
    store, repo, now, _, alert = new_alert()
    alert_id = alert['alert_id']
    repo.decide('u', alert_id, 'confirm', now)
    repo.claim_dispatch(alert_id, now, 'dispatch')
    repo.materialize(alert_id, 'dispatch', [dict(contact_id='c', chat_id='123')], {}, now)
    session_id = repo.get('u', alert_id)['emergency_session_id']
    store.rows[f'emergency_sessions/{session_id}']['status'] = 'RESOLVED'
    job_id = repo.jobs()[0]['job_id']
    assert repo.claim_job(job_id, now, 'send') is None
    assert repo.jobs(alert_id)[0]['error_code'] == 'SESSION_ENDED'


def test_safety_check_live_deadlines_and_authoritative_claim(monkeypatch):
    now = datetime.now(timezone.utc)
    query = FakeQuery([
        document('due', status='ACTIVE', grace_period_until=now - timedelta(seconds=1)),
        document('later', status='CHECK_REQUIRED', grace_period_until=(now + timedelta(hours=1)).isoformat()),
        document('invalid', status='ACTIVE', grace_period_until='invalid'),
    ])
    db = Mock()
    db.collection.return_value.where.return_value = query
    monkeypatch.setattr(SafetyCheckRepository, '_templates_seeded', True)
    repo = SafetyCheckRepository(db)
    assert [r['instance_id'] for r in repo.get_overdue_instances()] == ['due']
    # Cancellation from another device updates the candidate list.
    query.publish([query.documents[1]])
    assert repo.get_overdue_instances() == []
    repo.close()
    query.watch.unsubscribe.assert_called_once()


def test_worker_stop_releases_listener_resources():
    store = SimpleNamespace(close=Mock())
    worker = AlertWorker()
    worker._service = SimpleNamespace(repository=SimpleNamespace(store=store))
    asyncio.run(worker.stop())
    assert worker.tasks == []
    store.close.assert_called_once()


def test_health_probe_is_bounded_shared_and_reports_quota_failure(monkeypatch):
    clock = [0]
    db = Mock()
    monkeypatch.setattr(client, 'get_firestore_client', lambda: db)
    monkeypatch.setattr(client, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(client, '_health_expires_at', 0)
    for _ in range(10):
        assert client.check_firestore_connection()
    db.document.return_value.get.assert_called_once_with(retry=None, timeout=2)
    clock[0] = 16
    db.document.return_value.get.side_effect = ResourceExhausted('quota')
    assert not client.check_firestore_connection()
    assert not client.check_firestore_connection()
    assert db.document.return_value.get.call_count == 2
    clock[0] = 22
    db.document.return_value.get.side_effect = None
    assert client.check_firestore_connection()


def test_history_uses_order_and_limit_instead_of_reading_all():
    db = Mock()
    query = db.collection.return_value.where.return_value
    query.order_by.return_value.limit.return_value.stream.return_value = [
        document('session', status='ACTIVE')]
    rows = EmergencyRepository(db).list_by_user('u', limit=3)
    assert rows[0]['session_id'] == 'session'
    query.order_by.return_value.limit.assert_called_once_with(3)
    query.stream.assert_not_called()


def test_quota_error_does_not_trigger_larger_history_fallback():
    db = Mock()
    query = db.collection.return_value.where.return_value
    query.order_by.return_value.limit.return_value.stream.side_effect = ResourceExhausted('quota')
    with pytest.raises(ResourceExhausted):
        EmergencyRepository(db).list_by_user('u')
    query.stream.assert_not_called()


def test_worker_backs_off_failures_and_resets_after_success(monkeypatch):
    delays = []
    tick = Mock(side_effect=[ResourceExhausted('quota'), ResourceExhausted('quota'), None])
    async def tick_alerts():
        tick()
    async def sleep(delay):
        delays.append(delay)
        if len(delays) == 3:
            raise asyncio.CancelledError
    monkeypatch.setattr('app.modules.detection.alerts.service.asyncio.sleep', sleep)
    monkeypatch.setattr('app.modules.detection.alerts.service.random.uniform', lambda a, b: 0)
    worker = AlertWorker(lambda: SimpleNamespace(tick_alerts=tick_alerts))
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(worker._loop('tick_alerts'))
    assert delays == [1, 2, .5]
