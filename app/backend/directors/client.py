"""Anthropic client wrapper for the director tier.

All four generative roles (pivot director, everyday director, npc-actor,
architect) return *structured* output the backend can apply to the DB. We get
that with forced tool-use: define one tool whose `input_schema` is the desired
shape, force `tool_choice` to it, and read the tool_use block's validated input.
(Forced tool-use is incompatible with extended thinking, so we steer quality via
the model choice and prompt rather than a thinking budget.)

The big, stable system prompts are sent as a cached prefix (`cache_control`), so
repeated ticks in a session reuse them at ~0.1x cost — the volatile per-call
world state always rides in the user turn, after the cache breakpoint.

Models follow the engine's existing tier split (see CLAUDE.md → "The living
world"): Opus 4.8 for the secret-bearing pivots and world seeding, Sonnet 4.6
for the everyday collisions/reflection and blind voicing.
"""

from __future__ import annotations

import json
import os

MODEL_OPUS = "claude-opus-4-8"
MODEL_SONNET = "claude-sonnet-4-6"


class DirectorError(RuntimeError):
    pass


def available():
    """True if an API key is configured (directors can run)."""
    return bool(os.environ.get("ANTHROPIC_API_KEY")
                or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


_client = None


def _get_client():
    global _client
    if _client is None:
        try:
            import anthropic
        except ImportError as e:  # pragma: no cover
            raise DirectorError("anthropic SDK not installed") from e
        if not available():
            raise DirectorError(
                "No ANTHROPIC_API_KEY — the director tier is unavailable. "
                "The deterministic engine still runs; set a key to enable directors.")
        _client = anthropic.Anthropic()
    return _client


def structured_call(system, user, tool_name, tool_schema, *,
                    model=MODEL_SONNET, max_tokens=8000, tool_description=""):
    """One structured call: force `tool_name` and return its validated input dict.

    `system` is cached as a prefix; `user` carries the volatile per-call context.
    Raises DirectorError if the model returns no tool_use block.
    """
    client = _get_client()
    tools = [{
        "name": tool_name,
        "description": tool_description or f"Return the result as {tool_name}.",
        "input_schema": tool_schema,
    }]
    system_blocks = [{"type": "text", "text": system,
                      "cache_control": {"type": "ephemeral"}}]
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system_blocks,
        tools=tools,
        tool_choice={"type": "tool", "name": tool_name},
        messages=[{"role": "user", "content": user}],
    )
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use" and block.name == tool_name:
            return block.input
    raise DirectorError(f"model did not return a {tool_name} tool call")


def text_call(system, user, *, model=MODEL_SONNET, max_tokens=2000):
    """A plain text reply (the npc-actor speaks prose, not structured edits)."""
    client = _get_client()
    system_blocks = [{"type": "text", "text": system,
                      "cache_control": {"type": "ephemeral"}}]
    resp = client.messages.create(
        model=model, max_tokens=max_tokens, system=system_blocks,
        messages=[{"role": "user", "content": user}],
    )
    parts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
    return "\n".join(parts).strip()


def dumps(obj):
    """Stable JSON for embedding world state in a user turn."""
    return json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True)
