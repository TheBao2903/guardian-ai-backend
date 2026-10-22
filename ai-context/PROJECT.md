# Guardian AI — Project Definition

> **Project:** Guardian AI
> **Type:** Mobile AI Safety Application
> **Primary Client:** Flutter Mobile App
> **Backend:** Python + FastAPI
> **Authentication:** Firebase Authentication
> **Database:** Firebase Firestore
> **Object Storage:** Cloudflare R2
> **Realtime:** WebSocket + asynchronous processing
> **Notification:** Telegram Bot API
> **AI Runtime:** PyTorch / Python audio-processing ecosystem
> **Status:** Active development
> **Architecture Style:** Modular Monolith with clear feature boundaries

---

# 1. Project Overview

Guardian AI là một ứng dụng mobile hỗ trợ an toàn cá nhân, tập trung vào việc phát hiện các tín hiệu bất thường/nguy hiểm, hỗ trợ người dùng kích hoạt SOS và tự động liên hệ với người thân trong trường hợp khẩn cấp.

Sản phẩm được thiết kế theo hướng:

```text
Mobile-first
AI-assisted
Real-time
Emergency-oriented
Privacy-aware
Low-cost
Modular
Extensible
```

Guardian AI không phải là một hệ thống chẩn đoán y khoa và không được mô tả như một hệ thống có khả năng xác định chắc chắn người dùng đang gặp nguy hiểm.

AI chỉ tạo ra:

```text
Detection Signal
      ↓
Risk / Emergency Decision
      ↓
Emergency Workflow
```

Không được thiết kế:

```text
AI Model
   ↓
"Chắc chắn nguy hiểm"
   ↓
SOS ngay lập tức
```

---

# 2. Product Goal

Mục tiêu chính:

> Cung cấp cho người dùng một công cụ mobile có thể theo dõi các tín hiệu an toàn quan trọng, hỗ trợ phát hiện âm thanh bất thường/scream, cho phép kích hoạt SOS, chia sẻ vị trí và thông tin khẩn cấp, lưu lại bằng chứng âm thanh khi cần thiết và thông báo cho người thân.

Guardian AI cần ưu tiên:

1. Độ tin cậy của emergency workflow.
2. Không làm mất dữ liệu quan trọng.
3. Không gửi cảnh báo trùng lặp vô hạn.
4. Không tạo false positive quá mức.
5. Không làm rò rỉ thông tin y tế.
6. Không phá vỡ hệ thống khi một provider bên ngoài gặp lỗi.
7. Có thể mở rộng thêm capability trong tương lai mà không phải viết lại toàn bộ hệ thống.

---

# 3. Current Product Scope

## 3.1. Mobile Application

Ứng dụng mobile được xây dựng bằng:

```text
Flutter
Dart
```

Không xây web frontend trong scope hiện tại.

Desktop web/dashboard không phải deliverable chính của sản phẩm hiện tại.

Nếu sau này cần web client, web phải được xem là một client mới sử dụng lại backend contracts, không được làm thay đổi business logic hiện tại chỉ để phục vụ web.

---

# 4. Core Features

## 4.1. Authentication

Người dùng có thể:

- đăng ký
- đăng nhập
- đăng xuất
- duy trì authenticated session
- lấy thông tin tài khoản hiện tại
- xử lý authentication state

Authentication provider:

```text
Firebase Authentication
```

Backend không tự quản lý password.

Backend có trách nhiệm:

```text
verify Firebase ID Token
        ↓
identify user
        ↓
authorize request
```

Không lưu password trong Firestore.

---

# 5. User Emergency Profile

Người dùng có thể lưu thông tin phục vụ tình huống khẩn cấp.

Thông tin cơ bản có thể gồm:

- họ tên
- tuổi
- ngày sinh

Thông tin y tế:

- nhóm máu
- chiều cao
- cân nặng

Thông tin khẩn cấp:

- dị ứng
- bệnh nền
- thuốc đang sử dụng
- ghi chú quan trọng

Nguồn yêu cầu ban đầu của sản phẩm có mô tả nhóm thông tin cá nhân, y tế và emergency notes này.

### Privacy requirement

Không được trả toàn bộ medical profile trong mọi API response.

Phải phân biệt:

```text
Private Medical Data
        vs
Emergency-Sharable Data
        vs
Lock-Screen Public Data
```

Người dùng phải có quyền quyết định dữ liệu nào được phép hiển thị trong tình huống khẩn cấp.

---

# 6. Emergency Contacts

Người dùng có thể quản lý:

- người thân
- bạn bè
- người liên hệ khẩn cấp
- mối quan hệ
- số điện thoại
- Telegram recipient/chat identifier nếu cần cho Telegram workflow
- thứ tự ưu tiên liên hệ
- trạng thái active/inactive

Các thao tác:

```text
Create
Read
Update
Delete
Reorder / Priority
Enable / Disable
```

Emergency contact không được mặc định đồng nghĩa với Telegram recipient.

Hai khái niệm phải được xử lý riêng:

```text
Emergency Contact
        │
        ├── Phone
        ├── Telegram
        └── Other notification channels
```

---

# 7. Real-time Location

Ứng dụng có thể thu thập vị trí hiện tại của người dùng khi user cho phép.

Location được sử dụng cho:

- emergency event
- SOS
- chia sẻ vị trí với emergency contacts
- contextual information
- emergency history

Không được ghi GPS vào Firestore ở tần suất quá cao một cách không cần thiết.

Kiến trúc:

```text
Mobile GPS
    │
    ├── realtime → WebSocket
    │
    └── checkpoint/event → Firestore
```

Firestore không phải realtime location stream.

---

# 8. Abnormal Sound Detection

Guardian AI có capability phát hiện các âm thanh bất thường.

Không được đồng nhất:

```text
abnormal sound
=
scream
=
speech
```

Đây là ba khái niệm khác nhau.

Hệ thống phải phân biệt:

```text
General Sound Detection
Scream / Distress Detection
Speech Recognition
```

---

# 9. Scream / Distress Detection

Scream detection là một capability riêng.

Model candidate:

```text
VocalBurst Locator
```

hoặc model chuyên biệt tương đương sau benchmark.

Không được hard-code architecture phụ thuộc duy nhất vào một model.

Model phải được đặt sau một abstraction/interface phù hợp để có thể thay thế.

Ví dụ:

```text
ScreamDetector
      │
      ├── VocalBurstDetector
      ├── FutureCustomScreamModel
      └── FutureOnDeviceModel
```

---

# 10. General Audio Detection

Model baseline có thể sử dụng:

```text
YAMNet
```

YAMNet được xem là general audio event classifier, không phải model chuyên biệt để quyết định SOS.

Không được sử dụng YAMNet như:

```text
YAMNet detects event
        ↓
automatic SOS
```

Phải có decision layer ở giữa.

---

# 11. Speech-to-Text

Speech-to-text chỉ được triển khai nếu sản phẩm thực sự cần transcript.

Candidate:

```text
faster-whisper
```

Không được dùng Whisper/faster-whisper để thay thế scream detector.

Whisper answers:

> "Người dùng nói gì?"

Scream detector answers:

> "Có vocal distress/scream hay không?"

Đây là hai bài toán khác nhau.

---

# 12. Emergency Audio Recording

Guardian AI có khả năng ghi âm trong emergency workflow.

Không được mặc định upload toàn bộ audio liên tục lên server.

Ưu tiên:

```text
Temporary / rolling audio buffer
             ↓
       suspicious event
             ↓
      emergency decision
             ↓
      preserve relevant audio
             ↓
             R2
```

R2 lưu binary/audio.

Firestore lưu metadata:

```text
recording_id
user_id
event_id
storage_key
duration
created_at
content_type
status
```

Không lưu binary audio trực tiếp trong Firestore.

---

# 13. SOS

SOS là một emergency workflow, không phải chỉ là một button.

Có thể được kích hoạt bởi:

```text
Manual SOS
Future native trigger
Future automatic safety signal
```

Tất cả phải đi qua cùng emergency workflow.

```text
SOS Trigger
    ↓
Emergency Session
    ↓
Capture Context
    ├── User
    ├── Location
    ├── Timestamp
    ├── Relevant Detection
    └── Audio
    ↓
Notify Contacts
    ↓
Track Status
```

Không được tạo một logic SOS riêng cho từng trigger.

---

# 14. Emergency Notification

Notification service là capability độc lập.

Telegram là notification provider hiện tại.

```text
Emergency Service
       ↓
Notification Service
       ↓
Telegram Adapter
       ↓
Telegram Bot API
```

Emergency business logic không được gọi Telegram API trực tiếp.

Sau này có thể thêm:

```text
Telegram
Push Notification
SMS
Email
Other Provider
```

mà không thay đổi emergency decision logic.

---

# 15. Lock-Screen Emergency Information

Sản phẩm có yêu cầu hỗ trợ hiển thị thông tin quan trọng khi điện thoại bị khóa.

Đây là mobile/OS feature.

Backend chỉ cung cấp dữ liệu được phép hiển thị.

Flutter/native layer chịu trách nhiệm:

```text
OS capability
      ↓
Lock-screen presentation
```

Không được đưa logic lock-screen vào FastAPI.

---

# 16. Power Button / Native SOS

Power-button SOS là một native OS capability.

Không được giả lập bằng JavaScript/web.

Nếu platform cho phép:

```text
OS event
   ↓
Native layer
   ↓
Flutter bridge
   ↓
Emergency Service
```

Nếu platform không cho phép thì phải ghi nhận limitation.

Không được hack hoặc tạo behavior giả để tuyên bố rằng feature đã hoạt động.

---

# 16b. Safety Check Timer (Hẹn giờ kiểm tra an toàn)

Safety Check Timer là tính năng cho phép người dùng đặt khoảng thời gian cần xác nhận an toàn trước khi di chuyển qua khu vực có rủi ro.

Không đồng nhất:
```text
Timer hết hạn = SOS khẩn cấp ngay lập tức
```

Quy trình Escalation Flow bắt buộc:
```text
ACTIVE
   ↓ (Hết hạn timer)
CHECK_REQUIRED
   ↓ (Grace Period: 30s - 10 phút tùy template)
User xác nhận
   ├── Bấm "Tôi an toàn" → COMPLETED
   └── Không phản hồi (Hết Grace Period)
          ↓
      ESCALATED (SAFETY_CHECK_TIMEOUT)
          ↓
      Emergency Service gửi cảnh báo người thân (Telegram)
      + Vị trí gần nhất đã ghi nhận
```

### Hệ thống Template
Bao gồm 5 template mặc định:
1. 🚶 Đi bộ về nhà (15-30 phút, Grace: 1 phút)
2. 🛵 Di chuyển bằng xe (30-60 phút, Grace: 2 phút)
3. 🥾 Khám phá ngoài trời (1-4 giờ, Grace: 5-10 phút)
4. 🏠 Kiểm tra an toàn (30 phút - 2 giờ, Grace: 2 phút)
5. 👤 Cuộc gặp an toàn (30-60 phút, Grace: 1-2 phút)

Và cho phép User tạo **Custom Template** riêng.

---

# 16c. Local Safety Signals & Direct Emergency Call (Mobile Layer)

1. **Còi hú báo động (Alarm Siren):**
   - Kích hoạt âm thanh tần số cao qua `AVAudioSessionCategoryPlayback` (iOS) để phát to ngay cả khi máy gạt nút im lặng (Silent Switch).
2. **Đèn Flash chớp tắt (Strobe Light):**
   - Nhấp nháy đèn flash LED camera tạo sức ép xua đuổi kẻ xấu hoặc hỗ trợ lực lượng cứu hộ định vị trong bóng tối.
3. **Gọi điện trực tiếp (Native Direct Call):**
   - Tự động mở trình quay số (`url_launcher: tel:...`) gọi ngay cho liên hệ khẩn cấp ưu tiên số 1 khi kích hoạt SOS.

---

# 16d. Môi trường phát triển & Kiểm thử iOS trên Windows

Do lập trình viên phát triển trên máy Windows và kiểm thử trên iPhone thật (không có máy Mac vật lý):
- Quá trình biên dịch iOS `.ipa` được tự động hóa qua **GitHub Actions CI/CD** (macOS Runner miễn phí).
- Cài đặt vào iPhone qua máy tính Windows sử dụng **Sideloadly / 3uTools** (Ký bằng Apple ID cá nhân miễn phí).
- Phát triển giao diện nhanh trên Flutter Desktop Windows / Web trước khi đóng gói `.ipa`.

---

# 17. Non-Goals

Các tính năng sau KHÔNG thuộc scope hiện tại:

```text
Camera / video detection
Fall detection
Disaster monitoring
Weather alerts
Flood detection
Earthquake monitoring
Community safety map
Qdrant recommendation system
Web dashboard
Desktop web application
Vehicle crash detection
Heart-rate anomaly detection
Fire detection
Gas leak detection
```

Các capability trên chỉ có thể được thêm trong tương lai thông qua architecture extension.

AI coding agent không được tự ý triển khai các tính năng này.

---

# 18. Main Architecture

```text
                     GUARDIAN AI
                          │
                 Flutter Mobile App
                          │
                   HTTPS / WebSocket
                          │
                          ▼
                    FastAPI Backend
                          │
        ┌─────────────────┼─────────────────┐
        │                 │                 │
     Firebase             │                R2
     Auth +               │          Audio / Files
     Firestore             │
                           │
              ┌────────────┼────────────┐
              │            │            │
          Emergency      Detection   Notification
            Module        Module       Module
              │            │            │
              └────────────┼────────────┘
                           │
                       Telegram
```

---

# 19. Product Philosophy

Guardian AI phải ưu tiên:

```text
Safety
Correctness
Reliability
Privacy
Testability
Maintainability
```

hơn:

```text
Number of features
Architecture complexity
Number of AI models
Premature scalability
```

Không được thêm technology chỉ vì "có thể cần sau này".

---

# 20. Definition of Done

Một feature chỉ được xem là hoàn thành khi:

- implementation hoàn tất
- happy path hoạt động
- validation hoạt động
- authentication/authorization đúng
- error handling đầy đủ
- edge cases được kiểm tra
- failure cases được kiểm tra
- integration với module liên quan được kiểm tra
- regression test được chạy
- test mới được bổ sung
- architecture không bị phá vỡ
- code nằm đúng feature folder
- không tạo duplicate business logic
- không tạo duplicate data model nếu entity đã tồn tại
- documentation/context được cập nhật nếu behavior thay đổi

AI không được coi:

```text
"code compile"
```

là:

```text
"feature completed"
```

---

# 21. Primary Development Rule

Mỗi implementation phải tuân thủ:

```text
Understand
    ↓
Inspect Existing Code
    ↓
Identify Dependencies
    ↓
Plan
    ↓
Implement
    ↓
Test
    ↓
Find Edge Cases
    ↓
Fix
    ↓
Run Regression Tests
    ↓
Verify Integration
    ↓
Update Documentation
    ↓
Complete
```

Không được bỏ qua các bước chỉ vì feature nhỏ.
