"""Authenticated, read-only websocket for audio alerts. Actions remain HTTP."""
import asyncio
from datetime import datetime, timezone
from anyio import CancelScope

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.security import HTTPAuthorizationCredentials

from app.core.exceptions import AppException
from app.modules.auth.dependencies import get_current_user
from .realtime import alert_feeds

router = APIRouter()


@router.websocket('/alerts/stream')
async def stream_alerts(websocket: WebSocket):
    await websocket.accept()
    receive_task = update_task = None
    try:
        # Browser clients cannot supply an Authorization header in the
        # handshake. Keep credentials out of URLs and access logs.
        message = await asyncio.wait_for(websocket.receive_json(), 10)
        if not isinstance(message, dict) or message.get('type') != 'AUTH' or not isinstance(message.get('token'), str):
            await websocket.close(code=4401)
            return
        credentials = HTTPAuthorizationCredentials(scheme='Bearer', credentials=message['token'])
        user = await get_current_user(credentials)
        async with alert_feeds.subscribe(user.uid) as queue:
            receive_task = asyncio.create_task(websocket.receive_json())
            update_task = asyncio.create_task(queue.get())
            last_auth = asyncio.get_running_loop().time()
            while True:
                done, _ = await asyncio.wait(
                    [receive_task, update_task], timeout=2,
                    return_when=asyncio.FIRST_COMPLETED)
                if receive_task in done:
                    incoming = receive_task.result()
                    if not isinstance(incoming, dict) or incoming.get('type') != 'PING':
                        await websocket.close(code=4400)
                        return
                    await websocket.send_json({'type': 'PONG'})
                    receive_task = asyncio.create_task(websocket.receive_json())
                now = asyncio.get_running_loop().time()
                if update_task in done or now - last_auth >= 60:
                    authorized = await get_current_user(credentials)
                    if authorized.uid != user.uid:
                        await websocket.close(code=4401)
                        return
                    last_auth = now
                if update_task in done:
                    value = update_task.result()
                    if isinstance(value, Exception):
                        await websocket.close(code=1013)
                        return
                    # A shared feed's latest state may predate a new subscriber.
                    # Countdown uses the send time, never a cached server clock.
                    if value is not None:
                        value = dict(value, server_time=datetime.now(timezone.utc).isoformat())
                    await websocket.send_json({'type': 'AUDIO_ALERT', 'data': value})
                    update_task = asyncio.create_task(queue.get())
                if not done:
                    await websocket.send_json({'type': 'HEARTBEAT'})
    except AppException as exc:
        await websocket.close(code=4401 if exc.status_code in (401, 403) else 1013)
    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:
        # ASGI shutdown/disconnect can cancel a socket before receive_json
        # observes the disconnect. This read-only endpoint still cleans up.
        pass
    except (ValueError, TypeError):
        await websocket.close(code=4400)
    except Exception:
        await websocket.close(code=1013)
    finally:
        for task in (receive_task, update_task):
            if task:
                task.cancel()
        with CancelScope(shield=True):
            await asyncio.gather(*(task for task in (receive_task, update_task) if task), return_exceptions=True)
