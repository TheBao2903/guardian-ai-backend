import asyncio
from datetime import datetime, timezone
from functools import lru_cache
import uuid

from app.core.exceptions import AppException
from app.core.logging import logger
from app.modules.notifications.schemas import SosAlertPayload, NotificationResult
from app.modules.notifications.medical_context import emergency_medical_fields
from app.shared.enums.contact import NotificationChannel
from .repository import AlertRepository
from .schemas import AlertResponse, DeliverySummary

MEDICAL_PROFILE_TIMEOUT_SECONDS = 1.0


class AlertService:
    def __init__(self, repository, contacts, users, telegram, now=None, *, medical_repo=None):
        self.repository, self.contacts, self.users, self.telegram = repository, contacts, users, telegram
        self.medical_repo = medical_repo
        self.now = now or (lambda: datetime.now(timezone.utc))
        self._delivery_slots = asyncio.Semaphore(10)

    async def present(self, row):
        if row is None:
            return None
        summary = DeliverySummary()
        if row['status'] == 'SOS_CREATED':
            jobs = await asyncio.to_thread(self.repository.jobs, row['alert_id'])
            summary = DeliverySummary(total=len(jobs),
                sent=sum(j['status'] == 'SENT' for j in jobs),
                pending=sum(j['status'] in ('PENDING', 'RETRY', 'SENDING') for j in jobs),
                failed=sum(j['status'] == 'FAILED' for j in jobs),
                uncertain=sum(bool(j.get('uncertain')) for j in jobs))
            summary.status = ('EXISTING_SOS' if row.get('reused_session') else
                'NO_RECIPIENTS' if not jobs else 'SENT' if summary.sent == summary.total else
                'PARTIAL_FAILURE' if summary.failed else 'PENDING')
        return AlertResponse(**{k: row[k] for k in ('alert_id', 'status', 'created_at', 'deadline_at')},
            emergency_session_id=row.get('emergency_session_id'), server_time=self.now(), delivery=summary)

    async def create(self, user_id, candidate):
        now = self.now()
        if candidate.captured_at.tzinfo is None or abs((now - candidate.captured_at).total_seconds()) > 35:
            raise AppException('Tín hiệu âm thanh đã cũ hoặc sai thời gian', code='STALE_AUDIO', status_code=422)
        row = await asyncio.to_thread(self.repository.create, user_id, candidate, now)
        return await self.present(row)

    async def current(self, user_id):
        row = await asyncio.to_thread(self.repository.current, user_id)
        return await self.present(row)

    async def decide(self, user_id, alert_id, action):
        row = await asyncio.to_thread(self.repository.decide, user_id, alert_id, action, self.now())
        if row['status'] == 'DISPATCHING':
            await self.dispatch(row['alert_id'])
            row = await asyncio.to_thread(self.repository.get, user_id, alert_id)
        return await self.present(row)

    async def dispatch(self, alert_id):
        token = uuid.uuid4().hex
        row = await asyncio.to_thread(self.repository.claim_dispatch, alert_id, self.now(), token)
        if not row:
            return
        # Side effects never run inside a retryable transaction. A crash here is
        # recovered by the durable DISPATCHING state and the expiring lease.
        contacts = await self.contacts.list_contacts(row['user_id'])
        user = await asyncio.to_thread(self.users.get_by_id, row['user_id']) or {}
        from app.core.config import get_settings
        eligible = [c for c in contacts if c.is_active and c.telegram_id][:get_settings().MAX_EMERGENCY_CONTACTS_PER_USER]
        recipients = [{'contact_id': c.id, 'chat_id': c.telegram_id} for c in eligible]
        location = ({'latitude': row['latitude'], 'longitude': row['longitude']}
                    if row.get('latitude') is not None and row.get('longitude') is not None else None)
        medical_fields = {}
        if self.medical_repo is not None:
            try:
                medical = await asyncio.wait_for(
                    asyncio.to_thread(self.medical_repo.get_by_uid, row['user_id']),
                    timeout=MEDICAL_PROFILE_TIMEOUT_SECONDS,
                ) or {}
                medical_fields = emergency_medical_fields(user, medical)
            except Exception:
                # Urgent SOS must still send, but do not fall back to legacy
                # medical data when the current sharing preference is unknown.
                logger.warning('Medical profile unavailable; sending SOS without medical details')
        payload = SosAlertPayload(user_name=user.get('name') or user.get('display_name') or 'Người dùng Guardian AI',
            user_phone=user.get('phone'), trigger_type='SCREAM_DETECTED', event_type='SCREAM',
            location=location, **medical_fields)
        await asyncio.to_thread(self.repository.materialize, alert_id, token, recipients,
                                payload.model_dump(mode='json', exclude_none=True), self.now())

    async def tick_alerts(self):
        rows = await asyncio.to_thread(self.repository.work, self.now())
        async def run(row):
            try:
                if row['status'] == 'PENDING':
                    await asyncio.to_thread(self.repository.decide, row['user_id'], row['alert_id'], 'timeout', self.now())
                await self.dispatch(row['alert_id'])
            except Exception:
                logger.exception('Audio alert dispatch failed; durable work will be retried')
        # Bound the number of dispatches without delaying the independent sender.
        for start in range(0, len(rows), 10):
            await asyncio.gather(*(run(r) for r in rows[start:start + 10]))

    async def tick_deliveries(self):
        jobs = await asyncio.to_thread(self.repository.jobs)
        async def send(job):
            async with self._delivery_slots:
                token = uuid.uuid4().hex
                row = await asyncio.to_thread(self.repository.claim_job, job['job_id'], self.now(), token)
                if not row:
                    return
                try:
                    result = await self.telegram.send_sos_alert(row['chat_id'], SosAlertPayload(**row['payload']))
                except Exception:
                    result = NotificationResult(success=False, channel=NotificationChannel.TELEGRAM,
                        recipient=row['chat_id'], retryable=True, delivery_uncertain=True, error_code='TRANSPORT_ERROR')
                await asyncio.to_thread(self.repository.finish_job, row['job_id'], token, result, self.now())
        await asyncio.gather(*(send(j) for j in jobs))


@lru_cache
def get_alert_service():
    from app.infrastructure.firestore.client import get_firestore_client
    from app.modules.contacts.service import ContactService
    from app.modules.users.repository import UserRepository
    from app.modules.users.medical_repository import MedicalProfileRepository
    from app.modules.notifications.providers.telegram import TelegramBotProvider
    from .store import FirestoreStore
    return AlertService(AlertRepository(FirestoreStore(get_firestore_client())),
                        ContactService(), UserRepository(), TelegramBotProvider(),
                        medical_repo=MedicalProfileRepository())


class AlertWorker:
    def __init__(self, service_factory=get_alert_service):
        self.service_factory = service_factory
        self.tasks = []

    def start(self):
        if not self.tasks:
            self.tasks = [asyncio.create_task(self._loop('tick_alerts')),
                          asyncio.create_task(self._loop('tick_deliveries'))]

    async def _loop(self, method):
        while True:
            try:
                await getattr(self.service_factory(), method)()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception('Audio alert worker failed; retrying persisted work')
            await asyncio.sleep(.5)

    async def stop(self):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()


alert_worker = AlertWorker()
