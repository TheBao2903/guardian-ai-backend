import hashlib
from datetime import timedelta

from app.core.exceptions import AppException


def key(value):
    return hashlib.sha256(value.encode()).hexdigest()[:40]


def ensure_active_session(tx, user_id, session):
    """Shared by manual SOS and audio dispatch to serialize session creation."""
    pointer = f'emergency_active_users/{key(user_id)}'
    guard = tx.get(pointer) or {}
    existing = tx.get(f"emergency_sessions/{guard['session_id']}") if guard.get('session_id') else None
    if not existing or existing.get('status') != 'ACTIVE':
        # Adopt an existing pre-migration session before creating a new one.
        old = tx.query('emergency_sessions', [('user_id', '==', user_id)])
        existing = next((r for r in old if r.get('status') == 'ACTIVE'), None)
    chosen = existing or session
    if not existing:
        tx.set(f"emergency_sessions/{session['session_id']}", session)
    tx.set(pointer, {'session_id': chosen['session_id']})
    return chosen


class AlertRepository:
    def __init__(self, store):
        self.store = store

    def create(self, user_id, candidate, now):
        alert_id = key(user_id + ':' + candidate.idempotency_key)
        path = f'audio_alerts/{alert_id}'

        def operation(tx):
            existing = tx.get(path)
            if existing:
                return existing
            pointer = f'audio_alert_users/{key(user_id)}'
            guard = tx.get(pointer) or {}
            previous = tx.get(f"audio_alerts/{guard['alert_id']}") if guard.get('alert_id') else None
            if previous:
                if previous['status'] in ('PENDING', 'DISPATCHING'):
                    return previous
                if previous.get('emergency_session_id'):
                    session = tx.get(f"emergency_sessions/{previous['emergency_session_id']}")
                    if session and session.get('status') == 'ACTIVE':
                        return previous
                if now < previous.get('decided_at', previous['created_at']) + timedelta(seconds=30):
                    return previous
            check = None
            if candidate.safety_check_instance_id:
                check = tx.get(f'safety_check_instances/{candidate.safety_check_instance_id}')
                if not check or check.get('user_id') != user_id or check.get('status') not in ('ACTIVE', 'CHECK_REQUIRED'):
                    raise AppException('Safety Check không còn hoạt động', code='INACTIVE_SAFETY_CHECK', status_code=409)
            row = dict(alert_id=alert_id, user_id=user_id, status='PENDING',
                       monitoring_session_id=candidate.monitoring_session_id,
                       created_at=now, deadline_at=now + timedelta(seconds=10),
                       safety_check_instance_id=candidate.safety_check_instance_id,
                       latitude=candidate.latitude, longitude=candidate.longitude)
            tx.set(path, row)
            tx.set(pointer, {'alert_id': alert_id})
            return row
        return self.store.atomic(operation)

    def get(self, user_id, alert_id):
        row = self.store.read(f'audio_alerts/{alert_id}')
        if not row or row['user_id'] != user_id:
            raise AppException('Không tìm thấy cảnh báo', code='ALERT_NOT_FOUND', status_code=404)
        return row

    def current(self, user_id):
        guard = self.store.read(f'audio_alert_users/{key(user_id)}')
        return self.get(user_id, guard['alert_id']) if guard else None

    def decide(self, user_id, alert_id, action, now):
        def operation(tx):
            path = f'audio_alerts/{alert_id}'
            row = tx.get(path)
            if not row or row['user_id'] != user_id:
                raise AppException('Không tìm thấy cảnh báo', code='ALERT_NOT_FOUND', status_code=404)
            if row['status'] == 'PENDING':
                if action == 'timeout' and now < row['deadline_at']:
                    return row
                cancelled = action == 'cancel' and now < row['deadline_at']
                row.update(status='CANCELLED' if cancelled else 'DISPATCHING', decided_at=now,
                           decision_reason=action if now < row['deadline_at'] else 'timeout')
                tx.set(path, row)
            return row
        return self.store.atomic(operation)

    def claim_dispatch(self, alert_id, now, token):
        def operation(tx):
            path = f'audio_alerts/{alert_id}'
            row = tx.get(path)
            if not row or row['status'] != 'DISPATCHING':
                return None
            if row.get('lease_until') and row['lease_until'] > now:
                return None
            row.update(lease_until=now + timedelta(seconds=30), lease_token=token)
            tx.set(path, row)
            return row
        return self.store.atomic(operation)

    def materialize(self, alert_id, token, recipients, payload, now):
        def operation(tx):
            path = f'audio_alerts/{alert_id}'
            row = tx.get(path)
            if not row or row['status'] != 'DISPATCHING' or row.get('lease_token') != token:
                return row
            proposed = f'audio-{alert_id}'
            location = ({'latitude': row['latitude'], 'longitude': row['longitude']}
                        if row.get('latitude') is not None and row.get('longitude') is not None else None)
            session = ensure_active_session(tx, row['user_id'], dict(
                session_id=proposed, user_id=row['user_id'], status='ACTIVE',
                trigger_type='SCREAM_DETECTED', severity='CRITICAL', event_details='SCREAM',
                initial_location=location, latest_location=location,
                activated_at=now, created_at=now, updated_at=now))
            # Snapshot only the recipients and text payload; never audio/features.
            if session['session_id'] == proposed:
                for recipient in recipients:
                    job_id = key(alert_id + ':' + recipient['contact_id'])
                    job_path = f'audio_notification_outbox/{job_id}'
                    if not tx.get(job_path):
                        tx.set(job_path, dict(job_id=job_id, alert_id=alert_id, user_id=row['user_id'],
                            contact_id=recipient['contact_id'], chat_id=recipient['chat_id'], payload=payload,
                            status='PENDING', attempts=0, next_attempt_at=now, lease_until=now))
            check_id = row.get('safety_check_instance_id')
            check = tx.get(f'safety_check_instances/{check_id}') if check_id else None
            if check and check.get('user_id') == row['user_id'] and check.get('status') in ('ACTIVE', 'CHECK_REQUIRED'):
                check.update(status='CANCELLED', cancelled_reason='SOS_HANDOFF', updated_at=now)
                tx.set(f'safety_check_instances/{check_id}', check)
            row.update(status='SOS_CREATED', emergency_session_id=session['session_id'],
                       reused_session=session['session_id'] != proposed, lease_until=now)
            tx.set(path, row)
            return row
        return self.store.atomic(operation)

    def work(self, now):
        # Single-field indexes suffice; a dedicated worker keeps deadline timing
        # independent of the existing 30-second Safety Check scheduler.
        rows = self.store.scan('audio_alerts', [('status', 'in', ['PENDING', 'DISPATCHING'])])
        return [r for r in rows if r['deadline_at'] <= now or r['status'] == 'DISPATCHING']

    def jobs(self, alert_id=None):
        filters = [('alert_id', '==', alert_id)] if alert_id else [('status', 'in', ['PENDING', 'RETRY', 'SENDING'])]
        return self.store.scan('audio_notification_outbox', filters)

    def claim_job(self, job_id, now, token):
        def operation(tx):
            path = f'audio_notification_outbox/{job_id}'
            row = tx.get(path)
            if not row or row['status'] not in ('PENDING', 'RETRY', 'SENDING'):
                return None
            if row['next_attempt_at'] > now or row['lease_until'] > now:
                return None
            alert = tx.get(f"audio_alerts/{row['alert_id']}") or {}
            session_id = alert.get('emergency_session_id')
            session = tx.get(f'emergency_sessions/{session_id}') if session_id else None
            if session and session.get('status') != 'ACTIVE':
                row.update(status='FAILED', error_code='SESSION_ENDED', lease_until=now)
                tx.set(path, row)
                return None
            row.update(status='SENDING', attempts=row['attempts'] + 1, lease_token=token,
                       uncertain=row['status'] == 'SENDING' or row.get('uncertain', False),
                       lease_until=now + timedelta(seconds=30))
            tx.set(path, row)
            return row
        return self.store.atomic(operation)

    def finish_job(self, job_id, token, result, now):
        def operation(tx):
            path = f'audio_notification_outbox/{job_id}'
            row = tx.get(path)
            if row.get('lease_token') != token or row['status'] != 'SENDING':
                return
            retry = not result.success and result.retryable and row['attempts'] < 6
            delay = max(result.retry_after_seconds or 0, min(120, 2 ** row['attempts']))
            row.update(status='SENT' if result.success else 'RETRY' if retry else 'FAILED',
                       message_id=result.message_id, error_code=result.error_code,
                       uncertain=row.get('uncertain', False) or result.delivery_uncertain,
                       lease_until=now, next_attempt_at=now + timedelta(seconds=delay))
            tx.set(path, row)
        self.store.atomic(operation)
