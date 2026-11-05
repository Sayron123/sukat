"""Getting a photo into storage: presigned upload URLs, and the local-dev upload route."""

import re
import uuid
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field

from app.auth.deps import CurrentMemberDep
from app.core.config import settings
from app.core.storage import LocalStorage, Storage, get_storage

router = APIRouter(tags=["scans"])

EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
# "<store uuid>/scans/<32 hex>.<ext>": nothing else is ever a valid photo key.
KEY_RE = re.compile(r"^([0-9a-f-]{36})/scans/[0-9a-f]{32}\.(jpg|png|webp)$")

StorageDep = Annotated[Storage, Depends(get_storage)]


def key_belongs_to_store(key: str, store_id: UUID) -> bool:
    """True only for a well-formed photo key under this store's prefix."""
    m = KEY_RE.match(key)
    return bool(m) and m.group(1) == str(store_id)


class UploadUrlIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content_type: Literal["image/jpeg", "image/png", "image/webp"] = "image/jpeg"
    size_bytes: int = Field(gt=0)


class UploadUrlOut(BaseModel):
    photo_key: str
    upload_url: str
    method: str
    headers: dict[str, str]
    expires_in: int


@router.post("/scans/upload-url", response_model=UploadUrlOut)
def create_upload_url(body: UploadUrlIn, current: CurrentMemberDep, storage: StorageDep):
    """Any staff member can upload a list photo. The key is made here (never by the
    client) and always starts with the caller's store_id."""
    if body.size_bytes > settings.UPLOAD_MAX_BYTES:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"Photo is too large (max {settings.UPLOAD_MAX_BYTES // (1024 * 1024)} MB)",
        )
    key = f"{current.store_id}/scans/{uuid.uuid4().hex}.{EXTENSIONS[body.content_type]}"
    up = storage.presign_put(key, body.content_type, body.size_bytes)
    return UploadUrlOut(
        photo_key=up.key,
        upload_url=up.url,
        method=up.method,
        headers=up.headers,
        expires_in=up.expires_in,
    )


@router.put("/uploads/local/{key:path}", status_code=status.HTTP_204_NO_CONTENT)
async def local_upload(
    key: str,
    request: Request,
    storage: StorageDep,
    expires: Annotated[int, Query()],
    size: Annotated[int, Query()],
    sig: Annotated[str, Query(max_length=64)],
) -> None:
    """Development stand-in for R2: accepts a PUT only with a valid, unexpired signature
    for exactly this key, content type, and size. No login needed (like R2)."""
    if not isinstance(storage, LocalStorage):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    content_type = request.headers.get("content-type", "")
    if (
        not KEY_RE.match(key)
        or size > settings.UPLOAD_MAX_BYTES
        or not storage.check_signature(key, expires, content_type, size, sig)
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Invalid or expired upload URL")

    # Read at most size+1 bytes, so a lying client can't make us buffer a huge body.
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > size:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Body is larger than signed size")
    if len(body) != size:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Body size does not match")
    # File I/O is blocking: run it in the thread pool, not on the event loop.
    await run_in_threadpool(storage.save, key, bytes(body))
