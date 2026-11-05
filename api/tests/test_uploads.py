import time
from urllib.parse import parse_qs, urlsplit

import pytest

from app.core.config import settings
from app.core.storage import R2Storage
from app.inventory.scan_service import key_belongs_to_store

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 96  # 100 bytes that start like a JPEG
JPEG_SIZE = len(JPEG)


def _upload_url(api, headers, size=JPEG_SIZE, content_type="image/jpeg"):
    return api.post(
        "/scans/upload-url",
        json={"content_type": content_type, "size_bytes": size},
        headers=headers,
    )


def _put(api, up, body=JPEG, content_type=None):
    path = urlsplit(up["upload_url"])
    return api.put(
        f"{path.path}?{path.query}",
        content=body,
        headers={"Content-Type": content_type or up["headers"]["Content-Type"]},
    )


def test_upload_url_key_is_prefixed_by_store(api, manager):
    me = api.get("/auth/me", headers=manager).json()
    up = _upload_url(api, manager).json()
    assert up["photo_key"].startswith(f"{me['store_id']}/scans/")
    assert up["photo_key"].endswith(".jpg")
    assert up["method"] == "PUT" and up["headers"] == {"Content-Type": "image/jpeg"}
    assert key_belongs_to_store(up["photo_key"], me["store_id"])


def test_local_upload_round_trip(api, manager, storage):
    up = _upload_url(api, manager).json()
    assert _put(api, up).status_code == 204
    assert storage.read(up["photo_key"], 10_000) == JPEG


@pytest.mark.parametrize(
    "change",
    ["wrong_size", "bigger_body", "wrong_type", "bad_sig", "other_key", "expired"],
)
def test_local_upload_rejects_tampering(api, manager, storage, change, monkeypatch):
    up = _upload_url(api, manager).json()
    path = urlsplit(up["upload_url"])
    q = {k: v[0] for k, v in parse_qs(path.query).items()}
    body, ctype, key = JPEG, "image/jpeg", up["photo_key"]
    if change == "wrong_size":
        body = JPEG[:50]
    elif change == "bigger_body":
        body = JPEG + b"extra"
    elif change == "wrong_type":
        ctype = "image/png"
    elif change == "bad_sig":
        q["sig"] = "0" * 64
    elif change == "other_key":
        key = key.replace(key.split("/")[0], "00000000-0000-0000-0000-000000000000")
    elif change == "expired":
        monkeypatch.setattr(time, "time", lambda: int(q["expires"]) + 1)
    res = api.put(
        f"/uploads/local/{key}",
        params=q,
        content=body,
        headers={"Content-Type": ctype},
    )
    assert res.status_code in (400, 403), change
    assert storage.read(up["photo_key"], 10_000) is None


def test_upload_url_rejects_too_large_and_bad_type(api, manager):
    assert _upload_url(api, manager, size=settings.UPLOAD_MAX_BYTES + 1).status_code == 413
    assert _upload_url(api, manager, content_type="application/pdf").status_code == 422


def test_upload_url_needs_login_but_any_role(api, signup):
    assert api.post("/scans/upload-url", json={"size_bytes": 10}).status_code == 401


def test_key_belongs_to_store_rejects_tricks():
    store = "11111111-1111-1111-1111-111111111111"
    good = f"{store}/scans/{'a' * 32}.jpg"
    assert key_belongs_to_store(good, store)
    for bad in (
        f"22222222-2222-2222-2222-222222222222/scans/{'a' * 32}.jpg",
        f"{store}/scans/../../etc/passwd",
        f"{store}/scans/{'a' * 32}.jpg/../x.jpg",
        f"{store}/other/{'a' * 32}.jpg",
        f"/{good}",
    ):
        assert not key_belongs_to_store(bad, store), bad


def test_r2_presigned_url_signs_type_and_size():
    r2 = R2Storage("acct123", "AKIDEXAMPLE", "secret", "sukat-photos")
    up = r2.presign_put("s/scans/x.jpg", "image/jpeg", 1234)
    parts = urlsplit(up.url)
    q = parse_qs(parts.query)
    assert parts.netloc == "acct123.r2.cloudflarestorage.com"
    assert parts.path == "/sukat-photos/s/scans/x.jpg"
    signed = q["X-Amz-SignedHeaders"][0].split(";")
    assert "content-length" in signed and "content-type" in signed
    assert q["X-Amz-Expires"] == [str(settings.UPLOAD_URL_EXPIRE_SECONDS)]
