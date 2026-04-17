"""
FastAPI admin API uygulaması.
Manuel draft onaylama, kuyruk yönetimi, analytics görüntüleme.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from prometheus_client import make_asgi_app

from aitopiahub.api.routers import analytics, drafts, queue, health, monetization
from aitopiahub.core.config import get_settings
from aitopiahub.core.logging import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Aitopiahub Admin API",
        description="Instagram bot yönetim paneli",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(health.router, tags=["Health"])
    app.include_router(queue.router, prefix="/api/v1", tags=["Queue"])
    app.include_router(drafts.router, prefix="/api/v1", tags=["Drafts"])
    app.include_router(analytics.router, prefix="/api/v1", tags=["Analytics"])
    app.include_router(monetization.router, prefix="/api/v1", tags=["Monetization"])

    # Prometheus metrics endpoint
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)

    # Local storage'ı public olarak servis et
    images_dir = Path(settings.storage_local_path).resolve()
    images_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/images", StaticFiles(directory=str(images_dir)), name="images")

    videos_dir = Path("./data/videos").resolve()
    videos_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/videos", StaticFiles(directory=str(videos_dir)), name="videos")

    return app


app = create_app()
