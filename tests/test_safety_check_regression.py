"""Existing Safety Check business contracts; this feature changes no SC code."""
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

import pytest

from app.core.exceptions import UnauthorizedException, ValidationException
from app.modules.emergency.safety_check.schemas import (
    StartSafetyCheckRequest, ExtendSafetyCheckRequest, ConfirmSafeRequest,
    CancelSafetyCheckRequest,
)
from app.modules.emergency.safety_check.service import SafetyCheckService


class Repository:
    def __init__(self):
        self.rows = {}

    def get_active_instance_by_user(self, uid):
        return next((deepcopy(row) for row in self.rows.values()
                     if row['user_id'] == uid and row['status'] in ('ACTIVE', 'CHECK_REQUIRED')), None)

    def get_visible_template(self, uid, template_id):
        return dict(name='Đi bộ về nhà', default_grace_period_seconds=120)

    def create_instance(self, instance_id, row):
        self.rows[instance_id] = deepcopy(row)
        return deepcopy(row)

    def get_instance(self, instance_id):
        return deepcopy(self.rows.get(instance_id))

    def update_instance(self, instance_id, data):
        self.rows[instance_id].update(deepcopy(data))
        return self.get_instance(instance_id)

    def claim_overdue(self, instance_id, now):
        row = self.rows[instance_id]
        if row['status'] not in ('ACTIVE', 'CHECK_REQUIRED') or row['grace_period_until'] > now:
            return None
        return self.update_instance(instance_id, dict(status='ESCALATED', escalated_at=now))


def setup_service():
    repo = Repository()
    contacts = AsyncMock()
    contacts.list_contacts.return_value = []
    notifications = AsyncMock()
    users = Mock()
    users.get_by_id.return_value = {'name': 'User'}
    medical = Mock()
    medical.get_by_uid.return_value = {'privacy_level': 'PRIVATE'}
    svc = SafetyCheckService(repo, contacts, notifications, AsyncMock(), users, medical)
    return svc, repo, notifications


def test_start_keeps_duration_template_grace_and_blocks_duplicate():
    async def run():
        svc, _, _ = setup_service()
        request = StartSafetyCheckRequest(template_id='walking', duration_minutes=20)
        started = await svc.start_safety_check('u', request)
        assert started.status == 'ACTIVE'
        assert started.name == 'Đi bộ về nhà'
        assert started.expires_at - started.started_at == timedelta(minutes=20)
        assert started.grace_period_until - started.expires_at == timedelta(seconds=120)
        with pytest.raises(ValidationException):
            await svc.start_safety_check('u', request)
    asyncio.run(run())


def test_extend_keeps_original_deadline_basis_grace_and_three_extension_limit():
    async def run():
        svc, repo, _ = setup_service()
        started = await svc.start_safety_check('u', StartSafetyCheckRequest(duration_minutes=20, grace_period_seconds=90))
        repo.rows[started.instance_id]['status'] = 'CHECK_REQUIRED'
        for count in range(1, 4):
            response = await svc.extend_timer('u', started.instance_id, ExtendSafetyCheckRequest(extend_minutes=15))
            assert response.status == 'ACTIVE'
            assert response.extension_count == count
            assert response.expires_at == started.expires_at + timedelta(minutes=15 * count)
            assert response.grace_period_until - response.expires_at == timedelta(seconds=90)
        with pytest.raises(ValidationException):
            await svc.extend_timer('u', started.instance_id, ExtendSafetyCheckRequest())
    asyncio.run(run())


@pytest.mark.parametrize('action', ['confirm', 'cancel', 'extend'])
def test_other_user_cannot_change_safety_check(action):
    async def run():
        svc, repo, _ = setup_service()
        started = await svc.start_safety_check('u', StartSafetyCheckRequest(duration_minutes=20))
        before = deepcopy(repo.rows)
        with pytest.raises(UnauthorizedException):
            if action == 'confirm':
                await svc.confirm_safe('other', started.instance_id, ConfirmSafeRequest())
            elif action == 'cancel':
                await svc.cancel_instance('other', started.instance_id, CancelSafetyCheckRequest())
            else:
                await svc.extend_timer('other', started.instance_id, ExtendSafetyCheckRequest())
        assert repo.rows == before
    asyncio.run(run())


@pytest.mark.parametrize('action,expected', [('confirm', 'COMPLETED'), ('cancel', 'CANCELLED')])
def test_confirm_or_cancel_prevents_late_scheduler_escalation(action, expected):
    async def run():
        svc, repo, notification = setup_service()
        started = await svc.start_safety_check('u', StartSafetyCheckRequest(duration_minutes=20))
        stale = repo.get_instance(started.instance_id)
        if action == 'confirm':
            await svc.confirm_safe('u', started.instance_id, ConfirmSafeRequest())
        else:
            await svc.cancel_instance('u', started.instance_id, CancelSafetyCheckRequest())
        response = await svc.escalate_instance(stale)
        assert response.status == expected
        notification.broadcast_safety_check_timeout.assert_not_awaited()
    asyncio.run(run())


def test_grace_expiration_escalates_once_then_confirm_sends_all_clear():
    async def run():
        svc, repo, notification = setup_service()
        started = await svc.start_safety_check('u', StartSafetyCheckRequest(duration_minutes=20))
        pending = repo.get_instance(started.instance_id)
        await svc.escalate_instance(pending)
        notification.broadcast_safety_check_timeout.assert_not_awaited()
        repo.rows[started.instance_id]['grace_period_until'] = datetime.now(timezone.utc) - timedelta(seconds=1)
        response = await svc.escalate_instance(pending)
        assert response.status == 'ESCALATED'
        notification.broadcast_safety_check_timeout.assert_awaited_once()
        payload = notification.broadcast_safety_check_timeout.call_args.args[2]
        assert payload.medical_notes is None
        assert payload.medical_profile_url is None
        await svc.escalate_instance(pending)
        notification.broadcast_safety_check_timeout.assert_awaited_once()
        completed = await svc.confirm_safe('u', started.instance_id, ConfirmSafeRequest())
        assert completed.status == 'COMPLETED'
        notification.broadcast_all_clear.assert_awaited_once()
    asyncio.run(run())
