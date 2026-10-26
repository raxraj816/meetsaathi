"""Envelope encryption for server-side objects (master 8.4).

Per-tenant data keys are derived with HKDF-SHA256 from the environment master key (supplied by a
KMS/HSM-backed secret store in production). Objects are AES-256-GCM with a random 96-bit nonce and the
object key bound as associated data, so a ciphertext cannot be swapped between objects.

Format: b"MSE1" | key_version (1 byte) | nonce (12) | ciphertext+tag
"""
from __future__ import annotations

import hashlib
import hmac
import os
import uuid

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from ..config import get_settings

MAGIC = b"MSE1"


def _tenant_key(tenant_id: uuid.UUID, version: int) -> bytes:
    s = get_settings()
    hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=uuid.UUID(str(tenant_id)).bytes,
                info=f"meetsaathi-dek-v{version}".encode())
    return hkdf.derive(s.master_key())


def encrypt_object(tenant_id: uuid.UUID, object_key: str, plaintext: bytes) -> bytes:
    version = get_settings().master_key_version
    nonce = os.urandom(12)
    ct = AESGCM(_tenant_key(tenant_id, version)).encrypt(nonce, plaintext, object_key.encode())
    return MAGIC + bytes([version]) + nonce + ct


def decrypt_object(tenant_id: uuid.UUID, object_key: str, blob: bytes) -> bytes:
    if not blob.startswith(MAGIC):
        raise ValueError("not a MeetSaathi encrypted object")
    version = blob[4]
    nonce = blob[5:17]
    return AESGCM(_tenant_key(tenant_id, version)).decrypt(nonce, blob[17:], object_key.encode())


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())
