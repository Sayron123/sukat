from app.core.config import settings


def test_json_body_over_the_limit_is_413(api):
    res = api.post(
        "/auth/login",
        content=b'{"email":"a@example.com","password":"' + b"x" * 2 * 1024 * 1024 + b'"}',
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 413
    assert res.json()["detail"] == "Request is too large"
    assert "x-request-id" in res.headers


def test_chunked_body_over_the_limit_is_413(api):
    def chunks():
        for _ in range(3):
            yield b"x" * (600 * 1024)

    res = api.post("/auth/login", content=chunks(), headers={"Content-Type": "application/json"})
    assert res.status_code == 413


def test_normal_body_still_works(api, signup):
    out = signup()
    res = api.post("/auth/login", json={"email": out["email"], "password": out["password"]})
    assert res.status_code == 200


def test_photo_upload_path_allows_up_to_the_photo_limit(api, manager, storage):
    size = 2 * 1024 * 1024
    up = api.post(
        "/scans/upload-url",
        json={"content_type": "image/jpeg", "size_bytes": size},
        headers=manager,
    ).json()
    res = api.put(up["upload_url"], content=b"\xff" * size, headers=up["headers"])
    assert res.status_code == 204, res.text


def test_photo_over_the_photo_limit_is_413(api):
    res = api.put(
        "/uploads/local/stores/x/scans/y.jpg?expires=1&size=1&sig=z",
        content=b"x" * (settings.UPLOAD_MAX_BYTES + 1),
        headers={"Content-Type": "image/jpeg"},
    )
    assert res.status_code == 413
