from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.providers.anthropic import AnthropicProvider

from app.config import settings


def _build_model() -> str | AnthropicModel:
    """按 LLM_MODEL (`{provider}:{model}`) 构造 Model；仅在需要自定义 endpoint 时显式构造。"""
    provider_name, _, model_name = settings.llm_model.partition(":")
    if not model_name:
        raise RuntimeError(
            f"LLM_MODEL must be '{{provider}}:{{model}}', got: {settings.llm_model!r}"
        )
    if provider_name == "anthropic":
        # 走 Azure 上的 Claude：用 AZURE_LLM_* 这对配置显式构造
        # （Anthropic SDK 只认 ANTHROPIC_BASE_URL / ANTHROPIC_API_KEY，不会自动读 AZURE_LLM_*）
        provider = AnthropicProvider(
            api_key=settings.azure_llm_api_key,
            base_url=settings.azure_llm_base_url or None,
        )
        return AnthropicModel(model_name, provider=provider)
    # openai / google-gla 暂时走 pydantic-ai 的 string shortcut
    # —— 其 SDK 自己读 OPENAI_BASE_URL / GEMINI_API_KEY
    return settings.llm_model


def build_agent(system_prompt: str, **kwargs) -> Agent:
    """切换 LLM / endpoint 只需改 .env，不需要改代码。

    - `LLM_MODEL` 决定 provider + model
    - Anthropic 系：`AZURE_LLM_BASE_URL` 填上即切到 Azure，留空直连官方
    - OpenAI 系：`OPENAI_BASE_URL` 填上切到 OpenRouter / DeepSeek / Qwen 等兼容 proxy
    """
    settings.require_llm_key()
    return Agent(_build_model(), system_prompt=system_prompt, **kwargs)
