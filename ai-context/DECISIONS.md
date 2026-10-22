# Guardian AI — Architecture Decision Records

This document records important decisions that must not be silently reversed by an AI coding agent.

---

# ADR-001 — Mobile App Instead of Web Application

## Status

**Accepted**

## Decision

Guardian AI sẽ được phát triển chính dưới dạng **mobile application**.

Framework:

```text
Flutter
```

Web frontend không nằm trong scope hiện tại.

## Reason

Guardian AI có các requirement có tính mobile/OS-centric:

- microphone
- location
- background execution
- native notification
- lock-screen interaction
- emergency workflow
- potential power-button/native SOS
- device permissions

Web/PWA có nhiều giới hạn đối với các capability này.

Flutter cho phép xây dựng native mobile application từ đầu và có thể mở rộng xuống native platform APIs khi cần.

## Consequence

Flutter trở thành client chính.

Backend không được phụ thuộc vào Flutter implementation.

Backend phải cung cấp stable API/contracts để future clients có thể sử dụng.

---

# ADR-002 — Flutter Instead of React Native/Expo

## Status

**Accepted**

## Decision

Mobile client sử dụng:

```text
Flutter + Dart
```

thay vì React Native + Expo.

## Reason

Guardian AI có nhu cầu native/mobile capability tương đối cao.

Flutter không phụ thuộc vào Expo Go runtime.

Application được build như application của chính project.

Khi cần native functionality:

```text
Flutter
    ↓
Platform abstraction
    ↓
Kotlin / Swift
```

## Important Limitation

Flutter không bypass giới hạn của iOS/Android.

Nếu OS không cho phép:

```text
power button interception
background execution
lock-screen behavior
automatic calling
```

thì Flutter cũng không được phép giả vờ rằng feature đó hoạt động.

## Consequence

Mọi OS-specific capability phải được kiểm chứng trên platform thực tế.

Không được coi:

```text
Flutter API exists
```

là:

```text
iOS behavior guaranteed
```

---

# ADR-003 — Python as the Only Backend Language

## Status

**Accepted**

## Decision

Backend chỉ sử dụng:

```text
Python
```

Framework:

```text
FastAPI
```

## Reason

Guardian AI có AI/audio-processing requirements.

Một backend language duy nhất:

- giảm complexity
- giảm context switching
- dễ maintain
- thuận lợi cho AI libraries
- thuận lợi cho FastAPI async APIs

Không tạo Node.js backend song song nếu không có requirement bắt buộc.

---

# ADR-004 — Firebase Authentication

## Status

**Accepted**

## Decision

Authentication sử dụng:

```text
Firebase Authentication
```

FastAPI verify Firebase ID Token.

## Reason

Không cần tự xây dựng:

- password storage
- password hashing flow
- email authentication infrastructure
- token issuance system

## Consequence

Backend identity bắt nguồn từ verified Firebase token.

Không trust arbitrary `user_id` do client gửi.

---

# ADR-005 — Firestore Instead of PostgreSQL

## Status

**Accepted**

## Decision

Firestore là primary business database.

PostgreSQL không bắt buộc và không được thêm vào MVP nếu không có requirement cụ thể.

## Reason

Current workload chủ yếu là:

```text
user profile
emergency contacts
emergency sessions
detection events
location checkpoints
notifications
recording metadata
```

Firestore phù hợp với scope này và giảm operational complexity.

## Consequence

Firestore schema phải được thiết kế có chủ đích.

Không biến Firestore thành:

```text
high-frequency telemetry database
```

Location realtime phải dùng WebSocket.

---

# ADR-006 — Cloudflare R2 for Audio/Binary Storage

## Status

**Accepted**

## Decision

Cloudflare R2 dùng để lưu:

```text
emergency audio
future binary evidence
```

Firestore lưu metadata.

## Reason

Firestore không phù hợp để lưu binary audio lớn.

## Consequence

Mỗi recording phải có metadata reference.

Ví dụ:

```text
recording_id
event_id
user_id
storage_key
content_type
duration
created_at
```

---

# ADR-007 — WebSocket for Realtime

## Status

**Accepted**

## Decision

Realtime communication sử dụng:

```text
FastAPI WebSocket
+
asyncio
```

## Use Cases

- realtime location
- emergency state
- detection status
- relevant realtime UI updates

## Not For

Không sử dụng WebSocket chỉ vì REST "không hiện đại".

Không stream raw audio vô hạn qua WebSocket nếu không có requirement rõ ràng.

---

# ADR-008 — No Redis/Kafka/RabbitMQ in MVP

## Status

**Accepted**

## Decision

Không thêm:

```text
Redis
Kafka
RabbitMQ
Celery
```

trong MVP nếu chưa có workload yêu cầu.

## Reason

Hiện tại làm tăng:

- infrastructure complexity
- deployment complexity
- debugging cost
- development cost

mà chưa có benefit tương xứng.

## Future Trigger

Có thể xem xét khi xuất hiện requirement thực tế như:

```text
high-volume background jobs
multi-instance coordination
large event queue
distributed inference
rate limiting at scale
```

---

# ADR-009 — Separate Detection from Emergency Decision

## Status

**Accepted**

## Decision

AI detector không được trực tiếp trigger SOS.

Architecture:

```text
Detector
   ↓
DetectionSignal
   ↓
Temporal / Decision Layer
   ↓
Emergency Decision
   ↓
Emergency Service
```

## Reason

Một model prediction không đồng nghĩa với emergency.

Cần chống:

- false positive
- noisy audio
- repeated frames
- transient sound
- duplicate alerts

---

# ADR-010 — YAMNet for General Audio Baseline

## Status

**Accepted as Baseline**

## Decision

YAMNet có thể được sử dụng làm general audio event detection baseline.

## Important

YAMNet không phải:

```text
Scream detector
```

và không được hard-code thành emergency decision engine.

---

# ADR-011 — Specialized Scream Detection

## Status

**Candidate / Benchmark Required**

## Decision

Scream detection sử dụng model chuyên biệt nếu benchmark cho thấy phù hợp.

Candidate:

```text
VocalBurst Locator
```

Model phải được benchmark về:

- accuracy
- precision
- recall
- false positive rate
- inference latency
- CPU usage
- RAM usage
- model size
- suitability for mobile/server
- real-world noisy environment

Không chốt production model chỉ vì model "có vẻ mạnh".

---

# ADR-012 — Speech-to-Text Is Optional

## Status

**Accepted**

## Decision

Không thêm speech-to-text nếu sản phẩm không cần transcript.

Nếu cần:

```text
faster-whisper
```

có thể được benchmark.

## Important

Whisper không thay thế scream detector.

---

# ADR-013 — Audio Should Not Be Uploaded Continuously

## Status

**Accepted**

## Decision

Không upload raw microphone audio liên tục lên backend nếu không cần.

Ưu tiên:

```text
local/temporary buffer
       ↓
detection
       ↓
emergency condition
       ↓
preserve relevant segment
       ↓
R2
```

## Reason

Giảm:

- bandwidth
- storage
- cost
- latency
- privacy risk

---

# ADR-014 — Emergency Is a Workflow, Not a Button

## Status

**Accepted**

SOS không chỉ là:

```text
POST /sos
```

SOS là:

```text
Trigger
 ↓
Emergency Session
 ↓
Context Collection
 ↓
Notification
 ↓
Tracking
 ↓
Cancel / Resolve
```

Các trigger khác nhau phải hội tụ vào cùng workflow.

---

# ADR-015 — Emergency Contacts and Notification Providers Are Separate

## Status

**Accepted**

Emergency Contact là domain entity.

Telegram là notification provider.

Không gộp:

```text
EmergencyContact = TelegramAccount
```

Một contact có thể có:

```text
phone
telegram
other channel
```

Notification layer quyết định provider nào có thể gửi.

---

# ADR-016 — Telegram Is the First Notification Provider

## Status

**Accepted**

Telegram Bot API là notification channel hiện tại.

Architecture phải cho phép:

```text
Telegram
Push
SMS
Email
```

trong tương lai mà không sửa Emergency Service.

---

# ADR-017 — Lock-Screen Information Is a Client/OS Responsibility

## Status

**Accepted**

Backend cung cấp dữ liệu được phép chia sẻ.

Flutter/native layer chịu trách nhiệm hiển thị theo OS capability.

Medical information không được tự động hiển thị toàn bộ.

User privacy preference phải được tôn trọng.

---

# ADR-018 — Power Button SOS Is OS-Dependent

## Status

**Accepted / Platform Validation Required**

Requirement:

```text
Power button → SOS
```

được xem là native capability.

Không implement bằng web.

Không giả định Android và iOS giống nhau.

Architecture:

```text
OS Event
   ↓
Native Layer
   ↓
Flutter
   ↓
Emergency API
```

Nếu platform không cho phép thì phải ghi rõ limitation.

Không dùng unsupported/hacky behavior để giả lập feature.

---

# ADR-019 — No Camera

## Status

**Accepted**

Camera/fall detection không thuộc scope hiện tại.

AI coding agent không được tự thêm:

```text
camera
YOLO
fall detection
video processing
```

trừ khi có requirement mới được xác nhận.

---

# ADR-020 — No Disaster Module

## Status

**Accepted**

Không triển khai:

```text
earthquake
flood
storm
weather
disaster alerts
```

trong current product scope.

Các tài liệu kiến trúc cũ có disaster architecture, nhưng đó là historical architecture và không được coi là current implementation requirement.

---

# ADR-021 — No Web Frontend

## Status

**Accepted**

Web frontend không phải deliverable hiện tại.

Guardian AI client:

```text
Flutter Mobile App
```

Nếu sau này thêm web:

```text
Web Client
    ↓
same FastAPI contracts
```

Không sửa backend architecture chỉ để web client tồn tại.

---

# ADR-022 — Feature-First Code Organization

## Status

**Accepted**

Code phải nằm theo capability:

```text
emergency
detection
location
contacts
recordings
notifications
users
auth
```

Không gom tất cả service vào một folder chung.

Mục tiêu:

```text
feature ownership
+
low coupling
+
high cohesion
```

---

# ADR-023 — No Unnecessary Microservices

## Status

**Accepted**

Backend hiện tại là:

```text
Modular Monolith
```

Không chia:

```text
auth-service
audio-service
sos-service
notification-service
location-service
```

thành các deployment riêng nếu chưa có requirement.

Module boundaries phải rõ ngay cả khi cùng process.

Sau này nếu một module thực sự cần scale độc lập:

```text
modular monolith
       ↓
extract module
```

---

# ADR-024 — Mandatory Scenario-Based Testing

## Status

**Accepted / Mandatory**

Mọi feature phải được kiểm tra theo scenario.

Tối thiểu phải xem xét:

```text
Happy path
Invalid input
Empty state
Missing data
Duplicate action
Concurrent action
Timeout
Network failure
Permission denied
Permission revoked
Authentication failure
Authorization failure
Provider failure
Database failure
Storage failure
App background
App foreground
App killed
Reconnect
Retry
Cancellation
Expired state
Already completed state
```

Không được chỉ test:

```text
normal successful flow
```

---

# ADR-025 — Regression Is Mandatory

## Status

**Accepted / Mandatory**

Sau mỗi feature:

```text
New Tests
   ↓
Feature Tests
   ↓
Related Integration Tests
   ↓
Regression Tests
```

Nếu lỗi:

```text
Fix
 ↓
Run failed test
 ↓
Run related tests
 ↓
Run regression
```

Không được kết thúc task ngay sau khi sửa lỗi đầu tiên.

---

# ADR-026 — AI Coding Agent Must Preserve Architecture

## Status

**Accepted / Mandatory**

AI agent không được:

- tạo duplicate service
- tạo duplicate entity
- bỏ qua existing repository
- đặt code sai module
- sửa unrelated modules
- đổi technology stack tự ý
- thêm infrastructure không cần thiết
- bypass contracts
- hard-code provider
- hard-code business decision vào model
- bỏ qua tests
- báo hoàn thành khi chưa verify

---

# ADR-027 — Current Source of Truth

## Status

**Accepted**

Khi có conflict giữa:

```text
old documentation
vs
current confirmed requirements
```

thì:

```text
current confirmed requirements
```

là source of truth.

Các tài liệu cũ có thể được tham khảo để lấy architectural ideas nhưng không được tự động coi là requirement hiện tại.

---

# ADR-028 — AI Must Not Expand Scope

## Status

**Accepted**

Nếu AI nhận thấy một feature tương lai có thể hữu ích:

```text
DO NOT IMPLEMENT AUTOMATICALLY.
```

Phải:

1. ghi nhận suggestion
2. giải thích impact
3. chờ user approval

Không tự thêm feature.

---

# ADR-029 — Architecture Changes Require Explicit Reason

## Status

**Accepted**

Nếu implementation phát hiện architecture hiện tại không đủ:

```text
Do not silently rewrite architecture.
```

Phải:

```text
identify problem
→ explain
→ propose alternatives
→ assess impact
→ get approval if architectural change is significant
→ implement
```

---

# ADR-030 — Definition of a Stable Feature

Một feature được coi là stable khi:

```text
Implementation
+
Unit tests
+
Integration tests
+
Edge-case tests
+
Failure handling
+
Regression tests
+
Architecture validation
+
Security validation
+
Documentation
```

đều hoàn thành.

"Code chạy được" không đồng nghĩa "feature hoàn thành".

---

# ADR-031 — Safety Check Timer Architecture & Escalation Flow

## Status

**Accepted**

## Decision

Safety Check Timer là một tính năng tiền khẩn cấp (Pre-emergency safety monitoring).
Khi timer hết hạn, hệ thống **không được lập tức coi là SOS nguy hiểm**.

Quy trình bắt buộc phải qua Escalation Flow:

```text
ACTIVE
   ↓ (now >= expires_at)
CHECK_REQUIRED
   ↓ (Grace Period: 30s - 10m tùy template)
User xác nhận
   ├── Bấm "Tôi an toàn" → COMPLETED
   └── Không phản hồi (hết Grace Period)
          ↓
      ESCALATED (SAFETY_CHECK_TIMEOUT)
          ↓
      Emergency Service kích hoạt cảnh báo người thân (Telegram)
      + Gửi vị trí gần nhất đã biết (không khẳng định chắc chắn vị trí hiện tại)
```

Không dùng countdown backend từng giây. Backend chỉ lưu `expires_at`, `grace_period_until` (UTC ISO). Mobile tự đếm ngược và hẹn giờ Native Local Notification.

---

# ADR-032 — Local Hardware Alarm (Siren & Strobe Light) on Mobile

## Status

**Accepted**

## Decision

Khi xảy ra biến cố nguy hiểm / SOS hoặc xác nhận âm thanh bất thường đe dọa:
Mobile app Flutter có khả năng kích hoạt:
1. **Còi hú báo động (Alarm Siren):** Phát âm thanh tần số cao qua `AVAudioSessionCategoryPlayback` (iOS) để vẫn phát to ngay cả khi máy gạt nút im lặng / Silent Switch.
2. **Đèn Flash chớp tắt (Strobe Light):** Nhấp nháy đèn flash LED của camera để gây sức ép đuổi kẻ xấu hoặc hỗ trợ lực lượng cứu hộ tìm kiếm ban đêm.

## Limitation

Apple iOS không cho phép ứng dụng bên thứ 3 tự kéo thanh trượt Master Volume của máy lên mức 100% qua Public API. App chỉ có thể phát âm thanh ở mức tối đa của stream hiện tại (`player.setVolume(1.0)`).

---

# ADR-033 — Mandatory Header Documentation for Every Code File

## Status

**Accepted / Mandatory**

## Decision

Mọi file mã nguồn (`.py` và `.dart`) phải có khối header comment chuẩn ở đầu file nêu rõ:
- Module / Feature sở hữu
- Role / Single Responsibility
- Connections / Dependencies (các service, router, database, API liên quan)
- Input / Output chính

## Reason

Giúp nhà phát triển và AI rà soát bug nhanh chóng, tránh phá vỡ kiến trúc (break contracts), ngăn chặn race condition và bảo trì minh bạch.

---

# ADR-034 — iOS Development Workflow on Windows

## Status

**Accepted**

## Decision

Do môi trường phát triển là máy Windows và thiết bị kiểm thử là iPhone (không có máy Mac vật lý):
1. **Không thể cắm cáp USB `flutter run` trực tiếp từ Windows sang iPhone** (giới hạn của Apple yêu cầu macOS để biên dịch Xcode).
2. **Quy trình triển khai kiểm thử iOS:**
   - Source code Flutter được đẩy lên GitHub repository.
   - **GitHub Actions (macOS Runner miễn phí)** tự động biên dịch dự án thành file ứng dụng **`.ipa`**.
   - Nhà phát triển tải file `.ipa` về máy tính Windows.
   - Dùng công cụ **Sideloadly / 3uTools** trên Windows kết nối cáp USB với iPhone, sử dụng Apple ID cá nhân để ký số và cài trực tiếp vào iPhone để kiểm thử thực tế phần cứng (Flash, Siren, GPS).
3. **Phát triển giao diện & logic:** Tận dụng Flutter Desktop (Windows) hoặc Chrome để Hot Reload giao diện tức thì trước khi đóng gói `.ipa`.

---

# ADR-035 — Native Direct Phone Call Intent

## Status

**Accepted**

## Decision

Khi người dùng kích hoạt SOS khẩn cấp, ngoài kênh thông báo backend qua Telegram Bot API (gửi tọa độ Maps + audio recording R2):
Phía mobile app Flutter sẽ cung cấp intent gọi điện trực tiếp (`url_launcher: tel:...`) đến số điện thoại ưu tiên số 1 trong danh bạ khẩn cấp của người dùng để thực hiện cuộc gọi GSM truyền thống ngay lập tức.

---

# ADR-036 — Limit Emergency Contacts & Live Watchers to 10 for Cost & Bandwidth Optimization

## Status

**Accepted**

## Decision

Nhằm tối ưu chi phí hạ tầng cơ sở dữ liệu (Firestore reads/writes) và băng thông WebSocket server cho mô hình startup:
1. **Giới hạn tối đa 10 người liên hệ khẩn cấp (Emergency Contacts):** Mỗi người dùng chỉ được thêm tối đa 10 người thân vào danh bạ khẩn cấp (`MAX_EMERGENCY_CONTACTS_PER_USER = 10`). Thêm người thứ 11 sẽ bị từ chối với lỗi `VALIDATION_FAILED` (HTTP 422).
2. **Giới hạn phát tán thông báo:** Quy trình cảnh báo SOS/Timeout/All-Clear qua Telegram chỉ phát tán tối đa cho 10 người thân tích cực (`is_active=True`), thực thi bất đồng bộ song song (`asyncio.gather`) để giảm triệt để độ trễ.
3. **Giới hạn phòng quan sát (Watchers Room):** Mỗi tài khoản nạn nhân chỉ cho phép tối đa 10 kết nối WebSocket người thân quan sát trực tiếp (`MAX_WATCHERS_PER_USER = 10`) để tránh nghẽn băng thông stream GPS.

---

# ADR-037 — YAMNet ONNX Deep Learning Inference with Automatic Model Provisioning

## Status

**Accepted**

## Decision

Nhằm đảm bảo khả năng nhận diện âm thanh nguy hiểm (Scream, Gunshot, Explosion, Glass Shatter, Distress Cry) chuẩn xác, tốc độ cao và độc lập với nền tảng mobile:
1. **Model Format & Engine:** Sử dụng **ONNX Runtime (`onnxruntime`)** trên Backend thay vì PyTorch/TensorFlow cồng kềnh. Model `yamnet.onnx` (~15.3MB) và `yamnet_class_map.csv` được lưu tại `backend/app/models/`.
2. **Tự động cấp phát (Automatic Provisioning):** `_ensure_yamnet_model_files()` tự động kiểm tra và tải file weights từ Hugging Face (`zeropointnine/yamnet-onnx`) nếu chưa có trên đĩa.
3. **Cơ chế Fallback an toàn:** Nếu ONNX runtime gặp sự cố hoặc thiếu file model, hệ thống tự động fallback êm dịu về bộ lọc heuristic và acoustic descriptors mà không làm gián đoạn API.

