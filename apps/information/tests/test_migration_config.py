from alembic.config import Config

from zeromind.shared.migration_config import apply_database_url


def test_environment_database_url_overrides_alembic_ini(monkeypatch) -> None:
    monkeypatch.setenv(
        "ZEROMIND_DATABASE_URL",
        "postgresql+psycopg://zeromind:secret@postgres:5432/zeromind",
    )
    config = Config()
    config.set_main_option(
        "sqlalchemy.url",
        "postgresql+psycopg://zeromind:zeromind@localhost:5432/zeromind",
    )

    apply_database_url(config)

    assert config.get_main_option("sqlalchemy.url") == (
        "postgresql+psycopg://zeromind:secret@postgres:5432/zeromind"
    )
