# ValueInvesting

基于 AI agent 的价值投资工具：多指标筛选 + 主观价值判断，支持 A 股 / 美股 / 港股。

> 详细设计：`~/.claude/plans/ai-agent-wiggly-moon.md`

## 技术栈

- **前端**：Next.js 15 + React 19 + TypeScript + Tailwind 4 + shadcn/ui（端口 **8420**）
- **后端**：FastAPI + Python 3.12 + Pydantic AI + uv（端口 **8421**）
- **数据**：本地 PostgreSQL + Redis + DuckDB（分析）
- **行情数据源**：AkShare（A 股/港股）、yfinance（美股）、SEC EDGAR（年报 RAG）

## 前置条件

本地已安装：
- Python 3.12+
- Node.js 20+
- [uv](https://docs.astral.sh/uv/) — Python 包管理
- PostgreSQL（本地实例）
- Redis（本地实例）

## 启动

### 1. 后端

```bash
cd backend
cp .env.example .env         # 填 LLM key + 本地 Postgres 连接串
uv sync
uv run uvicorn app.main:app --reload --port 8421
```

验证：<http://localhost:8421/health>
OpenAPI 文档：<http://localhost:8421/docs>

### 2. 前端

```bash
cd frontend
cp .env.example .env.local   # 通常无需改
npm install
npm run dev
```

访问：<http://localhost:8420>

## 目录

```
backend/       FastAPI + Pydantic AI
frontend/      Next.js 15
.gitignore     已覆盖 Python + Node + data/ + 密钥
```

## 实施路线

当前：**Phase 1 — MVP 骨架**（✅ 已完成）

下一步：AkShare provider → 筛选接口 → 前端筛选面板 → 第一个 Pydantic AI agent（详见 plan 文件）。
