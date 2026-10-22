from fastapi import APIRouter, Depends, Path

from app.modules.auth.dependencies import get_current_user
from app.modules.auth.schemas import AuthenticatedUser
from app.shared.schemas.envelope import ApiResponse
from .schemas import AlertCandidate, AlertResponse
from .service import AlertService, get_alert_service

router = APIRouter()


@router.post('/alerts', response_model=ApiResponse[AlertResponse])
async def create_alert(data: AlertCandidate, user: AuthenticatedUser = Depends(get_current_user),
                       service: AlertService = Depends(get_alert_service)):
    return ApiResponse.ok(data=await service.create(user.uid, data))


@router.get('/alerts/current', response_model=ApiResponse[AlertResponse | None])
async def current_alert(user: AuthenticatedUser = Depends(get_current_user),
                        service: AlertService = Depends(get_alert_service)):
    return ApiResponse.ok(data=await service.current(user.uid))


@router.post('/alerts/{alert_id}/confirm', response_model=ApiResponse[AlertResponse])
async def confirm_alert(alert_id: str = Path(pattern=r'^[a-f0-9]{40}$'),
                        user: AuthenticatedUser = Depends(get_current_user),
                        service: AlertService = Depends(get_alert_service)):
    return ApiResponse.ok(data=await service.decide(user.uid, alert_id, 'confirm'))


@router.post('/alerts/{alert_id}/cancel', response_model=ApiResponse[AlertResponse])
async def cancel_alert(alert_id: str = Path(pattern=r'^[a-f0-9]{40}$'),
                       user: AuthenticatedUser = Depends(get_current_user),
                       service: AlertService = Depends(get_alert_service)):
    return ApiResponse.ok(data=await service.decide(user.uid, alert_id, 'cancel'))
