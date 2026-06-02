from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class AbstractMemoryStore(ABC):

    @abstractmethod
    async def get_history(
        self,
        user_id: str,
        channel_id: str,
        *,
        agent_id: str = "",
    ) -> list[dict[str, Any]]:
        """Return Anthropic-compatible messages list for this user/channel."""

    @abstractmethod
    async def append_turn(
        self,
        user_id: str,
        channel_id: str,
        platform: str,
        role: str,
        content: str | list[Any],
        display_name: str = "",
        *,
        agent_id: str = "",
        person_id: str = "",
    ) -> None:
        """Append a single turn (role + content) to conversation history."""

    @abstractmethod
    async def trim_history(
        self,
        user_id: str,
        channel_id: str,
        max_turns: int,
        *,
        agent_id: str = "",
    ) -> None:
        """Trim history to at most max_turns entries, keeping the most recent."""

    @abstractmethod
    async def get_facts(self, user_id: str, *, agent_id: str = "") -> dict[str, str]:
        """Return persistent facts dict for this user."""

    @abstractmethod
    async def upsert_fact(self, user_id: str, key: str, value: str, *, agent_id: str = "") -> None:
        """Insert or update a single fact for this user."""

    @abstractmethod
    async def get_all_conversations(self, user_id: str, *, agent_id: str = "") -> list:
        """Return all ConversationFile objects for a user_id (across all channels)."""
