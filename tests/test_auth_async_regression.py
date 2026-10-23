import asyncio
from datetime import datetime, timedelta, timezone
from threading import get_ident
from types import SimpleNamespace
from unittest.mock import Mock

import jwt
import pytest
from fastapi.security import HTTPAuthorizationCredentials

from app.core.exceptions import UnauthorizedException
from app.modules.auth import dependencies


@pytest.mark.parametrize('status', ['active', 'disabled'])
def test_auth_account_status_still_read_from_database_in_worker_thread(monkeypatch, status):
    secret = 'offline-regression-test-secret-32-bytes'
    monkeypatch.setattr(dependencies, 'get_settings', lambda: SimpleNamespace(
        JWT_SECRET=secret, JWT_ALGORITHM='HS256'))
    db = Mock()
    main_thread = get_ident()
    threads = []
    def read():
        threads.append(get_ident())
        return SimpleNamespace(exists=True, to_dict=lambda: {'status': status, 'role': 'user'})
    db.collection.return_value.document.return_value.get.side_effect = read
    monkeypatch.setattr(dependencies, 'get_firestore_client', lambda: db)
    token = jwt.encode({'uid': 'u', 'exp': datetime.now(timezone.utc) + timedelta(minutes=1)},
                       secret, algorithm='HS256')
    credentials = HTTPAuthorizationCredentials(scheme='Bearer', credentials=token)
    if status == 'disabled':
        with pytest.raises(UnauthorizedException):
            asyncio.run(dependencies.get_current_user(credentials))
    else:
        assert asyncio.run(dependencies.get_current_user(credentials)).uid == 'u'
    assert len(threads) == 1 and threads[0] != main_thread
    db.collection.assert_called_once_with('users')
    db.collection.return_value.document.assert_called_once_with('u')
