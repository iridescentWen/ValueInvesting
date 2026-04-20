from pydantic_ai import Agent

from app.agents.base import build_agent
from app.skills.registry import catalog_prompt, load_skill_content

_CORE_PRINCIPLES = """\
You are a value investing analyst in the tradition of Benjamin Graham and Warren Buffett.

Core principles (always apply):
- Margin of safety: never buy without a meaningful discount to intrinsic value.
- Circle of competence: refuse to evaluate businesses you don't understand.
- A stock is part ownership in a business, not a ticker to trade.
- Price is not value: Mr. Market's quote is an offer, not a verdict.
- Owner earnings matter more than reported earnings (Buffett, 1986).
"""

_LANG_HINTS = {
    "en": "Always respond in English.",
    "zh": "始终使用中文回复。",
}


def build_value_agent(locale: str = "en") -> Agent:
    lang_hint = _LANG_HINTS.get(locale, _LANG_HINTS["en"])
    catalog = catalog_prompt() or "(no skills available yet)"
    system_prompt = f"""{_CORE_PRINCIPLES}
## Available skills (use `load_skill` tool to fetch full content when relevant)
{catalog}

{lang_hint}
"""
    agent = build_agent(system_prompt)

    @agent.tool_plain
    def load_skill(name: str) -> str:
        """按 name 加载一个 skill 的完整内容。name 必须精确匹配 skill 目录中的条目。"""
        return load_skill_content(name)

    return agent
