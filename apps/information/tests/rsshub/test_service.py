import pytest

from zeromind.rsshub.credentials import CredentialCipher
from zeromind.rsshub.domain import (
    DuplicateRSSHubInstanceError,
    RSSHubAuthenticationMode,
    RSSHubInstanceInUseError,
)
from zeromind.rsshub.repository import InMemoryRSSHubInstanceRepository
from zeromind.rsshub.service import RSSHubInstanceService


def make_service() -> RSSHubInstanceService:
    return RSSHubInstanceService(
        InMemoryRSSHubInstanceRepository(),
        CredentialCipher("test-credential-secret"),
    )


@pytest.mark.asyncio
async def test_first_enabled_instance_becomes_active_and_activation_moves_default() -> None:
    service = make_service()
    first = await service.create(
        name="Primary",
        base_url="https://rsshub.example.com",
        access_key="secret",
    )
    second = await service.create(
        name="Backup",
        base_url="https://backup.example.com",
    )

    activated = await service.activate(second.id)

    assert first.active is True
    assert second.active is False
    assert activated.active is True
    assert (await service.get(first.id)).active is False


@pytest.mark.asyncio
async def test_service_encrypts_and_preserves_or_clears_access_key() -> None:
    service = make_service()
    created = await service.create(
        name="Primary",
        base_url="https://rsshub.example.com",
        access_key="secret",
    )
    assert created.encrypted_access_key is not None
    assert "secret" not in created.encrypted_access_key

    preserved = await service.update(
        created.id,
        name="Primary",
        base_url="https://rsshub.example.com",
        authentication_mode=RSSHubAuthenticationMode.CODE,
        enabled=True,
    )
    assert preserved.encrypted_access_key == created.encrypted_access_key

    cleared = await service.update(
        created.id,
        name="Primary",
        base_url="https://rsshub.example.com",
        authentication_mode=RSSHubAuthenticationMode.CODE,
        enabled=True,
        access_key=None,
    )
    assert cleared.encrypted_access_key is None


@pytest.mark.asyncio
async def test_active_instance_cannot_be_disabled_or_deleted() -> None:
    service = make_service()
    active = await service.create(
        name="Primary",
        base_url="https://rsshub.example.com",
    )

    with pytest.raises(RSSHubInstanceInUseError):
        await service.update(
            active.id,
            name="Primary",
            base_url="https://rsshub.example.com",
            authentication_mode=RSSHubAuthenticationMode.KEY,
            enabled=False,
        )
    with pytest.raises(RSSHubInstanceInUseError):
        await service.delete(active.id)


@pytest.mark.asyncio
async def test_duplicate_name_and_base_url_are_rejected() -> None:
    service = make_service()
    await service.create(name="Primary", base_url="https://rsshub.example.com")

    with pytest.raises(DuplicateRSSHubInstanceError):
        await service.create(name="Primary", base_url="https://backup.example.com")
    with pytest.raises(DuplicateRSSHubInstanceError):
        await service.create(name="Backup", base_url="https://rsshub.example.com")


@pytest.mark.asyncio
async def test_disabled_instance_cannot_be_activated() -> None:
    service = make_service()
    disabled = await service.create(
        name="Disabled",
        base_url="https://rsshub.example.com",
        enabled=False,
    )

    with pytest.raises(ValueError, match="disabled"):
        await service.activate(disabled.id)
