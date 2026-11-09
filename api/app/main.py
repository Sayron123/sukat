"""App entry point: middleware, error handling, and the routers of each feature."""

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.auth.router import router as auth_router
from app.core.body_limit import BodySizeLimitMiddleware
from app.core.config import Settings, settings
from app.core.errors import AppError
from app.core.health import router as health_router
from app.core.observability import RequestIdMiddleware, init_sentry, setup_logging
from app.exports.router import router as exports_router
from app.insights.chat_router import router as chat_router
from app.insights.router import router as insights_router
from app.inventory.router import router as inventory_router
from app.products.router import router as products_router
from app.stores.router import router as stores_router

# Every API path lives under /v1, so a future /v2 can change things without breaking
# phones still on the old app. /health stays at the root (hosts and monitors expect it).
API_PREFIX = "/v1"


def create_app(config: Settings = settings) -> FastAPI:
    """Build the API. In production the interactive docs (/docs, /redoc) and the
    OpenAPI schema are off: they list every endpoint for anyone who looks."""
    setup_logging(config.LOG_LEVEL)
    init_sentry(config)
    docs = not config.is_production
    application = FastAPI(
        title="Sukat API",
        version="0.1.0",
        debug=config.DEBUG,
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
    )

    @application.exception_handler(AppError)
    def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        """Render business-rule errors the same way FastAPI renders HTTPException."""
        return JSONResponse(exc.body(), status_code=exc.status_code, headers=exc.headers)

    # Only the configured web origins may call the API from a browser (in production:
    # https:// origins only; checked in settings).
    # Added before CORS so it runs inside it: a 413 still carries the CORS headers.
    application.add_middleware(
        BodySizeLimitMiddleware,
        max_bytes=config.MAX_REQUEST_BYTES,
        upload_max_bytes=config.UPLOAD_MAX_BYTES,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

    v1 = APIRouter(prefix=API_PREFIX)
    for feature_router in (
        auth_router,
        stores_router,
        products_router,
        inventory_router,
        insights_router,
        chat_router,
        exports_router,
    ):
        v1.include_router(feature_router)

    application.include_router(health_router)
    application.include_router(v1)
    # Outermost: every response (errors and CORS replies too) gets the request ID.
    application.add_middleware(RequestIdMiddleware)
    return application


app = create_app()
