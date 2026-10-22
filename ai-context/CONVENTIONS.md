# Guardian AI — Development Conventions

> **This document is mandatory for every developer and AI coding agent.**

---

# 1. Golden Rule

**Không được code ngay khi chưa hiểu codebase hiện tại.**

Trước mọi implementation:

```text
Read Context
    ↓
Inspect Existing Code
    ↓
Understand Current Architecture
    ↓
Identify Related Features
    ↓
Identify Existing Contracts
    ↓
Identify Potential Side Effects
    ↓
Plan
    ↓
Implement
```

AI không được tự suy diễn:

```text
"Feature này đơn giản"
```

rồi bỏ qua việc kiểm tra hệ thống.

---

# 2. Mandatory Context Reading

Mỗi coding session phải đọc tối thiểu:

```text
ai-context/PROJECT.md
ai-context/ARCHITECTURE.md
ai-context/CONVENTIONS.md
ai-context/DECISIONS.md
```

Sau đó mới đọc source code liên quan.

Không cần đọc toàn bộ repository nếu feature không liên quan, nhưng phải xác định dependency trước.

---

# 3. Existing Code First

Trước khi tạo file mới:

1. Search xem capability đã tồn tại chưa.
2. Search model/schema tương tự.
3. Search service tương tự.
4. Search repository tương tự.
5. Search API endpoint tương tự.
6. Search enum/contract liên quan.
7. Search tests liên quan.

Nếu đã có code phù hợp:

> **Modify / extend existing code before creating duplicate code.**

---

# 4. Do Not Duplicate

Không tạo:

```text
EmergencyContactService
EmergencyContactsService
ContactEmergencyService
```

chỉ vì AI không tìm thấy file ngay.

Phải search trước.

Không tạo duplicate:

- models
- DTO/schema
- enums
- repositories
- notification logic
- authentication logic
- location logic
- emergency logic

---

# 5. Feature Ownership

Mọi code phải có owner rõ ràng.

Ví dụ:

```text
Audio detection
→ modules/detection/

SOS
→ modules/emergency/

Telegram
→ modules/notifications/

User profile
→ modules/users/

Emergency contacts
→ modules/contacts/

Location
→ modules/location/

Recording
→ modules/recordings/
```

Không đặt code theo kiểu:

> "file này tiện đặt ở đây."

---

# 6. Shared Folder Rule

`shared/` chỉ chứa thứ thực sự shared.

Được phép:

```text
shared/contracts
shared/enums
shared/types
shared/utils
```

Không được dùng:

```text
shared/
    everything.py
```

hoặc biến `shared/` thành nơi chứa business logic không có owner.

Nếu một logic chỉ thuộc một feature:

```text
để trong feature đó.
```

---

# 7. Service Responsibility

Một service phải có responsibility rõ ràng.

Ví dụ:

```text
EmergencyService
```

chịu trách nhiệm emergency workflow.

Không nên chịu trách nhiệm:

```text
Telegram HTTP implementation
Firestore SDK implementation
Audio model inference
GPS implementation
```

Thay vào đó:

```text
EmergencyService
   ↓
NotificationService
   ↓
TelegramProvider
```

---

# 8. Router Responsibility

FastAPI router chỉ nên:

```text
authenticate
validate
call service
return response
```

Không chứa:

- business workflow dài
- AI inference
- Firestore transaction phức tạp
- Telegram request
- R2 upload logic

---

# 9. Flutter Responsibility

Flutter presentation layer không được chứa backend business rules.

Không:

```text
if scream > 0.8:
    call telegram
```

Flutter chỉ:

```text
capture
display
request
send
receive
```

Business decision nằm backend hoặc native capability layer tùy use case.

---

# 10. Native Code

Platform-specific code:

```text
android/
ios/
```

chỉ được dùng khi cần OS capability.

Không đưa toàn bộ business logic vào Kotlin/Swift.

Ưu tiên:

```text
Flutter
   ↓
Platform abstraction
   ↓
Native implementation
```

---

# 11. AI Model Rule

AI model không được sở hữu business decision.

Không:

```text
model.predict()
    ↓
send_telegram()
```

Nên:

```text
model.predict()
    ↓
DetectionSignal
    ↓
Decision layer
    ↓
Emergency workflow
```

---

# 12. Confidence Is Not Truth

Không coi:

```text
confidence = 0.95
```

là:

```text
danger = TRUE
```

Confidence chỉ là một input.

Decision có thể cần:

```text
confidence
duration
repeated detections
context
current emergency state
cooldown
```

---

# 13. Error Handling

Mọi external dependency phải có:

```text
timeout
error handling
logging
retry policy where appropriate
failure state
```

External dependencies:

- Firebase
- Firestore
- R2
- Telegram
- AI model
- network
- device permissions

Không được catch:

```python
except Exception:
    pass
```

trừ khi có lý do rất rõ và có logging/state handling.

---

# 14. Emergency Reliability

Emergency path là critical path.

Không để một optional component làm chết toàn bộ workflow.

Ví dụ:

```text
Telegram unavailable
        ↓
Emergency session vẫn phải tồn tại
```

Không:

```text
Telegram exception
        ↓
SOS failed
```

---

# 15. State Management

Các state quan trọng phải được định nghĩa rõ.

Ví dụ:

```text
EmergencySession:
CREATED
ACTIVE
CANCELLED
RESOLVED
EXPIRED
```

Không dùng string tùy ý ở nhiều nơi:

```python
status = "active"
status = "ACTIVE"
status = "running"
```

Dùng enum/contract thống nhất.

---

# 16. Idempotency

Emergency workflow phải tránh duplicate.

Ví dụ user double-tap SOS:

```text
tap
tap
```

không được tạo hai emergency sessions nếu policy yêu cầu một active session duy nhất.

Notification cũng phải tránh:

```text
same event
same recipient
same channel
```

bị gửi vô hạn.

---

# 17. Concurrency

AI phải kiểm tra race conditions.

Ví dụ:

```text
SOS request A
SOS request B
```

cùng thời điểm.

Hoặc:

```text
detection A
detection B
```

cùng tạo emergency.

Phải xác định:

- locking
- transaction
- idempotency key
- unique constraint/pattern
- state transition validation

phù hợp với trường hợp.

---

# 18. Permission Handling

Mobile phải xử lý:

```text
permission granted
permission denied
permission denied permanently
permission revoked
permission unavailable
```

Không giả định user luôn cho phép:

```text
microphone
location
notification
background capability
```

UI phải phản ánh trạng thái thực tế.

---

# 19. Network Failure

Mọi mobile API phải xem xét:

```text
online
offline
slow
timeout
server error
authentication expired
WebSocket disconnected
reconnected
```

Không chỉ test khi Internet ổn định.

---

# 20. WebSocket Rules

Phải xử lý:

```text
connect
authenticate
subscribe
receive
disconnect
reconnect
duplicate connection
stale connection
server unavailable
```

Không giả định WebSocket luôn tồn tại.

---

# 21. Database Rules

Firestore:

- business metadata
- state
- events
- user data

R2:

- audio
- binary

Không lưu binary lớn trong Firestore.

Không tạo Firestore write liên tục nếu realtime stream có thể xử lý bằng WebSocket.

---

# 22. Privacy Rules

Không log:

- password
- Firebase token
- full medical information
- sensitive audio content
- unnecessary personal information

Không trả medical profile nếu endpoint không cần.

Không expose R2 storage credentials cho client.

---

# 23. Security

Mọi protected API phải:

```text
authenticate
→ identify user
→ authorize resource
→ execute
```

Không trust:

```text
user_id
```

do client gửi nếu identity có thể lấy từ Firebase token.

Ví dụ:

```text
POST /users/me/...
```

backend xác định user từ token.

---

# 24. Testing Philosophy

**Test behavior, not implementation details.**

Không chỉ test:

```text
function returns 123
```

Phải test:

```text
user action
→ service
→ state change
→ external effect
```

khi cần.

---

# 25. Mandatory Feature Development Protocol

Đây là rule quan trọng nhất đối với AI coding agent.

Mỗi lần triển khai feature phải thực hiện:

## Step 1 — Understand

Đọc:

```text
PROJECT.md
ARCHITECTURE.md
CONVENTIONS.md
DECISIONS.md
```

và source code liên quan.

## Step 2 — Impact Analysis

Xác định:

```text
feature dependencies
affected modules
affected database collections
affected API
affected mobile screens
affected native capabilities
affected realtime flow
affected notifications
affected tests
```

## Step 3 — Scenario Enumeration

AI phải tự liệt kê các trường hợp:

```text
Happy path
Invalid input
Missing data
Duplicate action
Concurrent action
Permission denied
Network unavailable
Timeout
Provider failure
Database failure
Authentication failure
Expired session
State conflict
User cancellation
App background
App foreground
App killed
Reconnect
Retry
Partial failure
```

Không được chỉ test happy path.

## Step 4 — Implement

Code đúng module/folder.

Không tạo file ngoài architecture nếu không cần.

## Step 5 — Unit Tests

Test logic cốt lõi.

## Step 6 — Integration Tests

Test module interactions.

## Step 7 — API Tests

Test:

```text
authentication
authorization
validation
success
failure
edge cases
```

## Step 8 — Mobile Tests

Test UI/state/platform behavior liên quan.

## Step 9 — Failure Injection

Cố tình mô phỏng:

```text
network failure
provider failure
permission denial
invalid token
duplicate request
empty data
malformed response
timeout
```

## Step 10 — Regression

Chạy test suite liên quan và test toàn hệ thống khi cần.

## Step 11 — Fix

Nếu test phát hiện lỗi:

```text
fix
→ rerun failed test
→ rerun related tests
→ rerun regression
```

Không dừng sau lần fix đầu tiên.

## Step 12 — Architecture Verification

Kiểm tra:

- duplicate logic?
- circular dependency?
- wrong folder?
- broken contract?
- inconsistent state?
- unnecessary dependency?
- security regression?
- data duplication?
- API breaking change?

## Step 13 — Documentation

Nếu behavior/architecture thay đổi:

```text
DECISIONS.md
ARCHITECTURE.md
PROJECT.md
```

phải được cập nhật khi cần.

---

# 26. "Done" Means Tested

Không được báo:

> "Feature implemented."

nếu chưa test.

Phải báo:

```text
Implemented
Tested
Edge cases checked
Integration checked
Regression checked
```

Nếu có limitation:

```text
Known limitation:
...
```

Không được nói feature hoàn thành nếu thực tế chưa test được.

---

# 27. No Unrelated Refactoring

Khi implement feature:

Không tự ý:

- rename toàn project
- đổi framework
- đổi database
- đổi architecture
- format hàng nghìn file
- refactor module không liên quan

trừ khi phát hiện issue bắt buộc để feature hoạt động an toàn.

Nếu phát hiện refactor cần thiết:

```text
STOP
Explain
Evaluate impact
Then implement only if justified
```

---

# 28. No Premature Technology

Không tự thêm:

```text
Redis
Kafka
RabbitMQ
Celery
Kubernetes
Qdrant
PostgreSQL
microservices
```

nếu chưa có requirement thực tế.

Kiến trúc hiện tại ưu tiên:

```text
FastAPI
Firestore
R2
WebSocket
asyncio
```

đủ cho MVP.

---

# 29. Dependency Rules

Không thêm dependency chỉ vì:

> "thư viện này tiện."

Trước khi thêm:

1. Kiểm tra dependency hiện tại.
2. Kiểm tra có thể dùng standard library không.
3. Kiểm tra package compatibility.
4. Kiểm tra Python 3.14 compatibility.
5. Kiểm tra maintenance.
6. Kiểm tra security.
7. Kiểm tra license.
8. Chỉ thêm nếu thật sự cần.

---

# 30. Python Rules

Backend dùng:

```text
Python 3.14
```

Pin dependency versions.

Không assume mọi package đều hỗ trợ Python 3.14 chỉ vì Python itself hỗ trợ.

AI phải kiểm tra compatibility trước khi thêm package AI/audio.

---

# 31. Naming

Python:

```text
snake_case
```

Dart:

```text
lowerCamelCase
UpperCamelCase for types
```

Tên phải thể hiện domain.

Ưu tiên:

```text
EmergencySession
DetectionSignal
EmergencyContact
Recording
Notification
```

Không dùng tên mơ hồ:

```text
Data
Info
Helper
Manager
Processor
Utils
```

nếu không có ngữ nghĩa rõ.

---

# 32. Comments

Comment giải thích:

```text
WHY
```

không phải:

```text
WHAT THE CODE OBVIOUSLY DOES
```

Không comment dư thừa.

---

# 33. File Header Documentation Rule (BẮT BUỘC Ở ĐẦU MỖI FILE CODE)

Mọi file mã nguồn (cả Python backend và Dart mobile) **bắt buộc phải có khối header comment chuẩn hóa ở đầu file** trước bất kỳ dòng code hoặc import nào.

Mục đích:
- Giúp developer và AI hiểu ngay lập tức trách nhiệm của file khi mở ra.
- Xác định rõ vai trò kiến trúc và ranh giới trách nhiệm (single responsibility).
- Liệt kê toàn bộ kết nối (dependencies, callers, database, external services) để rà soát bug, race condition và side-effect khi bảo trì hoặc sửa đổi.

### Cấu trúc chuẩn cho Python (`.py`):

```python
"""
=============================================================================
FILE: app/modules/emergency/safety_check/service.py
MODULE: Emergency - Safety Check
ROLE / RESPONSIBILITY:
    - Quản lý vòng đời của Safety Check Instance (ACTIVE, CHECK_REQUIRED, COMPLETED, ESCALATED).
    - Xử lý xác nhận an toàn, gia hạn và tính toán quá hạn (expiration check).
    - Khi hết grace period mà không có phản hồi, leo thang (escalate) sang EmergencyService.

CONNECTIONS / DEPENDENCIES:
    - Gọi: EmergencyService (app/modules/emergency/service.py) khi ESCALATED.
    - Gọi: NotificationService (app/modules/notifications/service.py) gửi cảnh báo.
    - Gọi: LocationService (app/modules/location/service.py) lấy checkpoint gần nhất.
    - Database: Firestore collections `safety_check_instances`, `safety_check_templates`.
    - Được gọi bởi: SafetyCheckRouter (app/modules/emergency/safety_check/router.py), Background Worker Scheduler.

INPUT / OUTPUT:
    - Input: SafetyCheckCreateDTO, ConfirmSafeDTO, ExtendDTO.
    - Output: SafetyCheckInstanceResponse, Event trigger sang Emergency workflow.
=============================================================================
"""
```

### Cấu trúc chuẩn cho Dart / Flutter (`.dart`):

```dart
/// =============================================================================
/// FILE: lib/features/safety_check/presentation/safety_check_screen.dart
/// MODULE: Safety Check Feature
/// ROLE / RESPONSIBILITY:
///     - Hiển thị danh sách template (5 mặc định + custom) và đếm ngược phiên đang chạy.
///     - Cung cấp các thao tác nhanh: [Tôi an toàn], [Gia hạn], [Hủy], [Bắt đầu].
///
/// CONNECTIONS / DEPENDENCIES:
///     - State: SafetyCheckBloc / SafetyCheckNotifier.
///     - Local Notifications: NotificationService (để hủy local alarm khi đã bấm an toàn).
///     - Hardware: FlashlightService, SirenSoundService (nếu có kích hoạt báo động).
///     - Backend API: SafetyCheckRepository -> /api/v1/safety-check/...
///
/// INPUT / OUTPUT:
///     - Input: User tap events, Timer countdown stream.
///     - Output: UI render, API requests, local alarm trigger.
/// =============================================================================
```

Tuyệt đối không được bỏ qua khối header này trong bất kỳ file code mới nào.

---

# 34. Final AI Rule

Khi được yêu cầu triển khai một feature, AI phải tự hỏi:

> "Nếu feature này được sử dụng sai, sử dụng liên tục, sử dụng đồng thời, mất mạng, mất quyền, server lỗi, provider lỗi, app bị background/killed, dữ liệu thiếu hoặc dữ liệu cũ thì hệ thống sẽ làm gì?"

Nếu chưa trả lời được câu hỏi đó:

**Feature chưa hoàn thành.**

