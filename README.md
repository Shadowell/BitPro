# BitPro - 加密货币量化交易平台

> 一站式 Crypto 量化交易工具：行情监控、策略研发、回测引擎、模拟盘、实盘交易

![Version](https://img.shields.io/badge/version-1.0-blue)
![Python](https://img.shields.io/badge/python-3.11+-green)
![React](https://img.shields.io/badge/react-18-blue)
![License](https://img.shields.io/badge/license-MIT-green)

---

## 功能特性

| 模块 | 功能 | 说明 |
|------|------|------|
| **首页看板** | 行情概览、资金费率套利、市场指标 | 一站式数据面板 |
| **行情监控** | K线图、订单簿、成交记录 | 支持 OKX 交易所 |
| **策略研发** | 策略编写、管理、数据库存储 | 内置多种专业策略模板 |
| **策略回测** | 历史数据回测 (v2引擎)、绩效分析 | 夏普比率、最大回撤等指标 |
| **模拟盘** | 多实例并行模拟交易 | 支持同时运行多个策略 |
| **实盘交易** | 策略自动执行、风险管理 | 支持 OKX 实盘/测试网 |
| **数据管理** | 历史K线数据同步、本地缓存 | SQLite 存储，定时增量同步 |
| **告警监控** | 策略运行状态、告警通知 | 支持 Telegram 推送 |

---

## 技术架构

```
Frontend (React 18 + TypeScript + Vite + TailwindCSS)
    │
    │  http://localhost:8888
    │  /api/* 代理到后端
    ▼
Backend (FastAPI + Python 3.11 + Uvicorn)
    │
    │  http://localhost:8889
    │
    ┌───┴───────────┐
    ▼               ▼
SQLite DB       CCXT (OKX API)
(本地数据库)     (交易所接口)
    │
    ├── kline_history    K线历史数据
    ├── strategies       策略信息
    ├── backtest_results 回测结果
    └── trading_events   交易事件
```

---

## 快速开始

### 环境要求

- **Python** 3.11+
- **Node.js** 18+
- **npm** 9+
- **操作系统** macOS / Linux

### 方式一：一键部署（推荐）

```bash
# 1. 克隆项目
git clone <repo-url>
cd BitPro

# 2. 一键初始化
chmod +x deploy.sh
./deploy.sh

# 3. 配置交易所 API（可选，公开行情数据无需配置）
vim backend/.env

# 4. 启动服务
./start.sh
```

### 方式二：手动部署

```bash
# 后端
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env     # 编辑 .env 填入 API Key
uvicorn app.main:app --host 0.0.0.0 --port 8889

# 前端（新终端）
cd frontend
npm install
npm run dev
```

### 访问应用

| 服务 | 地址 |
|------|------|
| 前端页面 | http://localhost:8888 |
| 后端 API | http://localhost:8889 |
| API 文档 (Swagger) | http://localhost:8889/docs |
| API 文档 (ReDoc) | http://localhost:8889/redoc |

---

## 运维脚本

项目根目录提供了一套完整的运维脚本：

### 脚本一览

| 脚本 | 功能 | 常用命令 |
|------|------|----------|
| `start.sh` | 启动服务 | `./start.sh` |
| `stop.sh` | 停止服务 | `./stop.sh` |
| `restart.sh` | 重启服务 | `./restart.sh` |
| `status.sh` | 查看状态 | `./status.sh` |
| `deploy.sh` | 部署/初始化 | `./deploy.sh` |
| `tests/run_tests.sh` | 运行测试 | `cd tests && bash run_tests.sh` |

### 详细用法

#### `start.sh` — 启动服务

```bash
./start.sh                  # 启动前端 + 后端
./start.sh --backend-only   # 只启动后端
./start.sh --frontend-only  # 只启动前端
```

启动流程：
1. 检查 Python/Node.js 等环境依赖
2. 检查端口 8888/8889 是否可用
3. 自动创建虚拟环境并安装依赖（首次）
4. 日志轮转（超过 10MB 自动归档）
5. 启动 uvicorn 后端（端口 8889）
6. 健康检查等待后端就绪
7. 启动 Vite 前端（端口 8888）
8. 健康检查等待前端就绪

#### `stop.sh` — 停止服务

```bash
./stop.sh                   # 优雅停止所有服务
./stop.sh --backend-only    # 只停止后端
./stop.sh --frontend-only   # 只停止前端
./stop.sh --force           # 强制杀掉进程 (kill -9)
```

停止流程：
1. 通过 PID 文件发送终止信号
2. 通过进程名匹配清理残留子进程
3. 通过端口号兜底清理
4. 等待端口释放确认

#### `restart.sh` — 重启服务

```bash
./restart.sh                    # 重启全部
./restart.sh --backend-only     # 只重启后端（前端不受影响）
./restart.sh --frontend-only    # 只重启前端（后端不受影响）
./restart.sh --force            # 强制重启
```

> **重要**: 每次修改代码后，请使用 `./restart.sh` 重启服务，不要手动 kill 进程。

#### `status.sh` — 查看运行状态

```bash
./status.sh          # 查看详细状态（进程、端口、CPU、内存、日志大小等）
./status.sh --json   # JSON 格式输出（方便脚本调用）
```

输出内容包括：
- 前端/后端运行状态、PID、端口
- CPU 和内存使用率
- 进程运行时间
- 日志文件大小
- 数据库大小
- 磁盘使用情况

#### `deploy.sh` — 部署/初始化

```bash
./deploy.sh           # 首次部署（创建环境、安装依赖、初始化目录）
./deploy.sh --update  # 更新依赖（保留数据和配置）
./deploy.sh --clean   # 清理所有（删除 venv/node_modules/logs）
./deploy.sh --check   # 仅检查环境（不做任何修改）
```

#### `tests/run_tests.sh` — 运行测试

```bash
cd tests && bash run_tests.sh
```

测试模块：
1. 健康检查 & 交易所连接
2. 行情数据 API
3. 交易 API
4. 策略/回测/资金费率
5. 前端页面检查
6. E2E 页面交互测试 (Playwright)

---

## 项目结构

```
BitPro/
├── start.sh                    # 启动脚本
├── stop.sh                     # 停止脚本
├── restart.sh                  # 重启脚本
├── status.sh                   # 状态检查脚本
├── deploy.sh                   # 部署/初始化脚本
│
├── backend/                    # 后端服务 (FastAPI)
│   ├── app/
│   │   ├── main.py             # 应用入口
│   │   ├── core/
│   │   │   └── config.py       # 配置管理 (Pydantic Settings)
│   │   ├── api/
│   │   │   ├── api.py          # 路由注册
│   │   │   └── endpoints/      # API 端点
│   │   │       ├── health.py       # 健康检查
│   │   │       ├── market.py       # 行情数据
│   │   │       ├── trading.py      # 交易下单
│   │   │       ├── strategy.py     # 策略管理
│   │   │       ├── backtest.py     # 回测执行
│   │   │       ├── live_trading.py # 实盘交易
│   │   │       ├── paper_trading.py# 模拟盘（多实例）
│   │   │       ├── funding.py      # 资金费率
│   │   │       ├── monitor.py      # 监控告警
│   │   │       ├── data_sync.py    # 数据同步
│   │   │       └── websocket.py    # WebSocket
│   │   ├── services/           # 业务逻辑
│   │   │   ├── strategy_backtest.py  # 回测引擎 (v2)
│   │   │   ├── strategy_registry.py  # 策略注册中心
│   │   │   ├── paper_trading.py      # 模拟交易引擎
│   │   │   ├── auto_trader.py        # 自动交易编排器
│   │   │   ├── pro_strategies.py     # 专业策略库
│   │   │   ├── indicators.py         # 技术指标计算
│   │   │   ├── risk_manager.py       # 风险管理
│   │   │   ├── market_service.py     # 行情服务
│   │   │   ├── funding_service.py    # 资金费率服务
│   │   │   ├── data_sync_service.py  # 数据同步服务
│   │   │   ├── alert_service.py      # 告警服务
│   │   │   └── telegram_notifier.py  # Telegram 通知
│   │   ├── db/
│   │   │   └── local_db.py     # SQLite 数据库管理
│   │   ├── exchange/
│   │   │   ├── base.py         # 交易所基类
│   │   │   ├── manager.py      # 交易所管理器
│   │   │   └── okx.py          # OKX 交易所封装
│   │   ├── models/
│   │   │   └── schemas.py      # Pydantic 数据模型
│   │   └── strategies/
│   │       └── base_strategy.py# 策略基类
│   ├── requirements.txt        # Python 依赖
│   ├── .env                    # 环境变量（不入库）
│   └── .env.example            # 环境变量模板
│
├── frontend/                   # 前端应用 (React)
│   ├── src/
│   │   ├── pages/              # 页面组件
│   │   │   ├── Home.tsx            # 首页看板
│   │   │   ├── Market.tsx          # 行情监控
│   │   │   ├── Strategy.tsx        # 策略管理
│   │   │   ├── Backtest.tsx        # 策略回测
│   │   │   ├── LiveTrading.tsx     # 实盘/模拟盘
│   │   │   ├── Trading.tsx         # 交易下单
│   │   │   ├── DataManager.tsx     # 数据管理
│   │   │   └── Monitor.tsx         # 监控面板
│   │   ├── components/         # 通用组件
│   │   ├── api/
│   │   │   └── client.ts       # API 客户端
│   │   ├── stores/             # 状态管理 (Zustand)
│   │   └── types/              # TypeScript 类型定义
│   ├── vite.config.ts          # Vite 配置（端口8888，API代理到8889）
│   └── package.json
│
├── tests/                      # 测试套件
│   ├── run_tests.sh            # 测试运行脚本
│   ├── test_01_health.py       # 健康检查测试
│   ├── test_02_market.py       # 行情API测试
│   ├── test_03_trading.py      # 交易API测试
│   ├── test_04_strategy.py     # 策略回测测试
│   └── test_05_frontend.py     # 前端检查测试
│
├── docs/                       # 文档
│   ├── 美股投资完全指南.md
│   ├── 全球交割日完全指南.md
│   ├── 全球期权市场全景指南.md
│   ├── 期权入门指南.md
│   ├── Quant_Strategies_Guide.md
│   ├── Strategy_Research_Notes.md
│   ├── Technical_Reference.md
│   └── ...
│
├── logs/                       # 运行日志（自动生成）
│   ├── backend.log
│   ├── backend.pid
│   ├── frontend.log
│   └── frontend.pid
│
└── data/                       # 数据文件
```

---

## 端口约定

| 服务 | 端口 | 协议 |
|------|------|------|
| 前端 (Vite) | 8888 | HTTP |
| 后端 (Uvicorn) | 8889 | HTTP |
| WebSocket | 8889 | WS (`/api/v1/ws/*`) |

> 前端 Vite 配置了 `/api/*` 请求自动代理到后端 8889 端口，开发时无需处理跨域。

---

## 环境变量配置

复制 `backend/.env.example` 为 `backend/.env`，按需填写：

```bash
# 交易所 API（OKX）
OKX_API_KEY=your_okx_api_key          # OKX API Key
OKX_API_SECRET=your_okx_secret        # OKX Secret
OKX_PASSPHRASE=your_okx_passphrase    # OKX Passphrase
OKX_TESTNET=true                      # true=测试网, false=实盘

# 代理配置（国内访问交易所API可能需要）
# HTTP_PROXY=http://127.0.0.1:7890
# HTTPS_PROXY=http://127.0.0.1:7890

# Telegram 告警（可选）
# TELEGRAM_BOT_TOKEN=your_bot_token
# TELEGRAM_CHAT_ID=your_chat_id

# 应用配置
LOG_LEVEL=INFO                        # 日志级别: DEBUG/INFO/WARNING/ERROR
BACKEND_CORS_ORIGINS=["http://localhost:8888","http://127.0.0.1:8888"]

# 数据同步间隔（秒）
SYNC_INTERVAL_TICKER=10               # Ticker 刷新间隔
SYNC_INTERVAL_FUNDING=60              # 资金费率刷新间隔
SYNC_INTERVAL_KLINE=300               # K线数据同步间隔
```

---

## API 快速参考

```bash
# 健康检查
GET  /api/v1/health

# 行情数据
GET  /api/v1/market/ticker?exchange=okx&symbol=BTC/USDT
GET  /api/v1/market/klines?exchange=okx&symbol=BTC/USDT&timeframe=1h

# 资金费率
GET  /api/v1/funding/rates?exchange=okx
GET  /api/v1/funding/opportunities?exchange=okx&min_rate=0.0001

# 策略管理
GET  /api/v1/strategy/list
POST /api/v1/strategy/create
PUT  /api/v1/strategy/{id}

# 回测
POST /api/v1/backtest/run

# 模拟盘（支持多实例）
POST /api/v1/paper_trading/run
GET  /api/v1/paper_trading/instances
GET  /api/v1/paper_trading/instances/{instance_id}
DEL  /api/v1/paper_trading/instances/{instance_id}

# 实盘交易
GET  /api/v1/live/strategies
POST /api/v1/live/configure
POST /api/v1/live/start
POST /api/v1/live/stop
```

完整 API 文档请访问: http://localhost:8889/docs

---

## 内置策略

| 策略 | 类型 | 适用 | 说明 |
|------|------|------|------|
| 双均线交叉 | 趋势跟踪 | 中长线 | SMA 金叉/死叉 |
| RSI 超买超卖 | 均值回归 | 短线 | RSI 阈值反转 |
| MACD 动量 | 趋势/动量 | 中线 | MACD 信号线交叉 |
| 布林带突破 | 波动率 | 短线 | 布林带上下轨突破 |
| KDJ 策略 | 震荡 | 短线 | KDJ 超买超卖 |
| 资金费率套利 | 套利 | 持续 | 永续-现货价差 |
| 多时间框架 | 趋势 | 中长线 | 多周期共振确认 |
| 自适应布林带 | 波动率 | 中线 | 动态调整参数 |
| 趋势跟踪 | CTA | 中长线 | 唐奇安通道+ATR |

所有策略均存储在 SQLite 数据库中，可通过前端页面查看、编辑和选择。

---

## 常见问题

### Q: 端口被占用怎么办？

```bash
# 查看端口占用
lsof -i :8888
lsof -i :8889

# 使用 stop 脚本清理
./stop.sh --force

# 或手动清理
kill -9 $(lsof -ti :8888,:8889)
```

### Q: 后端启动失败？

```bash
# 查看后端日志
tail -100 logs/backend.log

# 常见原因:
# 1. 虚拟环境未创建 → ./deploy.sh
# 2. 依赖缺失 → source backend/venv/bin/activate && pip install -r backend/requirements.txt
# 3. .env 配置错误 → 检查 backend/.env
```

### Q: 前端启动失败？

```bash
# 查看前端日志
tail -100 logs/frontend.log

# 常见原因:
# 1. node_modules 缺失 → cd frontend && npm install
# 2. Node.js 版本过低 → 需要 Node.js 18+
```

### Q: 如何只重启后端（修改Python代码后）？

```bash
./restart.sh --backend-only
```

### Q: 如何查看当前服务状态？

```bash
./status.sh
```

### Q: 如何清理重新部署？

```bash
./deploy.sh --clean    # 清理所有生成文件
./deploy.sh            # 重新初始化
./start.sh             # 启动
```

### Q: 国内无法连接交易所 API？

在 `backend/.env` 中配置代理：

```bash
HTTP_PROXY=http://127.0.0.1:7890
HTTPS_PROXY=http://127.0.0.1:7890
```

---

## 开发计划

- [x] Phase 1: 基础架构（FastAPI + React + SQLite + CCXT）
- [x] Phase 2: 行情模块（K线、Ticker、资金费率、WebSocket）
- [x] Phase 3: 策略模块（策略引擎、内置策略、回测引擎 v2）
- [x] Phase 4: 交易模块（下单、风控、告警、Telegram通知）
- [x] Phase 5: 高级策略（多时间框架、自适应策略、资金费率套利）
- [x] 策略数据库统一存储
- [x] 模拟盘多实例并行
- [ ] Phase 6: 期权策略研发
- [ ] Phase 7: 跨市场套利
- [ ] Phase 8: AI 辅助决策

---

## 学习资源

项目 `docs/` 目录包含丰富的学习文档：

| 文档 | 内容 |
|------|------|
| [美股投资完全指南](docs/美股投资完全指南.md) | 美股市场、三大指数、交易规则、选股策略 |
| [全球交割日完全指南](docs/全球交割日完全指南.md) | 期权/期货/股指交割日时间表与市场影响 |
| [全球期权市场全景指南](docs/全球期权市场全景指南.md) | 美股/港股/A股/加密期权对比 |
| [期权入门指南](docs/期权入门指南.md) | 期权基础、Greeks、交易策略 |
| [量化策略指南](docs/Quant_Strategies_Guide.md) | 量化策略开发方法论 |
| [策略研究笔记](docs/Strategy_Research_Notes.md) | 各策略研究过程记录 |
| [技术参考文档](docs/Technical_Reference.md) | 技术指标计算方法 |

---

## 许可证

MIT License

---

## 免责声明

本项目仅供学习交流，不构成任何投资建议。加密货币市场风险极高，请谨慎投资。
