# BitPro Module Map (v2 Refactor)

## Backend
- `app/api/v2/endpoints/*`: v2 API contract layer
- `app/domain/market/*`: market service/repository split
- `app/domain/funding/*`: funding domain service with strict upstream and non-blocking execution
- `app/domain/trading/*`: trading read domain service
- `app/domain/strategy/*`: strategy domain service facade
- `app/domain/sync/*`: sync domain service facade
- `app/domain/system/*`: health/exchange domain service
- `app/core/contracts.py`: unified API response envelope helpers
- `app/core/errors.py`: typed app errors and global handlers

## Frontend
- `src/api/client.ts`: v2 client, request/response key normalization
- `src/App.tsx`: route-level lazy loading
- `src/services/websocketManager.ts`: singleton websocket manager
- `src/hooks/useWebSocket.ts`: subscription hooks over singleton manager
- `src/pages/Monitor.tsx`: migrated to v2 client (`monitorApi`, `marketApi`) without direct axios/v1 coupling

## Compatibility
- v1 router remains available at `/api/v1/*`.
- v2 router is mounted at `/api/v2/*`.
- Backtest/Live/Paper/Agent legacy handlers are temporarily mounted under v2 namespace.
