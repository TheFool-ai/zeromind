from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="ZEROMIND_",
        extra="ignore",
    )

    environment: str = "development"
    database_url: str = "sqlite+aiosqlite:///./data/zeromind.db"
    redis_url: str = "redis://localhost:6379/0"
    pi_command: str = "node /app/pi-runner/dist/main.js"
    admin_username: str = "admin"
    admin_password: str = Field(default="change-me", repr=False)
    token_secret: str = Field(default="development-only-secret", repr=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()

