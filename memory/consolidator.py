from __future__ import annotations

import logging
import os
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import aiofiles

from core.memory_curator import MemoryCuratorAgent
from core.model_adapter import ModelAdapter
from core.persona import get_companion_agent, list_companion_agents
from memory.file_store import FileMemoryStore
from memory.person_map import PersonMap
from memory.schemas import ConversationFile
from memory.session_index import SessionIndex
from memory.vector_store import VectorMemoryStore

logger = logging.getLogger(__name__)

CONSOLIDATION_THRESHOLD = 30       # total turns across all files for a person
FIRST_CONSOLIDATION_THRESHOLD = 15 # lower threshold when MEMORY.md doesn't exist yet
GATE_BYPASS_HOURS = 72             # bypass curator gate if last consolidation was this long ago
KEEP_TURNS_AFTER = 10
MEMORY_CAP = 2000   # chars cap for MEMORY.md
MAX_SCORE_PER_UID_PER_CYCLE = 1000
MAX_CONSOLIDATION_ROWS = 300


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
        vector_store: VectorMemoryStore | None = None,
        importance_threshold: float = 0.6,
        memory_dir: str | None = None,
    ) -> None:
        self._adapter = adapter
        self._store = memory_store
        self._person_map = person_map
        self._notes_dir = notes_dir
        self._threshold = threshold
        self._keep_turns = keep_turns
        self._curator = curator
        self._session_index = session_index
        self._vector_store = vector_store
        self._importance_threshold = importance_threshold
        # memory_dir is stored explicitly so paths don't depend on notes_dir's location.
        # Falls back to notes_dir/../memory for backward compatibility.
        self._memory_dir = Path(memory_dir) if memory_dir else Path(notes_dir).parent / "memory"

    async def run_all(self) -> None:
        targets: dict[tuple[str, str], set[str]] = {}

        for agent in list_companion_agents():
            for person_id in self._person_map.all_persons():
                targets.setdefault((agent["id"], person_id), set())

        if self._session_index is not None:
            backlog_rows = [
                *await self._session_index.get_users_with_unscored_turns(),
                *await self._session_index.get_users_with_pending_consolidation(self._importance_threshold),
            ]
            for row in backlog_rows:
                user_id = row.get("user_id", "")
                agent_id = row.get("agent_id", "")
                if not user_id or not agent_id:
                    continue
                person_id = self._person_map.get_person_id(user_id) or user_id
                if person_id != user_id:
                    self._person_map.link_user_id(person_id, user_id)
                targets.setdefault((agent_id, person_id), set()).add(user_id)

        for (agent_id, person_id), extra_user_ids in sorted(targets.items()):
            try:
                await self._check_and_consolidate(agent_id, person_id, extra_user_ids=extra_user_ids)
            except Exception:
                logger.exception("Consolidation failed for agent '%s' person '%s'", agent_id, person_id)

    def _user_ids_for_person(self, person_id: str, extra_user_ids: set[str] | None = None) -> list[str]:
        user_ids = self._person_map.get_person_user_ids(person_id)
        merged = list(dict.fromkeys([*user_ids, *(extra_user_ids or set())]))
        return merged or [person_id]

    async def _score_unscored_turns(self, agent_id: str, person_id: str, user_ids: list[str]) -> None:
        if not self._curator or not self._session_index:
            return

        for uid in user_ids:
            scored_for_uid = 0
            while scored_for_uid < MAX_SCORE_PER_UID_PER_CYCLE:
                unscored = await self._session_index.get_unscored_turns(uid, limit=200, agent_id=agent_id)
                if not unscored:
                    break
                scores = await self._curator.score_turns(unscored)
                await self._session_index.set_importance_batch(scores)
                if self._vector_store:
                    await self._vector_store.set_importance_batch(
                        _memory_namespace(agent_id, person_id),
                        scores,
                    )
                logger.info(
                    "Curator scored %d/%d turns for '%s'",
                    len(scores), len(unscored), uid,
                )
                scored_for_uid += len(unscored)
                if len(unscored) < 200:
                    break

    async def _check_and_consolidate(
        self,
        agent_id: str,
        person_id: str,
        *,
        extra_user_ids: set[str] | None = None,
    ) -> None:
        user_ids = self._user_ids_for_person(person_id, extra_user_ids)

        # Importance scoring is useful even when there is not enough retained
        # JSON history to write MEMORY.md yet.
        await self._score_unscored_turns(agent_id, person_id, user_ids)

        # Use a lower threshold for first consolidation (MEMORY.md doesn't exist yet).
        # Check both the agent-scoped path and the legacy flat path so local installs
        # that predate the multi-agent migration don't get a spurious first-consolidation.
        safe = person_id.replace("/", "_").replace(":", "_")
        mem_file = self._memory_dir / "agents" / agent_id / safe / "MEMORY.md"
        if not mem_file.exists():
            legacy_mem = self._memory_dir / safe / "MEMORY.md"
            if legacy_mem.exists():
                mem_file = legacy_mem
        effective_threshold = FIRST_CONSOLIDATION_THRESHOLD if not mem_file.exists() else self._threshold

        candidates = []
        if self._session_index:
            candidates = await self._session_index.get_unconsolidated_high_importance_turns(
                user_ids,
                threshold=self._importance_threshold,
                agent_id=agent_id,
                limit=MAX_CONSOLIDATION_ROWS,
            )

        if len(candidates) < effective_threshold:
            return
        logger.info(
            "Consolidating memory for '%s': %d pending high-importance rows (threshold %d)",
            f"{agent_id}:{person_id}", len(candidates), effective_threshold,
        )

        await self._consolidate(agent_id, person_id, candidates)

        for uid in user_ids:
            convs = await self._store.get_all_conversations(uid, agent_id=agent_id)
            for conv in convs:
                await self._store.trim_history(uid, conv.channel_id, self._keep_turns, agent_id=agent_id)

        logger.info(
            "Consolidation complete for '%s'. Files trimmed to %d turns.",
            person_id, self._keep_turns,
        )

    async def _consolidate(
        self,
        agent_id: str,
        person_id: str,
        rows: list[dict],
    ) -> None:
        transcript = _build_transcript_from_rows(agent_id, rows)

        if not transcript.strip():
            return

        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_ts = datetime.now(timezone.utc).isoformat()
        source_ids = [int(row["id"]) for row in rows]

        # Curator gate: skip if nothing new worth adding (bypassed after GATE_BYPASS_HOURS)
        safe = person_id.replace("/", "_").replace(":", "_")
        agent_mem_dir = self._memory_dir / "agents" / agent_id / safe
        if self._curator:
            existing_text = ""
            mem_file = agent_mem_dir / "MEMORY.md"
            if not mem_file.exists():
                legacy_mem = self._memory_dir / safe / "MEMORY.md"
                if legacy_mem.exists():
                    mem_file = legacy_mem
            if mem_file.exists():
                existing_text = mem_file.read_text(encoding="utf-8")
            if not await self._curator.should_consolidate(transcript, existing_text):
                last_ts = _read_last_consolidation_time(agent_mem_dir)
                secs_since = (time.time() - last_ts) if last_ts is not None else float("inf")
                if secs_since < GATE_BYPASS_HOURS * 3600:
                    logger.info("Curator gate: skipping consolidation for '%s' (no new value)", person_id)
                    if self._session_index:
                        await self._session_index.mark_consolidated(source_ids, run_id, run_ts)
                    await _append_run_manifest(
                        self._notes_dir,
                        agent_id,
                        person_id,
                        {
                            "run_id": run_id,
                            "timestamp": run_ts,
                            "status": "skipped_by_curator_gate",
                            "source_session_ids": source_ids,
                            "importance_threshold": self._importance_threshold,
                        },
                    )
                    _write_last_consolidation_time(agent_mem_dir)
                    return
                logger.info(
                    "Curator gate bypassed for '%s' — %.1fh since last consolidation (limit %dh)",
                    person_id, secs_since / 3600, GATE_BYPASS_HOURS,
                )

        notes_text = await self._ask_model(agent_id, person_id, transcript)
        if not notes_text:
            return

        # Append new bullet points into MEMORY.md (bounded, trim oldest to make room)
        memory_file = agent_mem_dir / "MEMORY.md"
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
        person_notes_dir = os.path.join(self._notes_dir, agent_id, person_id)
        os.makedirs(person_notes_dir, exist_ok=True)
        audit_path = os.path.join(person_notes_dir, f"memories_{run_id}.md")
        async with aiofiles.open(audit_path, "w", encoding="utf-8") as f:
            await f.write(f"<!-- source_session_ids: {','.join(str(sid) for sid in source_ids)} -->\n\n")
            await f.write(notes_text)
        await _append_run_manifest(
            self._notes_dir,
            agent_id,
            person_id,
            {
                "run_id": run_id,
                "timestamp": run_ts,
                "status": "consolidated",
                "source_session_ids": source_ids,
                "importance_threshold": self._importance_threshold,
                "audit_path": audit_path,
                "notes_chars": len(notes_text),
                "bullet_count": len(bullets),
            },
        )

        if self._session_index:
            await self._session_index.mark_consolidated(source_ids, run_id, run_ts)
        _write_last_consolidation_time(agent_mem_dir)
        logger.info("Memory consolidated for '%s' → %s (%d chars)", person_id, memory_file, len(existing))

    async def _ask_model(self, agent_id: str, person_id: str, transcript: str) -> str:
        cfg = get_companion_agent(agent_id)
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
    agent_id: str,
    convs: list[ConversationFile],
    high_importance_content: set[str] | None = None,
) -> str:
    """Build a text transcript from conversation files.

    When high_importance_content is provided, only turns whose text starts with
    one of those snippets are included. This filters the transcript to scored
    high-importance content before passing it to the consolidation model.
    """
    cfg = get_companion_agent(agent_id)
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


def _build_transcript_from_rows(agent_id: str, rows: list[dict]) -> str:
    """Build a consolidation transcript from durable sessions.db rows."""
    cfg = get_companion_agent(agent_id)
    agent_name = cfg.get("agent_name", "Agent")
    parts: list[str] = []

    for row in rows:
        role_label = agent_name if row.get("role") == "assistant" else (row.get("display_name") or "User")
        content = str(row.get("content", "")).strip()
        if not content:
            continue
        if len(content) > 700:
            content = content[:700] + "..."
        platform = str(row.get("platform", "?")).upper()
        ts = str(row.get("timestamp", ""))[:19]
        score = row.get("importance", "?")
        parts.append(
            f"[session:{row.get('id')} | {platform} | {ts} | importance:{score}]\n"
            f"{role_label}: {content}"
        )

    return "\n\n---\n\n".join(parts)


def _memory_namespace(agent_id: str, person_id: str) -> str:
    return f"{agent_id.replace('/', '_').replace(':', '_')}::{person_id}" if agent_id else person_id


def _read_last_consolidation_time(person_dir: Path) -> float | None:
    stamp = person_dir / ".last_consolidation"
    try:
        return float(stamp.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _write_last_consolidation_time(person_dir: Path) -> None:
    try:
        person_dir.mkdir(parents=True, exist_ok=True)
        (person_dir / ".last_consolidation").write_text(str(time.time()), encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not write last-consolidation timestamp: %s", exc)


async def _append_run_manifest(notes_dir: str, agent_id: str, person_id: str, record: dict) -> None:
    person_notes_dir = Path(notes_dir) / agent_id / person_id
    person_notes_dir.mkdir(parents=True, exist_ok=True)
    manifest = person_notes_dir / "consolidation_runs.jsonl"
    async with aiofiles.open(manifest, "a", encoding="utf-8") as f:
        await f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
