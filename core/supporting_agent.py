from __future__ import annotations

import asyncio
import logging
from typing import Any

from core.model_adapter import ModelAdapter, make_adapter

logger = logging.getLogger(__name__)


class SupportingAgent:
    """
    Lightweight base class for specialist supporting agents.

    Each instance has its own ModelAdapter (potentially a different provider
    and model from the main OpenPalAI agent) and a focused system prompt.
    Supporting agents are NOT full AgentCore instances — no memory, tools,
    or persona. They exist for scoped reasoning tasks only.

    Model selection comes from data/agent_config.json["supporting_agents"][agent_name].
    Falls back to the main agent's adapter if not configured.
    """

    def __init__(self, adapter: ModelAdapter, system_prompt: str) -> None:
        self._adapter = adapter
        self._system_prompt = system_prompt
        self._lock = asyncio.Lock()

    async def run(self, user_message: str, max_tokens: int = 512) -> str:
        """Run a single turn against the supporting agent's model."""
        async with self._lock:
            return await self._adapter.create_simple(
                system=self._system_prompt,
                messages=[{"role": "user", "content": user_message}],
                max_tokens=max_tokens,
            )


def make_supporting_adapter(
    settings: Any,
    agent_cfg: dict,
    agent_name: str,
) -> ModelAdapter:
    """
    Build a ModelAdapter for a named supporting agent using per-agent config
    stored in agent_config.json["supporting_agents"][agent_name].

    Falls back to the main agent's provider/model if the agent block is absent
    or its fields are empty.
    """
    supporting_cfg: dict = agent_cfg.get("supporting_agents", {}).get(agent_name, {})
    return make_adapter(
        settings,
        supporting_cfg.get("model_provider"),
        supporting_cfg.get("model_name"),
    )
