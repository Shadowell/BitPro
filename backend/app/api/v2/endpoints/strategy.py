"""Strategy endpoints for API v2."""
from fastapi import APIRouter, Query

from app.core.contracts import ok
from app.core.errors import BadRequestError, NotFoundError
from app.domain.strategy import strategy_domain_service
from app.models.schemas import StrategyCreate, StrategyUpdate

router = APIRouter()


@router.get("")
async def list_strategies():
    return ok(await strategy_domain_service.list())


@router.get("/{strategy_id}")
async def get_strategy(strategy_id: int):
    item = await strategy_domain_service.get(strategy_id)
    if not item:
        raise NotFoundError("Strategy not found")
    return ok(item)


@router.post("")
async def create_strategy(payload: StrategyCreate):
    return ok(await strategy_domain_service.create(payload))


@router.put("/{strategy_id}")
async def update_strategy(strategy_id: int, payload: StrategyUpdate):
    item = await strategy_domain_service.update(strategy_id, payload)
    if not item:
        raise NotFoundError("Strategy not found")
    return ok(item)


@router.delete("/{strategy_id}")
async def delete_strategy(strategy_id: int):
    success = await strategy_domain_service.delete(strategy_id)
    if not success:
        raise NotFoundError("Strategy not found")
    return ok({"deleted": True})


@router.post("/{strategy_id}/start")
async def start_strategy(strategy_id: int):
    success = await strategy_domain_service.start(strategy_id)
    if not success:
        raise BadRequestError("Failed to start strategy")
    return ok({"started": True})


@router.post("/{strategy_id}/stop")
async def stop_strategy(strategy_id: int):
    success = await strategy_domain_service.stop(strategy_id)
    if not success:
        raise BadRequestError("Failed to stop strategy")
    return ok({"stopped": True})


@router.get("/{strategy_id}/status")
async def strategy_status(strategy_id: int):
    status = await strategy_domain_service.status(strategy_id)
    if not status:
        raise NotFoundError("Strategy not found")
    return ok(status)


@router.get("/{strategy_id}/trades")
async def strategy_trades(strategy_id: int, limit: int = Query(50, ge=1, le=500)):
    return ok(await strategy_domain_service.trades(strategy_id, limit))
