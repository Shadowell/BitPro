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

## 模块截图

### 首页看板

> 全市场行情总览，支持现货/币币/合约分类筛选，内置热门、DeFi、公链、Meme、AI 等板块标签，实时展示币种价格、24h 涨跌幅、成交额和价格走势，支持自选收藏和搜索。

![首页看板](docs/screenshots/01-home.png)

### 行情监控

> 专业级 K 线图表和订单簿深度图，支持 BTC/USDT 等主流交易对，提供 1m/5m/15m/1h/4h/1d 多个时间周期切换，WebSocket 实时推送最新价格和涨跌变动。

![行情监控](docs/screenshots/02-market.png)

### 交易下单

> 现货/合约双模式，限价/市价下单，实时价格展示。资产面板、当前挂单和历史订单三栏切换，买入/卖出快捷操作，内置风险提示。

![交易下单](docs/screenshots/03-trading.png)

### 策略中心

> 策略管理面板，展示所有策略的状态、绑定交易对、收益情况，支持策略启停控制、参数配置、脚本编辑和新建策略。

![策略中心](docs/screenshots/04-strategy.png)

### 策略回测

> 自研 v2 回测引擎，逐 bar 模拟交易，30+ 技术指标内置。BigQuant 风格核心指标面板 (累计收益/年化/夏普/胜率/盈亏比/最大回撤)，策略收益率 vs 基准指数 vs 相对收益多曲线对比图表，回撤区域可视化，支持按时间范围缩放。

![策略回测](docs/screenshots/05-backtest.png)

### 模拟盘 / 实盘交易

> 策略实盘运行面板，模拟盘/实盘一键切换，选择策略 → 配置参数 → 飞行检查 → 运行监控四步流程。策略卡片展示回测收益率、夏普比率、最大回撤等关键指标，支持风险等级标签。

![模拟盘/实盘](docs/screenshots/06-live.png)

### 监控中心

> 系统状态仪表盘，多空比、持仓量、运行中策略数、活跃告警数一览。告警规则配置支持价格突破/跌破/波动、资金费率阈值等五种类型，支持 Telegram 消息推送和 Webhook 通知。

![监控中心](docs/screenshots/07-monitor.png)

### 数据管理中心

> K 线历史数据同步管理，资金费率归档，支持按交易对、时间范围查询和数据导出，展示数据覆盖率和同步进度。

![数据管理](docs/screenshots/08-data.png)

### AI 策略研发 (v2 Multi-Agent)

> GAN-inspired 多 Agent 闭环系统：Planner 规格书 → Sprint 合约协商 → Strategist 生成 → Backtester 回测 → Evaluator 独立评估，循环迭代直至达标。支持 5 维度雷达图评分、方向决策 (Pivot/Refine)、合约验收。

![AI策略研发](docs/screenshots/09-ailab.png)

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
├── strategies/                # 策略脚本示例 (可粘贴到策略编辑器)
├── data/seed/                 # 种子数据 (17 个内置策略定义)
├── scripts/
│   ├── check.sh               # CI 检查
│   └── seed_strategies.py     # 种子策略导入脚本
├── init.sh                    # 首次初始化 (依赖+建表+导入策略)
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

### 2. 首次初始化

```bash
./init.sh
```

自动完成：创建虚拟环境、安装前后端依赖、初始化数据库、导入 17 个内置量化策略。

### 3. 启动

```bash
./start.sh
```

启动完成后：

- 前端: http://localhost:8888
- 后端: http://localhost:8889
- API 文档: http://localhost:8889/docs

### 4. 运维命令

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
