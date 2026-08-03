from cryptography.fernet import Fernet


class Encryption:
    """
    This class is used to encrypt and decrypt sensitive values (e.g. BSNs).

    Unlike notifications_utils.clients.signing.Signing, this genuinely encrypts
    data (Fernet/AES) -- ciphertext cannot be read without the secret key, not
    just base64-decoded.
    """

    def init_app(self, app):
        self.fernet = Fernet(app.config.get("ENCRYPTION_SECRET_KEY"))

    def encrypt(self, plaintext: str) -> str:
        return self.fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        return self.fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
