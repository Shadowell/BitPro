# BitPro - 加密货币量化交易平台

> 一站式 Crypto 量化交易工具：行情监控、策略开发、回测、实盘

![Version](https://img.shields.io/badge/version-1.0-blue)
![Python](https://img.shields.io/badge/python-3.11+-green)
![React](https://img.shields.io/badge/react-18-blue)
![License](https://img.shields.io/badge/license-MIT-green)

---

## 功能特性

| 模块 | 功能 | 说明 |
|------|------|------|
| **首页看板** | 行情概览、资金费率套利机会、市场指标 | 一站式数据面板 |
| **行情监控** | K线图、订单簿、成交记录 | 支持 Binance/OKX/Bybit |
| **策略开发** | Python 策略编写、策略管理 | 内置套利、网格等模板 |
| **策略回测** | 历史数据回测、绩效分析 | 夏普、回撤等指标 |
| **实时监控** | 策略运行状态、告警系统 | 支持 Telegram 通知 |

---

## 技术架构

```
Frontend (React + TypeScript + Vite)
          │
          ▼
Backend (FastAPI + Python 3.11)
          │
    ┌─────┴─────┐
    ▼           ▼
SQLite DB    CCXT API
(本地缓存)   (Binance/OKX/Bybit)
```

---

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+
- npm 或 yarn

### 1. 克隆项目

```bash
git clone <repo-url>
cd BitPro
```

### 2. 启动后端

```bash
cd backend

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量 (可选，公开数据无需 API Key)
cp .env.example .env
# 编辑 .env 填入交易所 API Key

# 启动服务
uvicorn app.main:app --reload --port 8000
```

### 3. 启动前端

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

### 4. 访问应用

- 前端: http://localhost:8888
- API 文档: http://localhost:8889/docs

---

## 项目结构

```
BitPro/
├── backend/                    # 后端服务
│   ├── app/
│   │   ├── api/endpoints/      # API 端点
│   │   ├── services/           # 业务服务
│   │   ├── db/                 # 数据库
│   │   ├── exchange/           # 交易所封装
│   │   ├── strategies/         # 策略模板
│   │   └── main.py             # 应用入口
│   └── requirements.txt
│
├── frontend/                   # 前端应用
│   ├── src/
│   │   ├── pages/              # 页面组件
│   │   ├── components/         # 通用组件
│   │   ├── api/                # API 客户端
│   │   ├── stores/             # 状态管理
│   │   └── types/              # 类型定义
│   └── package.json
│
├── docs/                       # 文档
├── scripts/                    # 脚本工具
├── strategies/                 # 用户策略
├── data/                       # 数据目录
├── Crypto_Quant_Guide.md       # 完整指南文档
└── README.md
```

---

## API 快速参考

```bash
# 获取行情
GET /api/v1/market/ticker?exchange=binance&symbol=BTC/USDT

# 获取 K 线
GET /api/v1/market/klines?exchange=binance&symbol=BTC/USDT&timeframe=1h

# 获取资金费率
GET /api/v1/funding/rates?exchange=binance

# 获取套利机会
GET /api/v1/funding/opportunities?exchange=binance&min_rate=0.0001

# 策略列表
GET /api/v1/strategy/list

# 创建策略
POST /api/v1/strategy/create
```

完整 API 文档请访问 http://localhost:8889/docs

---

## 配置说明

### 后端环境变量 (backend/.env)

```bash
# 交易所 API (可选，公开数据无需配置)
BINANCE_API_KEY=your_api_key
BINANCE_API_SECRET=your_secret
BINANCE_TESTNET=true

OKX_API_KEY=your_api_key
OKX_API_SECRET=your_secret
OKX_PASSPHRASE=your_passphrase
OKX_TESTNET=true

# 应用配置
LOG_LEVEL=INFO
BACKEND_CORS_ORIGINS=["http://localhost:5173"]
```

---

## 开发计划

- [x] Phase 1: 基础架构
  - [x] 项目结构
  - [x] FastAPI 框架
  - [x] 数据库设计
  - [x] CCXT 交易所封装
  - [x] React 前端框架

- [x] Phase 2: 行情模块
  - [x] 实时行情 API
  - [x] K线数据 + ECharts 图表
  - [x] 资金费率
  - [x] WebSocket 实时推送

- [x] Phase 3: 策略模块
  - [x] 策略执行引擎
  - [x] 内置策略模板 (套利/双均线/网格)
  - [x] 回测引擎

- [x] Phase 4: 交易与监控
  - [x] 交易 API
  - [x] 告警系统
  - [x] Telegram 通知

---

## 学习资源

详细的 B 圈量化学习指南请查看 [Crypto_Quant_Guide.md](./Crypto_Quant_Guide.md)，包含：

- 股市 vs Crypto 核心差异
- B圈术语详解（资金费率、永续合约等）
- 交易所选择与账户准备
- 策略开发路径（套利 → CTA → 高频）
- 避坑指南与风险控制

---

## 许可证

MIT License

---

## 免责声明

本项目仅供学习交流，不构成任何投资建议。加密货币市场风险极高，请谨慎投资。
