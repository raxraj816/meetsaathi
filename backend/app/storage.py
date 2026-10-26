"""Encrypted object storage. Local filesystem implementation; the interface is what an S3/GCS adapter
implements. Keys are opaque, tenant-prefixed; no listing API is exposed to clients (UNI-018)."""
from __future__ import annotations

import os
import pathlib
import uuid
import tempfile

from botocore.exceptions import ClientError

from .config import get_settings
from .security.crypto import decrypt_object, encrypt_object


class ObjectStore:
    def __init__(self, root: str | None = None) -> None:
        self.root = pathlib.Path(root or get_settings().object_store_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> pathlib.Path:
        validate_key(key)
        p = (self.root / key).resolve()
        if not p.is_relative_to(self.root) or p == self.root:
            raise ValueError("invalid object key")
        return p

    def put(self, tenant_id: uuid.UUID, key: str, data: bytes) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".upload-")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(encrypt_object(tenant_id, key, data))
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, p)
        finally:
            pathlib.Path(tmp).unlink(missing_ok=True)

    def get(self, tenant_id: uuid.UUID, key: str) -> bytes:
        return decrypt_object(tenant_id, key, self._path(key).read_bytes())

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def delete(self, key: str) -> bool:
        p = self._path(key)
        if p.exists():
            p.unlink()
            return True
        return False

    def delete_prefix(self, prefix: str) -> int:
        base = self._path(prefix)
        count = 0
        if base.is_dir():
            for f in sorted(base.rglob("*"), reverse=True):
                if f.is_file():
                    f.unlink()
                    count += 1
                else:
                    f.rmdir()
            base.rmdir()
        return count


def validate_key(key: str) -> str:
    if not key or key.startswith("/") or "\\" in key or any(p in ("", ".", "..") for p in key.split("/")):
        raise ValueError("invalid object key")
    return key


class S3ObjectStore:
    """Application encryption plus SSE-KMS. Purge removes all versions, including delete markers.

    APIs share the local store's synchronous contract. Cloud SDK work is offloaded by async callers.
    Version listings are completed before deletion to avoid invalidating pagination cursors.
    """

    def __init__(self, *, client=None) -> None:
        from .aws import client as aws_client

        s = get_settings()
        self.bucket = s.s3_bucket
        self.kms_key = s.s3_kms_key_id
        self.client = client or aws_client("s3")

    def put(self, tenant_id: uuid.UUID, key: str, data: bytes) -> None:
        self.client.put_object(Bucket=self.bucket, Key=validate_key(key), Body=encrypt_object(tenant_id, key, data),
                               ServerSideEncryption="aws:kms", SSEKMSKeyId=self.kms_key,
                               ContentType="application/octet-stream")

    def get(self, tenant_id: uuid.UUID, key: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=validate_key(key))
        try:
            return decrypt_object(tenant_id, key, response["Body"].read())
        finally:
            response["Body"].close()

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=validate_key(key))
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] in ("404", "NoSuchKey", "NotFound"):
                return False
            raise

    def _purge(self, prefix: str, *, exact: bool) -> int:
        versions = []
        paginator = self.client.get_paginator("list_object_versions")
        for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
            for obj in page.get("Versions", []) + page.get("DeleteMarkers", []):
                if not exact or obj["Key"] == prefix:
                    versions.append({"Key": obj["Key"], "VersionId": obj["VersionId"]})
        for i in range(0, len(versions), 1000):
            result = self.client.delete_objects(Bucket=self.bucket, Delete={"Objects": versions[i:i + 1000], "Quiet": True})
            if result.get("Errors"):
                raise RuntimeError("S3 purge incomplete")  # deletion must not report COMPLETE on partial failure
        return len(versions)

    def delete(self, key: str) -> bool:
        return self._purge(validate_key(key), exact=True) > 0

    def delete_prefix(self, prefix: str) -> int:
        return self._purge(validate_key(prefix) + "/", exact=False)


_store: ObjectStore | S3ObjectStore | None = None


def get_store() -> ObjectStore | S3ObjectStore:
    global _store
    if _store is None:
        _store = S3ObjectStore() if get_settings().object_store_backend == "s3" else ObjectStore()
    return _store


def reset_store() -> None:
    global _store
    _store = None


def chunk_key(tenant_id: uuid.UUID, session_id: uuid.UUID, sequence: int) -> str:
    return f"t/{tenant_id}/s/{session_id}/audio/{sequence:09d}.pcm"


def session_prefix(tenant_id: uuid.UUID, session_id: uuid.UUID) -> str:
    return f"t/{tenant_id}/s/{session_id}"
