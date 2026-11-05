"""App entry point: middleware, error handling, and the routers of each feature."""

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.auth.router import router as auth_router
from app.core.config import settings
from app.core.errors import AppError
from app.core.health import router as health_router
from app.insights.router import router as insights_router
from app.inventory.router import router as inventory_router
from app.products.router import router as products_router
from app.stores.router import router as stores_router

# Every API path lives under /v1, so a future /v2 can change things without breaking
# phones still on the old app. /health stays at the root (hosts and monitors expect it).
API_PREFIX = "/v1"

app = FastAPI(title="Sukat API", version="0.1.0")


@app.exception_handler(AppError)
def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    """Render business-rule errors the same way FastAPI renders HTTPException."""
    return JSONResponse(exc.body(), status_code=exc.status_code, headers=exc.headers)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

v1 = APIRouter(prefix=API_PREFIX)
for feature_router in (
    auth_router,
    stores_router,
    products_router,
    inventory_router,
    insights_router,
):
    v1.include_router(feature_router)

app.include_router(health_router)
app.include_router(v1)
