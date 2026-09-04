import os

from alembic.config import Config


def apply_database_url(config: Config) -> None:
    database_url = os.getenv("ZEROMIND_DATABASE_URL")
    if database_url:
        config.set_main_option("sqlalchemy.url", database_url)
