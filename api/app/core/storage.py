"""Photo storage: Cloudflare R2 in production, a local folder in development.

The phone uploads straight to storage with a short-lived presigned PUT URL, so photos
never pass through the API (saves bandwidth and memory). The signature fixes the key,
content type, and exact size, so the URL can't be reused for anything else.
"""

import hashlib
import hmac
import os
import time
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import Protocol
from urllib.parse import quote, urlencode

from app.core.config import settings


@dataclass(frozen=True)
class PresignedUpload:
    key: str
    url: str
    expires_in: int
    method: str = "PUT"
    # Headers the client MUST send with the PUT (they are part of the signature).
    headers: dict[str, str] = field(default_factory=dict)


class Storage(Protocol):
    def presign_put(self, key: str, content_type: str, size: int) -> PresignedUpload: ...

    def read(self, key: str, max_bytes: int) -> bytes | None:
        """The object's bytes, or None if it doesn't exist. Raises ValueError if larger
        than max_bytes."""
        ...


# ---------------- local folder (development) ----------------


class LocalStorage:
    """Saves files under `root`. Upload URLs point to this API's /uploads/local route and
    carry an HMAC signature, mimicking how R2 presigned URLs work."""

    def __init__(self, root: str, public_api_url: str, secret: str) -> None:
        self.root = Path(root).resolve()
        self.public_api_url = public_api_url.rstrip("/")
        self._secret = secret.encode()

    def _sign(self, key: str, expires: int, content_type: str, size: int) -> str:
        msg = f"{key}|{expires}|{content_type}|{size}".encode()
        return hmac.new(self._secret, msg, hashlib.sha256).hexdigest()

    def presign_put(self, key: str, content_type: str, size: int) -> PresignedUpload:
        expires_in = settings.UPLOAD_URL_EXPIRE_SECONDS
        expires = int(time.time()) + expires_in
        query = urlencode(
            {"expires": expires, "size": size, "sig": self._sign(key, expires, content_type, size)}
        )
        return PresignedUpload(
            key=key,
            url=f"{self.public_api_url}/uploads/local/{quote(key)}?{query}",
            expires_in=expires_in,
            headers={"Content-Type": content_type},
        )

    def check_signature(
        self, key: str, expires: int, content_type: str, size: int, sig: str
    ) -> bool:
        """True if the URL was made by presign_put and has not expired."""
        expected = self._sign(key, expires, content_type, size)
        return hmac.compare_digest(expected, sig) and expires >= time.time()

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):  # defence in depth; keys are validated too
            raise ValueError("bad key")
        return path

    def save(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".part")
        tmp.write_bytes(data)
        os.replace(tmp, path)  # atomic: a reader never sees a half-written file

    def read(self, key: str, max_bytes: int) -> bytes | None:
        path = self._path(key)
        if not path.is_file():
            return None
        if path.stat().st_size > max_bytes:
            raise ValueError("file too large")
        return path.read_bytes()


# ---------------- Cloudflare R2 (S3-compatible) ----------------


class R2Storage:
    def __init__(self, account_id: str, access_key: str, secret_key: str, bucket: str) -> None:
        import boto3  # imported here so local development doesn't need AWS settings
        from botocore.config import Config

        self.bucket = bucket
        self._s3 = boto3.client(
            "s3",
            endpoint_url=f"https://{account_id}.r2.cloudflarestorage.com",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name="auto",
            config=Config(signature_version="s3v4", retries={"max_attempts": 2}),
        )

    def presign_put(self, key: str, content_type: str, size: int) -> PresignedUpload:
        expires_in = settings.UPLOAD_URL_EXPIRE_SECONDS
        url = self._s3.generate_presigned_url(
            "put_object",
            # ContentLength is signed, so R2 rejects a body of any other size.
            Params={
                "Bucket": self.bucket,
                "Key": key,
                "ContentType": content_type,
                "ContentLength": size,
            },
            ExpiresIn=expires_in,
            HttpMethod="PUT",
        )
        return PresignedUpload(
            key=key, url=url, expires_in=expires_in, headers={"Content-Type": content_type}
        )

    def read(self, key: str, max_bytes: int) -> bytes | None:
        from botocore.exceptions import ClientError

        try:
            obj = self._s3.get_object(Bucket=self.bucket, Key=key)
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") in ("NoSuchKey", "404"):
                return None
            raise
        if obj.get("ContentLength", 0) > max_bytes:
            raise ValueError("file too large")
        return obj["Body"].read()


@cache
def get_storage() -> Storage:
    """The configured storage backend (FastAPI dependency; override it in tests)."""
    if settings.STORAGE_BACKEND == "r2":
        return R2Storage(
            settings.R2_ACCOUNT_ID,
            settings.R2_ACCESS_KEY_ID,
            settings.R2_SECRET_ACCESS_KEY,
            settings.R2_BUCKET,
        )
    return LocalStorage(settings.LOCAL_UPLOAD_DIR, settings.PUBLIC_API_URL, settings.JWT_SECRET)
