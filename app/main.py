<<<<<<< HEAD
<<<<<<< HEAD
from fastapi import FastAPI

from app.api import health, demo
from app.config import settings
from app.core.logging import setup_logging

setup_logging("DEBUG" if settings.DEBUG else "INFO")

app = FastAPI(title=settings.APP_NAME)
app.include_router(health.router)
app.include_router(demo.router)


@app.get("/")
async def root():
    return {"status": "ok", "app": settings.APP_NAME}
=======
=======
>>>>>>> origin/develop
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

from fastapi import FastAPI

from app.api import health, demo, voice_routes
from app.config import settings
from app.core.logging import setup_logging

setup_logging("DEBUG" if settings.DEBUG else "INFO")

app = FastAPI(title=settings.APP_NAME)

app.include_router(health.router)
app.include_router(demo.router)
app.include_router(voice_routes.router)


@app.get("/")
async def root():
    return {"status": "ok", "app": settings.APP_NAME}
>>>>>>> origin/develop
