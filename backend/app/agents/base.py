from pydantic_ai import Agent

from app.config import settings


def build_agent(system_prompt: str, **kwargs) -> Agent:
    """切换 LLM 只需改 .env 中的 LLM_MODEL，不需要改代码。"""
    settings.require_llm_key()
    return Agent(settings.llm_model, system_prompt=system_prompt, **kwargs)
