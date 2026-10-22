# Guardian AI — Backend Implementation Roadmap & Task Tracker

> **Chiến lược hiện tại:** **BACKEND-FIRST**.  
> Tạm gác Frontend lại, tập trung hoàn thiện 100% thiết kế, mã nguồn, cơ chế xử lý background, kiểm thử scenario và tài liệu hóa cho toàn bộ Backend FastAPI.
>
> **Nguyên tắc bắt buộc:** Tuân thủ triệt để [CONVENTIONS.md](file:///D:/Projects/Guardian_AI/backend/ai-context/CONVENTIONS.md) (đặc biệt là Rule 33: Khối Header Comment bắt buộc ở đầu mỗi file) và các quyết định kiến trúc trong [DECISIONS.md](file:///D:/Projects/Guardian_AI/backend/ai-context/DECISIONS.md).

---

## 📋 TỔNG QUAN CÁC GIAI ĐOẠN BACKEND

```text
Phase B1: Core Foundation, Environment & Infrastructure Clients
   ↓
Phase B2: Domain Schemas, Enums & Shared Contracts
   ↓
Phase B3: Auth, User Profile & Emergency Contacts Modules
   ↓
Phase B4: Notification (Telegram Provider) & Recording (Cloudflare R2) Modules
   ↓
Phase B5: Real-time Location & WebSocket Stream
   ↓
Phase B6: Emergency Core Workflow (Manual SOS & Incident Management)
   ↓
Phase B7: Safety Check Timer Module & Async Expiration Scheduler
   ↓
Phase B8: AI Detection Ingestion & Decision Layer (Scream & Audio Events)
   ↓
Phase B9: End-to-End Integration, Scenario Tests & API Verification
```

---

## 🚀 CHI TIẾT CÁC GIAI ĐOẠN TRIỂN KHAI

### Phase B1: Core Foundation & Infrastructure Clients (HOÀN THÀNH)
Mục tiêu: Dựng bộ khung cấu hình vững chắc, an toàn và kết nối sẵn sàng tới các dịch vụ bên ngoài.

- [x] **B1.1. Cấu hình biến môi trường (`app/core/config.py`)**
  - [x] Pydantic `BaseSettings` đọc từ `.env`.
  - [x] Cấu hình Firebase (Path to Service Account JSON / Project ID).
  - [x] Cấu hình Cloudflare R2 (Account ID, Access Key, Secret Key, Bucket Name, Public Domain).
  - [x] Cấu hình Telegram (Bot Token, Webhook Secret, Default Emergency Channel).
  - [x] Cấu hình CORS, Host, Port, JWT/Session Secret, Log Level.
- [x] **B1.2. Logging & Bảo mật thông tin (`app/core/logging.py`)**
  - [x] Cấu hình Structured Logging (JSON format hoặc Colored Console).
  - [x] Bộ lọc bảo mật: Tự động che dấu (mask/redact) Firebase Token, Passwords, dữ liệu bệnh án y tế chi tiết trong log.
- [x] **B1.3. Quản lý ngoại lệ tập trung (`app/core/exceptions.py`)**
  - [x] Định nghĩa `AppException`, `EntityNotFoundException`, `UnauthorizedException`, `ValidationException`, `ProviderException`.
  - [x] Custom Exception Handlers chuẩn hóa format lỗi trả về client: `{ success: false, error: { code, message, details } }`.
- [x] **B1.4. Hạ tầng Firebase / Firestore Client (`app/infrastructure/firestore/client.py`)**
  - [x] Khởi tạo Firebase Admin SDK với Service Account JSON an toàn.
  - [x] Cung cấp Firestore Async Client / Database wrapper có dependency injection.
- [x] **B1.5. Hạ tầng Cloudflare R2 Client (`app/infrastructure/storage/r2/client.py`)**
  - [x] Khởi tạo S3-compatible client kết nối Cloudflare R2 endpoint.
  - [x] Các hàm tiện ích: upload binary stream, generate presigned url tải audio, check object exists, delete object.
- [x] **B1.6. Khởi tạo FastAPI Application & Health Check (`app/main.py`)**
  - [x] Lifespan quản lý startup/shutdown, CORS middleware.
  - [x] `/health` kiểm tra đồng thời Firestore & Cloudflare R2 connection.
  - [x] Bộ test unit tự động `tests/unit/test_phase1_foundation.py` đạt 7/7 PASSED.

---

### Phase B2: Enums, Domain Schemas & Shared Contracts (HOÀN THÀNH)
Mục tiêu: Cố định toàn bộ định dạng dữ liệu (data contracts) để các module giao tiếp nhất quán, không xung đột.

- [x] **B2.1. Shared Enums (`app/shared/enums/`)**
  - [x] Đa dạng hóa cảnh báo âm thanh nguy hiểm: `AudioEventType` (SCREAM, DISTRESS_CRY, CALL_FOR_HELP, GLASS_SHATTER, GUNSHOT, EXPLOSION, VIOLENT_STRUGGLE, AGGRESSIVE_BARK, CAR_CRASH_SOUND, ENVIRONMENTAL_ALARM, ABNORMAL_UNKNOWN).
  - [x] Các model nhận diện âm thanh: `DetectorModelType` (YAMNET, VOCAL_BURST, FASTER_WHISPER, CUSTOM_ENSEMBLE).
  - [x] Cấp độ rủi ro: `DetectionRiskLevel` (NEGLIGIBLE, SUSPICIOUS, WARNING, EMERGENCY).
  - [x] Trạng thái và kích hoạt khẩn cấp: `EmergencyStatus`, `EmergencyTriggerType`, `EmergencySeverity`.
  - [x] Trạng thái và mẫu kiểm tra an toàn: `SafetyCheckStatus`, `DefaultTemplateId` (5 template mặc định).
  - [x] Danh bạ và kênh thông báo: `ContactRelationship`, `NotificationChannel` (TELEGRAM, LOCAL_NOTIFICATION, DIRECT_PHONE_CALL, FCM_PUSH, SMS).
  - [x] Nhóm máu và mức độ bảo mật y tế: `BloodType`, `MedicalPrivacyLevel`.
- [x] **B2.2. Generic API Response Envelope & Schemas (`app/shared/schemas/`)**
  - [x] `ApiResponse[T]`: Cấu trúc bọc dữ liệu API thống nhất `{ success, data, message, timestamp }`.
  - [x] `PaginatedResponse[T]`: Phân trang chuẩn cho các danh sách `{ items, total, page, size, has_next }`.
  - [x] `GeoPointSchema`: Tọa độ địa lý chuẩn, validation vĩ độ/kinh độ và helper sinh link Google Maps.
  - [x] `DetectionSignal`: Contract tiếp nhận tín hiệu từ các AI model, phân tích mức độ nguy cơ cao `is_high_risk()`.
  - [x] Bộ test unit tự động `tests/unit/test_phase2_contracts.py` đạt 7/7 PASSED (Tổng số test toàn backend đạt 14/14 PASSED).

---

### Phase B3: Auth, User Profile & Emergency Contacts Modules
Mục tiêu: Quản lý người dùng, hồ sơ bệnh án khẩn cấp phân cấp bảo mật và danh bạ người thân (chia thành 3 phần nhỏ: B3.1, B3.2, B3.3).

- [x] **B3.1. Auth & User Profile Management (`app/modules/auth/` & `app/modules/users/`) (HOÀN THÀNH)**
  - [x] `app/modules/auth/dependencies.py`: Dependency `get_current_user` trích xuất Bearer token, xác thực qua Firebase Admin SDK (`auth.verify_id_token`), tự động đồng bộ Firestore user document.
  - [x] Xử lý ngoại lệ token hết hạn (`TOKEN_EXPIRED`), token bị thu hồi (`TOKEN_REVOKED`), token giả mạo (`INVALID_TOKEN`) trả về 401 Unauthorized.
  - [x] `POST /api/v1/auth/register`: Đăng ký tài khoản mới trên Firebase Auth + tạo Firestore document trong `users` + sinh custom token.
  - [x] `POST /api/v1/auth/login`: Xác thực Firebase ID Token (từ Flutter client) hoặc tài khoản, cập nhật `last_login_at`.
  - [x] `POST /api/v1/auth/forgot-password`: Sinh liên kết khôi phục mật khẩu bảo mật qua `firebase_admin.auth.generate_password_reset_link`.
  - [x] `POST /api/v1/auth/change-password`: Đổi mật khẩu cho tài khoản đang đăng nhập qua `firebase_admin.auth.update_user`.
  - [x] `GET /api/v1/auth/me`: Lấy thông tin định danh của phiên người dùng hiện tại (Protected).
  - [x] `GET /api/v1/users/me`: Xem chi tiết hồ sơ cá nhân (họ tên, tuổi, ngày sinh, SĐT, avatar, telegram).
  - [x] `PUT /api/v1/users/me`: Cập nhật thông tin hồ sơ cá nhân (họ tên, tuổi, ngày sinh, SĐT, avatar, telegram).
  - [x] Bộ test unit tự động `tests/unit/test_phase3_1_auth.py` đạt 4/4 PASSED (Tổng số test toàn backend đạt 18/18 PASSED).
- [x] **B3.2. Emergency Medical Profile Module (`app/modules/users/` medical) (HOÀN THÀNH)**
  - [x] Repository & Service quản lý Firestore collection `emergency_profiles`.
  - [x] Endpoint `GET|PUT /api/v1/users/me/medical`: Quản lý thông tin y tế (nhóm máu, chiều cao, cân nặng, dị ứng, bệnh nền, thuốc).
  - [x] Endpoint `GET /api/v1/users/{user_id}/public-emergency`: Endpoint công khai cho màn hình khóa hoặc cứu hộ (chỉ trả về dữ liệu cho phép, giấu bệnh án nhạy cảm).
  - [x] Bộ test unit tự động `tests/unit/test_phase3_2_medical.py` đạt 3/3 PASSED.
- [x] **B3.3. Emergency Contacts Module (`app/modules/contacts/`) (HOÀN THÀNH)**
  - [x] Repository & Service Firestore collection `emergency_contacts`.
  - [x] Endpoint `GET /api/v1/contacts`: Lấy danh sách người thân sắp xếp theo thứ tự ưu tiên (`priority`).
  - [x] Endpoint `POST /api/v1/contacts`: Thêm liên hệ mới (họ tên, quan hệ, SĐT, Telegram chat_id).
  - [x] Endpoint `PUT /api/v1/contacts/{id}` & `DELETE /api/v1/contacts/{id}`: Cập nhật / xóa liên hệ.
  - [x] Endpoint `PUT /api/v1/contacts/reorder`: Cập nhật lại thứ tự ưu tiên gọi điện.
  - [x] Bộ test unit tự động `tests/unit/test_phase3_3_contacts.py` đạt 2/2 PASSED (Tổng số test toàn backend đạt 24/24 PASSED).

---

### Phase B4: Notification (Telegram Provider) & Recording (Cloudflare R2) (HOÀN THÀNH)
Mục tiêu: Xây dựng khả năng phát tán tin nhắn cảnh báo và lưu trữ file ghi âm bằng chứng.

- [x] **B4.1. Notification Module (`app/modules/notifications/`) (HOÀN THÀNH)**
  - [x] `BaseNotificationProvider`: Interface chuẩn (`send_sos_alert`, `send_safety_check_alert`, `send_all_clear`, `send_audio_evidence`).
  - [x] `TelegramBotProvider`:
    - [x] Gửi định dạng HTML an toàn, trực quan, sinh động.
    - [x] Gửi vị trí kèm Pin Google Maps (`https://www.google.com/maps?q={lat},{lng}`).
    - [x] Gửi file audio ghi âm bằng chứng trực tiếp qua Telegram voice/audio method.
    - [x] Xử lý chịu lỗi mạng, không làm crash luồng SOS chính nếu Telegram lỗi (Fault-Tolerant).
  - [x] `NotificationService`: Phát tán cảnh báo tới toàn bộ danh bạ người thân, lưu vết Audit Trail vào Firestore `notifications`.
  - [x] Endpoint `POST /api/v1/notifications/test-telegram`: Kiểm tra kết nối bot Telegram.
- [x] **B4.2. Recordings Module (`app/modules/recordings/`) (HOÀN THÀNH)**
  - [x] Firestore collection `recordings` lưu metadata (file_name, storage_key, duration_seconds, event_id, created_at).
  - [x] Service nhận file audio (upload multipart), sanitize filename, đẩy vào Cloudflare R2 partitioned: `users/{user_id}/emergency/{event_id}/audio/{recording_id}_{filename}`.
  - [x] Tạo presigned URL thời hạn (`generate_presigned_url`) để người thân hoặc cứu hộ có thể nghe lại.
  - [x] Bảo vệ quyền sở hữu bản ghi (Data Ownership Isolation) và xóa đồng bộ cả R2 lẫn Firestore.
  - [x] Endpoints: `POST /upload`, `GET /recordings`, `GET /{id}`, `GET /{id}/playback-url`, `DELETE /{id}`.
  - [x] Bộ test unit tự động `tests/unit/test_phase4_notifications_and_recordings.py` đạt 5/5 PASSED (Tổng số test toàn backend đạt 29/29 PASSED).

---

### Phase B5: Real-time Location & WebSocket Stream (HOÀN THÀNH)
Mục tiêu: Quản lý vị trí GPS thời gian thực khi đang có biến cố mà không làm quá tải database.

- [x] **B5.1. Location Checkpoints (`app/modules/location/`) (HOÀN THÀNH)**
  - [x] Firestore collection `location_checkpoints`.
  - [x] Service lưu lại tọa độ quan trọng tại các thời điểm: kích hoạt SOS, escalate Safety Check, phát hiện tiếng la hét, sinh link Google Maps.
  - [x] Endpoints: `POST /checkpoints`, `GET /latest`, `GET /checkpoints`.
- [x] **B5.2. WebSocket Real-time Manager (`app/realtime/`) (HOÀN THÀNH)**
  - [x] `ConnectionManager`: Quản lý các kết nối WebSocket đang hoạt động của từng user, cache vị trí RAM, mô hình phòng quan sát Watchers.
  - [x] Xác thực Firebase Token ngay khi bắt đầu bắt tay WebSocket handshake qua Query param `?token=...` (đóng lỗi 1008 nếu thiếu/sai token).
  - [x] Nhận stream GPS từ điện thoại người dùng (`LOCATION_STREAM`) và broadcast tức thời (`LOCATION_UPDATE`).
  - [x] Hỗ trợ đăng ký theo dõi (`SUBSCRIBE_USER` / `UNSUBSCRIBE_USER`) và `PING`/`PONG`.
  - [x] Bộ test unit tự động `tests/unit/test_phase5_location_and_realtime.py` đạt 4/4 PASSED (Tổng số test toàn backend đạt 33/33 PASSED).

---

### Phase B6: Emergency Core Workflow (Orchestration & Idempotency) (HOÀN THÀNH)
Mục tiêu: Trái tim của hệ thống — điều phối toàn bộ phản ứng khẩn cấp một cách tin cậy tuyệt đối.

- [x] **B6.1. Emergency Repository & State Machine (`app/modules/emergency/`) (HOÀN THÀNH)**
  - [x] Firestore collection `emergency_sessions`.
  - [x] Vòng đời phiên khẩn cấp: `CREATED` $\rightarrow$ `ACTIVE` $\rightarrow$ `RESOLVED` / `CANCELLED` / `EXPIRED`.
- [x] **B6.2. Idempotent SOS Triggering Service (HOÀN THÀNH)**
  - [x] Xử lý Manual SOS & Native SOS nút nguồn.
  - [x] Cơ chế chống spam: Nếu đã có phiên `ACTIVE`, tái sử dụng cùng session_id, chỉ cập nhật vị trí mới.
- [x] **B6.3. Emergency Orchestration Pipeline (HOÀN THÀNH)**
  - [x] Bước 1: Tạo/Kích hoạt Emergency Session.
  - [x] Bước 2: Ghi nhận checkpoint vị trí GPS gần nhất.
  - [x] Bước 3: Lấy danh sách liên hệ khẩn cấp ưu tiên.
  - [x] Bước 4: Gọi NotificationService gửi thông báo khẩn cấp qua Telegram kèm ghim Google Maps.
  - [x] Bước 5: Broadcast WebSocket tức thời cho người thân / quan sát viên.
- [x] **B6.4. Hủy & Giải quyết phiên khẩn cấp (`/resolve`, `/cancel`) (HOÀN THÀNH)**
  - [x] Người dùng nhập mã PIN hoặc xác nhận hủy an toàn (`POST /cancel`, `POST /resolve`).
  - [x] Gửi thông báo an toàn All-Clear qua Telegram cho người thân.
  - [x] Endpoints: `POST /sos`, `POST /cancel`, `POST /resolve`, `GET /active`, `GET /sessions`, `GET /sessions/{id}`.
  - [x] Bộ test unit tự động `tests/unit/test_phase6_emergency.py` đạt 2/2 PASSED (Tổng số test toàn backend đạt 35/35 PASSED).

---

### Phase B7: Safety Check Timer Module & Async Expiration Scheduler (HOÀN THÀNH)
Mục tiêu: Hoàn thiện tính năng Hẹn giờ kiểm tra an toàn theo đúng đề xuất thiết kế đã duyệt.

- [x] **B7.1. Safety Check Templates (`app/modules/emergency/safety_check/`) (HOÀN THÀNH)**
  - [x] Firestore collection `safety_check_templates`.
  - [x] Seed sẵn 5 template mặc định vào hệ thống (Đi bộ về nhà, Di chuyển bằng xe, Khám phá ngoài trời, Kiểm tra an toàn, Cuộc gặp an toàn).
  - [x] API lấy danh sách template: `GET /api/v1/safety-check/templates`.
  - [x] API tạo custom template cho user: `POST /api/v1/safety-check/templates`.
- [x] **B7.2. Safety Check Instances Management (HOÀN THÀNH)**
  - [x] Firestore collection `safety_check_instances`.
  - [x] `POST /api/v1/safety-check/start`: Tạo phiên mới, tính toán `expires_at` và `grace_period_until` (chặn nếu đã có phiên ACTIVE).
  - [x] `GET /api/v1/safety-check/current`: Lấy phiên đang chạy.
  - [x] `POST /api/v1/safety-check/instances/{id}/confirm-safe`: Bấm "Tôi an toàn" $\rightarrow$ chuyển trạng thái `COMPLETED`.
  - [x] `POST /api/v1/safety-check/instances/{id}/extend`: Gia hạn thêm thời gian (tối đa 3 lần).
  - [x] `POST /api/v1/safety-check/instances/{id}/cancel`: Người dùng chủ động hủy phiên.
  - [x] `POST /api/v1/safety-check/instances/{id}/checkpoint-location`: Cập nhật tọa độ gần nhất.
- [x] **B7.3. Expiration Scheduler (Asyncio Periodic Worker) (HOÀN THÀNH)**
  - [x] `app/modules/emergency/safety_check/scheduler.py`: Background worker chạy định kỳ mỗi 15-30 giây.
  - [x] Quét các instance quá hạn: `grace_period_until <= now()` và `status in [ACTIVE, CHECK_REQUIRED]`.
  - [x] Đổi trạng thái sang `ESCALATED`.
  - [x] Gửi cảnh báo `SAFETY_CHECK_TIMEOUT` kèm vị trí gần nhất đến Telegram người thân qua `broadcast_safety_check_timeout`.
  - [x] Xử lý trường hợp đặc biệt: User bấm "Tôi an toàn" sau khi đã bị Escalate $\rightarrow$ tự động gửi thông báo đính chính All-Clear (`broadcast_all_clear`).
  - [x] Bộ test unit tự động `tests/unit/test_phase7_safety_check.py` đạt 5/5 PASSED (Tổng số test toàn backend đạt 40/40 PASSED).

---

### Phase B8: AI Detection Ingestion & Decision Layer (HOÀN THÀNH)
Mục tiêu: Tiếp nhận tín hiệu âm thanh và lọc false positive trước khi kích hoạt quy trình khẩn cấp.

- [x] **B8.1. Normalized Detection Contracts (`app/modules/detection/`) (HOÀN THÀNH)**
  - [x] Schema `DetectionSignalInput`, `DetectionSignalIngestRequest`, `AudioAnalyzeRequest`, `RiskDecisionResult`, `DetectionIngestResponse`, `DetectionConfigResponse`.
- [x] **B8.2. Model Inference Abstraction (HOÀN THÀNH)**
  - [x] Interface `BaseAudioDetector` trừu tượng hóa cho các bộ nhận diện âm thanh.
  - [x] Tích hợp `YAMNetDetector` (Google YAMNet baseline phân loại âm thanh tổng quát theo AudioSet ontology).
  - [x] Tích hợp `VocalBurstDetector` (VocalBurst locator chuyên nhận diện tiếng hét và tiếng khóc rên rỉ qua Pitch, Decibel, ZCR).
- [x] **B8.3. Temporal Aggregation & Risk Decision Layer (HOÀN THÀNH)**
  - [x] Bộ gom cụm thời gian `TemporalAggregator`: Sliding window 4.0s, lọc nhiễu tức thời (transient spike), yêu cầu nhiều frame liên tiếp đạt ngưỡng mới xác nhận.
  - [x] Bộ đệm giãn cách `CooldownManager`: Chống bão cảnh báo (alert storm) khi âm thanh nguy hiểm kéo dài liên tục (cooldown 30s).
  - [x] Bộ thẩm định rủi ro `RiskEvaluator`: Phân cấp rủi ro 4 mức (`NEGLIGIBLE` -> `SUSPICIOUS` -> `WARNING` -> `EMERGENCY`).
  - [x] Khi vượt ngưỡng khẩn cấp $\rightarrow$ Tự động điều phối sang `EmergencyService.trigger_sos()` kích hoạt SOS Orchestration Pipeline.
  - [x] Lưu trữ lịch sử sự kiện và kiểm toán vào Firestore collection `detection_events`.
  - [x] Endpoints: `POST /signals`, `POST /analyze-audio`, `GET /config`, `GET /history`.
  - [x] Bộ test unit tự động `tests/unit/test_phase8_detection.py` đạt 7/7 PASSED (Tổng số test toàn backend đạt 47/47 PASSED).

---

### Phase B9: Testing, Scenario Injection & Verification (HOÀN THÀNH)
Mục tiêu: Đảm bảo độ tin cậy tuyệt đối theo tiêu chuẩn [ADR-024](file:///D:/Projects/Guardian_AI/backend/ai-context/DECISIONS.md#L768-L810) và [ADR-030](file:///D:/Projects/Guardian_AI/backend/ai-context/DECISIONS.md#L942-L969).

- [x] **B9.1. Unit & Schema Tests (HOÀN THÀNH):** Kiểm tra validation, contract và state transition (Phases B1 - B8).
- [x] **B9.2. Scenario & Failure Injection Tests (HOÀN THÀNH):**
  - [x] Mô phỏng user spam đúp nút SOS (Double-tap SOS concurrency) -> Bảo toàn Idempotent, chỉ tạo đúng 1 session.
  - [x] Mô phỏng Race condition giữa `confirm-safe` và `escalate` trên Safety Check -> Trạng thái nhất quán, phát All-Clear tự động.
  - [x] Mô phỏng Telegram API bị sập hoặc trả về mã 500/timeout -> Fault-tolerant, Emergency session vẫn tạo thành công.
  - [x] Mô phỏng Firebase token hết hạn hoặc giả mạo -> Chặn bảo mật 401 UNAUTHORIZED toàn bộ API.
  - [x] Mô phỏng dữ liệu GPS bị trống hoặc quá cũ khi escalate/SOS -> Xử lý êm dịu, không crash hay lỗi null pointer.
- [x] **B9.3. Swagger / OpenAPI Documentation (HOÀN THÀNH):**
  - [x] Kiểm tra toàn bộ 8 modules xuất bản đầy đủ schema tại `/openapi.json` và `/docs`.
  - [x] Bổ sung REST companion endpoint `GET /api/v1/realtime/info` ghi nhận chuẩn kết nối WebSocket Stream.
  - [x] Bộ test kịch bản tự động `tests/unit/test_phase9_scenarios.py` đạt 6/6 PASSED.
  - [x] **TỔNG KẾT TOÀN BỘ BACKEND: 53/53 TESTS PASSED (100% HOÀN THÀNH CÁC PHASE B1 ĐẾN B9).**

---

## 📱 GIAI ĐOẠN SAU (POST-BACKEND: MOBILE CLIENT & DEPLOYMENT)
*(Tạm gác lại, sẽ kích hoạt sau khi Phase B1 - B9 hoàn thành và được kiểm thử toàn diện)*

- [ ] Khởi tạo dự án Flutter (Feature-first).
- [ ] Xây dựng giao diện 3 Tab (Màn hình chính, Tính năng, Thông tin cá nhân) theo mẫu Google Safety.
- [ ] Tích hợp Native Alarm Siren (`AVAudioSessionCategoryPlayback`) & Strobe Flashlight.
- [ ] Tích hợp Native Direct Call (`tel:...`).
- [ ] Tích hợp Local Notifications với Action buttons (`[Tôi an toàn]`, `[Gia hạn]`).
- [ ] Thiết lập GitHub Actions `.github/workflows/build_ios.yml` tự động đóng gói file `.ipa`.
- [ ] Hướng dẫn cài đặt vào iPhone qua Sideloadly / 3uTools trên Windows.
