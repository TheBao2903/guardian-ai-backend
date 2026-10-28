"""GPS API, tenant isolation and async I/O regressions; all I/O is fake."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from threading import get_ident
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
import json

import httpx
import pytest
from google.api_core.exceptions import FailedPrecondition, ResourceExhausted
from pydantic import ValidationError

from app.core.exceptions import EntityNotFoundException
from app.modules.detection.alerts.schemas import AlertCandidate
from app.modules.detection.schemas import AudioAnalyzeRequest
from app.modules.emergency.schemas import EmergencyTriggerRequest
from app.modules.emergency.safety_check.schemas import StartSafetyCheckRequest
from app.modules.location.repository import LocationRepository
from app.modules.location.schemas import LocationCheckpointCreateRequest
from app.modules.location.service import LocationService
from app.modules.notifications.providers.telegram import TelegramBotProvider
from app.modules.notifications.schemas import NotificationResult, SosAlertPayload
from app.modules.notifications.service import NotificationService
from app.modules.users.schemas import UpdateDeviceLocationRequest
from app.modules.users.service import UserService
from app.shared.enums.contact import NotificationChannel
from app.shared.schemas.location import GeoPointSchema


@pytest.mark.parametrize('model,base', [
    (UpdateDeviceLocationRequest, {'device_name': 'Phone'}),
    (EmergencyTriggerRequest, {}),
    (StartSafetyCheckRequest, {'duration_minutes': 15}),
    (AudioAnalyzeRequest, {}),
    (AlertCandidate, dict(monitoring_session_id='m', idempotency_key='k',
                          confidence=.9, captured_at=datetime.now(timezone.utc))),
])
@pytest.mark.parametrize('coordinates', [
    {'latitude': 21}, {'longitude': 105},
    {'latitude': 91, 'longitude': 105},
    {'latitude': 21, 'longitude': -181},
    {'latitude': float('nan'), 'longitude': 105},
    {'latitude': 21, 'longitude': float('inf')},
])
def test_location_requests_reject_invalid_or_partial_coordinates(model, base, coordinates):
    with pytest.raises(ValidationError):
        model(**base, **coordinates)


@pytest.mark.parametrize('accuracy', [-1, float('nan'), float('inf')])
def test_device_location_rejects_invalid_accuracy(accuracy):
    with pytest.raises(ValidationError):
        UpdateDeviceLocationRequest(device_name='Phone', latitude=0, longitude=0, accuracy=accuracy)


def test_no_gps_is_accepted_and_zero_coordinates_remain_valid():
    assert EmergencyTriggerRequest().latitude is None
    assert UpdateDeviceLocationRequest(device_name='Phone').latitude is None
    request = UpdateDeviceLocationRequest(device_name='Phone', latitude=0, longitude=0, accuracy=0)
    assert request.latitude == request.longitude == request.accuracy == 0


class Query:
    def __init__(self, rows, filters=(), fail=False):
        self.rows, self.filters, self.fail = rows, filters, fail

    def where(self, *, filter):
        return Query(self.rows, (*self.filters, filter), self.fail)

    def order_by(self, *args, **kwargs):
        if self.fail:
            raise FailedPrecondition('Index not ready')
        return self

    def limit(self, limit):
        return self

    def stream(self):
        return iter(SimpleNamespace(id=str(i), to_dict=lambda r=row: deepcopy(r))
                    for i, row in enumerate(self.rows)
                    if all(row.get(f.field_path) == f.value for f in self.filters))


@pytest.mark.parametrize('missing_index', [False, True])
def test_session_filter_never_returns_another_users_location(missing_index):
    repository = object.__new__(LocationRepository)
    repository.collection = Query([
        dict(user_id='owner', session_id='private-session', created_at='2026-10-28'),
        dict(user_id='other', session_id='public-session', created_at='2026-10-28'),
    ], fail=missing_index)
    assert repository.list_by_user('other', session_id='private-session') == []
    own = repository.list_by_user('owner', session_id='private-session')
    assert len(own) == 1 and own[0]['user_id'] == 'owner'


def test_quota_exhaustion_does_not_trigger_a_broader_query():
    repository = object.__new__(LocationRepository)
    repository.collection = Mock()
    query = repository.collection.where.return_value
    query.order_by.side_effect = ResourceExhausted('quota')
    with pytest.raises(ResourceExhausted):
        repository.list_by_user('u')
    repository.collection.where.assert_called_once()


def test_filtered_location_query_has_a_composite_index_in_both_manifests():
    root = Path(__file__).resolve().parents[2]
    for path in [root / 'firestore.indexes.json', root / 'backend/firestore.indexes.json']:
        indexes = json.loads(path.read_text(encoding='utf-8'))['indexes']
        assert any(index['collectionGroup'] == 'location_checkpoints' and
                   {f['fieldPath'] for f in index['fields']} ==
                   {'user_id', 'session_id', 'created_at'} for index in indexes)


def test_device_update_and_profile_reads_run_off_the_event_loop():
    main_thread = get_ident()
    threads = []
    repo, medical = Mock(), Mock()

    def update(uid, row):
        threads.append(get_ident())
        return dict(uid=uid, **row)

    def read_medical(uid):
        threads.append(get_ident())
        return {}

    repo.update.side_effect = update
    medical.get_by_uid.side_effect = read_medical
    service = UserService(repo, medical)
    response = asyncio.run(service.update_device_location('u', UpdateDeviceLocationRequest(
        device_name='Phone', latitude=0, longitude=0, accuracy=15)))
    assert response.last_known_location['latitude'] == 0
    assert response.last_known_location['accuracy'] == 15
    assert response.last_known_location['updated_at'].tzinfo is not None
    assert len(threads) == 2 and all(t != main_thread for t in threads)


def test_checkpoint_database_work_runs_off_loop_and_keeps_exact_coordinates():
    main_thread = get_ident()
    threads = []
    rows = []

    def create(checkpoint_id, row):
        threads.append(get_ident())
        rows.append(dict(row, created_at=datetime.now(timezone.utc)))
        return rows[-1]

    def read(*args, **kwargs):
        threads.append(get_ident())
        return rows[0]

    def listing(**kwargs):
        threads.append(get_ident())
        return rows

    repo = Mock(create=create, get_latest_by_user=read, list_by_user=listing)
    service = LocationService(repo)

    async def run():
        created = await service.record_checkpoint('u', LocationCheckpointCreateRequest(
            latitude=0, longitude=105.12345, accuracy_meters=12))
        latest = await service.get_latest_location('u')
        listing = await service.list_checkpoints('u')
        assert latest.location == created.location == listing[0].location
        assert latest.maps_url.endswith('0.0,105.12345')
        assert latest.location.accuracy_meters == 12

    asyncio.run(run())
    assert len(threads) == 3 and all(t != main_thread for t in threads)


def test_absent_checkpoint_returns_not_found_without_inventing_coordinates():
    service = LocationService(Mock(get_latest_by_user=Mock(return_value=None)))
    with pytest.raises(EntityNotFoundException):
        asyncio.run(service.get_latest_location('u'))


def test_corrupt_checkpoint_does_not_become_zero_zero():
    service = LocationService(Mock())
    with pytest.raises(ValidationError):
        service._to_checkpoint_response(dict(location={}, created_at=datetime.now(timezone.utc)))


def test_notification_audit_runs_off_loop_and_preserves_location_payload():
    main_thread = get_ident()
    threads = []
    provider = AsyncMock()
    provider.send_sos_alert.return_value = NotificationResult(
        success=True, channel=NotificationChannel.TELEGRAM, recipient='chat', message_id='1')
    service = NotificationService(telegram_provider=provider, db=Mock())
    service._log_notification_audit = lambda *args: threads.append(get_ident())
    payload = SosAlertPayload(user_name='Test', location=GeoPointSchema(latitude=0, longitude=0))
    result = asyncio.run(service.broadcast_sos('u', [SimpleNamespace(is_active=True, telegram_id='chat')], payload))
    assert result[0].success
    assert threads and threads[0] != main_thread
    assert provider.send_sos_alert.call_args.args[1] is payload


@pytest.mark.parametrize('location', [None, GeoPointSchema(latitude=0, longitude=0)])
def test_telegram_reports_missing_gps_or_sends_exact_maps_links(location):
    messages = []

    def send(request):
        messages.append(json.loads(request.content)['text'])
        return httpx.Response(200, json={'ok': True, 'result': {'message_id': 1}})

    provider = TelegramBotProvider(bot_token='offline-test-token', transport=httpx.MockTransport(send))
    result = asyncio.run(provider.send_sos_alert('chat', SosAlertPayload(user_name='Test', location=location)))
    assert result.success
    if location is None:
        assert 'Không có tọa độ GPS' in messages[0]
        assert 'maps?q=' not in messages[0]
    else:
        assert 'maps?q=0.0,0.0' in messages[0]
        assert 'destination=0.0,0.0' in messages[0]
