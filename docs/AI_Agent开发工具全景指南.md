# AI Agent 开发工具全景指南

> 从零了解 Agent 是什么、主流框架对比、如何选择、如何上手

---

## 目录

1. [Agent 是什么](#1-agent-是什么)
2. [Agent 核心架构](#2-agent-核心架构)
3. [主流 Agent 框架对比](#3-主流-agent-框架对比)
4. [LangChain 生态](#4-langchain-生态)
5. [LlamaIndex](#5-llamaindex)
6. [CrewAI — 多 Agent 协作](#6-crewai)
7. [AutoGen — 微软多 Agent](#7-autogen)
8. [Dify — 低代码 Agent 平台](#8-dify)
9. [Coze (扣子) — 字节跳动](#9-coze)
10. [OpenAI Agents SDK](#10-openai-agents-sdk)
11. [其他重要工具](#11-其他重要工具)
12. [模型服务与 API](#12-模型服务与-api)
13. [向量数据库](#13-向量数据库)
14. [Agent 开发实战选型](#14-agent-开发实战选型)
15. [学习路线图](#15-学习路线图)

---

## 1. Agent 是什么

### 一句话定义

```
AI Agent = LLM（大脑）+ Tools（工具）+ Memory（记忆）+ Planning（规划）

它不只是"聊天机器人"，而是一个能：
  - 理解任务
  - 拆解步骤
  - 调用工具
  - 自主决策
  - 迭代执行
  - 完成目标
的自主智能体
```

### ChatBot vs Agent

```
ChatBot（聊天机器人）：
  用户问 → 模型答 → 结束
  单轮或多轮对话，但不执行实际操作

Agent（智能体）：
  用户给目标 → Agent 拆解任务 → 调用工具 → 观察结果 → 继续推理 → 循环直到完成
  
  关键区别：Agent 有"行动能力"和"自主决策能力"
```

### 经典例子

```
用户: "帮我查一下比特币今天的价格，如果跌破 60000 就买入 0.1 BTC"

ChatBot 的反应:
  "比特币当前价格是 $59,800，已经跌破 60000。
   您可以在交易所手动下单买入。"
  （只给建议，不行动）

Agent 的反应:
  1. 思考: 需要查价格 → 调用行情 API
  2. 工具调用: get_btc_price() → $59,800
  3. 思考: $59,800 < $60,000，需要买入
  4. 工具调用: place_order(BTC, buy, 0.1)
  5. 观察: 订单已成交，成交价 $59,810
  6. 回复: "BTC 当前价 $59,800，已跌破 60000，
          我已帮您买入 0.1 BTC，成交价 $59,810。"
  （理解 → 判断 → 行动 → 反馈）
```

---

## 2. Agent 核心架构

### 2.1 ReAct 模式（最经典）

```
ReAct = Reasoning + Acting（推理 + 行动）

循环流程：
  Thought（思考）→ Action（行动）→ Observation（观察）→ Thought → ...

示例：
  Thought:  用户需要查天气，我应该调用天气 API
  Action:   call weather_api("北京")
  Observation: 北京今天 15°C，多云
  Thought:  我已经获得了天气信息，可以回答用户了
  Answer:   北京今天 15°C，多云，建议穿薄外套

这是 LangChain Agent、OpenAI Function Calling 的底层原理
```

### 2.2 Agent 的四大组件

```
┌─────────────────────────────────────────┐
│              AI Agent                    │
│                                         │
│  ┌──────────┐     ┌──────────────┐      │
│  │   LLM    │     │   Planning   │      │
│  │  (大脑)   │────▶│  (规划拆解)  │      │
│  └──────────┘     └──────────────┘      │
│       │                  │              │
│       ▼                  ▼              │
│  ┌──────────┐     ┌──────────────┐      │
│  │  Memory  │     │    Tools     │      │
│  │  (记忆)   │     │  (工具调用)  │      │
│  └──────────┘     └──────────────┘      │
│                                         │
└─────────────────────────────────────────┘

1. LLM（大脑）：
   GPT-4, Claude, Qwen, DeepSeek 等
   负责理解、推理、决策

2. Tools（工具）：
   API 调用、数据库查询、代码执行、文件操作、浏览器操作等
   Agent 的"手和脚"

3. Memory（记忆）：
   短期记忆 = 对话上下文
   长期记忆 = 向量数据库存储的历史信息
   让 Agent 能"记住"之前的交互和知识

4. Planning（规划）：
   任务拆解、步骤排序、错误重试
   决定"先做什么，后做什么"
```

### 2.3 Function Calling（函数调用）

```
这是 Agent 调用工具的核心机制

流程：
  1. 开发者定义工具（函数名 + 参数描述 + 功能说明）
  2. 把工具列表发给 LLM
  3. LLM 根据用户请求，决定调用哪个工具、传什么参数
  4. 系统执行工具，把结果返回给 LLM
  5. LLM 根据结果继续推理或回答

支持 Function Calling 的模型：
  OpenAI GPT-4/4o/4o-mini ✅（最成熟）
  Claude 3/3.5/4 ✅（Tool Use）
  Qwen 2.5 ✅
  DeepSeek V3/R1 ✅
  Gemini 2.0 ✅
  GLM-4 ✅
```

### 2.4 RAG（检索增强生成）

```
RAG = Retrieval-Augmented Generation

解决 LLM 的两大痛点：
  1. 知识截止日期（训练数据有时效性）
  2. 专有知识不在训练数据中

流程：
  用户问题 → 向量检索（从知识库找相关文档）→ 把检索结果 + 问题一起发给 LLM → 生成回答

  例子：
  问："我们公司的退款政策是什么？"
  1. 从公司文档向量库检索"退款政策"相关段落
  2. 把检索到的段落作为上下文发给 LLM
  3. LLM 基于这些段落生成准确回答

RAG vs Fine-tuning：
  RAG：不改模型，实时检索，数据可随时更新 → 推荐
  Fine-tuning：修改模型权重，需要重新训练 → 成本高
```

### 2.5 MCP（Model Context Protocol）

```
MCP = Anthropic 提出的模型上下文协议（2024年底发布）

类比：USB 接口标准
  USB 之前：每个设备有自己的接口 → 混乱
  USB 之后：统一接口 → 任何设备都能连接

MCP 之前：每个 Agent 框架自己定义工具接口 → 不兼容
MCP 之后：统一的工具/资源/提示词协议 → 互通

架构：
  MCP Host（客户端）：Claude Desktop, Cursor, IDEs
  MCP Server（服务端）：提供工具能力（文件系统、数据库、API等）
  
  一个 MCP Server 可以同时被多个 Host 使用
  一个 Host 可以同时连接多个 MCP Server

现状（2026年初）：
  Cursor IDE 已原生支持 MCP
  Claude Desktop 已原生支持 MCP
  VS Code 已支持 MCP
  越来越多工具在发布 MCP Server
  
  可能成为 Agent 工具生态的标准协议
```

---

## 3. 主流 Agent 框架对比

### 总览表

```
┌──────────────┬────────┬──────────┬──────────┬───────────┬──────────┐
│ 框架          │ 语言    │ 难度     │ 特点      │ 适合场景   │ Star     │
├──────────────┼────────┼──────────┼──────────┼───────────┼──────────┤
│ LangChain    │ Python │ ★★★☆    │ 最全面    │ 通用Agent  │ 100k+   │
│ LlamaIndex   │ Python │ ★★★☆    │ RAG最强   │ 知识库Agent│ 38k+    │
│ CrewAI       │ Python │ ★★☆☆    │ 多Agent   │ 团队协作   │ 25k+    │
│ AutoGen      │ Python │ ★★★☆    │ 微软出品  │ 多Agent    │ 38k+    │
│ Dify         │ Python │ ★☆☆☆    │ 低代码    │ 快速搭建   │ 60k+    │
│ Coze(扣子)   │ 可视化  │ ★☆☆☆    │ 零代码    │ 快速原型   │ N/A     │
│ OpenAI SDK   │ Python │ ★★☆☆    │ 官方出品  │ OpenAI生态 │ 5k+     │
│ Semantic K.  │ C#/Py  │ ★★★☆    │ 微软企业级│ .NET生态   │ 22k+    │
│ Haystack     │ Python │ ★★★☆    │ 管道式    │ 搜索/RAG   │ 18k+    │
│ Agno(phidata)│ Python │ ★★☆☆    │ 轻量简洁  │ 快速开发   │ 18k+    │
│ smolagents   │ Python │ ★★☆☆    │ HF出品    │ 代码Agent  │ 15k+    │
│ Mastra       │ TS     │ ★★☆☆    │ TypeScript│ JS/TS生态  │ 10k+    │
└──────────────┴────────┴──────────┴──────────┴───────────┴──────────┘

Star 数据为 2026 年初近似值
```

### 选择建议速查

```
"我是 Python 新手，想快速做一个 Agent"
  → Dify 或 Coze（零/低代码，拖拽搭建）

"我要做 RAG 知识库问答"
  → LlamaIndex（RAG 最专业）或 Dify（最快）

"我要做复杂的多步骤 Agent"
  → LangChain（最成熟）或 LangGraph（有状态流程）

"我要多个 Agent 协作完成任务"
  → CrewAI（最简单）或 AutoGen（最灵活）

"我用 OpenAI 的模型"
  → OpenAI Agents SDK（官方，最直接）

"我用 TypeScript/Node.js"
  → Mastra 或 Vercel AI SDK

"我要企业级 .NET 项目"
  → Semantic Kernel（微软官方）
```

---

## 4. LangChain 生态

### 4.1 概述

```
LangChain 是目前最流行的 Agent 开发框架
由 Harrison Chase 创建（2022年10月），发展极快

核心理念：
  用"链"（Chain）把 LLM 和各种组件串起来

生态全家桶：
  langchain-core  → 核心抽象和接口
  langchain       → 主框架（Chains, Agents, Tools）
  langgraph       → 有状态的 Agent 工作流（图结构）
  langsmith       → 可观测性/调试/监控平台
  langserve       → Agent 部署为 API
```

### 4.2 核心概念

```
Models（模型）：
  支持 OpenAI, Claude, Qwen, DeepSeek, Ollama 等几乎所有模型
  统一接口，切换模型只需改一行代码

Prompts（提示词）：
  PromptTemplate → 模板化提示词
  ChatPromptTemplate → 对话式提示词
  支持变量注入、Few-shot 示例

Chains（链）：
  把多个步骤串联起来
  例: 提示词 → LLM → 解析输出 → 下一步

Agents（智能体）：
  ReAct Agent → 推理+行动循环
  Tool-calling Agent → 基于 Function Calling
  Plan-and-Execute → 先规划后执行

Tools（工具）：
  内置 100+ 工具：搜索、计算、代码执行、API 调用等
  自定义工具非常简单（装饰器方式）

Memory（记忆）：
  ConversationBufferMemory → 完整对话记录
  ConversationSummaryMemory → 摘要式记忆
  VectorStoreMemory → 向量检索式记忆

Retrievers（检索器）：
  向量检索、关键词检索、混合检索
  支持各种向量数据库
```

### 4.3 代码示例

```python
# 基础 Agent 示例（LangChain + OpenAI）
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate

# 1. 定义工具
@tool
def get_btc_price() -> str:
    """获取比特币当前价格"""
    import requests
    resp = requests.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd")
    price = resp.json()["bitcoin"]["usd"]
    return f"BTC 当前价格: ${price:,.2f}"

@tool
def calculate(expression: str) -> str:
    """计算数学表达式"""
    return str(eval(expression))

# 2. 创建 LLM
llm = ChatOpenAI(model="gpt-4o", temperature=0)

# 3. 创建提示词
prompt = ChatPromptTemplate.from_messages([
    ("system", "你是一个加密货币助手，可以查询价格和进行计算。"),
    ("human", "{input}"),
    ("placeholder", "{agent_scratchpad}"),
])

# 4. 创建 Agent
tools = [get_btc_price, calculate]
agent = create_tool_calling_agent(llm, tools, prompt)
executor = AgentExecutor(agent=agent, tools=tools, verbose=True)

# 5. 运行
result = executor.invoke({"input": "比特币现在多少钱？如果我买 0.5 个要花多少？"})
print(result["output"])
```

### 4.4 LangGraph（高级版）

```
LangGraph = LangChain 的"进化版"
用图（Graph）结构替代线性链（Chain）

优势：
  - 有状态管理（State）
  - 支持条件分支（if-else 路由）
  - 支持循环（Agent 循环执行）
  - 支持人工介入（Human-in-the-loop）
  - 支持多 Agent 编排
  - 更好的错误处理和恢复

适合：
  - 复杂的多步骤工作流
  - 需要人工审批的流程
  - 多 Agent 协作场景

代码示例（概念）：

  from langgraph.graph import StateGraph

  # 定义状态
  graph = StateGraph(AgentState)

  # 添加节点
  graph.add_node("analyze", analyze_task)
  graph.add_node("search", search_info)
  graph.add_node("generate", generate_answer)
  graph.add_node("review", human_review)

  # 添加边（流程）
  graph.add_edge("analyze", "search")
  graph.add_edge("search", "generate")
  graph.add_conditional_edges("generate",
      should_review,
      {"yes": "review", "no": END}
  )

  app = graph.compile()
```

---

## 5. LlamaIndex

### 5.1 概述

```
LlamaIndex（原 GPT Index）= RAG 领域的王者

创始人：Jerry Liu
定位：专注于数据连接和知识检索

核心优势：
  1. 最丰富的数据连接器（160+ 种数据源）
  2. 最专业的索引和检索策略
  3. 开箱即用的 RAG 管线
  4. 支持多模态（文本+图片+表格）

LlamaIndex vs LangChain：
  LlamaIndex → "数据专家"，擅长 RAG 和知识管理
  LangChain  → "全能选手"，擅长 Agent 和工具调用
  
  很多项目两者配合使用：
  LlamaIndex 负责 RAG → LangChain 负责 Agent 逻辑
```

### 5.2 核心功能

```
数据连接器（LlamaHub）：
  文件：PDF, DOCX, PPT, Excel, Markdown, HTML
  数据库：MySQL, PostgreSQL, MongoDB
  网页：爬虫, Notion, Confluence, Slack
  API：GitHub, Jira, Google Drive
  ... 160+ 种数据源

索引类型：
  VectorStoreIndex   → 向量索引（最常用）
  TreeIndex          → 树状索引（层级结构）
  KeywordTableIndex  → 关键词索引
  KnowledgeGraphIndex→ 知识图谱索引

查询引擎：
  简单问答 → 直接检索+生成
  子问题分解 → 复杂问题拆成多个子问题
  多文档查询 → 跨多个文档检索
  结构化查询 → SQL/表格查询

Agent 集成：
  ReActAgent → 内置 ReAct Agent
  可用 LlamaIndex 的检索能力作为 Agent 工具
```

### 5.3 代码示例

```python
# RAG 问答系统（5行代码）
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader

# 1. 加载文档
documents = SimpleDirectoryReader("./docs").load_data()

# 2. 构建索引
index = VectorStoreIndex.from_documents(documents)

# 3. 查询
query_engine = index.as_query_engine()
response = query_engine.query("BitPro 支持哪些交易所？")
print(response)
```

---

## 6. CrewAI

### 6.1 概述

```
CrewAI = 多 Agent 协作框架

核心理念：
  一个人（Agent）能力有限
  多个各有专长的 Agent 组成"团队"（Crew）
  各司其职，协作完成复杂任务

类比：
  一个创业团队：
    CEO（规划者）+ 程序员（执行者）+ 设计师（创意者）+ QA（审查者）
  
  每个角色是一个 Agent，有自己的：
    - Role（角色定义）
    - Goal（目标）
    - Backstory（背景故事）
    - Tools（可用工具）
```

### 6.2 核心概念

```
Agent（智能体）：
  有角色、目标、背景故事的 AI 实体
  
Task（任务）：
  具体要完成的工作，指定给某个 Agent
  
Crew（团队）：
  多个 Agent + 多个 Task 的编排
  
Process（流程）：
  Sequential（顺序执行）
  Hierarchical（层级式，有 Manager Agent）
```

### 6.3 代码示例

```python
from crewai import Agent, Task, Crew

# 1. 定义 Agent
researcher = Agent(
    role="加密货币研究分析师",
    goal="深入研究并分析加密货币市场趋势",
    backstory="你是一个有10年经验的加密货币分析师...",
    tools=[search_tool, price_tool],
    llm="gpt-4o"
)

writer = Agent(
    role="投资报告撰写者",
    goal="将研究结果写成清晰的投资报告",
    backstory="你是一个专业的金融报告撰写者...",
    llm="gpt-4o"
)

# 2. 定义任务
research_task = Task(
    description="研究 BTC 和 ETH 本周的市场表现和关键事件",
    agent=researcher,
    expected_output="包含价格走势、关键事件、技术分析的研究报告"
)

report_task = Task(
    description="基于研究结果，撰写一份投资建议报告",
    agent=writer,
    expected_output="500字的投资建议报告，包含买入/卖出建议"
)

# 3. 组建团队执行
crew = Crew(
    agents=[researcher, writer],
    tasks=[research_task, report_task],
    verbose=True
)

result = crew.kickoff()
```

---

## 7. AutoGen

### 7.1 概述

```
AutoGen = 微软研究院出品的多 Agent 对话框架

核心特点：
  - Agent 之间通过"对话"协作
  - 支持人类参与对话（Human-in-the-loop）
  - 可以生成和执行代码
  - 灵活的对话流程控制

AutoGen vs CrewAI：
  AutoGen → 更灵活、更底层、学习曲线更陡
  CrewAI  → 更简单、更直观、上手更快
```

### 7.2 核心概念

```
ConversableAgent：可对话的 Agent 基类
AssistantAgent：AI 助手（由 LLM 驱动）
UserProxyAgent：用户代理（可执行代码、请求人工输入）
GroupChat：多 Agent 群聊
GroupChatManager：群聊管理者（决定谁发言）
```

### 7.3 代码示例

```python
from autogen import AssistantAgent, UserProxyAgent

# 1. 创建助手
assistant = AssistantAgent(
    name="crypto_analyst",
    system_message="你是加密货币分析师，擅长分析市场数据和策略。",
    llm_config={"model": "gpt-4o"}
)

# 2. 创建用户代理（可执行代码）
user_proxy = UserProxyAgent(
    name="trader",
    human_input_mode="NEVER",  # 不需要人工输入
    code_execution_config={"work_dir": "coding"}
)

# 3. 开始对话
user_proxy.initiate_chat(
    assistant,
    message="分析 BTC 最近一周的价格走势，用 Python 画出 K 线图"
)
# assistant 会生成 Python 代码 → user_proxy 自动执行 → 返回结果
```

---

## 8. Dify

### 8.1 概述

```
Dify = 开源的低代码 AI 应用开发平台

特点：
  - 可视化拖拽搭建 Agent/RAG/Workflow
  - 不用写代码也能做 Agent
  - 支持私有部署
  - 内置模型管理（接多个 LLM 提供商）
  - 内置 RAG 引擎（文档知识库）
  - 内置监控和日志

GitHub Star：60k+（截至2026年初，增长极快）

适合：
  - 不想写代码的用户
  - 快速验证 Agent 想法
  - 企业内部 AI 应用搭建
  - 团队协作开发 Agent
```

### 8.2 核心功能

```
四种应用类型：
  1. 聊天助手（Chatbot）→ 对话式应用
  2. Agent    → 带工具调用的智能体
  3. 文本生成 → 单次输入输出
  4. Workflow → 可视化工作流编排

关键能力：
  模型接入：OpenAI, Claude, Qwen, DeepSeek, Ollama, 本地模型
  知识库：PDF/Word/网页 → 向量化 → RAG 检索
  工具：内置 Google搜索、天气、计算器等，支持自定义 API
  Workflow：拖拽式流程编排，支持条件分支、循环、代码节点
  API 发布：搭建好的应用可直接生成 API
```

### 8.3 部署方式

```bash
# Docker 一键部署
git clone https://github.com/langgenius/dify.git
cd dify/docker
docker compose up -d

# 访问 http://localhost/install 初始化
# 支持 PostgreSQL + Redis + Weaviate/Qdrant
```

---

## 9. Coze（扣子）

### 9.1 概述

```
Coze（国内叫"扣子"）= 字节跳动的 AI Bot 开发平台

特点：
  - 零代码，纯可视化
  - 免费使用（含免费模型额度）
  - 可发布到微信、飞书、Discord、Telegram 等平台
  - 内置丰富的插件市场
  - 支持工作流、知识库、长期记忆

国际版：coze.com
国内版：coze.cn（扣子）

适合：
  - 完全不会编程的用户
  - 想快速做一个能用的 Bot
  - 需要接入即时通讯平台的场景
```

### 9.2 核心功能

```
Bot 搭建：
  设定人设 → 添加技能 → 添加知识库 → 测试 → 发布

插件（Plugins）：
  内置 500+ 插件（搜索、天气、翻译、图片生成等）
  可自定义 API 插件

工作流（Workflow）：
  可视化拖拽
  支持条件判断、循环、变量
  支持 JavaScript 代码节点

知识库：
  上传文档（PDF/Word/Excel/网页）
  自动切割和向量化
  支持表格类型文档

记忆（Memory）：
  短期记忆（对话历史）
  长期记忆（跨对话记住用户偏好）

发布渠道：
  微信公众号/服务号
  飞书/Lark
  Discord
  Telegram
  Slack
  网页嵌入
  API 调用
```

---

## 10. OpenAI Agents SDK

### 10.1 概述

```
OpenAI 官方的 Agent 开发 SDK（2025年3月发布）

前身是 "Swarm"（OpenAI 实验性多 Agent 框架）

特点：
  - OpenAI 官方出品，与 GPT 模型深度集成
  - 原生支持 Function Calling + Code Interpreter
  - 内置 Handoff（Agent 之间任务交接）
  - 内置 Guardrails（安全护栏）
  - Tracing（追踪调试）

定位：
  如果你只用 OpenAI 模型 → 这是最直接的选择
  如果需要多模型支持 → 用 LangChain 或其他框架
```

### 10.2 核心概念

```python
from openai import agents

# Agent：有指令和工具的智能体
agent = agents.Agent(
    name="crypto_helper",
    instructions="你是一个加密货币助手...",
    tools=[get_price, place_order]
)

# Handoff：Agent 之间的任务交接
analyst = agents.Agent(name="analyst", ...)
trader = agents.Agent(name="trader", ...)
# analyst 可以把"执行交易"的任务交给 trader

# Guardrails：安全护栏
# 可以定义输入/输出的校验规则
# 防止 Agent 执行危险操作

# Runner：运行 Agent
result = agents.Runner.run_sync(agent, "查一下 BTC 价格")
```

---

## 11. 其他重要工具

### 11.1 Semantic Kernel（微软）

```
微软官方的 AI 编排 SDK

特点：
  - 支持 C# 和 Python
  - 企业级设计，适合 .NET 生态
  - 与 Azure OpenAI 深度集成
  - "Plugin" 概念清晰

适合：企业级 .NET 项目、Azure 用户
```

### 11.2 Haystack（deepset）

```
专注于 NLP 管道和 RAG 的框架

特点：
  - Pipeline（管道）式设计
  - 模块化组件（Retriever, Reader, Generator）
  - 适合构建搜索和问答系统
  - 社区活跃

适合：搜索引擎、问答系统
```

### 11.3 Agno（原 Phidata）

```
轻量级 Agent 框架

特点：
  - 代码极简（几行代码创建 Agent）
  - 内置 Web UI
  - 支持多模型
  - 活跃开发中

适合：快速原型开发
```

### 11.4 smolagents（Hugging Face）

```
Hugging Face 出品的轻量 Agent 框架

特点：
  - Code Agent → Agent 生成 Python 代码来执行任务
  - 轻量（核心代码 < 1000 行）
  - 与 Hugging Face Hub 深度集成
  - 支持本地模型

适合：喜欢 Hugging Face 生态的开发者
```

### 11.5 Mastra

```
TypeScript/JavaScript 的 Agent 框架

特点：
  - 原生 TypeScript
  - 支持 Workflow、RAG、Agent
  - 集成 100+ 工具
  - 适合前端/全栈开发者

适合：TypeScript/JavaScript 开发者
```

### 11.6 n8n / Flowise

```
n8n：开源工作流自动化工具
  - 可视化拖拽
  - 内置 AI 节点（LLM, Agent, RAG）
  - 400+ 集成（Gmail, Slack, Database...）
  - 可私有部署

Flowise：基于 LangChain 的低代码 Agent 平台
  - 拖拽搭建 LangChain 工作流
  - 开源免费
  - Docker 部署
```

---

## 12. 模型服务与 API

### 12.1 商业 API

```
┌────────────────┬────────────────────┬──────────┬───────────────┐
│ 提供商          │ 主力模型            │ 价格      │ 特点           │
├────────────────┼────────────────────┼──────────┼───────────────┤
│ OpenAI         │ GPT-4o, o1, o3     │ $$$      │ 最成熟的生态    │
│ Anthropic      │ Claude 4, 3.5      │ $$$      │ 最好的代码能力  │
│ Google         │ Gemini 2.0         │ $$       │ 多模态最强      │
│ 阿里云          │ Qwen 2.5, QwQ      │ $        │ 中文最强之一    │
│ DeepSeek       │ DeepSeek V3, R1    │ $        │ 性价比极高      │
│ 百度            │ 文心一言 4.0        │ $        │ 中文生态       │
│ Mistral        │ Mistral Large 2    │ $$       │ 欧洲最强       │
│ xAI            │ Grok 3             │ $$       │ 推理能力强      │
└────────────────┴────────────────────┴──────────┴───────────────┘

$ = 便宜  $$ = 中等  $$$ = 较贵

推荐组合：
  主力：Claude 4 / GPT-4o（复杂任务）
  辅助：DeepSeek V3 / Qwen 2.5（简单任务，省钱）
  推理：o3 / DeepSeek R1 / QwQ（需要深度思考的任务）
```

### 12.2 本地部署

```
Ollama（推荐）：
  一行命令运行开源模型
  ollama run llama3.3
  ollama run qwen2.5:72b
  ollama run deepseek-r1:14b
  支持 macOS/Linux/Windows
  API 兼容 OpenAI 格式

vLLM：
  高性能推理引擎
  支持 GPU 加速
  适合生产环境

llama.cpp：
  CPU 推理（也支持 GPU）
  最轻量的方案
  适合边缘设备

LocalAI：
  OpenAI API 兼容的本地服务
  支持多种模型格式

推荐本地模型（按参数量）：
  7B  → Qwen2.5-7B, Llama3.1-8B（需要 8GB+ 内存）
  14B → Qwen2.5-14B, DeepSeek-R1-14B（需要 16GB+ 内存）
  32B → Qwen2.5-32B（需要 32GB+ 内存）
  72B → Qwen2.5-72B（需要 GPU 或 64GB+ 内存）
```

---

## 13. 向量数据库

### 13.1 为什么需要向量数据库

```
RAG 的核心流程：
  文档 → 切块 → Embedding 向量化 → 存储到向量数据库
  查询 → Embedding → 在向量库中检索最相似的文档块 → 返回给 LLM

向量数据库 = Agent 的"长期记忆"
```

### 13.2 主流向量数据库对比

```
┌──────────────┬────────┬──────────┬──────────┬───────────────┐
│ 数据库        │ 类型    │ 部署     │ 价格     │ 特点           │
├──────────────┼────────┼──────────┼──────────┼───────────────┤
│ Chroma       │ 嵌入式  │ 本地     │ 免费     │ 最简单上手     │
│ FAISS        │ 库      │ 本地     │ 免费     │ Meta 出品，最快 │
│ Milvus       │ 独立    │ 自建/云  │ 开源免费  │ 最专业，功能全  │
│ Pinecone     │ 云服务  │ 全托管   │ 付费     │ 最省心，纯云    │
│ Weaviate     │ 独立    │ 自建/云  │ 开源免费  │ GraphQL 接口   │
│ Qdrant       │ 独立    │ 自建/云  │ 开源免费  │ Rust 写的，极快 │
│ pgvector     │ 插件    │ PostgreSQL│ 免费    │ 不用额外部署    │
│ Elasticsearch│ 独立    │ 自建/云  │ 开源免费  │ 老牌搜索引擎   │
└──────────────┴────────┴──────────┴──────────┴───────────────┘

推荐：
  个人项目/学习 → Chroma（零配置） 或 FAISS
  小规模生产 → Qdrant 或 pgvector
  大规模生产 → Milvus 或 Pinecone
```

---

## 14. Agent 开发实战选型

### 场景一：个人学习 / 快速原型

```
推荐方案：Dify + Ollama

步骤：
  1. Docker 部署 Dify
  2. 本地 Ollama 运行 Qwen2.5-7B
  3. 在 Dify 中配置 Ollama 为模型提供商
  4. 可视化搭建 Agent
  
成本：$0（全部本地运行）
时间：30 分钟上手
```

### 场景二：知识库问答系统

```
推荐方案：LlamaIndex + Chroma + GPT-4o-mini

步骤：
  1. pip install llama-index chromadb
  2. 加载文档 → 构建向量索引
  3. 查询引擎 → 用户问答
  
成本：GPT-4o-mini 费用极低
时间：1 小时上手
```

### 场景三：复杂工作流 Agent

```
推荐方案：LangGraph + GPT-4o

步骤：
  1. 设计工作流图
  2. 定义状态和节点
  3. 实现各节点逻辑（工具调用、条件判断）
  4. 编排为 Graph
  
成本：按 GPT-4o 调用量
时间：1 周
```

### 场景四：多 Agent 协作

```
推荐方案：CrewAI + GPT-4o / Claude

步骤：
  1. 设计 Agent 角色和分工
  2. 定义各 Agent 的工具
  3. 定义任务和依赖关系
  4. 组建 Crew 运行
  
成本：多 Agent 模型调用较多
时间：1 周
```

### 场景五：量化交易 Agent

```
推荐方案（与 BitPro 结合）：

架构设计：
  Agent 1: 市场分析师
    工具: 行情API, 技术指标计算, 新闻搜索
    任务: 分析市场状态和趋势

  Agent 2: 策略研究员  
    工具: 回测引擎, 策略数据库, 参数优化
    任务: 选择和优化策略

  Agent 3: 风控员
    工具: 风险计算器, 仓位管理器
    任务: 评估风险，设定止损

  Agent 4: 交易执行员
    工具: 交易所API, 下单接口
    任务: 执行交易

框架选择：
  CrewAI（多Agent协作）+ LangChain（工具调用）
  或 LangGraph（有状态工作流）
```

---

## 15. 学习路线图

### 阶段一：入门（1~2周）

```
□ 理解 Agent 基本概念（本文档）
□ 注册 OpenAI / Claude / DeepSeek API
□ 用 Dify 或 Coze 搭建第一个 Agent（零代码）
□ 体验 Cursor IDE 中的 AI Agent 功能
□ 阅读 ReAct 论文或解读文章
```

### 阶段二：动手（2~4周）

```
□ 学习 LangChain 基础（Chains, Agents, Tools）
□ 用 LangChain 实现一个带工具的 Agent
□ 学习 RAG，用 LlamaIndex 构建知识库
□ 了解 Embedding 和向量数据库
□ 部署 Ollama，体验本地模型
```

### 阶段三：进阶（1~2月）

```
□ 学习 LangGraph（有状态 Agent 工作流）
□ 学习 CrewAI（多 Agent 协作）
□ 学习 MCP 协议，开发 MCP Server
□ 了解 Agent 安全性（Prompt Injection 防护等）
□ 结合 BitPro 开发交易相关的 Agent
```

### 阶段四：生产（持续）

```
□ Agent 可观测性（LangSmith / Phoenix）
□ Agent 评测（如何衡量 Agent 的好坏）
□ 成本优化（模型选择、缓存、批处理）
□ 部署和扩展（Docker、Kubernetes）
□ 关注最新进展（Agent 领域迭代极快）
```

### 推荐学习资源

```
官方文档（最权威）：
  LangChain: python.langchain.com/docs
  LlamaIndex: docs.llamaindex.ai
  CrewAI: docs.crewai.com
  Dify: docs.dify.ai
  OpenAI: platform.openai.com/docs

视频课程：
  DeepLearning.AI（Andrew Ng）: 多门 Agent 课程（免费）
  吴恩达 x LangChain 课程系列

GitHub 仓库：
  awesome-ai-agents: github.com/e2b-dev/awesome-ai-agents
  awesome-langchain: github.com/kyrolabs/awesome-langchain

社区：
  LangChain Discord
  Dify 社区（中文友好）
  Hacker News / Reddit r/LangChain
```

---

*文档版本：v1.0 | 更新日期：2026-02-08*
*AI Agent 领域发展极快，本文档内容可能随时过时，请关注各框架官方文档获取最新信息。*
