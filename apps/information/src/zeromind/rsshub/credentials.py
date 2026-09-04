import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


class CredentialDecryptionError(ValueError):
    pass


class CredentialCipher:
    def __init__(self, secret: str) -> None:
        clean_secret = secret.strip()
        if not clean_secret:
            raise ValueError("credential secret is required")
        key = base64.urlsafe_b64encode(hashlib.sha256(clean_secret.encode()).digest())
        self._fernet = Fernet(key)

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode()).decode()
        except InvalidToken as error:
            raise CredentialDecryptionError("stored credential cannot be decrypted") from error
