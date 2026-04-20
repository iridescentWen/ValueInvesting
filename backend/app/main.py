import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agents.registry import close_all as close_all_agents
from app.api import chat, health, stocks
from app.config import settings
from app.data.providers import close_all as close_all_providers


def _configure_logging() -> None:
    log_dir = Path(__file__).resolve().parent.parent / "logs"
    log_dir.mkdir(exist_ok=True)

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # 每天午夜切一次,保留 14 份,归档文件名形如 backend.log.2026-04-20
    file_handler = TimedRotatingFileHandler(
        log_dir / "backend.log",
        when="midnight",
        interval=1,
        backupCount=14,
        encoding="utf-8",
        utc=False,
    )
    file_handler.suffix = "%Y-%m-%d"
    file_handler.setFormatter(fmt)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)

    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = [file_handler, stream_handler]

    # uvicorn 有自己的 logger,把它们也引到同一套 handler
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = [file_handler, stream_handler]
        lg.propagate = False


_configure_logging()
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    log.info("Starting ValueInvesting API in env=%s", settings.env)
    yield
    log.info("Shutting down ValueInvesting API")
    await close_all_providers()
    close_all_agents()


app = FastAPI(
    title="ValueInvesting API",
    version="0.1.0",
    description="AI agent backend for value investing",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(stocks.router)
app.include_router(chat.router)
