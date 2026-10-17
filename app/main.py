# # from fastapi import FastAPI
# #
# # from app.api import health, demo
# # from app.config import settings
# # from app.core.logging import setup_logging
# #
# # setup_logging("DEBUG" if settings.DEBUG else "INFO")
# #
# # app = FastAPI(title=settings.APP_NAME)
# # app.include_router(health.router)
# # app.include_router(demo.router)
# #
# #
# # @app.get("/")
# # async def root():
# #     return {"status": "ok", "app": settings.APP_NAME}
#
# from fastapi import FastAPI
#
# from app.api import health, demo
# from app.api import voice_routes
# from app.config import settings
# from app.core.logging import setup_logging
#
# setup_logging("DEBUG" if settings.DEBUG else "INFO")
#
# app = FastAPI(title=settings.APP_NAME)
#
# app.include_router(health.router)
# app.include_router(demo.router)
# app.include_router(voice_routes.router)   # ← теперь /synthesize доступен
#
#
# @app.get("/")
# async def root():
#     return {"status": "ok", "app": settings.APP_NAME}

    # from fastapi import FastAPI
    #
    # from app.api import health, demo, voice_routes
    # from app.config import settings
    # from app.core.logging import setup_logging
    # from app.voice.audio_server import AudioServer
    # import asyncio
    #
    # import asyncio
    # from contextlib import asynccontextmanager
    # from fastapi import FastAPI
    #
    # from app.config import settings
    # from app.api.voice_routes import router as voice_router
    # from app.voice.audio_server import AudioServer
    # setup_logging("DEBUG" if settings.DEBUG else "INFO")
    #
    # app = FastAPI(title=settings.APP_NAME)
    #
    # app.include_router(health.router)
    # app.include_router(demo.router)
    # app.include_router(voice_routes.router)
    #
    #
    # @app.get("/")
    # async def root():
    #     return {"status": "ok", "app": settings.APP_NAME}
    #
    #
    #
    # @app.on_event("startup")
    # async def start_audio_server():
    #     asyncio.create_task(AudioServer().start())

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
    # WebSocket-сервер для Asterisk
    task = asyncio.create_task(AudioServer().start())
    yield
    # Корректное завершение при остановке
    task.cancel()


app = FastAPI(title=settings.APP_NAME, lifespan=lifespan)

app.include_router(health.router)
app.include_router(demo.router)
app.include_router(voice_routes.router)


@app.get("/")
async def root():
    return {"status": "ok", "app": settings.APP_NAME}
