from __future__ import annotations

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.api import users, products
from app.api.utils import register_exception_handlers
from app.logging_config import configure_logging

configure_logging()

app = FastAPI(
    title="Caelus Deploy",
    description="Service for provisioning user-owned webapp instances on cloud infrastructure",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173", "https://app.deprutser.be"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    """Redirect root URL to Swagger UI docs."""
    return RedirectResponse(url="/api/docs")


@app.get("/docs", include_in_schema=False)
def redirect_to_docs() -> RedirectResponse:
    """Redirect /docs to /api/docs for backwards compatibility."""
    return RedirectResponse(url="/api/docs")


app.include_router(users.router, prefix="/api")
app.include_router(products.router, prefix="/api")

register_exception_handlers(app)

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, log_level="info", reload=True)
