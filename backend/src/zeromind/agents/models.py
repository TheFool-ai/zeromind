import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from zeromind.shared.models import Base


class ProviderProfileModel(Base):
    __tablename__ = "provider_profiles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    provider: Mapped[str] = mapped_column(String(120), nullable=False)
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    api_key_env: Mapped[str] = mapped_column(String(255), nullable=False)
    thinking_level: Mapped[str] = mapped_column(String(20), nullable=False)
    parameters: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AgentDefinitionModel(Base):
    __tablename__ = "agent_definitions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(String(1000), nullable=False)
    capabilities: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    provider_profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("provider_profiles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    input_schema: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    output_schema: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

