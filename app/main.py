"""
=============================================================================
FILE: app/main.py
MODULE: Root Application Entrypoint
ROLE / RESPONSIBILITY:
    - Khởi tạo ứng dụng FastAPI cho Guardian AI backend.
    - Cấu hình lifespan (startup / shutdown): khởi tạo logging, Firebase Admin SDK, R2 client.
    - Cấu hình CORS middleware, gắn exception handlers chuẩn hóa.
    - Cung cấp health check endpoint (/health) và root endpoint (/).
    - Nơi đăng ký toàn bộ routers từ các modules con.

CONNECTIONS / DEPENDENCIES:
    - app/core/config.py (get_settings)
    - app/core/logging.py (setup_logging, logger)
    - app/core/exceptions.py (register_exception_handlers)
    - app/infrastructure/firestore/client.py (init_firebase, check_firestore_connection)
    - app/infrastructure/storage/r2/client.py (get_r2_client, check_connection)

INPUT / OUTPUT:
    - Input: HTTP / WebSocket requests từ client (Flutter app).
    - Output: JSON responses, WebSocket messages.
=============================================================================
"""

from contextlib import asynccontextmanager
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator, Dict, Any

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging, logger
from app.infrastructure.firestore.client import init_firebase, check_firestore_connection
from app.modules.auth.router import router as auth_router
from app.modules.contacts.router import router as contacts_router
from app.modules.detection.router import router as detection_router
from app.modules.detection.alerts.service import alert_worker
from app.modules.emergency.router import router as emergency_router
from app.modules.emergency.safety_check.router import router as safety_check_router
from app.modules.emergency.safety_check.scheduler import safety_check_scheduler
from app.modules.location.router import router as location_router
from app.modules.notifications.router import router as notifications_router
from app.modules.recordings.router import router as recordings_router
from app.modules.users.router import router as users_router
from app.realtime.router import router as realtime_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Quản lý vòng đời khởi động và kết thúc của ứng dụng FastAPI."""
    settings = get_settings()
    setup_logging()
    logger.info(f"Đang khởi động {settings.APP_NAME} v{settings.APP_VERSION} (Env: {settings.APP_ENV})...")

    # Khởi tạo kết nối hạ tầng
    try:
        init_firebase()
        logger.info("Firebase Admin SDK sẵn sàng.")
    except Exception as e:
        logger.error(f"Khởi tạo Firebase thất bại lúc startup: {str(e)}")

    # Khởi động worker kiểm tra Safety Check định kỳ
    safety_check_scheduler.start()
    alert_worker.start()

    yield

    # Dừng worker khi tắt ứng dụng
    safety_check_scheduler.stop()
    await safety_check_scheduler.wait_stopped()
    await alert_worker.stop()
    logger.info(f"Đang dừng {settings.APP_NAME}...")


def create_app() -> FastAPI:
    """Factory function tạo và cấu hình FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Backend API cho ứng dụng an toàn cá nhân Guardian AI.",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    # 1. Đăng ký Exception Handlers chuẩn hóa
    register_exception_handlers(app)

    # 2. Cấu hình CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 2.1. Thêm HTTP Security Headers (Chống Clickjacking, MIME-sniffing, XSS)
    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        return response

    # 3. Root Endpoint
    @app.get("/api-info", tags=["General"])
    @app.get("/", tags=["General"])
    async def root() -> Dict[str, Any]:
        return {
            "name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "environment": settings.APP_ENV,
            "status": "online",
            "docs_url": "/docs",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    # 4. Health Check Endpoint
    @app.get("/health", tags=["Health"])
    async def health_check() -> JSONResponse:
        firestore_healthy = await asyncio.to_thread(check_firestore_connection)
        from app.modules.detection.router import detection_service
        audio_ready = detection_service.yamnet.is_available()

        is_healthy = firestore_healthy and audio_ready
        status_code = status.HTTP_200_OK if is_healthy else status.HTTP_503_SERVICE_UNAVAILABLE

        return JSONResponse(
            status_code=status_code,
            content={
                "status": "healthy" if is_healthy else "degraded",
                "version": settings.APP_VERSION,
                "environment": settings.APP_ENV,
                "services": {
                    "firestore": "healthy" if firestore_healthy else "unhealthy",
                    "audio_model": "ready" if audio_ready else "unavailable",
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    # 5. Đăng ký Feature Routers
    app.include_router(auth_router, prefix=f"{settings.API_V1_PREFIX}/auth", tags=["Authentication"])
    app.include_router(users_router, prefix=f"{settings.API_V1_PREFIX}/users", tags=["Users"])
    app.include_router(contacts_router, prefix=f"{settings.API_V1_PREFIX}/contacts", tags=["Emergency Contacts"])
    app.include_router(notifications_router, prefix=f"{settings.API_V1_PREFIX}/notifications", tags=["Notifications"])
    app.include_router(recordings_router, prefix=f"{settings.API_V1_PREFIX}/recordings", tags=["Recordings"])
    app.include_router(location_router, prefix=f"{settings.API_V1_PREFIX}/location", tags=["Location Checkpoints"])
    app.include_router(realtime_router, prefix=f"{settings.API_V1_PREFIX}/realtime", tags=["Real-time Stream"])
    app.include_router(emergency_router, prefix=f"{settings.API_V1_PREFIX}/emergency", tags=["Emergency Core Workflow"])
    app.include_router(safety_check_router, prefix=f"{settings.API_V1_PREFIX}/safety-check", tags=["Safety Check Timer"])
    app.include_router(detection_router, prefix=f"{settings.API_V1_PREFIX}/detection", tags=["AI Audio Detection"])

    # 6. Mount Frontend Web SPA nếu đã build
    frontend_web_dir = Path(__file__).resolve().parent.parent.parent / "frontend" / "build" / "web"
    if frontend_web_dir.exists():
        app.mount("/", StaticFiles(directory=str(frontend_web_dir), html=True), name="frontend")
        logger.info(f"Đã mount Frontend Web SPA từ: {frontend_web_dir}")

    return app


# Instance app chạy bởi Uvicorn (uvicorn app.main:app)
app = create_app()


