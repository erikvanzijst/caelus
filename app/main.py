from __future__ import annotations

from fastapi import FastAPI

from app.api import products, users

app = FastAPI(title="Caelus")


app.include_router(users.router)
app.include_router(products.router)
