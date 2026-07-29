from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from zeromind.agents.models import (  # noqa: F401
    AgentDefinitionModel,
    ProviderProfileModel,
)
from zeromind.ingestion.models import (  # noqa: F401
    ContentReferenceModel,
    ReferenceRevisionModel,
)
from zeromind.shared.models import Base
from zeromind.subscriptions.models import SubscriptionModel  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
