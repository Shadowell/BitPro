"""Data sync endpoints for API v2."""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Query

from app.core.contracts import ok
from app.domain.sync import sync_domain_service

router = APIRouter()


@router.get("/status")
async def status():
    return ok(sync_domain_service.status())


@router.get("/config")
async def config():
    return ok(sync_domain_service.config())


@router.get("/data")
async def available_data(exchange: Optional[str] = Query(None, description="交易所")):
    return ok(sync_domain_service.available_data(exchange))


@router.post("/start")
async def start(payload: Dict[str, Any] = Body(default_factory=dict)):
    return ok(await sync_domain_service.start(payload))


@router.post("/sync-one")
async def sync_one(payload: Dict[str, Any] = Body(...)):
    return ok(await sync_domain_service.sync_one(payload))


@router.get("/table-stats")
async def table_stats():
    return ok(sync_domain_service.table_stats())
