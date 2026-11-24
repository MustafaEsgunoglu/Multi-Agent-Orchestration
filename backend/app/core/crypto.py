"""AES-256-GCM envelope encryption for BYOK LLM API keys and MCP auth headers.

Security guarantees:
- 256-bit symmetric key loaded from MASTER_ENCRYPTION_KEY.
- Fresh 96-bit (12-byte) CSPRNG nonce per encryption call.
- Optional Associated Authenticated Data (AAD), such as tenant_id, binds ciphertext
  to its owning tenant so encrypted blobs cannot be replayed across tenants.
- Never logs decrypted secrets or raw key material.
"""

from __future__ import annotations

import base64
import binascii
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings

TOKEN_VERSION_PREFIX = "v1:"
NONCE_SIZE_BYTES = 12
AES_256_KEY_BYTES = 32


class CryptoError(ValueError):
    """Raised when encryption key configuration or decryption/authentication fails."""


def _parse_master_key(raw_key: str) -> bytes:
    """Decode a 32-byte master key from 64-char hex or URL-safe base64."""
    cleaned = raw_key.strip()
    if len(cleaned) == 64:
        try:
            key = bytes.fromhex(cleaned)
            if len(key) == AES_256_KEY_BYTES:
                return key
        except ValueError:
            pass

    try:
        padded = cleaned + "=" * (-len(cleaned) % 4)
        key = base64.urlsafe_b64decode(padded.encode("ascii"))
    except (binascii.Error, UnicodeEncodeError) as exc:
        raise CryptoError("MASTER_ENCRYPTION_KEY must be valid base64 or 64-char hex.") from exc

    if len(key) != AES_256_KEY_BYTES:
        raise CryptoError(
            f"MASTER_ENCRYPTION_KEY must decode to exactly {AES_256_KEY_BYTES} bytes."
        )
    return key


class SecretCipher:
    """Stateless AES-256-GCM cipher wrapper."""

    def __init__(self, master_key: str) -> None:
        self._aesgcm = AESGCM(_parse_master_key(master_key))

    def encrypt(self, plaintext: str, aad: str | None = None) -> str:
        """Encrypt UTF-8 plaintext into a versioned base64 token."""
        if not plaintext:
            raise CryptoError("Cannot encrypt empty secret.")
        nonce = os.urandom(NONCE_SIZE_BYTES)
        aad_bytes = aad.encode("utf-8") if aad is not None else None
        ciphertext = self._aesgcm.encrypt(nonce, plaintext.encode("utf-8"), aad_bytes)
        payload = base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")
        return f"{TOKEN_VERSION_PREFIX}{payload}"

    def decrypt(self, token: str, aad: str | None = None) -> str:
        """Decrypt and authenticate a versioned base64 token."""
        if not token.startswith(TOKEN_VERSION_PREFIX):
            raise CryptoError("Unsupported encrypted token format.")
        encoded = token[len(TOKEN_VERSION_PREFIX) :]
        try:
            raw = base64.urlsafe_b64decode(encoded.encode("ascii"))
        except (binascii.Error, UnicodeEncodeError) as exc:
            raise CryptoError("Corrupted encrypted token encoding.") from exc

        if len(raw) <= NONCE_SIZE_BYTES + 16:
            raise CryptoError("Encrypted token payload is too short.")

        nonce = raw[:NONCE_SIZE_BYTES]
        ciphertext = raw[NONCE_SIZE_BYTES:]
        aad_bytes = aad.encode("utf-8") if aad is not None else None
        try:
            plaintext = self._aesgcm.decrypt(nonce, ciphertext, aad_bytes)
        except InvalidTag as exc:
            raise CryptoError("Secret authentication failed (invalid key, AAD, or tampered data).") from exc

        return plaintext.decode("utf-8")


def get_cipher() -> SecretCipher:
    """Build a SecretCipher from application settings."""
    return SecretCipher(get_settings().master_encryption_key)


def encrypt_secret(plaintext: str, aad: str | None = None) -> str:
    return get_cipher().encrypt(plaintext, aad=aad)


def decrypt_secret(token: str, aad: str | None = None) -> str:
    return get_cipher().decrypt(token, aad=aad)


def mask_secret(secret: str) -> str:
    """Return a non-sensitive display hint (e.g., 'sk-...9f2a') without exposing the secret."""
    if len(secret) <= 8:
        return "****"
    return f"{secret[:3]}...{secret[-4:]}"
