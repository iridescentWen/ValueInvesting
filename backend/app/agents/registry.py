from pydantic_ai import Agent

from app.agents.value_agent import build_value_agent

_VALUE_AGENTS: dict[str, Agent] = {}


def get_value_agent(locale: str) -> Agent:
    if locale not in _VALUE_AGENTS:
        _VALUE_AGENTS[locale] = build_value_agent(locale)
    return _VALUE_AGENTS[locale]


def close_all() -> None:
    _VALUE_AGENTS.clear()
