from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth.router import router as auth_router
from app.core.config import settings
from app.core.health import router as health_router
from app.inventory.scans import router as scans_router
from app.inventory.transactions import router as transactions_router
from app.inventory.uploads import router as uploads_router
from app.products.router import router as products_router
from app.stores.router import router as stores_router

app = FastAPI(title="Sukat API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(stores_router)
app.include_router(products_router)
app.include_router(uploads_router)
app.include_router(scans_router)
app.include_router(transactions_router)
