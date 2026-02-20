"""
AES-256-CBC encryption and HMAC-SHA256 authentication for ASP protocol.

Uses pycryptodome. Keys loaded from Django settings:
  - ASP_AES_KEY: 64 hex chars (32 bytes)
  - ASP_HMAC_KEY: 64 hex chars (32 bytes)
"""

import hmac
import hashlib
import os

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad


# ---------------------------------------------------------------------------
#  Key helpers
# ---------------------------------------------------------------------------

def _bytes_from_hex(hex_str: str) -> bytes:
    """Convert hex string to bytes. Accepts 64-char hex → 32 bytes."""
    return bytes.fromhex(hex_str)


def get_keys() -> tuple[bytes, bytes]:
    """Return (aes_key, hmac_key) from Django settings."""
    from django.conf import settings
    aes_key = _bytes_from_hex(settings.ASP_AES_KEY)
    hmac_key = _bytes_from_hex(settings.ASP_HMAC_KEY)
    if len(aes_key) != 32:
        raise ValueError(f"ASP_AES_KEY must be 32 bytes, got {len(aes_key)}")
    if len(hmac_key) != 32:
        raise ValueError(f"ASP_HMAC_KEY must be 32 bytes, got {len(hmac_key)}")
    return aes_key, hmac_key


# ---------------------------------------------------------------------------
#  AES-256-CBC
# ---------------------------------------------------------------------------

def encrypt(plaintext: bytes, aes_key: bytes) -> bytes:
    """
    Encrypt plaintext with AES-256-CBC.

    Returns: IV (16 bytes) + ciphertext
    """
    iv = os.urandom(16)
    cipher = AES.new(aes_key, AES.MODE_CBC, iv)
    ciphertext = cipher.encrypt(pad(plaintext, AES.block_size))
    return iv + ciphertext


def decrypt(encrypted: bytes, aes_key: bytes) -> bytes:
    """
    Decrypt IV-prefixed ciphertext with AES-256-CBC.

    Input: IV (16 bytes) + ciphertext
    Returns: plaintext bytes
    Raises: ValueError on padding or decryption failure.
    """
    if len(encrypted) < 32:  # 16 IV + 16 min ciphertext block
        raise ValueError("Encrypted data too short")
    iv = encrypted[:16]
    ciphertext = encrypted[16:]
    cipher = AES.new(aes_key, AES.MODE_CBC, iv)
    return unpad(cipher.decrypt(ciphertext), AES.block_size)


# ---------------------------------------------------------------------------
#  HMAC-SHA256
# ---------------------------------------------------------------------------

def sign(data: bytes, hmac_key: bytes) -> bytes:
    """Compute HMAC-SHA256 tag (32 bytes) over data."""
    return hmac.new(hmac_key, data, hashlib.sha256).digest()


def verify(data: bytes, tag: bytes, hmac_key: bytes) -> bool:
    """Verify HMAC-SHA256 tag. Returns True if valid."""
    expected = hmac.new(hmac_key, data, hashlib.sha256).digest()
    return hmac.compare_digest(expected, tag)
