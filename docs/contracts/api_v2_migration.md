# BitPro API v2 Migration Guide

## Overview
- Base path: `/api/v2`
- v1 remains available at `/api/v1` during migration window.
- v2 response contract prefers envelope:
  - success: `{ "success": true, "data": ... }`
  - error: `{ "success": false, "error": { "code", "message", "details" } }`

## Major Path Changes
- Health
  - v1: `/health`
  - v2: `/system/health`
- Exchanges
  - v1: `/health/exchanges`
  - v2: `/system/exchanges`
- Strategy
  - v1: `/strategy/*`
  - v2: `/strategies/*`
- Data sync
  - v1: `/data_sync/*`
  - v2: `/sync/*` (legacy `/data_sync/*` is temporarily mounted in v2)
- Funding
  - v1: `/funding/*`
  - v2: `/funding/*` (adds unified pagination `offset`/`limit` on list endpoints)
- Monitor
  - v1: `/monitor/alert*`, `/monitor/running-strategies`, `/monitor/long-short-ratio`, `/monitor/open-interest`
  - v2: `/monitor/alerts*`, `/monitor/running-strategies`, `/monitor/long-short-ratio`, `/monitor/open-interest`
- WebSocket
  - v1: `/api/v1/ws`
  - v2: `/api/v2/ws`

## Frontend Compatibility
- Frontend client now normalizes payloads:
  - request keys: camelCase -> snake_case
  - response keys: snake_case -> camelCase
- Both v2 envelope and legacy raw payloads are supported by the client.

## Strict Failure Policy
- Exchange dependency remains strict.
- When OKX is not reachable, API returns explicit failure instead of fallback data.

## Newly Stabilized v2 Behaviors
- Funding and market domain calls now use non-blocking adapter execution (`asyncio.to_thread`) to avoid blocking async routes.
- Realtime websocket loops now fetch/publish in parallel and keep subscription snapshots isolated from concurrent mutation.
- Subscription key parsing now supports symbols containing `:` (for example perpetual symbols like `BTC/USDT:USDT`).

## Rollback
- Revert frontend `API_BASE` from `/api/v2` to `/api/v1`.
- Disable v2 router mount in `backend/app/main.py`.
- Re-enable old middleware behavior if required.
