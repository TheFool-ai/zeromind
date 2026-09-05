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
    rsshub_private_hosts: str = ""
    pi_command: str = "node /app/pi-runner/dist/main.js"
    credential_secret: str = Field(
        default="development-only-credential-secret",
        repr=False,
    )

    @property
    def rsshub_private_hostnames(self) -> frozenset[str]:
        return frozenset(
            normalized
            for item in self.rsshub_private_hosts.split(",")
            if (normalized := item.strip().lower().rstrip("."))
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
