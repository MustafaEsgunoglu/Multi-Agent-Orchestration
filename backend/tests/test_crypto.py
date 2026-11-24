"""Tests for AES-256-GCM BYOK secret encryption and tenant AAD binding."""

from __future__ import annotations

import base64
import secrets

import pytest

from app.core.crypto import CryptoError, SecretCipher, mask_secret


def _random_b64_key() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii")


def test_encrypt_decrypt_roundtrip_and_nonce_uniqueness() -> None:
    cipher = SecretCipher(_random_b64_key())
    secret = "sk-live-super-secret-api-key-1234567890"
    tenant_aad = "11111111-1111-1111-1111-111111111111"

    token_1 = cipher.encrypt(secret, aad=tenant_aad)
    token_2 = cipher.encrypt(secret, aad=tenant_aad)

    assert token_1 != token_2  # Fresh 96-bit nonce per call
    assert secret not in token_1
    assert cipher.decrypt(token_1, aad=tenant_aad) == secret
    assert cipher.decrypt(token_2, aad=tenant_aad) == secret


def test_hex_master_key_supported() -> None:
    hex_key = secrets.token_hex(32)
    cipher = SecretCipher(hex_key)
    token = cipher.encrypt("anthropic-key-xyz")
    assert cipher.decrypt(token) == "anthropic-key-xyz"


def test_cross_tenant_aad_mismatch_fails_decryption() -> None:
    cipher = SecretCipher(_random_b64_key())
    token = cipher.encrypt("sk-tenant-a-secret", aad="tenant-a")
    with pytest.raises(CryptoError):
        cipher.decrypt(token, aad="tenant-b")


def test_tampered_ciphertext_fails_authentication() -> None:
    cipher = SecretCipher(_random_b64_key())
    token = cipher.encrypt("sk-integrity-check")
    tampered = token[:-4] + ("AAAA" if not token.endswith("AAAA") else "BBBB")
    with pytest.raises(CryptoError):
        cipher.decrypt(tampered)


def test_wrong_key_fails_decryption() -> None:
    cipher_a = SecretCipher(_random_b64_key())
    cipher_b = SecretCipher(_random_b64_key())
    token = cipher_a.encrypt("sk-secret")
    with pytest.raises(CryptoError):
        cipher_b.decrypt(token)


def test_mask_secret_never_exposes_middle() -> None:
    assert mask_secret("sk-proj-1234567890abcdef") == "sk-...cdef"
    assert mask_secret("short") == "****"
