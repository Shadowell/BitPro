# BitPro — 加密货币量化交易平台

全栈量化交易平台，集行情监控、策略回测、模拟/实盘交易、AI 多 Agent 策略研发于一体。

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.11 · FastAPI · Uvicorn · SQLite · CCXT |
| 前端 | React 18 · TypeScript · Vite · TailwindCSS · Zustand |
| 交易所 | OKX (现货 + 合约)，通过 CCXT 统一接口 |
| AI Agent | 通义千问 Qwen (OpenAI 兼容 API) · 多 Agent 闭环架构 |
| 运维 | Bash 脚本一键启停 · 日志轮转 · 健康检查 |

## 功能模块

### 行情与交易

- **首页看板** — 全市场行情总览，支持板块筛选 (热门/DeFi/公链/Meme/AI)，实时价格和 24h 涨跌
- **行情监控** — 专业 K 线图表 + 订单簿深度图，多时间周期切换，WebSocket 实时推送
- **交易下单** — 限价/市价下单，持仓管理，账户余额和订单历史
- **模拟盘/实盘** — 策略实盘运行，支持模拟盘验证后再上线

### 策略与回测

- **策略中心** — 策略管理、参数配置、启停控制
- **策略回测** — 自研 v2 回测引擎，逐 bar 模拟，30+ 技术指标内置，完整绩效报告 (夏普/回撤/胜率/盈亏比)

### AI 多 Agent 策略研发 (v2)

基于 [Anthropic Harness Design](https://www.anthropic.com/engineering/harness-design-long-running-apps) 论文思想构建的 GAN-inspired 多 Agent 闭环系统：

```
Planner (规格书) → [Sprint 合约协商 → Strategist (生成) → Backtester (回测) → Evaluator (评估)] × N
```

| Agent | 职责 |
|---|---|
| **Planner** | 将用户简短 prompt 扩展为完整策略规格书 (市场分析 + 候选方向 + 迭代计划) |
| **Strategist** | 生成 Python 策略代码，支持 Sprint 合约约束 |
| **Backtester** | 在 v2 引擎中执行回测 (无 LLM，纯计算) |
| **Evaluator** | 独立于 Generator 的评估者，5 维度量化打分 + Pivot/Refine 方向决策 |

核心机制：
- **分离生成与评估** — 消除 LLM 自我评估偏见
- **多维度评分** — 风控 (25%) · 盈利 (25%) · 稳健 (20%) · 逻辑 (15%) · 原创 (15%)
- **Sprint 合约** — 每轮迭代前 Strategist 和 Evaluator 协商验收标准
- **Context Reset** — 每轮结构化交接文档，防止上下文退化
- **Pivot/Refine** — 根据评分趋势自动决定优化当前策略还是换方向
- **代码沙箱** — AST 静态分析 + 受限 exec，防止 AI 生成危险代码

### 监控与数据

- **监控中心** — 系统状态、交易所连接、策略运行监控、告警 (Telegram)
- **数据管理** — K 线历史数据同步、资金费率归档、数据导出

## 项目结构

```
BitPro/
├── backend/
│   ├── app/
│   │   ├── api/endpoints/     # REST API 端点
│   │   ├── core/              # 配置、错误处理
│   │   ├── db/                # SQLite 数据层
│   │   ├── exchange/          # 交易所适配 (OKX/CCXT)
│   │   ├── services/          # 业务逻辑
│   │   │   └── agent/         # AI 多 Agent 系统
│   │   │       ├── planner_agent.py
│   │   │       ├── strategist_agent.py
│   │   │       ├── backtester_agent.py
│   │   │       ├── evaluator_agent.py
│   │   │       ├── orchestrator.py
│   │   │       ├── code_sandbox.py
│   │   │       ├── llm_client.py
│   │   │       ├── prompts.py
│   │   │       └── schemas.py
│   │   └── strategies/        # 策略基类
│   ├── .env.example
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── pages/             # 9 个功能页面
│       ├── components/        # K 线图、订单簿等组件
│       ├── hooks/             # WebSocket hook
│       └── stores/            # Zustand 状态管理
├── start.sh                   # 一键启动
├── stop.sh                    # 一键停止
├── restart.sh                 # 重启
└── status.sh                  # 状态检查
```

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+
- 代理软件 (国内访问 OKX 需要)

### 1. 配置环境变量

```bash
cd backend
cp .env.example .env
```

编辑 `backend/.env`，填入：

```bash
# 必填 — OKX 交易所 API
OKX_API_KEY=your_key
OKX_API_SECRET=your_secret
OKX_PASSPHRASE=your_passphrase

# 必填 (国内) — 代理
HTTP_PROXY=http://127.0.0.1:7890
HTTPS_PROXY=http://127.0.0.1:7890

# 可选 — AI Agent 功能
QWEN_API_KEY=your_qwen_api_key
QWEN_MODEL=qwen3.5-flash
```

### 2. 启动

```bash
./start.sh
```

首次启动会自动创建虚拟环境、安装依赖。启动完成后：

- 前端: http://localhost:8888
- 后端: http://localhost:8889
- API 文档: http://localhost:8889/docs

### 3. 运维命令

```bash
./status.sh          # 查看服务状态
./stop.sh            # 停止所有服务
./restart.sh         # 重启
./start.sh --backend-only   # 只启动后端
./start.sh --frontend-only  # 只启动前端
```

## API 概览

| 模块 | 端点前缀 | 说明 |
|---|---|---|
| 行情 | `/api/v1/market` | Tickers、K 线、订单簿 |
| 交易 | `/api/v1/trading` | 下单、撤单、持仓 |
| 策略 | `/api/v1/strategy` | 策略 CRUD、启停 |
| 回测 | `/api/v1/backtest` | 执行回测、查看结果 |
| AI Agent | `/api/v1/agent` | 创建任务、查看迭代、接受策略 |
| 监控 | `/api/v1/monitor` | 系统状态、告警 |
| 数据 | `/api/v1/data-sync` | K 线/资金费率同步 |
| WebSocket | `/api/v1/ws` | 实时行情推送 |

## 配置项

| 变量 | 说明 | 默认值 |
|---|---|---|
| `OKX_API_KEY` | OKX API Key | — |
| `OKX_API_SECRET` | OKX Secret | — |
| `OKX_PASSPHRASE` | OKX Passphrase | — |
| `OKX_TESTNET` | 是否使用测试网 | `true` |
| `HTTP_PROXY` | HTTP 代理地址 | — |
| `QWEN_API_KEY` | 通义千问 API Key (AI Agent) | — |
| `QWEN_MODEL` | Qwen 模型名 | `qwen3.5-flash` |
| `LOG_LEVEL` | 日志级别 | `INFO` |
| `BACKEND_CORS_ORIGINS` | CORS 白名单 | `localhost:8888` |

## License

MIT
