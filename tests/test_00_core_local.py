"""
BitPro 核心本地测试（不依赖外网/交易所）。
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

from app.core.contracts import fail, ok, page_meta  # noqa: E402
from app.core.errors import BadRequestError, register_exception_handlers  # noqa: E402


def test_contract_helpers() -> None:
    payload = ok({"name": "bitpro"}, meta=page_meta(total=12, offset=0, limit=5))
    assert payload["success"] is True
    assert payload["data"]["name"] == "bitpro"
    assert payload["meta"] == {"total": 12, "offset": 0, "limit": 5}

    error = fail("BAD_REQUEST", "invalid params", details={"field": "symbol"})
    assert error["success"] is False
    assert error["error"]["code"] == "BAD_REQUEST"
    assert error["error"]["details"]["field"] == "symbol"


def test_exception_handlers_envelope() -> None:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/bad")
    async def bad():
        raise BadRequestError("bad input")

    @app.get("/boom")
    async def boom():
        raise RuntimeError("unexpected")

    client = TestClient(app, raise_server_exceptions=False)

    r1 = client.get("/bad")
    assert r1.status_code == 400
    body1 = r1.json()
    assert body1["success"] is False
    assert body1["error"]["code"] == "BAD_REQUEST"
    assert body1["error"]["message"] == "bad input"

    r2 = client.get("/boom")
    assert r2.status_code == 500
    body2 = r2.json()
    assert body2["success"] is False
    assert body2["error"]["code"] == "INTERNAL_ERROR"
