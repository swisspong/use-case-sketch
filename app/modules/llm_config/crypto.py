"""Encryption at rest for API keys (Fernet: AES-128-CBC + HMAC-SHA256, random IV per call)."""

import base64
import hashlib

from cryptography.fernet import Fernet


class ApiKeyCipher:
    def __init__(self, secret: str):
        # any long random string works as the secret; Fernet needs exactly 32 url-safe base64 bytes
        self._fernet = Fernet(
            base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
        )

    def encrypt(self, plain: str) -> str:
        return self._fernet.encrypt(plain.encode()).decode()

    def decrypt(self, token: str) -> str:
        return self._fernet.decrypt(token.encode()).decode()
