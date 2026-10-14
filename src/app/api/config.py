from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    redis_url: str = "redis://localhost:6379/0"
    mss_base_url: str = "https://crm-med-mock.dbi-testing.ru/api/v1"
    mss_token: str = ""
    schedule_path: str = "data/schedule.xlsx"

settings = Settings()