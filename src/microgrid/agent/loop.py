"""Provider-agnostic tool-calling loop.

The loop speaks the OpenAI Chat Completions protocol but takes the client
as a constructor argument, so tests inject a fake that replays scripted
responses — no network, no API key. Self-correction needs no special code:
tool errors are ordinary tool results, and the model reacts to them.

Termination is explicit: either the model answers with plain content, or
``max_steps`` completion rounds pass and the agent *gives up loudly*
(``gave_up=True`` + a fixed message) rather than hallucinating an answer.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from microgrid.agent.prompts import GIVE_UP_MESSAGE, SYSTEM_PROMPT, TOOL_SCHEMAS

__all__ = ["Step", "AgentResult", "DataAgent"]


@dataclass
class Step:
    """One executed tool call, kept for the --show-trace transcript."""

    tool: str
    args: dict
    result: str


@dataclass
class AgentResult:
    answer: str
    steps: list[Step] = field(default_factory=list)
    gave_up: bool = False


class DataAgent:
    """Ask one question; the model drives the tools until it can answer.

    ``client`` is anything exposing ``chat.completions.create`` (the openai
    SDK, or a test fake). ``toolset`` maps tool name -> callable(args dict)
    -> result string (see :func:`microgrid.agent.tools.build_toolset`).
    """

    def __init__(
        self,
        client: Any,
        model: str,
        toolset: Mapping[str, Callable[[dict], str]],
        max_steps: int = 8,
        system_prompt: str = SYSTEM_PROMPT,
        tool_schemas: list | None = None,
    ) -> None:
        self.client = client
        self.model = model
        self.toolset = toolset
        self.max_steps = max_steps
        self.system_prompt = system_prompt
        self.tool_schemas = TOOL_SCHEMAS if tool_schemas is None else tool_schemas

    def ask(self, question: str) -> AgentResult:
        messages: list[Any] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": question},
        ]
        steps: list[Step] = []

        for _ in range(self.max_steps):
            response = self.client.chat.completions.create(
                model=self.model, messages=messages, tools=self.tool_schemas
            )
            msg = response.choices[0].message
            tool_calls = getattr(msg, "tool_calls", None)

            if not tool_calls:  # plain content = the final answer
                return AgentResult(answer=msg.content or "", steps=steps)

            # The SDK message object is a valid input message; append as-is.
            messages.append(msg)
            for call in tool_calls:
                name = call.function.name
                try:
                    args = json.loads(call.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = self._dispatch(name, args)
                steps.append(Step(tool=name, args=args, result=result))
                messages.append(
                    {"role": "tool", "tool_call_id": call.id, "content": result}
                )

        return AgentResult(answer=GIVE_UP_MESSAGE, steps=steps, gave_up=True)

    def _dispatch(self, name: str, args: dict) -> str:
        """Run one tool; any failure becomes a result string the model can read."""
        fn = self.toolset.get(name)
        if fn is None:
            return f"ERROR: unknown tool '{name}'. Available: {', '.join(self.toolset)}"
        try:
            return fn(args)
        except Exception as e:  # noqa: BLE001 — never crash the loop on a tool bug
            return f"TOOL ERROR ({type(e).__name__}): {e}"
