# 🛡️ Guardian AI — Backend API Engine

> **Hệ thống Backend API & AI Engine thời gian thực cho nền tảng bảo vệ an toàn cá nhân và cứu hộ khẩn cấp Guardian AI.**

[![Python Version](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.14-blue?logo=python)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![Firebase Firestore](https://img.shields.io/badge/Database-Cloud%20Firestore-FFA000?logo=firebase)](https://firebase.google.com/)
[![Privacy-First](https://img.shields.io/badge/Privacy-Zero%20Audio%20Storage-success)]()
[![AI Engine](https://img.shields.io/badge/AI%20Model-Google%20YAMNet%20ONNX-purple)](https://huggingface.co/zeropointnine/yamnet-onnx)
[![Live Status](https://img.shields.io/badge/Render-Live%20Deploy-brightgreen?logo=render)](https://guardian-ai-backend-srdi.onrender.com/health)

---

## 📖 1. Giới thiệu tổng quan

**Guardian AI Backend** là hạt nhân điều phối thông minh của hệ sinh thái Guardian AI. Backend chịu trách nhiệm xử lý các luồng nghiệp vụ khẩn cấp đòi hỏi độ trễ cực thấp (Low Latency), độ tin cậy tuyệt đối (High Reliability), và tính toàn vẹn dữ liệu cao:

* **Trí tuệ nhân tạo âm thanh (Audio AI Engine):** Tích hợp mô hình học sâu **Google YAMNet (ONNX Runtime)** phân loại hơn 520 lớp âm thanh, chuyên biệt hóa nhận diện các tín hiệu nguy hiểm: Tiếng la hét (Screaming), tiếng khóc lóc cầu cứu (Distress Cry), tiếng kính vỡ (Glass Shatter), tiếng súng/nổ (Gunshot/Explosion), còi báo động (Alarm).
* **Quản lý quy trình SOS & Safety Check:** Đếm ngược an toàn thông minh, lên lịch kiểm tra định kỳ (Cron/Background Scheduler), tự động kích hoạt quy trình cứu trợ khi nạn nhân bất tỉnh hoặc mất khả năng tương tác.
* **Mã PIN chống cưỡng bức (Duress PIN System):** Thuật toán Bcrypt độc quyền phân biệt trạng thái hủy thật (`Safe PIN`) và hủy giả dưới sự uy hiếp (`Duress PIN`) để âm thầm phát báo động cứu hộ khẩn cấp.
* **Cứu trợ đa kênh (Omni-channel Alert Dispatcher):** Gửi cảnh báo tức thì qua Telegram Bot tới mạng lưới người thân ưu tiên, đính kèm định vị GPS thời gian thực và hồ sơ y tế bệnh án.
* **Bảo mật & Quyền riêng tư (Privacy-First):** Hệ thống không lưu trữ các đoạn băng ghi âm lên đám mây, triệt tiêu mọi rủi ro lộ lọt dữ liệu giọng nói và đời tư người dùng.

---

## 🏛️ 2. Kiến trúc hệ thống (Clean Architecture & Modular)

Backend được thiết kế theo mô hình **Modular Architecture kết hợp Repository Pattern**, phân tách rõ ràng giữa Business Logic, Data Access và Transport Layer:

```
backend/
├── app/
│   ├── config/              # Chứa .gitkeep và chứng thực dịch vụ an toàn
│   ├── core/                # Cấu hình hệ thống (Settings), Logging, Bảo mật, Rate Limiting
│   │   ├── config.py        # Pydantic BaseSettings đọc .env & auto-detect credentials
│   │   ├── dependencies.py  # Dependency Injection (Auth, DB client, Services)
│   │   ├── exceptions.py    # Chuẩn hóa lỗi API (RFC 7807 problem details)
│   │   └── security/        # Bcrypt Hasher (Safe PIN & Duress PIN)
│   ├── infrastructure/      # Kết nối dịch vụ hạ tầng đám mây
│   │   └── firestore/       # Google Cloud Firestore NoSQL Database Client
│   ├── models/              # Trọng số AI: yamnet.onnx & yamnet_class_map.csv
│   ├── modules/             # Các Feature Modules độc lập
│   │   ├── auth/            # Đăng ký, đăng nhập, JWT, quản lý PIN
│   │   ├── users/           # Hồ sơ cá nhân, Hồ sơ y tế khẩn cấp
│   │   ├── contacts/        # Danh bạ người thân, phân cấp ưu tiên (P1, P2, P3)
│   │   ├── detection/       # Audio ML Pipeline, YAMNet ONNX, Temporal Aggregator
│   │   ├── emergency/       # Vòng đời SOS, Xác thực PIN, Silent Duress Trigger
│   │   │   └── safety_check/# Scheduler đếm ngược an toàn, Background Worker
│   │   ├── location/        # Thu thập tọa độ GPS, Checkpoints lộ trình
│   │   ├── notifications/   # Dispatcher Telegram Bot, Format thông điệp cứu hộ
│   │   └── recordings/      # Upload & streaming file ghi âm bằng chứng
│   ├── realtime/            # WebSocket Connection Manager kết nối 2 chiều
│   └── shared/              # Enums, Schemas dùng chung, DTO Envelopes
│   └── main.py              # Application Entrypoint, Lifespan, CORS, Middleware
├── requirements.txt         # Production dependencies
├── .env.example             # Template biến môi trường
└── vercel.json / .gitignore # Cấu hình triển khai và bảo mật
```

---

## ⚡ 3. Các công nghệ & Dịch vụ sử dụng

| Lĩnh vực | Công nghệ | Mục đích sử dụng |
| :--- | :--- | :--- |
| **Framework** | **FastAPI 0.115+** | API bất đồng bộ (Async/Await) tốc độ cao, Swagger/OpenAPI tự động |
| **ASGI Server** | **Uvicorn** | Web server tiêu chuẩn công nghiệp hiệu năng cao |
| **Database** | **Cloud Firestore** | Cơ sở dữ liệu tài liệu NoSQL phân tán, thời gian phản hồi miligiây |
| **AI Inference** | **ONNX Runtime** | Chạy mô hình YAMNet deep learning tối ưu trên CPU không cần GPU |
| **Notification** | **Telegram Bot API** | Hệ thống thông báo khẩn cấp tức thì (miễn phí, ổn định 99.99%) |
| **Bảo mật** | **Bcrypt & PyJWT** | Băm mã PIN 10 rounds salt ngẫu nhiên, xác thực token không trạng thái |
| **Kiểm thử** | **Pytest & AsyncIO** | 100% test coverage cho các luồng xác thực PIN, Audio, SOS |

---

## 🎯 4. Các luồng xử lý cốt lõi (Core Workflows)

### 🔊 A. Quy trình phân tích âm thanh khẩn cấp (AI Audio Pipeline)
1. Client gửi đoạn âm thanh WAV PCM (16kHz, mono) hoặc đặc trưng vector lên endpoint `/api/v1/detection/analyze-audio`.
2. `YAMNetDetector` nạp tensor âm thanh vào mô hình ONNX, tính toán phân phối xác suất trên 521 nhãn âm thanh.
3. Bộ lọc `AUDIOSET_LABEL_MAPPING` lọc các tín hiệu trọng yếu: `SCREAM`, `DISTRESS_CRY`, `GLASS_SHATTER`, `GUNSHOT`, `EXPLOSION`.
4. `TemporalAggregator` tổng hợp chuỗi thời gian, loại trừ tiếng ồn môi trường và tiếng nói thông thường.
5. Nếu vượt ngưỡng nguy hiểm (`confidence >= 0.80`): Tự động khởi tạo phiên cảnh báo nguy cơ cao.

### 🛡️ B. Quy trình Safety Check tự động kích hoạt SOS
1. Người dùng khởi tạo Safety Check với thời gian hẹn (ví dụ: 15 phút khi đi taxi).
2. `safety_check_scheduler` chạy ngầm định kỳ (Background Worker) quét các phiên đến hạn.
3. Nếu hết giờ mà người dùng không bấm "Tôi an toàn":
   - Bước đệm: Cho phép thời gian ân hạn 60 giây (Grace Period).
   - Nếu vẫn im lặng: Tự động chuyển đổi Safety Check thành **Active SOS Session**.
   - Ngay lập tức gửi thông báo khẩn cấp tới danh bạ người thân kèm vị trí cuối cùng ghi nhận được.

### 🤫 C. Cơ chế Safe PIN vs Duress PIN (Chống cưỡng bức)
* **Safe PIN:** Khi nhập đúng mã Safe PIN, phiên SOS kết thúc an toàn, hệ thống ghi nhận `cancelled_via: "SAFE_PIN"`.
* **Duress PIN:** Khi bị hung thủ ép hủy SOS, nạn nhân nhập Duress PIN. Hệ thống sẽ:
  - Trả về phản hồi thành công để ứng dụng đóng giao diện cảnh báo (đánh lừa hung thủ).
  - Ngầm ghi nhận trạng thái `cancelled_via: "DURESS_PIN"`.
  - Kích hoạt cảnh báo ngầm mức độ đỏ: *"Nạn nhân đang bị khống chế, vừa mở khóa bằng mã cưỡng bức!"* và chuyển ngay tới người thân.

---

## 📡 5. Danh mục Endpoints chính (API Reference)

### 🔹 Health & System
* `GET /health` — Kiểm tra trạng thái Firestore DB và tính sẵn sàng của mô hình AI YAMNet.
* `GET /` hoặc `GET /api-info` — Thông tin phiên bản, môi trường và tài liệu Swagger.
* `GET /docs` — Giao diện Swagger UI tương tác trực tiếp.

### 🔹 Authentication & Security
* `POST /api/v1/auth/register` — Đăng ký tài khoản người dùng mới.
* `POST /api/v1/auth/login` — Đăng nhập hệ thống, cấp Access Token & Refresh Token.
* `PUT /api/v1/users/me/pins` — Cập nhật Safe PIN và Duress PIN (Mã hóa Bcrypt).

### 🔹 Detection & Audio AI
* `POST /api/v1/detection/analyze-audio` — Phân tích đoạn âm thanh bằng YAMNet ONNX Engine.
* `GET /api/v1/detection/events` — Lịch sử các sự kiện âm thanh phát hiện nguy hiểm.

### 🔹 Emergency & SOS
* `POST /api/v1/emergency/sos` — Kích hoạt SOS khẩn cấp tức thì.
* `POST /api/v1/emergency/active/cancel` — Hủy SOS bằng Safe PIN hoặc Duress PIN.
* `GET /api/v1/emergency/active` — Truy vấn phiên SOS đang hoạt động.

### 🔹 Safety Check
* `POST /api/v1/safety-check/start` — Khởi tạo đếm ngược an toàn theo template hoặc tự do.
* `POST /api/v1/safety-check/instances/{id}/confirm-safe` — Xác nhận an toàn đúng giờ.
* `POST /api/v1/safety-check/instances/{id}/extend` — Gia hạn thời gian đếm ngược.
* `GET /api/v1/safety-check/templates` — Danh sách các mẫu lịch trình an toàn định sẵn.

### 🔹 Contacts & Medical
* `GET /api/v1/contacts` / `POST /api/v1/contacts` — Quản lý danh bạ người thân ưu tiên.
* `GET /api/v1/users/me/medical` / `PUT /api/v1/users/me/medical` — Quản lý hồ sơ y tế cứu sinh.

---

## 🚀 6. Hướng dẫn cài đặt & Triển khai

### Khởi chạy môi trường Local
```bash
# 1. Di chuyển vào thư mục backend
cd backend

# 2. Tạo virtualenv & kích hoạt
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

# 3. Cài đặt toàn bộ thư viện
pip install -r requirements.txt

# 4. Sao chép và cấu hình biến môi trường
cp .env.example .env
# Chỉnh sửa thông số Firebase, Telegram trong .env

# 5. Khởi chạy server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Triển khai Cloud (Render / Railway / Docker)
* **Root Directory:** `backend`
* **Build Command:** `pip install -r requirements.txt`
* **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
* **Health Check Path:** `/health`
* **Secret Files:** Tải file `firebase-service-account.json` lên mục Secret Files của Render.

---

## 🔒 7. Bảo mật & Cam kết toàn vẹn dữ liệu
* **Zero Secret Leakage:** Tuyệt đối không commit file `.env` hay file JSON Service Account private key lên Git (đã kiểm định qua `.gitignore` chặt chẽ).
* **Bcrypt Protection:** Mã Safe PIN và Duress PIN được băm với salt ngẫu nhiên, không thể đảo ngược ngay cả khi dữ liệu bị trích xuất.
* **HTTP Security Headers:** Tích hợp sẵn `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`.

---
*© 2026 Guardian AI Team — Đồng hành bảo vệ an toàn cho mọi hành trình.*
