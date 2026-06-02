from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

from core.persona import MessageContext

logger = logging.getLogger(__name__)

MEMORY_CAP = 2000   # chars
USER_CAP   = 1200   # chars

_DELIMITER = "§"

# ------------------------------------------------------------------ security scan

# Invisible / confusable Unicode: zero-width chars, directional overrides, BOM
_INVISIBLE_RE = re.compile(
    r"[\u200b-\u200f\u202a-\u202e\u2060-\u2064\u206a-\u206f\ufeff\u00ad]"
)

# Prompt-injection phrases (case-insensitive)
_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bignore\s+(previous|all|above|prior)\s+(instructions?|prompts?|context)\b",
        r"\byou\s+are\s+now\b",
        r"\bnew\s+instructions?\s*:",
        r"\bact\s+as\b",
        r"\bdisregard\s+(all|previous|your)\b",
        r"\bforget\s+everything\b",
        r"\bsystem\s*:\s",
        r"\[system\]",
        r"\boverride\s+(your|all|previous)\b",
        r"\bjailbreak\b",
        r"\bdo\s+anything\s+now\b",
        r"\bdan\s+mode\b",
    ]
]

# Credential / exfiltration patterns — structural matches only (high precision, low false-positive rate).
# Text-intent patterns (e.g. bare "exfiltrate") are intentionally excluded; they produce too many
# false positives when the agent discusses security topics in normal conversation.
_EXFIL_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in [
        # Action + destination: "send [my/the/all] [secrets/keys/tokens] to <somewhere>"
        r"\bsend\s+(all|my|the)\s+(data|keys?|tokens?|passwords?|secrets?)\s+(to|via)\b",
        # Exfiltrate only when paired with a destination indicator
        r"\bexfiltrate\s+.{0,60}(to|via|at)\s+(https?://|[0-9]{1,3}\.[0-9]{1,3})",
        # API key shapes: sk-..., AKIA..., Bearer <long token>
        r"\bsk-[A-Za-z0-9]{20,}\b",
        r"\bAKIA[A-Z0-9]{16}\b",
        r"Bearer\s+[A-Za-z0-9\-_\.]{20,}",
        # SSH / PGP private key headers
        r"-----BEGIN\s+(RSA|EC|OPENSSH|DSA|PGP)\s+PRIVATE",
        # Shell command injection: backtick execution or subshell
        r"`[^`]{0,200}`",
        r"\$\([^\)]{0,200}\)",
    ]
]


def _scan_entry(text: str) -> str | None:
    """Return an error string if the entry fails security checks, else None."""
    if _INVISIBLE_RE.search(text):
        return "Entry contains invisible or directional Unicode characters and was rejected."
    for pat in _INJECTION_PATTERNS:
        if pat.search(text):
            return "Entry contains a prompt-injection pattern and was rejected."
    for pat in _EXFIL_PATTERNS:
        if pat.search(text):
            return "Entry matches a credential-exfiltration pattern and was rejected."
    return None


def _memory_dir(memory_base: str, person_id: str, agent_id: str = "") -> Path:
    safe = person_id.replace("/", "_").replace(":", "_")
    if agent_id:
        d = Path(memory_base) / "agents" / agent_id.replace("/", "_").replace(":", "_") / safe
    else:
        d = Path(memory_base) / safe
    d.mkdir(parents=True, exist_ok=True)
    return d


def _file_path(memory_base: str, person_id: str, store: str, agent_id: str = "") -> Path:
    fname = "MEMORY.md" if store == "memory" else "USER.md"
    return _memory_dir(memory_base, person_id, agent_id) / fname


def _cap_for(store: str) -> int:
    return MEMORY_CAP if store == "memory" else USER_CAP


def _read_file(path: Path) -> str:
    if path.exists():
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            return ""
    return ""


def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _entries(content: str) -> list[str]:
    """Split §-delimited content into individual entries (non-empty)."""
    return [e.strip() for e in content.split(_DELIMITER) if e.strip()]


def _join_entries(entries: list[str]) -> str:
    if not entries:
        return ""
    return ("\n" + _DELIMITER + "\n").join(entries)


def _add_entry(content: str, text: str) -> str:
    entries = _entries(content)
    entries.append(text.strip())
    return _join_entries(entries)


def _remove_entry(content: str, old_text: str) -> tuple[str, bool]:
    entries = _entries(content)
    new_entries = [e for e in entries if old_text not in e]
    if len(new_entries) == len(entries):
        return content, False
    return _join_entries(new_entries), True


def _replace_entry(content: str, old_text: str, new_text: str) -> tuple[str, bool]:
    entries = _entries(content)
    changed = False
    new_entries = []
    for e in entries:
        if old_text in e:
            new_entries.append(e.replace(old_text, new_text.strip(), 1))
            changed = True
        else:
            new_entries.append(e)
    return _join_entries(new_entries), changed


def _trim_to_cap(content: str, cap: int) -> str:
    """If content exceeds cap, drop oldest entries until it fits."""
    if len(content) <= cap:
        return content
    entries = _entries(content)
    while entries and len(_join_entries(entries)) > cap:
        entries.pop(0)
    return _join_entries(entries)


async def handle_memory(
    tool_input: dict,
    context: MessageContext,
    memory_base: str,
) -> str:
    action   = tool_input.get("action", "").strip()
    store    = tool_input.get("store", "memory").strip()
    text     = tool_input.get("text", "").strip()
    old_text = tool_input.get("old_text", "").strip()

    if store not in ("memory", "user"):
        return "Invalid store. Use 'memory' or 'user'."

    person_id = context.person_id or context.user_id
    path = _file_path(memory_base, person_id, store, context.agent_id)
    cap  = _cap_for(store)

    loop = asyncio.get_event_loop()

    if action == "add":
        if not text:
            return "text is required for action 'add'."
        if err := _scan_entry(text):
            logger.warning("memory.add blocked for %s: %s", person_id, err)
            return err
        content = await loop.run_in_executor(None, _read_file, path)
        content = _add_entry(content, text)
        content = _trim_to_cap(content, cap)
        await loop.run_in_executor(None, _write_file, path, content)
        label = "MEMORY" if store == "memory" else "USER profile"
        return f"Added to {label}."

    elif action == "remove":
        if not old_text:
            return "old_text is required for action 'remove'."
        content = await loop.run_in_executor(None, _read_file, path)
        content, found = _remove_entry(content, old_text)
        if not found:
            return f"No entry found containing: {old_text!r}"
        await loop.run_in_executor(None, _write_file, path, content)
        label = "MEMORY" if store == "memory" else "USER profile"
        return f"Removed from {label}."

    elif action == "replace":
        if not old_text or not text:
            return "Both old_text and text are required for action 'replace'."
        if err := _scan_entry(text):
            logger.warning("memory.replace blocked for %s: %s", person_id, err)
            return err
        content = await loop.run_in_executor(None, _read_file, path)
        content, found = _replace_entry(content, old_text, text)
        if not found:
            return f"No entry found containing: {old_text!r}"
        content = _trim_to_cap(content, cap)
        await loop.run_in_executor(None, _write_file, path, content)
        label = "MEMORY" if store == "memory" else "USER profile"
        return f"Updated entry in {label}."

    else:
        return "Invalid action. Use 'add', 'replace', or 'remove'."
