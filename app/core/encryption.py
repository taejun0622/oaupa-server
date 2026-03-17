"""AES-256-GCM envelope encryption for the token vault.

Master key from env var encrypts per-row data encryption keys (DEKs).
Each DEK encrypts the actual token data. This enables key rotation
without re-encrypting all data at once.

Encrypted blob format:
  [1 byte: key_version_len][key_version bytes][12 bytes: nonce][ciphertext + 16 byte GCM tag]
"""

import base64
import os
import struct

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings

_KEY_VERSION = "v1"


def _get_master_key() -> bytes:
    raw = settings.oaupa_master_key
    if not raw:
        raise RuntimeError("OAUPA_MASTER_KEY is not set")
    key = base64.b64decode(raw)
    if len(key) != 32:
        raise RuntimeError("OAUPA_MASTER_KEY must be 32 bytes (base64-encoded)")
    return key


def encrypt(plaintext: str, key_version: str = _KEY_VERSION) -> bytes:
    master_key = _get_master_key()
    master_aes = AESGCM(master_key)

    # Generate a random DEK
    dek = os.urandom(32)
    dek_nonce = os.urandom(12)
    encrypted_dek = master_aes.encrypt(dek_nonce, dek, None)

    # Encrypt plaintext with DEK
    data_nonce = os.urandom(12)
    data_aes = AESGCM(dek)
    ciphertext = data_aes.encrypt(data_nonce, plaintext.encode("utf-8"), None)

    # Pack: key_version_len(1) | key_version | dek_nonce(12) | encrypted_dek | data_nonce(12) | ciphertext
    version_bytes = key_version.encode("utf-8")
    return (
        struct.pack("B", len(version_bytes))
        + version_bytes
        + dek_nonce
        + struct.pack(">H", len(encrypted_dek))
        + encrypted_dek
        + data_nonce
        + ciphertext
    )


def decrypt(blob: bytes) -> str:
    master_key = _get_master_key()
    master_aes = AESGCM(master_key)

    offset = 0

    # Read key version
    (version_len,) = struct.unpack_from("B", blob, offset)
    offset += 1
    _key_version = blob[offset : offset + version_len].decode("utf-8")  # noqa: F841
    offset += version_len

    # Read encrypted DEK
    dek_nonce = blob[offset : offset + 12]
    offset += 12
    (encrypted_dek_len,) = struct.unpack_from(">H", blob, offset)
    offset += 2
    encrypted_dek = blob[offset : offset + encrypted_dek_len]
    offset += encrypted_dek_len

    # Decrypt DEK
    dek = master_aes.decrypt(dek_nonce, encrypted_dek, None)

    # Read and decrypt data
    data_nonce = blob[offset : offset + 12]
    offset += 12
    ciphertext = blob[offset:]

    data_aes = AESGCM(dek)
    plaintext = data_aes.decrypt(data_nonce, ciphertext, None)
    return plaintext.decode("utf-8")


def get_current_key_version() -> str:
    return _KEY_VERSION
