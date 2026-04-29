"""OpenAI backend implementation."""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Any

from little_agent.agent.nodes import (
    AssistantResponseNode,
    Node,
    ToolCallNode,
    ToolResultNode,
    UserPromptNode,
)
from little_agent.tools.protocol import ToolMap

from .protocol import BackendToolCall, BackendTurnResult

if TYPE_CHECKING:
    from little_agent.agent.core import SessionCore

logger = logging.getLogger(__name__)


def _tool_map_to_openai_functions(tool_map: ToolMap) -> list[dict[str, Any]]:
    """Convert ToolMap to OpenAI function definitions."""
    functions = []
    for name, (desc, args) in tool_map.items():
        properties: dict[str, Any] = {}
        required: list[str] = []
        for arg_name, arg_type, arg_desc, arg_required in args:
            properties[arg_name] = {
                "type": arg_type,
                "description": arg_desc,
            }
            if arg_required:
                required.append(arg_name)
        functions.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": desc,
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    },
                },
            }
        )
    return functions


def _chain_to_messages(tail: Node | None) -> list[dict[str, Any]]:
    """Convert chain of nodes to OpenAI messages."""
    messages: list[dict[str, Any]] = []
    node = tail
    chain: list[Node] = []
    while node is not None:
        chain.append(node)
        node = node.prev
    chain.reverse()

    for n in chain:
        if isinstance(n, UserPromptNode):
            if isinstance(n.prompt, str):
                messages.append({"role": "user", "content": n.prompt})
            else:
                messages.append({"role": "user", "content": json.dumps(n.prompt)})
        elif isinstance(n, AssistantResponseNode):
            messages.append({"role": "assistant", "content": n.text})
        elif isinstance(n, ToolCallNode):
            tool_calls = []
            for call_id, call_data in n.calls.items():
                tool_calls.append(
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": call_data["tool_name"],
                            "arguments": json.dumps(call_data["arguments"]),
                        },
                    }
                )
            messages.append({"role": "assistant", "tool_calls": tool_calls})
        elif isinstance(n, ToolResultNode):
            for call_id, result in n.results.items():
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": json.dumps(result),
                    }
                )
    return messages


class OpenAIBackend:
    """OpenAI backend implementation."""

    def __init__(self, model: str, api_key: str, base_url: str | None = None) -> None:
        import openai

        if base_url is not None:
            self._client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
        else:
            self._client = openai.AsyncOpenAI(api_key=api_key)
        self._model = model

    async def generate(self, session: SessionCore) -> BackendTurnResult:
        """Generate a response from OpenAI."""
        tool_map = session.agent.tools.list()
        messages = _chain_to_messages(session.tail)
        tools = _tool_map_to_openai_functions(tool_map) if tool_map else None

        logger.debug(
            "OpenAI request payload: model=%s messages=%s tools=%s", self._model, messages, tools
        )

        start_time = time.perf_counter()
        response = await self._client.chat.completions.create(  # type: ignore[call-overload]
            model=self._model,
            messages=messages,
            tools=tools,
            tool_choice="auto" if tools else None,
        )
        elapsed = time.perf_counter() - start_time

        choice = response.choices[0]
        message = choice.message

        usage: dict[str, int] | None = None
        if response.usage:
            usage = {
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
            }
            if (
                hasattr(response.usage, "prompt_tokens_details")
                and response.usage.prompt_tokens_details
            ):
                cached = getattr(response.usage.prompt_tokens_details, "cached_tokens", None)
                if cached is not None:
                    usage["cached_tokens"] = cached

        logger.info(
            "OpenAI response: model=%s finish_reason=%s "
            "input_tokens=%s output_tokens=%s cached_tokens=%s elapsed=%.3fs",
            self._model,
            choice.finish_reason,
            usage.get("input_tokens") if usage else None,
            usage.get("output_tokens") if usage else None,
            usage.get("cached_tokens") if usage else None,
            elapsed,
        )

        if message.tool_calls:
            tool_calls = [
                BackendToolCall(
                    call_id=tc.id,
                    tool_name=tc.function.name,
                    arguments=json.loads(tc.function.arguments),
                )
                for tc in message.tool_calls
            ]
            return BackendTurnResult(
                output_text=message.content or "",
                tool_calls=tool_calls,
                finish_reason="tool_call",
                usage=usage,
            )

        return BackendTurnResult(
            output_text=message.content or "",
            tool_calls=[],
            finish_reason="completed",
            usage=usage,
        )
