from __future__ import annotations

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import users, products
from app.api.utils import register_exception_handlers

app = FastAPI(
    title="Caelus Deploy",
    description="Service for provisioning user-owned webapp instances on cloud infrastructure",
    version="0.1.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi.responses import RedirectResponse


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    """Redirect root URL to Swagger UI docs."""
    return RedirectResponse(url="/docs")


app.include_router(users.router)
app.include_router(products.router)

register_exception_handlers(app)

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8001, log_level="info", reload=True)
