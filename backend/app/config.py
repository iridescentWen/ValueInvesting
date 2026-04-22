from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# 把 .env 注入 os.environ，让 Anthropic/OpenAI/Gemini SDK 能自动读到 KEY 和 BASE_URL
# （pydantic-settings 默认只把 .env 读进 Settings 字段，不会写 os.environ）
load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM：格式 {provider}:{model}，详见 .env.example
    llm_model: str = "anthropic:claude-opus-4-7-noah"

    # Azure LLM（Azure 上的 Anthropic / OpenAI 等模型共用同一把 key + base_url）
    azure_llm_api_key: str | None = None
    azure_llm_base_url: str | None = None

    # OpenAI 系（含 OpenRouter / Azure OpenAI / DeepSeek / Qwen / Zhipu 等 OpenAI-compatible）
    openai_api_key: str | None = None
    openai_base_url: str | None = None

    # Google Gemini
    gemini_api_key: str | None = None

    tushare_token: str | None = None
    akshare_rate_limit: int = 10

    # RapidAPI / Seeking Alpha（美股 realtime + 股票代码补全）
    rapidapi_host: str = "seeking-alpha.p.rapidapi.com"
    rapidapi_key: str | None = None
    rapidapi_sa_autocomplete_url: str = "https://seeking-alpha.p.rapidapi.com/v2/auto-complete"
    rapidapi_sa_quote_url: str = "https://seeking-alpha.p.rapidapi.com/market/get-realtime-quotes"

    # Financial Modeling Prep（美股基本面 + 财报）
    fmp_api_key: str | None = None
    fmp_base_url: str = "https://financialmodelingprep.com/api"

    # Mairui（A 股财务指标——cwzb 接口：混合营收 / 利润 / 资产 / 比率）
    mairui_api_key: str | None = None
    mairui_base_url: str = "http://api.mairui.club"
    # Mairui 客户端限速:token bucket，每分钟最多 N 次请求。套餐对照:
    #   免费        50/天  (无法扫全市场,不要用)
    #   月卡/年卡    300/min (→ 保守配 240)
    #   铂金       3000/min (→ 保守配 2400)
    #   钻石       6000/min (→ 保守配 4800)
    # 默认 240 对应最便宜付费套餐,冷启动全 A 股 ~22 分钟。通过环境变量
    # MAIRUI_RATE_PER_MIN 调高。
    mairui_rate_per_min: int = 240

    database_url: str = ""
    redis_url: str = "redis://localhost:6379/0"
    duckdb_path: Path = Path("./data/analytics.duckdb")
    # screener prewarm 结果落盘路径。开发期 uvicorn --reload 每次重启都清空
    # in-memory cache,CN 冷启动 22 分钟——存磁盘重启能跳过 prewarm。
    screener_cache_path: Path = Path("./data/screener_cache.json")

    log_level: str = "INFO"
    env: str = "development"
    cors_origins: list[str] = ["http://localhost:8420"]

    def require_llm_key(self) -> None:
        provider = self.llm_model.split(":", 1)[0]
        # anthropic 走 Azure：用 AZURE_LLM_API_KEY
        key_map = {
            "anthropic": (self.azure_llm_api_key, "AZURE_LLM_API_KEY"),
            "openai": (self.openai_api_key, "OPENAI_API_KEY"),
            "google-gla": (self.gemini_api_key, "GEMINI_API_KEY"),
        }
        if provider not in key_map:
            raise RuntimeError(
                f"Unsupported LLM_MODEL provider '{provider}'. Supported: {', '.join(key_map)}"
            )
        key, env_var = key_map[provider]
        if not key:
            raise RuntimeError(f"LLM_MODEL is '{provider}' but {env_var} is unset")


settings = Settings()
