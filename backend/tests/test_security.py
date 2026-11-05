"""安全模块单元测试：密码哈希、JWT、AES-GCM 凭据加密与随机令牌。"""

from __future__ import annotations

import pytest

from app.core.security import (
    CredentialCipher,
    create_access_token,
    decode_token,
    hash_password,
    random_token,
    verify_password,
)


# ---------- 密码哈希 ----------


def test_password_hash_verify_roundtrip():
    stored = hash_password("s3cret-密码")
    assert stored.startswith("pbkdf2_sha256$")
    assert verify_password("s3cret-密码", stored) is True


def test_password_verify_wrong_password():
    stored = hash_password("correct-password")
    assert verify_password("wrong-password", stored) is False


def test_password_verify_malformed_hash():
    assert verify_password("whatever", "not-a-valid-hash") is False


# ---------- JWT ----------


def test_access_token_roundtrip():
    token = create_access_token("admin", secret_key="unit-test-key", expires_minutes=10)
    payload = decode_token(token, secret_key="unit-test-key")
    assert payload is not None
    assert payload["sub"] == "admin"


def test_access_token_wrong_secret():
    token = create_access_token("admin", secret_key="key-a", expires_minutes=10)
    assert decode_token(token, secret_key="key-b") is None


def test_access_token_expired():
    token = create_access_token("admin", secret_key="unit-test-key", expires_minutes=-1)
    assert decode_token(token, secret_key="unit-test-key") is None


# ---------- 凭据加密 ----------


def test_cipher_encrypt_dict_roundtrip():
    cipher = CredentialCipher("key-material-1")
    encrypted = cipher.encrypt_dict({"token": "sk-1234567890"})
    assert encrypted.startswith("enc1:")
    assert cipher.decrypt_dict(encrypted) == {"token": "sk-1234567890"}


def test_cipher_encrypt_str_roundtrip():
    cipher = CredentialCipher("key-material-1")
    encrypted = cipher.encrypt_str("cookie 值")
    assert encrypted.startswith("enc1:")
    assert cipher.decrypt_str(encrypted) == "cookie 值"


def test_cipher_wrong_key_raises():
    cipher = CredentialCipher("key-a")
    encrypted = cipher.encrypt_dict({"token": "sk-1234567890"})
    other = CredentialCipher("key-b")
    with pytest.raises(ValueError) as exc_info:
        other.decrypt_str(encrypted)
    assert "凭据解密失败" in str(exc_info.value)


def test_cipher_rejects_garbage():
    cipher = CredentialCipher("key-a")
    with pytest.raises(ValueError):
        cipher.decrypt_str("enc1:not-base64!!!")


# ---------- 随机令牌 ----------


def test_random_token():
    token = random_token()
    assert isinstance(token, str)
    assert len(token) > 0
    assert random_token() != random_token()
