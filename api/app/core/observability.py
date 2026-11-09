"""Logging with a request ID on every line, and error reporting to Sentry without
personal data.

- Every request gets an ID: the caller's X-Request-ID if it looks safe, else a new one.
  It is on every log line written while the request runs, in the X-Request-ID response
  header, and on the Sentry event, so a user's "it failed" can be found in the logs.
- One access line per request: method, path (never the query string), status, time.
- Sentry is on only when SENTRY_DSN is set. send_default_pii is off, local variables
  are not sent, request bodies are never sent, and scrub_event() removes headers,
  cookies, the user, query strings, emails and tokens from whatever is left.
"""

import logging
import re
import time
import uuid
from contextvars import ContextVar
from typing import Any

from app.core.config import Settings

REQUEST_ID_HEADER = "x-request-id"
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
_request_id: ContextVar[str] = ContextVar("request_id", default="-")

log = logging.getLogger("app.request")


def current_request_id() -> str:
    return _request_id.get()


# ---------- logging ----------


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id.get()
        return True


LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s"


def setup_logging(level: str) -> None:
    """Root logger: one stream handler with the request ID on every line. Uvicorn's own
    loggers are sent through it too, so its error lines carry the ID as well."""
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    handler.addFilter(RequestIdFilter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    for name in ("uvicorn", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True
    # Uvicorn's access log prints the full URL, query string included (it can hold data).
    # RequestIdMiddleware writes its own access line, path only, with the request ID.
    access = logging.getLogger("uvicorn.access")
    access.handlers = []
    access.propagate = False
    access.disabled = True


class RequestIdMiddleware:
    """Plain ASGI middleware (no body buffering): sets the request ID, adds it to the
    response headers, and writes one access log line."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = (
            dict(scope.get("headers") or []).get(REQUEST_ID_HEADER.encode(), b"").decode("latin-1")
        )
        request_id = incoming if _SAFE_ID.match(incoming) else uuid.uuid4().hex
        token = _request_id.set(request_id)
        status = 500
        start = time.perf_counter()

        async def send_with_id(message: dict) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = [
                    (k, v) for k, v in message.get("headers", []) if k.lower() != b"x-request-id"
                ]
                headers.append((b"x-request-id", request_id.encode()))
                message = {**message, "headers": headers}
            await send(message)

        try:
            _tag_sentry(request_id)
            await self.app(scope, receive, send_with_id)
        finally:
            log.info(
                "%s %s %s %.0fms",
                scope.get("method", "-"),
                scope.get("path", "-"),  # path only: query strings can hold data
                status,
                (time.perf_counter() - start) * 1000,
            )
            _request_id.reset(token)


# ---------- Sentry ----------

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_JWT = re.compile(r"eyJ[\w-]+\.[\w-]+\.[\w-]+")
_BEARER = re.compile(r"(?i)bearer\s+\S+")
_KEYS = re.compile(r"(?i)(sk-ant-[\w-]+|AIza[\w-]{20,})")


def scrub_text(text: str) -> str:
    """Remove emails, JWTs, bearer tokens and API keys from a message."""
    for pattern, replacement in (
        (_BEARER, "Bearer [removed]"),
        (_JWT, "[token]"),
        (_KEYS, "[key]"),
        (_EMAIL, "[email]"),
    ):
        text = pattern.sub(replacement, text)
    return text


def scrub_event(event: dict, hint: dict | None = None) -> dict:
    """Sentry before_send: keep what helps debugging (error type, stack, path, request
    ID), drop anything that can identify a person or hold a secret."""
    request = event.get("request")
    if isinstance(request, dict):
        event["request"] = {
            k: request[k] for k in ("method", "url") if k in request
        }  # no headers, cookies, body, query string, env
        if "url" in event["request"]:
            event["request"]["url"] = str(event["request"]["url"]).split("?")[0]
    event.pop("user", None)
    event.pop("server_name", None)
    if isinstance(event.get("message"), str):
        event["message"] = scrub_text(event["message"])
    logentry = event.get("logentry")
    if isinstance(logentry, dict):
        for key in ("message", "formatted"):
            if isinstance(logentry.get(key), str):
                logentry[key] = scrub_text(logentry[key])
        logentry.pop("params", None)
    for exc in (event.get("exception") or {}).get("values") or []:
        if isinstance(exc.get("value"), str):
            exc["value"] = scrub_text(exc["value"])
        for frame in (exc.get("stacktrace") or {}).get("frames") or []:
            frame.pop("vars", None)
    for crumb in (event.get("breadcrumbs") or {}).get("values") or []:
        if isinstance(crumb.get("message"), str):
            crumb["message"] = scrub_text(crumb["message"])
        crumb.pop("data", None)
    return event


def init_sentry(config: Settings) -> bool:
    """Start Sentry when SENTRY_DSN is set. @returns True if it was started."""
    if not config.SENTRY_DSN:
        return False
    import sentry_sdk

    sentry_sdk.init(
        dsn=config.SENTRY_DSN,
        environment=config.APP_ENV,
        release=config.RELEASE or None,
        send_default_pii=False,  # no IPs, users, cookies, headers
        include_local_variables=False,  # locals can hold passwords and tokens
        max_request_body_size="never",
        traces_sample_rate=config.SENTRY_TRACES_SAMPLE_RATE,
        before_send=scrub_event,  # type: ignore[arg-type]
        before_send_transaction=scrub_event,  # type: ignore[arg-type]
    )
    return True


def _tag_sentry(request_id: str) -> None:
    try:
        import sentry_sdk
    except ImportError:  # pragma: no cover
        return
    if sentry_sdk.is_initialized():
        sentry_sdk.get_isolation_scope().set_tag("request_id", request_id)
