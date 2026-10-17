import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health, demo, voice_routes
from app.config import settings
from app.core.logging import setup_logging
from app.voice.audio_server import AudioServer


setup_logging("DEBUG" if settings.DEBUG else "INFO")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Запуск фоновых задач при старте приложения."""
    task = asyncio.create_task(AudioServer().start())
    yield
    task.cancel()


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

app.include_router(health.router)
app.include_router(demo.router)
app.include_router(voice_routes.router)


@app.get("/")
async def root():
    return {"status": "ok", "app": settings.APP_NAME}