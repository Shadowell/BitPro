"""System endpoints for API v2."""
from fastapi import APIRouter

from app.core.contracts import ok
from app.domain.system import system_domain_service

router = APIRouter()


@router.get("/health")
async def health_check():
    return ok(await system_domain_service.health())


@router.get("/exchanges")
async def check_exchanges():
    return ok({"exchanges": await system_domain_service.exchanges()})
