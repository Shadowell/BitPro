"""
BitPro v2 契约本地测试（无外网、mock 依赖）。
"""
from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.api.v2.endpoints import funding, monitor, sync as sync_v2, system, trading  # noqa: E402
from app.core.errors import register_exception_handlers  # noqa: E402


def build_client() -> TestClient:
    app = FastAPI()
    app.include_router(system.router, prefix="/api/v2/system")
    app.include_router(funding.router, prefix="/api/v2/funding")
    app.include_router(trading.router, prefix="/api/v2/trading")
    app.include_router(monitor.router, prefix="/api/v2/monitor")
    app.include_router(sync_v2.router, prefix="/api/v2/sync")
    register_exception_handlers(app)
    return TestClient(app, raise_server_exceptions=False)


def test_system_exchanges_envelope(monkeypatch) -> None:
    async def fake_exchanges():
        return {"okx": "connected"}

    monkeypatch.setattr(system.system_domain_service, "exchanges", fake_exchanges)

    client = build_client()
    r = client.get("/api/v2/system/exchanges")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["exchanges"]["okx"] == "connected"


def test_funding_rates_pagination(monkeypatch) -> None:
    async def fake_rates(exchange: str, symbols=None):
        assert exchange == "okx"
        return [
            {"symbol": "BTC/USDT", "current_rate": 0.0001},
            {"symbol": "ETH/USDT", "current_rate": 0.0002},
            {"symbol": "SOL/USDT", "current_rate": 0.0003},
        ]

    monkeypatch.setattr(funding.funding_domain_service, "get_funding_rates", fake_rates)

    client = build_client()
    r = client.get("/api/v2/funding/rates?exchange=okx&offset=1&limit=1")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["meta"] == {"total": 3, "offset": 1, "limit": 1}
    assert len(body["data"]) == 1
    assert body["data"][0]["symbol"] == "ETH/USDT"


def test_trading_balance_aliases(monkeypatch) -> None:
    async def fake_balance(exchange: str):
        assert exchange == "okx"
        return [{"currency": "USDT", "free": 1000, "used": 0, "total": 1000}]

    monkeypatch.setattr(trading.trading_domain_service, "get_balance", fake_balance)

    client = build_client()
    r_accounts = client.get("/api/v2/trading/accounts/balance?exchange=okx")
    r_alias = client.get("/api/v2/trading/balance?exchange=okx")

    assert r_accounts.status_code == 200
    assert r_alias.status_code == 200
    body_accounts = r_accounts.json()
    body_alias = r_alias.json()
    assert body_accounts["success"] is True
    assert body_alias["success"] is True
    assert body_accounts["data"]["balance"][0]["currency"] == "USDT"
    assert body_alias["data"]["balance"][0]["currency"] == "USDT"


def test_trading_spot_order_risk_reject(monkeypatch) -> None:
    async def fake_risk(*args, **kwargs):
        return {"can_trade": False, "errors": ["risk blocked"], "warnings": []}

    monkeypatch.setattr(trading.trading_service, "check_order_risk", fake_risk)

    client = build_client()
    payload = {
        "exchange": "okx",
        "symbol": "BTC/USDT",
        "side": "buy",
        "type": "market",
        "amount": 0.01,
    }
    r = client.post("/api/v2/trading/spot/order", json=payload)
    assert r.status_code == 400
    body = r.json()
    assert body["success"] is False
    assert body["error"]["code"] == "BAD_REQUEST"
    assert "risk blocked" in str(body["error"]["details"])


def test_monitor_alert_not_found(monkeypatch) -> None:
    monkeypatch.setattr(monitor.alert_service, "get_alerts", lambda: [])

    client = build_client()
    r = client.put("/api/v2/monitor/alerts/99?enabled=true")
    assert r.status_code == 404
    body = r.json()
    assert body["success"] is False
    assert body["error"]["code"] == "NOT_FOUND"


def test_monitor_running_strategies(monkeypatch) -> None:
    async def fake_running():
        return [{"strategy_id": 1, "name": "demo", "status": "running"}]

    monkeypatch.setattr(monitor.strategy_service, "get_all_running", fake_running)

    client = build_client()
    r = client.get("/api/v2/monitor/running-strategies")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"][0]["name"] == "demo"


def test_sync_status_envelope(monkeypatch) -> None:
    monkeypatch.setattr(
        sync_v2.sync_domain_service,
        "status",
        lambda: {"is_running": False, "summary": {"total_records": 12}, "details": []},
    )

    client = build_client()
    r = client.get("/api/v2/sync/status")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["is_running"] is False
    assert body["data"]["summary"]["total_records"] == 12


def test_sync_table_stats(monkeypatch) -> None:
    monkeypatch.setattr(
        sync_v2.sync_domain_service,
        "table_stats",
        lambda: {
            "tables": [
                {
                    "table_name": "kline_1h",
                    "timeframe": "1h",
                    "exchange": "okx",
                    "symbol": "BTC/USDT",
                    "record_count": 123,
                    "first_timestamp": 1,
                    "last_timestamp": 2,
                }
            ],
            "total_records": 123,
            "total_pairs": 1,
        },
    )

    client = build_client()
    r = client.get("/api/v2/sync/table-stats")
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["total_records"] == 123
    assert body["data"]["tables"][0]["table_name"] == "kline_1h"


def test_sync_one_contract(monkeypatch) -> None:
    async def fake_sync_one(payload):
        assert payload["symbol"] == "BTC/USDT"
        assert payload["timeframe"] == "1h"
        return {
            "exchange": "okx",
            "symbol": "BTC/USDT",
            "timeframe": "1h",
            "status": "completed",
            "total_fetched": 300,
            "total_inserted": 280,
            "error": None,
        }

    monkeypatch.setattr(sync_v2.sync_domain_service, "sync_one", fake_sync_one)

    client = build_client()
    payload = {"exchange": "okx", "symbol": "BTC/USDT", "timeframe": "1h"}
    r = client.post("/api/v2/sync/sync-one", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"]["status"] == "completed"
    assert body["data"]["total_fetched"] == 300
