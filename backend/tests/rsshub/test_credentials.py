import pytest

from zeromind.rsshub.credentials import CredentialCipher


def test_credential_cipher_round_trips_without_storing_plaintext() -> None:
    cipher = CredentialCipher("test-credential-secret")

    encrypted = cipher.encrypt("rsshub-secret")

    assert encrypted != "rsshub-secret"
    assert "rsshub-secret" not in encrypted
    assert cipher.decrypt(encrypted) == "rsshub-secret"


def test_credential_cipher_rejects_empty_application_secret() -> None:
    with pytest.raises(ValueError, match="credential secret"):
        CredentialCipher(" ")
