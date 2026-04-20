import json
from collections.abc import AsyncIterator

import pytest
from pydantic import ValidationError
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ToolCallPart,
    ToolReturnPart,
)

from app.api.chat import ChatMessage, ChatRequest, _split_history, _stream_events


class _StubAgent:
    """模拟一个只暴露 run_stream_events() 的 Agent。"""

    def __init__(self, events: list, raise_exc: Exception | None = None):
        self._events = events
        self._raise = raise_exc
        self.calls: list[tuple[str, list]] = []

    async def run_stream_events(self, prompt: str, message_history=None) -> AsyncIterator:
        self.calls.append((prompt, list(message_history or [])))
        for e in self._events:
            yield e
        if self._raise is not None:
            raise self._raise


async def _collect(agent, req: ChatRequest) -> list[dict]:
    return [json.loads(p["data"]) async for p in _stream_events(agent, req)]


@pytest.mark.asyncio
async def test_text_deltas_emitted_in_order() -> None:
    agent = _StubAgent(
        [
            PartStartEvent(index=0, part=TextPart(content="Hello")),
            PartDeltaEvent(index=0, delta=TextPartDelta(content_delta=", ")),
            PartDeltaEvent(index=0, delta=TextPartDelta(content_delta="world")),
        ]
    )
    req = ChatRequest(messages=[ChatMessage(role="user", content="hi")])

    payloads = await _collect(agent, req)

    assert payloads == [
        {"type": "text-delta", "delta": "Hello"},
        {"type": "text-delta", "delta": ", "},
        {"type": "text-delta", "delta": "world"},
        {"type": "done"},
    ]
    # 单轮没有 history
    assert agent.calls == [("hi", [])]


@pytest.mark.asyncio
async def test_tool_call_then_result_emitted() -> None:
    tool_part = ToolCallPart(
        tool_name="load_skill",
        args={"name": "margin-of-safety"},
        tool_call_id="call_1",
    )
    tool_result = ToolReturnPart(
        tool_name="load_skill",
        content="# Margin of Safety\n...",
        tool_call_id="call_1",
    )
    agent = _StubAgent(
        [
            PartStartEvent(index=0, part=TextPart(content="Let me check. ")),
            FunctionToolCallEvent(part=tool_part),
            FunctionToolResultEvent(result=tool_result),
            PartStartEvent(index=1, part=TextPart(content="Done.")),
        ]
    )
    req = ChatRequest(messages=[ChatMessage(role="user", content="analyze AAPL")])

    payloads = await _collect(agent, req)

    assert payloads == [
        {"type": "text-delta", "delta": "Let me check. "},
        {
            "type": "tool-call",
            "id": "call_1",
            "name": "load_skill",
            "args": {"name": "margin-of-safety"},
        },
        {
            "type": "tool-result",
            "id": "call_1",
            "result": "# Margin of Safety\n...",
        },
        {"type": "text-delta", "delta": "Done."},
        {"type": "done"},
    ]


@pytest.mark.asyncio
async def test_exception_in_stream_yields_error_not_500() -> None:
    agent = _StubAgent(
        [PartStartEvent(index=0, part=TextPart(content="start"))],
        raise_exc=RuntimeError("upstream 429"),
    )
    req = ChatRequest(messages=[ChatMessage(role="user", content="hi")])

    payloads = await _collect(agent, req)

    assert payloads[0] == {"type": "text-delta", "delta": "start"}
    assert payloads[-1] == {"type": "error", "message": "upstream 429"}
    assert not any(p.get("type") == "done" for p in payloads)


def test_chat_request_rejects_empty_messages() -> None:
    with pytest.raises(ValidationError):
        ChatRequest(messages=[])


def test_split_history_requires_last_message_be_user() -> None:
    messages = [
        ChatMessage(role="user", content="hi"),
        ChatMessage(role="assistant", content="hello"),
    ]
    with pytest.raises(ValueError, match="last message must be from user"):
        _split_history(messages)


def test_split_history_converts_prior_turns_to_model_messages() -> None:
    from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

    messages = [
        ChatMessage(role="user", content="q1"),
        ChatMessage(role="assistant", content="a1"),
        ChatMessage(role="user", content="q2"),
    ]
    prompt, history = _split_history(messages)

    assert prompt == "q2"
    assert len(history) == 2
    assert isinstance(history[0], ModelRequest)
    assert isinstance(history[0].parts[0], UserPromptPart)
    assert history[0].parts[0].content == "q1"
    assert isinstance(history[1], ModelResponse)
    assert isinstance(history[1].parts[0], TextPart)
    assert history[1].parts[0].content == "a1"
