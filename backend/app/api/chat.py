import json
import logging
from collections.abc import AsyncIterator
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelRequest,
    ModelResponse,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from sse_starlette.sse import EventSourceResponse

from app.agents.registry import get_value_agent

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["chat"])


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., min_length=1)
    locale: Literal["en", "zh"] = "zh"


def _split_history(messages: list[ChatMessage]) -> tuple[str, list]:
    """最后一条必须是 user；前面的依次打包成 ModelRequest/ModelResponse 作为 message_history。"""
    if messages[-1].role != "user":
        raise ValueError("last message must be from user")
    prompt = messages[-1].content
    history: list = []
    for m in messages[:-1]:
        if m.role == "user":
            history.append(ModelRequest(parts=[UserPromptPart(content=m.content)]))
        else:
            history.append(ModelResponse(parts=[TextPart(content=m.content)]))
    return prompt, history


def _event_to_payload(event) -> dict | None:
    if isinstance(event, PartStartEvent):
        if isinstance(event.part, TextPart) and event.part.content:
            return {"type": "text-delta", "delta": event.part.content}
        return None
    if isinstance(event, PartDeltaEvent):
        if isinstance(event.delta, TextPartDelta) and event.delta.content_delta:
            return {"type": "text-delta", "delta": event.delta.content_delta}
        return None
    if isinstance(event, FunctionToolCallEvent):
        part: ToolCallPart = event.part
        args: dict
        if isinstance(part.args, dict):
            args = part.args
        elif isinstance(part.args, str):
            try:
                args = json.loads(part.args) if part.args else {}
            except json.JSONDecodeError:
                args = {"_raw": part.args}
        else:
            args = {}
        return {
            "type": "tool-call",
            "id": part.tool_call_id,
            "name": part.tool_name,
            "args": args,
        }
    if isinstance(event, FunctionToolResultEvent):
        result = event.result
        if isinstance(result, ToolReturnPart):
            return {
                "type": "tool-result",
                "id": result.tool_call_id,
                "result": str(result.content),
            }
        return None
    return None


async def _stream_events(agent: Agent, req: ChatRequest) -> AsyncIterator[dict]:
    try:
        prompt, history = _split_history(req.messages)
    except ValueError as e:
        log.warning("chat request rejected: %s", e)
        yield {"data": json.dumps({"type": "error", "message": str(e)})}
        return

    log.info(
        "chat stream start locale=%s prompt_len=%d history_turns=%d prompt_preview=%r",
        req.locale,
        len(prompt),
        len(history),
        prompt[:120],
    )
    event_count = 0
    emitted_count = 0
    try:
        async for event in agent.run_stream_events(prompt, message_history=history):
            event_count += 1
            payload = _event_to_payload(event)
            if payload is not None:
                emitted_count += 1
                if payload["type"] == "tool-call":
                    log.info("chat tool-call name=%s args=%s", payload["name"], payload["args"])
                elif payload["type"] == "tool-result":
                    log.info("chat tool-result id=%s len=%d", payload["id"], len(payload["result"]))
                yield {"data": json.dumps(payload)}
    except Exception as e:
        log.exception("chat stream failed after %d events", event_count)
        yield {"data": json.dumps({"type": "error", "message": str(e)})}
        return

    log.info(
        "chat stream done events_total=%d events_emitted=%d",
        event_count,
        emitted_count,
    )
    yield {"data": json.dumps({"type": "done"})}


@router.post("/chat")
async def chat(req: ChatRequest) -> EventSourceResponse:
    log.info("POST /api/chat messages=%d locale=%s", len(req.messages), req.locale)
    agent = get_value_agent(req.locale)
    return EventSourceResponse(_stream_events(agent, req))
