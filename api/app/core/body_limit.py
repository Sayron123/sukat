from typing import Any

from fastapi import HTTPException, status

UPLOAD_PREFIX = "/v1/uploads/"
TOO_LARGE = "Request is too large"


class BodySizeLimitMiddleware:
    def __init__(self, app: Any, max_bytes: int, upload_max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.upload_max_bytes = upload_max_bytes

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path: str = scope.get("path", "")
        limit = self.upload_max_bytes if path.startswith(UPLOAD_PREFIX) else self.max_bytes

        length = dict(scope.get("headers") or []).get(b"content-length")
        if length is not None:
            try:
                declared = int(length)
            except ValueError:
                declared = limit + 1
            if declared > limit:
                await _send_413(send)
                return

        received = 0

        async def limited_receive() -> dict:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, TOO_LARGE)
            return message

        await self.app(scope, limited_receive, send)


async def _send_413(send: Any) -> None:
    body = b'{"detail":"' + TOO_LARGE.encode() + b'"}'
    await send(
        {
            "type": "http.response.start",
            "status": status.HTTP_413_CONTENT_TOO_LARGE,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
