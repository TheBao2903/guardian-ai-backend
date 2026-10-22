"""
=============================================================================
FILE: app/modules/contacts/router.py
MODULE: Contacts - HTTP Router
ROLE / RESPONSIBILITY:
    - Định tuyến các API endpoint quản lý danh bạ khẩn cấp:
      + GET  /api/v1/contacts: Lấy danh sách người thân (sắp xếp theo priority).
      + POST /api/v1/contacts: Thêm liên hệ mới.
      + PUT  /api/v1/contacts/reorder: Sắp xếp lại thứ tự ưu tiên (Reorder).
      + GET  /api/v1/contacts/{contact_id}: Xem chi tiết một người thân.
      + PUT  /api/v1/contacts/{contact_id}: Cập nhật thông tin người thân.
      + DELETE /api/v1/contacts/{contact_id}: Xóa người thân khỏi danh bạ.
    - Toàn bộ endpoints được bảo vệ bởi dependency xác thực Firebase ID Token.

CONNECTIONS / DEPENDENCIES:
    - app/modules/auth/dependencies.py (get_current_user)
    - app/modules/auth/schemas.py (AuthenticatedUser)
    - app/modules/contacts/service.py (ContactService)
    - app/modules/contacts/schemas.py (ContactResponse, ContactCreateRequest, ContactUpdateRequest, ContactReorderRequest)
    - app/shared/schemas/envelope.py (ApiResponse)

INPUT / OUTPUT:
    - Input: ContactCreateRequest, ContactUpdateRequest, ContactReorderRequest.
    - Output: ApiResponse[ContactResponse | List[ContactResponse] | Dict].
=============================================================================
"""

from typing import Dict, List
from fastapi import APIRouter, Depends, Path, status

from app.modules.auth.dependencies import get_current_user
from app.modules.auth.schemas import AuthenticatedUser
from app.modules.contacts.schemas import (
    ContactCreateRequest,
    ContactReorderRequest,
    ContactResponse,
    ContactUpdateRequest,
)
from app.modules.contacts.service import ContactService
from app.shared.schemas.envelope import ApiResponse

router = APIRouter()
contact_service = ContactService()


@router.get(
    "",
    response_model=ApiResponse[List[ContactResponse]],
    summary="Lấy danh sách người liên hệ khẩn cấp",
)
async def list_emergency_contacts(
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[List[ContactResponse]]:
    """Trả về danh sách người thân sắp xếp theo thứ tự ưu tiên tăng dần (Priority 1 là người gọi chính)."""
    contacts = await contact_service.list_contacts(current_user.uid)
    return ApiResponse.ok(data=contacts, message="Lấy danh bạ khẩn cấp thành công")


@router.post(
    "",
    response_model=ApiResponse[ContactResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Thêm mới người liên hệ khẩn cấp",
)
async def create_emergency_contact(
    data: ContactCreateRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[ContactResponse]:
    """Thêm một người thân mới vào danh bạ khẩn cấp."""
    new_contact = await contact_service.create_contact(current_user.uid, data)
    return ApiResponse.ok(data=new_contact, message="Thêm người thân thành công")


@router.put(
    "/reorder",
    response_model=ApiResponse[List[ContactResponse]],
    summary="Sắp xếp lại thứ tự ưu tiên gọi điện của danh bạ",
)
async def reorder_emergency_contacts(
    data: ContactReorderRequest,
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[List[ContactResponse]]:
    """Cập nhật hàng loạt mức ưu tiên (Priority 1, 2, 3...) cho danh bạ."""
    reordered_contacts = await contact_service.reorder_contacts(current_user.uid, data)
    return ApiResponse.ok(data=reordered_contacts, message="Cập nhật thứ tự ưu tiên thành công")


@router.get(
    "/{contact_id}",
    response_model=ApiResponse[ContactResponse],
    summary="Xem chi tiết một người liên hệ khẩn cấp",
)
async def get_emergency_contact(
    contact_id: str = Path(..., description="ID của người liên hệ"),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[ContactResponse]:
    """Xem thông tin chi tiết một người thân."""
    contact = await contact_service.get_contact(current_user.uid, contact_id)
    return ApiResponse.ok(data=contact, message="Lấy chi tiết người thân thành công")


@router.put(
    "/{contact_id}",
    response_model=ApiResponse[ContactResponse],
    summary="Cập nhật thông tin người liên hệ khẩn cấp",
)
async def update_emergency_contact(
    data: ContactUpdateRequest,
    contact_id: str = Path(..., description="ID của người liên hệ"),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[ContactResponse]:
    """Cập nhật họ tên, mối quan hệ, SĐT, Telegram ID hoặc mức ưu tiên."""
    updated = await contact_service.update_contact(current_user.uid, contact_id, data)
    return ApiResponse.ok(data=updated, message="Cập nhật thông tin người thân thành công")


@router.delete(
    "/{contact_id}",
    response_model=ApiResponse[Dict[str, str]],
    summary="Xóa người liên hệ khỏi danh bạ khẩn cấp",
)
async def delete_emergency_contact(
    contact_id: str = Path(..., description="ID của người liên hệ"),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[Dict[str, str]]:
    """Xóa bỏ một người liên hệ khỏi danh bạ."""
    await contact_service.delete_contact(current_user.uid, contact_id)
    return ApiResponse.ok(data={"id": contact_id}, message="Đã xóa người thân khỏi danh bạ")


@router.post(
    "/{contact_id}/set-primary",
    response_model=ApiResponse[ContactResponse],
    summary="Đặt người liên hệ làm ưu tiên gọi #1",
)
async def set_primary_contact(
    contact_id: str = Path(..., description="ID của người liên hệ"),
    current_user: AuthenticatedUser = Depends(get_current_user),
) -> ApiResponse[ContactResponse]:
    """
    Đặt một người liên hệ làm số ưu tiên gọi khẩn cấp #1.
    Tự động hạ priority của người liên hệ cũ xuống.
    """
    updated = await contact_service.set_primary_contact(current_user.uid, contact_id)
    return ApiResponse.ok(data=updated, message="Đã đặt làm người gọi khẩn cấp ưu tiên #1")
