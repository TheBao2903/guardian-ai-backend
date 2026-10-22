# Guardian AI — Current Project State

> **Last Updated:** 2026-10-08  
> **Status:** All Backend Phases B1-B9 Completed (56/56 Tests Passed - 100%), Ready for Mobile Client & CI/CD Deployment

---

## 1. Project Summary

Guardian AI là ứng dụng an toàn cá nhân mobile (Mobile Personal Safety App) lấy cảm hứng từ Google Personal Safety nhưng được tinh gọn hóa và tối ưu chi phí:
- **Mobile-First Client:** Flutter / Dart (hỗ trợ kiểm thử trên iPhone bằng GitHub Actions CI + Sideloadly trên máy tính Windows).
- **Backend:** Python 3.14 + FastAPI (Modular Monolith).
- **Authentication:** Firebase Authentication (FastAPI xác thực Firebase ID Token).
- **Database:** Firebase Firestore.
- **Binary/Object Storage:** Cloudflare R2 (Lưu các đoạn ghi âm bằng chứng khẩn cấp).
- **Realtime:** WebSocket + asyncio (dành cho vị trí GPS thời gian thực và cập nhật trạng thái khẩn cấp).
- **Notification:** Telegram Bot API (gửi cảnh báo, link vị trí Google Maps và file ghi âm).
- **AI Audio Detection:** YAMNet (baseline nhận diện âm thanh chung) + VocalBurst Locator (phát hiện tiếng la hét / distress) + Temporal Aggregation chống false positive.

---

## 2. Core Features (Scope Locked)

1. **User Profile & Emergency Medical Profile:**
   - Thông tin cá nhân: Họ tên, tuổi, ngày sinh.
   - Thông tin y tế & khẩn cấp: Nhóm máu, chiều cao, cân nặng, dị ứng, bệnh nền, danh sách thuốc.
   - Phân cấp hiển thị 3 mức bảo mật: Private, Emergency-Sharable, Lock-Screen Public.
2. **Emergency Contacts:**
   - Quản lý danh bạ người thân (họ tên, mối quan hệ, số điện thoại, Telegram recipient, mức ưu tiên).
3. **Emergency SOS Workflow:**
   - Kích hoạt qua: Bấm nút trên app, Phím nguồn native (bấm nhanh $\ge 5$ lần), AI Detection Signal, hoặc Safety Check Timeout.
   - Vòng đời phiên khẩn cấp: `CREATED` $\rightarrow$ `ACTIVE` $\rightarrow$ `CANCELLED` / `RESOLVED` / `EXPIRED`.
   - Cơ chế Idempotent (chống spam duplicate session khi bấm liên tục).
4. **Safety Check Timer (Hẹn giờ kiểm tra an toàn):**
   - 5 template mặc định: Đi bộ về nhà, Di chuyển bằng xe, Khám phá ngoài trời, Kiểm tra an toàn, Cuộc gặp an toàn.
   - Cho phép người dùng tạo Custom Template.
   - Escalation Flow: `ACTIVE` $\rightarrow$ `CHECK_REQUIRED` (Grace Period 30s-10m) $\rightarrow$ `COMPLETED` / `CANCELLED` / `ESCALATED`.
   - Khi `ESCALATED`: Chuyển sang `SAFETY_CHECK_TIMEOUT` thông báo người thân + gửi vị trí gần nhất.
   - Local notification độc lập trên thiết bị, không chạy countdown backend từng giây.
5. **Local Safety Signals & Direct Call (Trên thiết bị di động):**
   - Hú còi báo động (Alarm Siren) qua `AVAudioSessionCategoryPlayback` (iOS) phát to ngay cả khi máy gạt tắt loa.
   - Nhấp nháy đèn flash LED camera (Strobe light) để xua đuổi kẻ xấu / định vị cứu hộ trong đêm.
   - Intent gọi điện trực tiếp (`url_launcher: tel:...`) cho số liên hệ ưu tiên số 1 khi kích hoạt SOS.
6. **Bằng chứng ghi âm (Emergency Audio Recording):**
   - Rolling buffer cục bộ $\rightarrow$ khi có sự kiện SOS mới trích xuất đoạn âm thanh liên quan tải lên Cloudflare R2.
7. **Chia sẻ vị trí thời gian thực:**
   - Stream GPS qua WebSocket, checkpoint lưu Firestore khi có sự kiện.

---

## 3. Quy trình phát triển & Kiểm thử iOS trên Windows

- Môi trường dev: Windows PC + iPhone thật (không có máy Mac).
- Phát triển logic & UI: Kiểm thử trực tiếp qua Flutter Windows / Web để Hot Reload tức thì.
- Biên dịch ứng dụng iOS: Đẩy code lên GitHub, sử dụng **GitHub Actions (macOS Runner miễn phí)** tự động build ra file **`.ipa`**.
- Cài đặt vào iPhone: Tải file `.ipa` về Windows, dùng **Sideloadly / 3uTools** cắm cáp USB ký bằng Apple ID cá nhân và cài trực tiếp vào iPhone để test phần cứng (Flash, Siren, GPS, Background Notifications).

---

## 4. Chiến lược triển khai hiện tại: BACKEND-FIRST

- **Quyết định:** Tạm gác hoàn toàn phần Frontend mobile lại, dồn toàn lực thiết kế, lập trình và kiểm thử toàn diện 100% cho hệ thống Backend FastAPI.
- **Trạng thái:**
  - [x] Rà soát và khóa toàn bộ phạm vi tính năng (Scope) từ tài liệu Word của khách hàng.
  - [x] Cố định kênh thông báo chính: **Telegram Bot API** (người thân) + **Native Local Notification** (nhắc nhở trên điện thoại người dùng). Sẵn sàng interface mở rộng FCM trong tương lai.
  - [x] Hoàn thiện bộ quy chuẩn kiến trúc: `PROJECT.md`, `ARCHITECTURE.md`, `CONVENTIONS.md` (Rule 33 Header Document), `DECISIONS.md` (ADR-001 đến ADR-035).
  - [x] Chi tiết hóa lộ trình Backend thành 9 giai đoạn rõ ràng trong `TODO.md` (Phase B1 đến Phase B9).
  - [x] **HOÀN THÀNH PHASE B1: Core Foundation & Infrastructure Clients**
    - `app/core/config.py`: Đọc cấu hình từ `.env` và tự động nạp file Firebase Admin SDK.
    - `app/core/logging.py`: Hệ thống log tự động che giấu (redact/mask) Token, Passwords, Medical data.
    - `app/core/exceptions.py`: Bộ ngoại lệ domain và Exception Handlers chuẩn hóa.
    - `app/infrastructure/firestore/client.py`: Kết nối Firebase Admin SDK & Firestore thành công (`Project ID: guardian-ai-66e0a`).
    - `app/infrastructure/storage/r2/client.py`: Kết nối Cloudflare R2 thành công (`Bucket: guardian-ai`).
    - `app/main.py`: Khởi tạo FastAPI app với lifespan và endpoint `/health` kiểm tra real-time các dịch vụ.
    - Unit tests đạt **7/7 PASSED** (`tests/unit/test_phase1_foundation.py`).
  - [x] **HOÀN THÀNH PHASE B2: Domain Schemas, Enums & Shared Contracts**
    - `app/shared/enums/detection.py`: Đa dạng hóa 11 loại sự kiện âm thanh nguy hiểm (`SCREAM`, `DISTRESS_CRY`, `CALL_FOR_HELP`, `GLASS_SHATTER`, `GUNSHOT`, `EXPLOSION`, `VIOLENT_STRUGGLE`, `AGGRESSIVE_BARK`, `CAR_CRASH_SOUND`, `ENVIRONMENTAL_ALARM`, `ABNORMAL_UNKNOWN`), 4 model AI (`YAMNET`, `VOCAL_BURST`, `FASTER_WHISPER`, `CUSTOM_ENSEMBLE`) và 4 cấp độ rủi ro (`NEGLIGIBLE`, `SUSPICIOUS`, `WARNING`, `EMERGENCY`).
    - `app/shared/enums/emergency.py` & `safety_check.py`: Vòng đời khẩn cấp, 5 trigger khẩn cấp, trạng thái Safety Check và 5 default template IDs.
    - `app/shared/enums/user.py` & `contact.py`: Nhóm máu, 3 cấp độ bảo vệ thông tin y tế, mối quan hệ và các kênh thông báo.
    - `app/shared/schemas/envelope.py`: Envelope `ApiResponse[T]` và `PaginatedResponse[T]`.
    - `app/shared/schemas/location.py`: `GeoPointSchema` với hàm sinh link Google Maps.
    - `app/shared/schemas/detection_signal.py`: Contract `DetectionSignal` chuẩn hóa từ AI model.
    - Bộ unit tests tự động đạt **14/14 PASSED** (7 tests Phase 1 + 7 tests Phase 2).
  - [x] **HOÀN THÀNH PHASE B3.1: Auth & User Profile Management**
    - `app/modules/auth/dependencies.py`: Dependency `get_current_user` xác thực Firebase ID Token qua `auth.verify_id_token(check_revoked=True)`.
    - `POST /api/v1/auth/register`: Đăng ký tài khoản trên Firebase Authentication + tạo user record trong Firestore `users` + cấp custom token.
    - `POST /api/v1/auth/login`: Xác thực ID Token (Mobile) hoặc Email, cập nhật `last_login_at`.
    - `POST /api/v1/auth/forgot-password`: Sinh link reset mật khẩu qua Firebase Admin SDK.
    - `POST /api/v1/auth/change-password`: Cập nhật mật khẩu tài khoản đang đăng nhập.
    - `GET /api/v1/auth/me`: Lấy thông tin định danh người dùng từ token Bearer.
    - `GET /api/v1/users/me` & `PUT /api/v1/users/me`: Quản lý hồ sơ cá nhân (Họ tên, Tuổi, Ngày tháng năm sinh, SĐT, Avatar, Telegram).
    - Bộ unit tests tự động đạt **19/19 PASSED** (thêm 5 tests cho Auth & Users).
  - [x] **HOÀN THÀNH PHASE B3.2: Emergency Medical Profile Module**
    - `app/modules/users/medical_schemas.py`: Phân cấp 3 tầng dữ liệu y tế (Tier 1 Private, Tier 2 Update, Tier 3 Lock-Screen Public).
    - `app/modules/users/medical_repository.py`: Thao tác Firestore collection `emergency_profiles` theo UID.
    - `app/modules/users/medical_service.py`: Xử lý Data Minimization & Privacy-by-design theo Nghị định 13/2023/NĐ-CP và GDPR.
    - `GET /api/v1/users/me/medical`: Lấy toàn bộ hồ sơ y tế cho chính chủ (nhóm máu, dị ứng, thuốc, bệnh nền, hiến tạng, ghi chú).
    - `PUT /api/v1/users/me/medical`: Cập nhật thông tin y tế và tùy chỉnh hiển thị màn hình khóa (`share_*_on_lock_screen`).
    - `GET /api/v1/users/{user_id}/public-emergency`: Endpoint công khai cho nhân viên y tế / người sơ cứu ngoài màn hình khóa (lọc dữ liệu nhạy cảm, tích hợp danh bạ gọi nhanh).
  - [x] **HOÀN THÀNH PHASE B3.3: Emergency Contacts Module**
    - `app/modules/contacts/schemas.py`: DTOs quản lý danh bạ khẩn cấp người thân, mối quan hệ, SĐT, Telegram Chat ID, Priority.
    - `app/modules/contacts/repository.py`: Thao tác Firestore subcollection `users/{uid}/emergency_contacts`.
    - `app/modules/contacts/service.py`: Tự động gán mức ưu tiên, sắp xếp Reorder, bảo vệ cách ly dữ liệu cá nhân.
    - `app/modules/contacts/router.py`: `GET /contacts`, `POST /contacts`, `PUT /contacts/reorder`, `GET /contacts/{id}`, `PUT /contacts/{id}`, `DELETE /contacts/{id}`.
    - Tích hợp tự động xóa dữ liệu liên hệ và y tế khi thực thi Quyền được lãng quên (`DELETE /api/v1/users/me/data`).
    - Bộ unit tests tự động toàn dự án đạt **24/24 PASSED** (0 warnings, 0 failures).
  - [x] **HOÀN THÀNH PHASE B4: Notification (Telegram Provider) & Recording (Cloudflare R2)**
    - `app/modules/notifications/providers/base.py`: Lớp trừu tượng `BaseNotificationProvider` mở rộng đa kênh.
    - `app/modules/notifications/providers/telegram.py`: `TelegramBotProvider` soạn thảo HTML trực quan, đính kèm Google Maps pin, mức pin thiết bị, cơ chế chống sập ứng dụng khi lỗi API Telegram, gửi audio bằng chứng.
    - `app/modules/notifications/service.py`: `NotificationService` phát tán cảnh báo hàng loạt cho người thân (`is_active=True`), ghi nhận Audit Trail vào Firestore `notifications`.
    - `POST /api/v1/notifications/test-telegram`: Endpoint kiểm tra kết nối bot tới Telegram Chat ID.
    - `app/modules/recordings/repository.py`: Firestore collection `recordings` lưu trữ metadata.
    - `app/modules/recordings/service.py`: Nhận stream upload multipart, sanitize tên file, đẩy binary vào Cloudflare R2 partitioned: `users/{user_id}/emergency/{event_id}/audio/{rec_id}_{file}`, sinh link presigned playback URL, kiểm tra quyền sở hữu bản ghi.
    - `POST /api/v1/recordings/upload`, `GET /api/v1/recordings`, `GET /api/v1/recordings/{id}`, `GET /api/v1/recordings/{id}/playback-url`, `DELETE /api/v1/recordings/{id}`.
  - [x] **HOÀN THÀNH PHASE B5: Real-time Location & WebSocket Stream**
    - `app/modules/location/schemas.py`: DTOs cho các mốc tọa độ Location Checkpoints và vị trí gần nhất (`LatestLocationResponse`).
    - `app/modules/location/repository.py`: Thao tác Firestore collection `location_checkpoints` lưu trữ các mốc vị trí quan trọng theo ADR-005.
    - `app/modules/location/service.py`: Ghi nhận checkpoint (SOS, AI detection, timeout), sinh URL Google Maps tự động.
    - `POST /api/v1/location/checkpoints`, `GET /api/v1/location/latest`, `GET /api/v1/location/checkpoints`.
    - `app/realtime/manager.py`: `ConnectionManager` quản lý vòng đời WebSocket, hỗ trợ đa thiết bị trên một tài khoản, mô hình phòng quan sát (Watchers) cho người thân subscribe stream vị trí GPS thời gian thực, cache RAM vị trí mới nhất.
    - `app/realtime/router.py`: WebSocket endpoint `/api/v1/realtime/stream?token=...` xác thực Firebase Token ngay lúc handshake (đóng lỗi 1008 nếu vi phạm), xử lý `PING`/`PONG`, tiếp nhận `LOCATION_STREAM` và phát tán `LOCATION_UPDATE` tức thời.
  - [x] **HOÀN THÀNH PHASE B6: Emergency Core Workflow (Orchestration & Idempotency)**
    - `app/modules/emergency/schemas.py`: DTOs kích hoạt SOS, vòng đời phiên khẩn cấp, hủy bỏ (Cancel) và giải quyết (Resolve).
    - `app/modules/emergency/repository.py`: Thao tác Firestore collection `emergency_sessions`, tìm kiếm phiên ACTIVE phục vụ cơ chế Idempotent chống spam khi bấm nút liên tục.
    - `app/modules/emergency/service.py`: Emergency Orchestration Pipeline 5 bước (Lưu session -> Ghi mốc tọa độ Location Checkpoint -> Lấy danh bạ người thân -> Gửi cảnh báo Telegram -> Broadcast WebSocket).
    - Hủy và giải quyết phiên khẩn cấp (`cancel_emergency`, `resolve_emergency`) kèm thông báo an toàn All-Clear cho người thân.
    - Endpoints: `POST /api/v1/emergency/sos`, `POST /api/v1/emergency/cancel`, `POST /api/v1/emergency/resolve`, `GET /api/v1/emergency/active`, `GET /api/v1/emergency/sessions`, `GET /api/v1/emergency/sessions/{id}`.
  - [x] **HOÀN THÀNH PHASE B7: Safety Check Timer Module & Async Expiration Scheduler**
    - `app/modules/emergency/safety_check/schemas.py`: DTOs cho các mẫu hẹn giờ (Templates), bắt đầu phiên (`StartSafetyCheckRequest`), gia hạn (`ExtendSafetyCheckRequest`), xác nhận an toàn (`ConfirmSafeRequest`), cập nhật tọa độ GPS (`UpdateLocationCheckpointRequest`).
    - `app/modules/emergency/safety_check/repository.py`: Firestore collections `safety_check_templates` và `safety_check_instances`. Tự động gieo mầm (Seeded) 5 mẫu hệ thống (`tpl_walking_home`, `tpl_commute_transit`, `tpl_outdoor_trekking`, `tpl_alone_home`, `tpl_meeting_stranger`).
    - `app/modules/emergency/safety_check/service.py`: Tính toán `expires_at`, `grace_period_until`, ngăn chặn trùng lặp phiên ACTIVE, gia hạn tối đa 3 lần, hủy phiên, chuyển đổi sang `COMPLETED`, cơ chế leo thang `ESCALATED` gọi Telegram và tự động gửi All-Clear nếu người dùng bấm an toàn sau khi trễ hẹn.
    - `app/modules/emergency/safety_check/scheduler.py`: Background worker chạy ngầm định kỳ (15-30 giây) quét các phiên quá hạn Grace Period và tự động kích hoạt leo thang cảnh báo.
    - `app/modules/emergency/safety_check/router.py`: Endpoints `/templates`, `/start`, `/current`, `/instances/{id}/confirm-safe`, `/instances/{id}/extend`, `/instances/{id}/cancel`, `/instances/{id}/checkpoint-location`.
  - [x] **HOÀN THÀNH PHASE B8: AI Detection Ingestion & Decision Layer**
    - `app/modules/detection/schemas.py`: DTOs tiếp nhận tín hiệu (`DetectionSignalIngestRequest`), phân tích audio thô (`AudioAnalyzeRequest`), thẩm định rủi ro (`RiskDecisionResult`), phản hồi (`DetectionIngestResponse`), cấu hình (`DetectionConfigResponse`).
    - `app/modules/detection/detectors/`: Lớp trừu tượng `BaseAudioDetector`, mô hình `YAMNetDetector` (AudioSet ontology) và `VocalBurstDetector` (chuyên nhận diện tiếng hét và khóc rên rỉ qua Pitch, Decibel, ZCR).
    - `app/modules/detection/decision/`: Bộ gom cụm chuỗi thời gian `TemporalAggregator` (Sliding window 4.0s lọc nhiễu tức thời, yêu cầu frame liên tiếp đạt ngưỡng), bộ đệm giãn cách `CooldownManager` (30s chống alert storm), bộ thẩm định rủi ro `RiskEvaluator` (4 cấp độ rủi ro).
    - Tự động chuyển giao sang `EmergencyService.trigger_sos()` kích hoạt quy trình cứu nạn khẩn cấp khi phát hiện tiếng hét hoặc âm thanh bạo lực kéo dài.
    - `app/modules/detection/repository.py`: Lưu vết kiểm toán vào Firestore collection `detection_events`.
  - [x] **HOÀN THÀNH PHASE B9: Testing, Scenario Injection & Verification (100% BACKEND COMPLETE)**
    - Kiểm thử chuyên sâu các kịch bản thực chiến khắc nghiệt và tiêm lỗi (Failure Injection) theo ADR-024 và ADR-030 trong `tests/unit/test_phase9_scenarios.py`:
      + Kịch bản 1: Bấm đúp nút SOS đồng thời (Concurrent Double-tap) -> Bảo toàn Idempotent, duy nhất 1 phiên ACTIVE được duy trì.
      + Kịch bản 2: Race condition giữa `confirm-safe` và `escalate` trên Safety Check -> Trạng thái dữ liệu nhất quán, gửi All-Clear tự động.
      + Kịch bản 3: Tiêm lỗi mạng / Telegram sập trả về lỗi 500 hoặc timeout -> Hệ thống Fault-Tolerant, luồng SOS vẫn thành công 100%.
      + Kịch bản 4: Tiêm lỗi giả mạo token xác thực (Expired, Malformed Bearer, Invalid Token) -> Toàn bộ API được bảo vệ với mã lỗi 401 UNAUTHORIZED.
      + Kịch bản 5: Dữ liệu GPS bị thiếu / trống khi kích hoạt SOS hoặc escalate -> Xử lý êm dịu, không crash hệ thống.
      + Kịch bản 6: Kiểm tra tài liệu Swagger / OpenAPI (/openapi.json và /docs) -> Toàn bộ 8 feature modules đều xuất bản đầy đủ schema, tags và response models. Bổ sung REST endpoint `GET /api/v1/realtime/info`.
      + Kịch bản 7 (ADR-036): Khống chế tối đa 10 người liên hệ khẩn cấp (HTTP 422 VALIDATION_FAILED khi thêm người thứ 11) và tối đa 10 người theo dõi phòng quan sát WebSocket trực tiếp để tối ưu băng thông và chi phí Firestore cho startup.
      + Kịch bản 8 (ADR-037): Tích hợp trực tiếp model AI Deep Learning `yamnet.onnx` (~15.3MB) qua ONNX Runtime trên Backend, tự động tải weights từ Hugging Face và kiểm thử nhận diện âm thanh nguy cấp (Scream, Gunshot, Explosion) với thời gian suy luận ~10-20ms.
    - **TỔNG KẾT TOÀN DỰ ÁN BACKEND: 56/56 UNIT & SCENARIO TESTS PASSED (100% HOÀN THÀNH CÁC GIAI ĐOẠN BACKEND B1 ĐẾN B9).**
  - [ ] **Sẵn sàng triển khai Giai đoạn tiếp theo (Post-Backend):** Mobile Client (Flutter) & CI/CD iOS IPA Build.

