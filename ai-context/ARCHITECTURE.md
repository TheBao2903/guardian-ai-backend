# Guardian AI — System Architecture

> **Architecture Style:** Modular Monolith
> **Mobile:** Flutter / Dart
> **Backend:** Python / FastAPI
> **Authentication:** Firebase Authentication
> **Database:** Firestore
> **Object Storage:** Cloudflare R2
> **Realtime:** WebSocket + asyncio
> **Notification:** Telegram Bot API
> **AI:** PyTorch + audio-processing libraries
> **Deployment:** Mobile App + cloud-hosted FastAPI backend

---

# 1. Core Architecture Principle

Guardian AI phải tuân thủ nguyên tắc:

> **Separate business capabilities, share common infrastructure, communicate through stable contracts.**

Không xây:

```text
One giant GuardianService
```

Không xây:

```text
SOSService
  ├── Telegram
  ├── Firestore
  ├── Audio
  ├── Location
  ├── User
  └── Contacts
```

theo kiểu mọi thứ phụ thuộc trực tiếp lẫn nhau.

Thay vào đó:

```text
Feature Modules
       ↓
Application / Business Logic
       ↓
Shared Contracts
       ↓
Infrastructure Adapters
```

---

# 2. High-Level Architecture

```text
┌─────────────────────────────────────────────┐
│              FLUTTER MOBILE APP             │
│                                             │
│  Auth │ Home │ SOS │ Location │ Audio       │
│  Profile │ Contacts │ Emergency History     │
│                                             │
│  Native Platform Layer                      │
│  ├── Location                               │
│  ├── Audio                                  │
│  ├── Notifications                          │
│  ├── Background capabilities                │
│  └── OS-specific emergency features         │
└──────────────────────┬──────────────────────┘
                       │
                HTTPS / WebSocket
                       │
┌──────────────────────▼──────────────────────┐
│                FASTAPI BACKEND              │
│                                             │
│  Auth                                        │
│  Users                                       │
│  Emergency                                   │
│  Contacts                                    │
│  Location                                    │
│  Detection                                   │
│  Notifications                               │
│  Recordings                                  │
│                                             │
│  Shared Domain / Contracts                   │
│  Infrastructure                              │
└───────────┬─────────────────┬────────────────┘
            │                 │
            ▼                 ▼
      ┌───────────┐      ┌────────────┐
      │ Firestore │      │ Cloudflare │
      │           │      │ R2         │
      └───────────┘      └────────────┘
            │
            ▼
      Telegram API
```

---

# 3. Backend Project Structure

Recommended structure:

```text
backend/
│
├── app/
│   │
│   ├── main.py
│   │
│   ├── core/
│   │   ├── config.py
│   │   ├── security.py
│   │   ├── exceptions.py
│   │   ├── logging.py
│   │   └── dependencies.py
│   │
│   ├── shared/
│   │   ├── contracts/
│   │   ├── enums/
│   │   ├── events/
│   │   ├── utils/
│   │   └── types/
│   │
│   ├── modules/
│   │   │
│   │   ├── auth/
│   │   │   ├── router.py
│   │   │   ├── service.py
│   │   │   ├── schemas.py
│   │   │   └── dependencies.py
│   │   │
│   │   ├── users/
│   │   │   ├── router.py
│   │   │   ├── service.py
│   │   │   ├── schemas.py
│   │   │   └── repository.py
│   │   │
│   │   ├── emergency/
│   │   │   ├── router.py
│   │   │   ├── service.py
│   │   │   ├── schemas.py
│   │   │   ├── models.py
│   │   │   ├── repository.py
│   │   │   └── safety_check/
│   │   │       ├── router.py
│   │   │       ├── service.py
│   │   │       ├── schemas.py
│   │   │       ├── repository.py
│   │   │       └── scheduler.py
│   │   │
│   │   ├── contacts/
│   │   │   ├── router.py
│   │   │   ├── service.py
│   │   │   ├── schemas.py
│   │   │   └── repository.py
│   │   │
│   │   ├── location/
│   │   │   ├── router.py
│   │   │   ├── service.py
│   │   │   ├── schemas.py
│   │   │   └── repository.py
│   │   │
│   │   ├── detection/
│   │   │   ├── router.py
│   │   │   ├── service.py
│   │   │   ├── schemas.py
│   │   │   ├── detectors/
│   │   │   ├── preprocessing/
│   │   │   └── decision/
│   │   │
│   │   ├── recordings/
│   │   │   ├── router.py
│   │   │   ├── service.py
│   │   │   ├── schemas.py
│   │   │   └── repository.py
│   │   │
│   │   └── notifications/
│   │       ├── service.py
│   │       ├── schemas.py
│   │       └── providers/
│   │           └── telegram.py
│   │
│   ├── infrastructure/
│   │   ├── firestore/
│   │   ├── storage/
│   │   │   └── r2/
│   │   ├── telegram/
│   │   └── realtime/
│   │
│   └── realtime/
│       ├── manager.py
│       ├── websocket.py
│       └── handlers.py
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── api/
│   └── e2e/
│
└── requirements.txt
```

---

# 4. Folder Ownership Rule

Một rule bắt buộc:

> **Code phải nằm trong folder của capability mà nó phục vụ.**

Ví dụ:

Scream detector:

```text
modules/detection/
```

Không được đặt:

```text
modules/emergency/scream_detector.py
```

Telegram:

```text
modules/notifications/
```

Không được đặt:

```text
modules/emergency/telegram_service.py
```

Location:

```text
modules/location/
```

Không được đặt:

```text
modules/users/location_service.py
```

Emergency orchestration có thể gọi location service, nhưng không được sở hữu location implementation.

---

# 5. Flutter Architecture

Flutter app nên được tổ chức feature-first.

```text
mobile/
├── lib/
│   ├── core/
│   │   ├── config/
│   │   ├── network/
│   │   ├── auth/
│   │   ├── storage/
│   │   ├── errors/
│   │   └── routing/
│   │
│   ├── shared/
│   │   ├── widgets/
│   │   ├── models/
│   │   └── utils/
│   │
│   ├── features/
│   │   ├── auth/
│   │   ├── home/
│   │   ├── emergency/
│   │   ├── location/
│   │   ├── audio_detection/
│   │   ├── recordings/
│   │   ├── contacts/
│   │   ├── profile/
│   │   └── settings/
│   │
│   └── main.dart
│
├── android/
├── ios/
└── test/
```

Không được để business code vào `main.dart`.

Không biến `shared/` thành nơi chứa mọi thứ không biết đặt ở đâu.

---

# 6. Client / Backend Boundary

Flutter không được truy cập Firestore/R2/Telegram backend credentials trực tiếp cho business workflow nếu không cần thiết.

Ưu tiên:

```text
Flutter
   ↓
FastAPI
   ↓
Business Logic
   ↓
Infrastructure
```

Firebase Authentication có thể được sử dụng ở client để authenticate.

Sau đó:

```text
Firebase ID Token
        ↓
FastAPI
        ↓
Token Verification
        ↓
User Identity
```

---

# 7. Emergency Architecture

Emergency là trung tâm của hệ thống.

```text
Trigger
   │
   ├── Manual SOS
   ├── Native SOS (Power button)
   ├── Detection Signal (Scream/Distress)
   └── Safety Check Timeout (Escalated)
           │
           ▼
    Emergency Service
           │
           ▼
    Create Emergency Session
           │
      ┌────┼────┐
      │    │    │
      ▼    ▼    ▼
 Location Audio Contacts
      │    │    │
      └────┼────┘
           ▼
   Notification Service
           │
           ▼
       Telegram
```

Emergency Service không được trực tiếp implement:

- audio model
- Telegram API
- GPS provider
- R2 SDK

Nó chỉ orchestration các capability.

---

# 7b. Safety Check Architecture & Escalation

Safety Check là thành phần tiền khẩn cấp:

```text
Safety Check Start
        ↓
ACTIVE (Client đếm ngược qua Server Timestamp UTC & Native Local Notification)
        ↓
CHECK_REQUIRED (Khi expires_at đến hạn)
        ↓
Grace Period (30s – 10m tùy Template)
        ├── User: "Tôi an toàn" → COMPLETED
        ├── User: "Gia hạn"     → ACTIVE (Cập nhật lại expires_at)
        └── Không phản hồi (now >= grace_period_until)
                ↓
            Backend Scheduler (Asyncio Periodic Worker)
                ↓
            ESCALATED (SAFETY_CHECK_TIMEOUT)
                ↓
            Emergency Service (Gửi tin nhắn Telegram + Vị trí gần nhất)
```

Không dùng countdown backend từng giây. Scheduler chỉ quét định kỳ các instance có `grace_period_until <= now()` bằng Firestore Transaction.

---

# 8. Detection Architecture

Detection phải tách thành các layer:

```text
Audio Input
    ↓
Preprocessing
    ↓
Detector
    ↓
Normalized Detection Signal
    ↓
Temporal Aggregation
    ↓
Risk / Emergency Decision
```

Ví dụ:

```text
YAMNet
   ↓
Audio Event

VocalBurst
   ↓
Scream Event

Other detector
   ↓
Abnormal Event
```

Các output phải được normalize về contract chung.

Ví dụ concept:

```text
DetectionSignal {
    type
    confidence
    started_at
    ended_at
    source
    metadata
}
```

Không để emergency module phụ thuộc trực tiếp vào output format riêng của YAMNet/VocalBurst.

---

# 9. Temporal Aggregation

Không được:

```text
one model frame
       ↓
SOS
```

Phải có temporal logic.

Ví dụ:

```text
Window 1 → scream 0.84
Window 2 → scream 0.89
Window 3 → scream 0.86
        ↓
Temporal aggregation
        ↓
Scream signal
```

Các threshold phải configurable.

Không hard-code nhiều threshold rải rác trong code.

---

# 10. False Positive Protection

Emergency workflow phải có:

```text
confidence threshold
+
temporal consistency
+
cooldown
+
duplicate prevention
+
user cancellation
```

Ví dụ:

```text
Scream detected
     ↓
candidate event
     ↓
confirm persistence
     ↓
Emergency decision
     ↓
create session
     ↓
cooldown
```

Không gửi 20 Telegram messages cho 20 audio windows.

---

# 11. Location Architecture

Location có hai loại:

### Realtime

```text
Mobile GPS
   ↓
WebSocket
   ↓
Realtime Manager
```

### Persistence

```text
Emergency checkpoint
   ↓
Firestore
```

Không ghi:

```text
GPS every 1 second
→ Firestore
```

trừ khi có lý do nghiệp vụ rõ ràng.

---

# 12. Recording Architecture

```text
Mobile
  ↓
Audio
  ↓
Temporary buffer
  ↓
Emergency condition
  ↓
Relevant segment
  ↓
Upload
  ↓
R2
```

Metadata:

```text
Firestore
```

Binary:

```text
R2
```

Không lưu binary lớn trong Firestore.

---

# 13. Notification Architecture

```text
Emergency Service
        ↓
Notification Service
        ↓
Notification Provider Interface
        ↓
Telegram Provider
```

Ví dụ:

```text
NotificationProvider
        │
        ├── TelegramProvider
        └── FuturePushProvider
```

Nếu Telegram API down:

```text
Telegram failure
      ↓
log provider failure
      ↓
preserve emergency event
      ↓
retry / fallback according to policy
```

Không được làm mất emergency event chỉ vì notification provider lỗi.

---

# 14. Firestore Architecture

Firestore là transactional/business data source.

Có thể có các nhóm collection:

```text
users
emergency_profiles
emergency_contacts
emergency_sessions
detection_events
location_checkpoints
recordings
notifications
safety_check_templates
safety_check_instances
```

Tên collection phải thống nhất.

Không tạo collection mới chỉ vì một màn hình cần một object nhỏ nếu entity đó đã có.

---

# 15. R2 Architecture

R2 dành cho:

```text
audio recordings
future binary evidence
```

Firestore chỉ lưu metadata.

Storage key phải predictable và partitioned.

Ví dụ:

```text
users/{user_id}/emergency/{event_id}/audio/{recording_id}.webm
```

Không dùng filename do user cung cấp trực tiếp làm storage key nếu không sanitize.

---

# 16. Realtime Architecture

WebSocket chỉ được dùng cho dữ liệu cần realtime.

Ví dụ:

```text
location updates
emergency state
detection status
```

Không dùng WebSocket chỉ vì "REST chậm".

Phải có lý do rõ ràng.

WebSocket manager phải quản lý:

```text
connection
authentication
user association
disconnect
reconnect
cleanup
```

Không giữ stale connections.

---

# 17. API Layer

Controller/router phải mỏng.

Không:

```python
@router.post("/sos")
async def sos(...):
    # 200 lines business logic
```

Nên:

```text
Router
   ↓
Application Service
   ↓
Domain/business logic
   ↓
Repository/provider
```

Router chịu trách nhiệm:

- parse request
- auth dependency
- call service
- map response

---

# 18. Native Boundary

Flutter feature code không được chứa quá nhiều platform-specific logic.

Nên:

```text
Feature
   ↓
Platform Service Interface
   ↓
Android implementation
iOS implementation
```

Ví dụ:

```text
NativeEmergencyTrigger
NativeAudioService
NativeLocationService
NativeNotificationService
```

Các capability không được OS hỗ trợ phải trả về trạng thái rõ ràng.

Không giả lập thành công.

---

# 19. Architecture Evolution Rule

Nếu thêm feature mới:

```text
New Feature
    ↓
Identify ownership
    ↓
Create module
    ↓
Define contract
    ↓
Integrate shared services
```

Không được:

```text
New Feature
    ↓
modify random existing module
    ↓
duplicate logic
```

Mọi thay đổi cross-module phải kiểm tra dependency impact.

---

# 20. Architecture Acceptance Criteria

Kiến trúc chỉ được xem là ổn định khi:

- [ ] Flutter là client chính.
- [ ] FastAPI là backend duy nhất.
- [ ] Authentication qua Firebase.
- [ ] Firestore là business database.
- [ ] R2 lưu binary.
- [ ] Telegram nằm sau notification abstraction.
- [ ] Detection nằm riêng khỏi emergency orchestration.
- [ ] Location nằm riêng khỏi emergency orchestration.
- [ ] Recording nằm riêng khỏi detection.
- [ ] Router không chứa business logic lớn.
- [ ] AI model không trực tiếp trigger Telegram.
- [ ] AI model không trực tiếp thao tác Firestore.
- [ ] Emergency không phụ thuộc vào một model cụ thể.
- [ ] Provider có thể thay thế.
- [ ] Không có duplicate business logic.
- [ ] Không có circular dependency.
- [ ] Feature code nằm đúng folder.
- [ ] Native code nằm ở native/platform layer.
- [ ] Web không phải dependency của mobile app.
- [ ] Optional feature failure không làm crash critical SOS workflow.
