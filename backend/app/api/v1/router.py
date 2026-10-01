from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import admin, auth, contacts, documents, feedback, health, overview, query, sources

api_router = APIRouter()
for module in (health, auth, query, sources, documents, feedback, contacts, admin, overview):
    api_router.include_router(module.router)
