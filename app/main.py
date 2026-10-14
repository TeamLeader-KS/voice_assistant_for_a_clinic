from fastapi import FastAPI

from app.api import health
from app.config import settings
from app.core.logging import setup_logging

setup_logging("DEBUG" if settings.DEBUG else "INFO")

app = FastAPI(title=settings.APP_NAME)
app.include_router(health.router)


@app.get("/")
async def root():
    return {"status": "ok", "app": settings.APP_NAME}