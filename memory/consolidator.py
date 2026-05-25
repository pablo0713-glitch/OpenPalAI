from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import aiofiles

from core.memory_curator import MemoryCuratorAgent
from core.model_adapter import ModelAdapter
from core.persona import get_agent_config
from memory.file_store import FileMemoryStore
from memory.person_map import PersonMap
from memory.schemas import ConversationFile
from memory.session_index import SessionIndex

logger = logging.getLogger(__name__)

CONSOLIDATION_THRESHOLD = 30   # total turns across all files for a person
KEEP_TURNS_AFTER = 10
MEMORY_CAP = 2000   # chars cap for MEMORY.md


class MemoryConsolidator:
    """
    Periodically reads conversation files for each known person, asks the model
    to extract what's worth remembering, saves the result as a Markdown note, then
    trims the source conversation files.

    Cross-platform consolidation: all user_ids linked to the same person
    (Discord + SL) are read together so the notes reflect the full picture.
    """

    def __init__(
        self,
        adapter: ModelAdapter,
        memory_store: FileMemoryStore,
        person_map: PersonMap,
        notes_dir: str,
        threshold: int = CONSOLIDATION_THRESHOLD,
        keep_turns: int = KEEP_TURNS_AFTER,
        curator: MemoryCuratorAgent | None = None,
        session_index: SessionIndex | None = None,
        importance_threshold: float = 0.6,
    ) -> None:
        self._adapter = adapter
        self._store = memory_store
        self._person_map = person_map
        self._notes_dir = notes_dir
        self._threshold = threshold
        self._keep_turns = keep_turns
        self._curator = curator
        self._session_index = session_index
        self._importance_threshold = importance_threshold

    async def run_all(self) -> None:
        for person_id in self._person_map.all_persons():
            try:
                await self._check_and_consolidate(person_id)
            except Exception:
                logger.exception("Consolidation failed for person '%s'", person_id)

    async def _check_and_consolidate(self, person_id: str) -> None:
        user_ids = self._person_map.get_person_user_ids(person_id)
        all_convs: list[ConversationFile] = []
        for uid in user_ids:
            all_convs.extend(await self._store.get_all_conversations(uid))

        if not all_convs:
            return

        total = sum(len(c.turns) for c in all_convs)
        if total < self._threshold:
            return
        logger.info(
            "Consolidating memory for '%s': %d files, %d total turns (threshold %d)",
            person_id, len(all_convs), total, self._threshold,
        )

        # Score unscored turns for all user_ids linked to this person
        if self._curator and self._session_index:
            for uid in user_ids:
                unscored = await self._session_index.get_unscored_turns(uid, limit=200)
                if unscored:
                    scores = await self._curator.score_turns(unscored)
                    await self._session_index.set_importance_batch(scores)
                    logger.info(
                        "Curator scored %d/%d turns for '%s'",
                        len(scores), len(unscored), uid,
                    )

        await self._consolidate(person_id, all_convs)

        for uid in user_ids:
            convs = await self._store.get_all_conversations(uid)
            for conv in convs:
                await self._store.trim_history(uid, conv.channel_id, self._keep_turns)

        logger.info(
            "Consolidation complete for '%s'. Files trimmed to %d turns.",
            person_id, self._keep_turns,
        )

    async def _consolidate(self, person_id: str, convs: list[ConversationFile]) -> None:
        # Build transcript filtered to high-importance turns when curator is available
        if self._curator and self._session_index:
            user_ids = self._person_map.get_person_user_ids(person_id)
            high_importance: set[str] = set()
            for uid in user_ids:
                rows = await self._session_index.get_high_importance_turns(
                    uid, threshold=self._importance_threshold
                )
                for row in rows:
                    high_importance.add(row["content"][:200])
            transcript = _build_transcript(convs, high_importance_content=high_importance or None)
        else:
            transcript = _build_transcript(convs)

        if not transcript.strip():
            return

        # Curator gate: skip if nothing new worth adding
        if self._curator:
            memory_dir = Path(self._notes_dir).parent / "memory"
            safe = person_id.replace("/", "_").replace(":", "_")
            existing_text = ""
            mem_file = memory_dir / safe / "MEMORY.md"
            if mem_file.exists():
                existing_text = mem_file.read_text(encoding="utf-8")
            if not await self._curator.should_consolidate(transcript, existing_text):
                logger.info("Curator gate: skipping consolidation for '%s' (no new value)", person_id)
                return

        notes_text = await self._ask_model(person_id, transcript)
        if not notes_text:
            return

        # Append new bullet points into MEMORY.md (bounded, trim oldest to make room)
        memory_dir = Path(self._notes_dir).parent / "memory"
        safe = person_id.replace("/", "_").replace(":", "_")
        memory_file = memory_dir / safe / "MEMORY.md"
        memory_file.parent.mkdir(parents=True, exist_ok=True)

        bullets = [
            line.lstrip("-•").strip()
            for line in notes_text.splitlines()
            if line.strip().startswith(("-", "•"))
        ]
        if not bullets:
            # No bullet list — treat the whole text as a single entry
            bullets = [notes_text.strip()]

        existing = memory_file.read_text(encoding="utf-8") if memory_file.exists() else ""
        from core.tool_handlers.memory import _entries, _join_entries, _add_entry, _scan_entry
        for bullet in bullets:
            if _scan_entry(bullet):
                logger.warning("Consolidator: blocked bullet for '%s': %s", person_id, bullet[:80])
                continue
            existing = _add_entry(existing, bullet)
        # Enforce cap — trim oldest entries
        while len(existing) > MEMORY_CAP and _entries(existing):
            entries = _entries(existing)
            entries.pop(0)
            existing = _join_entries(entries)
        memory_file.write_text(existing, encoding="utf-8")

        # Keep markdown audit trail
        person_notes_dir = os.path.join(self._notes_dir, person_id)
        os.makedirs(person_notes_dir, exist_ok=True)
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        audit_path = os.path.join(person_notes_dir, f"memories_{date_str}.md")
        async with aiofiles.open(audit_path, "w", encoding="utf-8") as f:
            await f.write(notes_text)

        logger.info("Memory consolidated for '%s' → %s (%d chars)", person_id, memory_file, len(existing))

    async def _ask_model(self, person_id: str, transcript: str) -> str:
        cfg = get_agent_config()
        agent_name = cfg.get("agent_name", "the agent")

        prompt = (
            f"You are {agent_name}. You're reviewing your conversation logs "
            f"with {person_id} across connected platforms.\n\n"
            f"Here are the conversations:\n\n{transcript}\n\n"
            f"Write your personal memory notes about {person_id}. Include:\n"
            f"- Important facts about them (name, preferences, context)\n"
            f"- Their interests and aesthetic tastes\n"
            f"- Ongoing projects or topics you've discussed\n"
            f"- Things that clearly matter to them\n"
            f"- Recurring themes or anything to carry forward\n"
            f"- How they use each platform and what they tend to talk about there\n\n"
            f"Write in first person as {agent_name}, as if writing in a personal journal. "
            f"Be selective — only keep what is genuinely worth remembering. "
            f"Do not include tool calls, raw JSON, or system messages."
        )

        return await self._adapter.create_simple(
            system="",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
        )


# ------------------------------------------------------------------ helpers

def _build_transcript(
    convs: list[ConversationFile],
    high_importance_content: set[str] | None = None,
) -> str:
    """Build a text transcript from conversation files.

    When high_importance_content is provided, only turns whose text starts with
    one of those snippets are included. This filters the transcript to scored
    high-importance content before passing it to the consolidation model.
    """
    cfg = get_agent_config()
    agent_name = cfg.get("agent_name", "Agent")
    parts: list[str] = []

    for conv in sorted(convs, key=lambda c: c.updated_at):
        header = f"[{conv.platform.upper()} | channel: {conv.channel_id} | last updated: {conv.updated_at[:10]}]"
        lines = [header]

        for turn in conv.turns:
            role_label = agent_name if turn["role"] == "assistant" else "User"
            content = turn.get("content", "")

            if isinstance(content, list):
                texts = [
                    b.get("text", "")
                    for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                ]
                content = " ".join(t for t in texts if t)

            if not content:
                continue

            if high_importance_content is not None:
                snippet = content[:200]
                if not any(snippet.startswith(hi[:200]) for hi in high_importance_content):
                    continue

            if len(content) > 500:
                content = content[:500] + "…"
            lines.append(f"{role_label}: {content}")

        if len(lines) > 1:
            parts.append("\n".join(lines))

    return "\n\n---\n\n".join(parts)
