from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "voice-assistant-clinic"
    DEBUG: bool = False

    DATABASE_URL: str = "postgresql+asyncpg://user:pass@db:5432/clinic"
    REDIS_URL: str = "redis://redis:6379/0"

    MIS_MODE: str = "mock"  # mock | real
    MIS_BASE_URL: str = "https://crm-med-mock.dbi-testing.ru/api/v1"
    MIS_TOKEN: str = ""

    # Расписание врачей
    SCHEDULE_XLSX_PATH: str = "data/schedule.xlsx"
    SCHEDULE_TODAY: str = "14.10.2026"  # пусто → берём datetime.now()

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()