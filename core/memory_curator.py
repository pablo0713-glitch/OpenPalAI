from __future__ import annotations

import json
import logging
import re

from core.model_adapter import ModelAdapter
from core.supporting_agent import SupportingAgent

logger = logging.getLogger(__name__)


def _extract_json(text: str) -> str:
    """Pull the first balanced {...} JSON object out of model output."""
    text = text.strip()
    if text.startswith("```"):
        inner = text.split("```")
        text = inner[1] if len(inner) > 1 else text
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    # Find first { and walk to its matching }, respecting strings and nesting
    start = text.find("{")
    if start == -1:
        return text
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    # No balanced close found — return from start and let json.loads raise
    return text[start:]


_SYSTEM = (
    "You are a memory curator for an AI companion. Your sole job is to assess "
    "conversation turns for long-term memory value. When asked, you score turns "
    "from 0.0 to 1.0:\n"
    "  0.0 = pure filler (greetings, one-word replies, acknowledgments, social noise)\n"
    "  0.3 = mild context (casual opinions, minor preferences)\n"
    "  0.6 = notable (strong preference, ongoing project, revealed need or goal)\n"
    "  1.0 = pivotal (name, life event, explicit request to be remembered, key fact)\n\n"
    "You respond ONLY with JSON. No explanation, no markdown, no surrounding text."
)


class MemoryCuratorAgent(SupportingAgent):
    """
    Specialist agent that scores conversation turns for importance.
    Runs during the memory consolidation cycle (every 6h) to decide
    which turns graduate to MEMORY.md vs. staying in the FTS/vector index.
    """

    BATCH_SIZE = 20

    def __init__(self, adapter: ModelAdapter) -> None:
        super().__init__(adapter, _SYSTEM)

    async def score_turns(self, turns: list[dict]) -> dict[int, float]:
        """
        Score a list of turn dicts (each must have 'id', 'role', 'content').
        Returns {session_id: importance_score}. On any batch failure the batch
        is silently skipped — turns stay at -1.0 and are retried next cycle.
        """
        results: dict[int, float] = {}
        for i in range(0, len(turns), self.BATCH_SIZE):
            batch = turns[i : i + self.BATCH_SIZE]
            batch_results = await self._score_batch(batch)
            results.update(batch_results)
        return results

    async def _score_batch(self, turns: list[dict]) -> dict[int, float]:
        items = [
            {"id": t["id"], "role": t["role"], "content": str(t.get("content", ""))[:300]}
            for t in turns
        ]
        prompt = (
            "Score each conversation turn for long-term memory significance.\n\n"
            "Turns:\n"
            + json.dumps(items, ensure_ascii=False)
            + '\n\nReply with JSON only: {"scores": [{"id": <id>, "score": <float>}, ...]}'
        )
        raw = ""
        try:
            raw = await self.run(prompt, max_tokens=600)
            extracted = _extract_json(raw)
            data = json.loads(extracted)
            return {int(entry["id"]): float(entry["score"]) for entry in data.get("scores", [])}
        except Exception as exc:
            logger.error(
                "MemoryCuratorAgent._score_batch failed: %s | raw output: %.300r",
                exc, raw,
            )
            # Assign a neutral default so these turns aren't silently dropped forever
            return {int(t["id"]): 0.3 for t in turns}

    async def should_consolidate(self, transcript: str, existing_memory: str) -> bool:
        """
        Reasoning gate: ask the curator whether consolidation is actually warranted
        given the current transcript and what's already in MEMORY.md.
        Returns True if the model says yes (or on any error, to avoid skipping consolidation).
        """
        prompt = (
            "You are deciding whether a memory consolidation run is worthwhile.\n\n"
            f"EXISTING MEMORY (already saved):\n{existing_memory[:800]}\n\n"
            f"NEW TRANSCRIPT:\n{transcript[:1200]}\n\n"
            "Does the new transcript contain information worth adding to the existing memory? "
            'Reply with JSON only: {"consolidate": true} or {"consolidate": false}'
        )
        try:
            raw = await self.run(prompt, max_tokens=64)
            raw = _extract_json(raw)
            data = json.loads(raw)
            return bool(data.get("consolidate", True))
        except Exception as exc:
            logger.warning("MemoryCuratorAgent.should_consolidate failed (%s) — defaulting True", exc)
            return True
