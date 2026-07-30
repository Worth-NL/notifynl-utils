import base64

import pytest
from cryptography.fernet import Fernet, InvalidToken

from notifications_utils.clients.encryption.encryption_client import Encryption


@pytest.fixture()
def encryption_client(app):
    client = Encryption()

    app.config["ENCRYPTION_SECRET_KEY"] = Fernet.generate_key()

    client.init_app(app)

    return client


def test_should_encrypt_content(encryption_client):
    assert encryption_client.encrypt("900285709") != "900285709"


def test_should_decrypt_content(encryption_client):
    encrypted = encryption_client.encrypt("900285709")
    assert encryption_client.decrypt(encrypted) == "900285709"


def test_encrypted_content_is_not_recoverable_by_base64_decoding(encryption_client):
    # This is the exact defect this client fixes: Signing's output could be
    # base64-decoded straight back to the plaintext with no key needed at all.
    encrypted = encryption_client.encrypt("900285709")
    raw = base64.urlsafe_b64decode(encrypted)
    assert b"900285709" not in raw


def test_decrypt_raises_on_tampered_or_invalid_ciphertext(encryption_client):
    with pytest.raises(InvalidToken):
        encryption_client.decrypt("not-a-real-token")
