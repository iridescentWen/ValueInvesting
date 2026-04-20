# ValueInvesting Backend

FastAPI + Pydantic AI backend.

## 启动

```bash
cd backend
cp .env.example .env          # 填 LLM key + 本地 Postgres 连接串
uv sync                        # 安装依赖
uv run uvicorn app.main:app --reload --port 8421
```

访问 http://localhost:8421/health 确认运行。
OpenAPI 文档：http://localhost:8421/docs

## 测试

```bash
uv run pytest
```

## 目录

```
app/
  api/              REST 路由
  agents/           Pydantic AI agents（model-agnostic）
  data/
    providers/      MarketDataProvider 实现（AkShare / yfinance / EDGAR）
    repositories/   数据库访问
  models/           SQLAlchemy / Pydantic 模型
  workers/          ARQ 定时任务
  ws/               WebSocket handlers
  config.py         Pydantic Settings
  main.py           FastAPI 入口
tests/
```
