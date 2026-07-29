import uuid
from dataclasses import dataclass

from zeromind.rsshub.credentials import CredentialCipher
from zeromind.rsshub.domain import (
    RSSHubAuthenticationMode,
    RSSHubInstance,
    RSSHubInstanceInUseError,
)
from zeromind.rsshub.repository import RSSHubInstanceRepository


@dataclass(frozen=True, slots=True)
class _AccessKeyUnchanged:
    pass


ACCESS_KEY_UNCHANGED = _AccessKeyUnchanged()


class RSSHubInstanceService:
    def __init__(
        self,
        repository: RSSHubInstanceRepository,
        cipher: CredentialCipher,
    ) -> None:
        self._repository = repository
        self._cipher = cipher

    async def create(
        self,
        *,
        name: str,
        base_url: str,
        access_key: str | None = None,
        authentication_mode: RSSHubAuthenticationMode = RSSHubAuthenticationMode.KEY,
        enabled: bool = True,
    ) -> RSSHubInstance:
        active = enabled and await self._repository.get_active() is None
        encrypted_access_key = self._cipher.encrypt(access_key) if access_key else None
        instance = RSSHubInstance.create(
            name=name,
            base_url=base_url,
            encrypted_access_key=encrypted_access_key,
            authentication_mode=authentication_mode,
            enabled=enabled,
            active=active,
        )
        await self._repository.add(instance)
        return instance

    async def get(self, instance_id: uuid.UUID) -> RSSHubInstance:
        instance = await self._repository.get(instance_id)
        if instance is None:
            raise KeyError(instance_id)
        return instance

    async def list(self) -> tuple[RSSHubInstance, ...]:
        return await self._repository.list()

    async def get_active(self) -> RSSHubInstance | None:
        return await self._repository.get_active()

    async def update(
        self,
        instance_id: uuid.UUID,
        *,
        name: str,
        base_url: str,
        authentication_mode: RSSHubAuthenticationMode,
        enabled: bool,
        access_key: str | None | _AccessKeyUnchanged = ACCESS_KEY_UNCHANGED,
    ) -> RSSHubInstance:
        instance = await self.get(instance_id)
        if instance.active and not enabled:
            raise RSSHubInstanceInUseError("active RSSHub instance cannot be disabled")
        encrypted_access_key = instance.encrypted_access_key
        if not isinstance(access_key, _AccessKeyUnchanged):
            encrypted_access_key = self._cipher.encrypt(access_key) if access_key else None
        instance.update(
            name=name,
            base_url=base_url,
            encrypted_access_key=encrypted_access_key,
            authentication_mode=authentication_mode,
            enabled=enabled,
        )
        await self._repository.save(instance)
        return instance

    async def activate(self, instance_id: uuid.UUID) -> RSSHubInstance:
        instance = await self.get(instance_id)
        if not instance.enabled:
            raise ValueError("disabled RSSHub instance cannot be activated")
        await self._repository.activate(instance_id)
        return await self.get(instance_id)

    async def delete(self, instance_id: uuid.UUID) -> None:
        instance = await self.get(instance_id)
        if instance.active:
            raise RSSHubInstanceInUseError("active RSSHub instance cannot be deleted")
        await self._repository.delete(instance_id)
