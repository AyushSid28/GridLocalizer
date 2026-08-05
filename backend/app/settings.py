from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://outage:outage@localhost:5432/outage"
    redis_url: str = "redis://localhost:6379/0"
    telemetry_stream: str = "telemetry.inbound"
    detect_wait_sec: int = 3
    expose_error_details: bool = False
    cors_origins: str = (
        "http://localhost:5173,http://localhost:3000,"
        "https://gridlocalizer.vercel.app,https://www.gridlocalizer.vercel.app"
    )
    openai_api_key: str = ""
    groq_api_key: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
