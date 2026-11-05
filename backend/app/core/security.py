"""Password hashing, JWT and AES-GCM credential encryption for DailyKeeper."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import Settings

_PBKDF2_ITERATIONS = 100_000
_SALT_BYTES = 16
_NONCE_BYTES = 12
_ENC_PREFIX = "enc1:"


def hash_password(password: str) -> str:
    """Hash a password with PBKDF2-SHA256.

    Returns the format ``pbkdf2_sha256$100000$<salt_hex>$<hash_hex>``.
    """
    salt = os.urandom(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS
    )
    return f"pbkdf2_sha256${_PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Verify a password against a stored ``pbkdf2_sha256$...`` hash."""
    try:
        algorithm, iterations, salt_hex, hash_hex = stored.split("$")
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    try:
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
        )
    except ValueError:
        return False
    return hmac.compare_digest(digest.hex(), hash_hex)


def create_access_token(subject: str, *, secret_key: str, expires_minutes: int) -> str:
    """Create a signed HS256 JWT with a ``sub`` claim and UTC ``exp``."""
    now = datetime.now(timezone.utc)
    payload = {"sub": subject, "exp": now + timedelta(minutes=expires_minutes)}
    return jwt.encode(payload, secret_key, algorithm="HS256")


def decode_token(token: str, *, secret_key: str) -> dict | None:
    """Decode and validate a JWT (including ``exp``).

    Returns the payload dict, or ``None`` when the token is invalid or expired.
    """
    try:
        return jwt.decode(token, secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


class CredentialCipher:
    """AES-256-GCM encryption for platform credentials stored in the DB.

    密钥派生说明：AES 密钥由 key_material 的 SHA-256 派生。这是面向开发的
    简化处理，对自托管单管理员工具而言是可接受的。
    """

    def __init__(self, key_material: str) -> None:
        key = hashlib.sha256(key_material.encode("utf-8")).digest()
        self._aesgcm = AESGCM(key)

    def encrypt_str(self, plaintext: str) -> str:
        """Encrypt a string into ``enc1:<urlsafe_base64(nonce + ciphertext)>``."""
        nonce = os.urandom(_NONCE_BYTES)
        ciphertext = self._aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
        return _ENC_PREFIX + base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")

    def decrypt_str(self, ciphertext: str) -> str:
        """Decrypt an ``enc1:`` string; raises ValueError when undecryptable."""
        try:
            raw = base64.urlsafe_b64decode(
                ciphertext.removeprefix(_ENC_PREFIX).encode("ascii")
            )
            nonce, encrypted = raw[:_NONCE_BYTES], raw[_NONCE_BYTES:]
            return self._aesgcm.decrypt(nonce, encrypted, None).decode("utf-8")
        except (InvalidTag, ValueError) as exc:
            raise ValueError(
                "凭据解密失败：加密密钥不匹配（ENCRYPTION_KEY/SECRET_KEY 变更后旧凭据无法解密）"
            ) from exc

    def encrypt_dict(self, data: dict) -> str:
        """Serialize a dict to JSON and encrypt it."""
        return self.encrypt_str(json.dumps(data, ensure_ascii=False))

    def decrypt_dict(self, ciphertext: str) -> dict:
        """Decrypt an ``enc1:`` string and parse it back into a dict."""
        return json.loads(self.decrypt_str(ciphertext))


def get_cipher(settings: Settings) -> CredentialCipher:
    """Build a cipher for the given settings.

    An empty ``encryption_key`` falls back to ``secret_key``.
    """
    return CredentialCipher(settings.encryption_key or settings.secret_key)


def random_token(nbytes: int = 32) -> str:
    """Return a URL-safe random token (for agent tokens, API keys, etc.)."""
    return secrets.token_urlsafe(nbytes)
