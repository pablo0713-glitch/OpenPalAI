from __future__ import annotations

import copy
import json
import logging
import re
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)

_startup_script_updated: bool = False  # set True when startup finds a newer template

_ROOT = Path(__file__).parent.parent
_ENV_PATH = _ROOT / ".env"
_CONFIG_PATH = _ROOT / "data" / "agent_config.json"
_IDENTITY_DIR = _ROOT / "data" / "identity"
_AGENTS_DIR = _ROOT / "data" / "agents"
_MEMORY_AGENTS_DIR = _ROOT / "data" / "memory" / "agents"
_SETUP_DIR = _ROOT / "setup"

_PERSON_MAP_PATH = _ROOT / "data" / "person_map.json"
_NOTES_DIR = _ROOT / "data" / "notes"
_LIBRARY_DIR = _ROOT / "data" / "library"
_CANONICAL_OWNER = "SL_Notes"
_IDENTITY_FILES = ("agent.md", "soul.md", "user.md")

_SENSITIVE_KEYS = {
    "ANTHROPIC_API_KEY",
    "DISCORD_TOKEN",
    "SL_BOT_PASSWORD",
    "SL_BRIDGE_SECRET",
    "SEARCH_API_KEY",
}
_MASK = "••••••••"


class _SetupBody(BaseModel):
    env: dict[str, str]
    agent_config: dict[str, Any]


class _ScriptUpdateBody(BaseModel):
    url: str
    secret: str
    triggers: list[str]
    opensim: bool = False


class _CompanionCreateBody(BaseModel):
    agent_name: str = ""
    id: str = ""


class _LibraryWriteBody(BaseModel):
    filename: str
    content: str


class _AgentsCfgBody(BaseModel):
    supporting_agents: dict


def _asset_version(path: Path) -> int:
    try:
        return int(path.stat().st_mtime)
    except OSError:
        return 0


def _normalize_creds(text: str) -> str:
    """Replace all credential/config fields with a fixed placeholder for structural comparison."""
    for pattern in (
        r'(string\s+SERVER_URL\s*=\s*")[^"]*(")',
        r'(string\s+SECRET\s*=\s*")[^"]*(")',
        r'(string\s+GRID\s*=\s*")[^"]*(")',
        r'(list\s+TRIGGER_NAMES\s*=\s*\[)[^\]]*(\])',
        r'(local\s+SERVER_URL\s*=\s*")[^"]*(")',
        r'(local\s+SECRET\s*=\s*")[^"]*(")',
        r'(local\s+GRID\s*=\s*")[^"]*(")',
    ):
        text = re.sub(pattern, lambda m: m.group(1) + "__" + m.group(2), text)
    return text


def _template_has_changed(template_path: Path, output_path: Path) -> bool:
    """True if the template has structural changes vs the current output file."""
    if not output_path.exists():
        return True
    try:
        return _normalize_creds(template_path.read_text(encoding="utf-8")) != \
               _normalize_creds(output_path.read_text(encoding="utf-8"))
    except OSError:
        return True


def _patch_scripts(url: str, secret: str, grid: str, triggers: list[str], force_template: bool = False) -> dict[str, str]:
    """Patch SERVER_URL / SECRET / GRID / TRIGGER_NAMES into the LSL and Lua scripts.

    If force_template=True (used on startup), always copies the .template over the
    output file first so git-pulled template changes are picked up automatically.
    If force_template=False (wizard button), only copies when the output is absent.

    Returns the results dict. Sets the module-level _startup_script_updated flag
    when force_template=True and a structurally changed template is detected.
    """
    global _startup_script_updated
    lsl_path = _ROOT / "lsl" / "companion_bridge.lsl"
    lua_path = _ROOT / "lua" / "agent_companion.lua"
    for path in (lsl_path, lua_path):
        template = path.with_suffix(path.suffix + ".template")
        if template.exists() and (force_template or not path.exists()):
            if force_template and _template_has_changed(template, path):
                _startup_script_updated = True
            shutil.copy(template, path)
    triggers_lsl = ", ".join(f'"{t}"' for t in triggers if t)
    results: dict[str, str] = {}

    def _sub(pattern: str, value: str, text: str) -> str:
        return re.sub(pattern, lambda m: m.group(1) + value + m.group(2), text)

    if lsl_path.exists():
        try:
            text = lsl_path.read_text(encoding="utf-8")
            text = _sub(r'(string\s+SERVER_URL\s*=\s*")[^"]*(")', url, text)
            text = _sub(r'(string\s+SECRET\s*=\s*")[^"]*(")', secret, text)
            text = _sub(r'(string\s+GRID\s*=\s*")[^"]*(")', grid, text)
            text = re.sub(
                r'(list\s+TRIGGER_NAMES\s*=\s*\[)[^\]]*(\])',
                lambda m: m.group(1) + triggers_lsl + m.group(2),
                text,
            )
            lsl_path.write_text(text, encoding="utf-8")
            results["lsl"] = "ok"
        except Exception as exc:
            results["lsl"] = str(exc)
    else:
        results["lsl"] = "not found"

    if lua_path.exists():
        try:
            text = lua_path.read_text(encoding="utf-8")
            text = _sub(r'(local\s+SERVER_URL\s*=\s*")[^"]*(")', url, text)
            text = _sub(r'(local\s+SECRET\s*=\s*")[^"]*(")', secret, text)
            text = _sub(r'(local\s+GRID\s*=\s*")[^"]*(")', grid, text)
            lua_path.write_text(text, encoding="utf-8")
            results["lua"] = "ok"
        except Exception as exc:
            results["lua"] = str(exc)
    else:
        results["lua"] = "not found"

    return results


def patch_scripts_from_env() -> None:
    """Read SL config from .env and patch both scripts. Called on every startup."""
    env = _read_dotenv()
    url = env.get("SL_BRIDGE_URL", "")
    if not url:
        return  # SL not configured — nothing to patch
    secret = env.get("SL_BRIDGE_SECRET", "")
    opensim = env.get("OPENSIM_ENABLED", "false").lower() == "true"
    grid = "opensim" if opensim else "sl"
    triggers_raw = env.get("SL_TRIGGER_NAMES", "")
    triggers = [t.strip() for t in triggers_raw.split(",") if t.strip()]
    results = _patch_scripts(url, secret, grid, triggers, force_template=True)
    logger.info("Script patch on startup: %s", results)


def create_setup_router() -> APIRouter:
    router = APIRouter()

    @router.get("/setup")
    async def setup_index() -> HTMLResponse:
        html = (_SETUP_DIR / "index.html").read_text(encoding="utf-8")
        css_version = _asset_version(_SETUP_DIR / "style.css")
        js_version = _asset_version(_SETUP_DIR / "wizard.js")
        html = html.replace("/setup/static/style.css", f"/setup/static/style.css?v={css_version}")
        html = html.replace("/setup/static/wizard.js", f"/setup/static/wizard.js?v={js_version}")
        return HTMLResponse(html, headers={"Cache-Control": "no-store"})

    @router.get("/setup/status")
    async def setup_status() -> JSONResponse:
        configured = _CONFIG_PATH.exists()
        agent_name = "Agent"
        if configured:
            try:
                from core.persona import get_agent_config
                cfg = get_agent_config()
                agent_name = cfg.get("agent_name", "Agent")
            except Exception:
                pass
        return JSONResponse({"configured": configured, "agent_name": agent_name})

    @router.get("/setup/config")
    async def get_config() -> JSONResponse:
        env_vals = _read_dotenv()
        for key in _SENSITIVE_KEYS:
            if env_vals.get(key):
                env_vals[key] = _MASK

        from core.persona import (
            get_agent_config,
            get_agent_identity_dir,
            get_default_agent_id,
            get_default_config,
            get_default_identity,
        )
        # Deepcopy so we never mutate the cached config when injecting identity.
        base_cfg = get_agent_config() if _CONFIG_PATH.exists() else get_default_config()
        agent_cfg = copy.deepcopy(base_cfg)
        defaults = get_default_identity()

        def _load_identity(aid: str) -> dict[str, str]:
            identity_dir = get_agent_identity_dir(aid, agent_cfg)
            out: dict[str, str] = {}
            for fname in _IDENTITY_FILES:
                key = fname.replace(".", "_")  # agent_md, soul_md, user_md
                fpath = identity_dir / fname
                out[key] = fpath.read_text(encoding="utf-8") if fpath.exists() else defaults.get(fname, "")
            return out

        # Per-agent identity for the multi-companion wizard.
        agents = agent_cfg.get("agents")
        if isinstance(agents, dict):
            for aid, comp in agents.items():
                if isinstance(comp, dict):
                    comp["identity"] = _load_identity(aid)

        # Top-level identity kept for the default agent (back-compat).
        agent_cfg["identity"] = _load_identity(get_default_agent_id(agent_cfg))

        return JSONResponse({"env": env_vals, "agent_config": agent_cfg})

    @router.post("/setup/config")
    async def post_config(body: _SetupBody) -> JSONResponse:
        try:
            # Update .env — skip any value that is still the mask
            env_updates = {k: v for k, v in body.env.items() if v != _MASK}
            _write_dotenv(env_updates)

            from core.persona import get_agent_config, get_default_agent_id
            agent_payload = dict(body.agent_config)

            if isinstance(agent_payload.get("agents"), dict) and agent_payload["agents"]:
                # Multi-companion registry payload (new wizard).
                normalized_cfg, identities = _build_registry_from_payload(agent_payload)
            else:
                # Legacy single-agent payload — merge onto the current default companion.
                identity = agent_payload.pop("identity", None)
                current_cfg = get_agent_config()
                default_agent_id = get_default_agent_id(current_cfg)
                default_agent = current_cfg.get("agents", {}).get(default_agent_id, {})
                updated_agent = {
                    **default_agent,
                    "id": default_agent_id,
                    "agent_name": agent_payload.get("agent_name", default_agent.get("agent_name", "Agent")),
                    "agent_profile_image": agent_payload.get("agent_profile_image", default_agent.get("agent_profile_image", "")),
                    "additional_context": agent_payload.get("additional_context", default_agent.get("additional_context", "")),
                    "tools": agent_payload.get("tools", default_agent.get("tools", {})),
                    "platform_awareness": agent_payload.get("platform_awareness", default_agent.get("platform_awareness", {})),
                    "platform_bindings": agent_payload.get("platform_bindings", default_agent.get("platform_bindings", {})),
                    "model_override": agent_payload.get("model_override", default_agent.get("model_override")),
                }
                normalized_cfg = {
                    "default_agent_id": default_agent_id,
                    "command_center_name": agent_payload.get(
                        "command_center_name",
                        current_cfg.get("command_center_name", "Command Center"),
                    ),
                    "agents": {**current_cfg.get("agents", {}), default_agent_id: updated_agent},
                    "supporting_agents": agent_payload.get(
                        "supporting_agents",
                        current_cfg.get("supporting_agents", {}),
                    ),
                }
                identities = {default_agent_id: identity} if isinstance(identity, dict) else {}

            _write_identities(normalized_cfg, identities)

            # Write agent_config.json
            _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            _CONFIG_PATH.write_text(
                json.dumps(normalized_cfg, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

            # Migrate person_map.json key → SL_Notes and rename notes folder
            _migrate_owner_key()

            # Invalidate persona cache so changes take effect immediately
            from core.persona import reload_agent_config
            reload_agent_config()

            return JSONResponse({"ok": True})
        except Exception as exc:
            logger.exception("Setup config save failed: %s", exc)
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=500)

    @router.get("/setup/scripts")
    async def get_scripts() -> JSONResponse:
        lsl_path = _ROOT / "lsl" / "companion_bridge.lsl"
        lua_path = _ROOT / "lua" / "agent_companion.lua"
        return JSONResponse({
            "lsl": lsl_path.read_text(encoding="utf-8") if lsl_path.exists() else None,
            "lua": lua_path.read_text(encoding="utf-8") if lua_path.exists() else None,
            "updated_on_startup": _startup_script_updated,
        })

    @router.post("/setup/update-scripts")
    async def update_scripts(body: _ScriptUpdateBody) -> JSONResponse:
        grid = "opensim" if body.opensim else "sl"
        results = _patch_scripts(body.url, body.secret, grid, body.triggers)
        ok = all(v == "ok" for v in results.values())
        return JSONResponse({"ok": ok, "results": results})

    # ---- Library CRUD -------------------------------------------------------

    @router.get("/setup/library")
    async def library_list() -> JSONResponse:
        from memory.library_store import LibraryStore
        _LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
        store = LibraryStore(str(_LIBRARY_DIR))
        return JSONResponse(store.list_modules())

    @router.get("/setup/library/{module_id}")
    async def library_get(module_id: str) -> JSONResponse:
        from memory.library_store import LibraryStore
        store = LibraryStore(str(_LIBRARY_DIR))
        mod = store.get_by_id(module_id)
        if mod is None:
            return JSONResponse({"error": f"Module '{module_id}' not found."}, status_code=404)
        return JSONResponse({
            "id": mod.id, "title": mod.title, "description": mod.description,
            "always_on": mod.always_on, "platforms": mod.platforms, "tags": mod.tags,
            "content": mod.content, "filename": mod.filename,
        })

    @router.post("/setup/library")
    async def library_write(body: _LibraryWriteBody) -> JSONResponse:
        filename = body.filename.strip()
        if not filename.endswith(".md"):
            filename += ".md"
        # Sanitize: only allow safe filenames
        safe = re.sub(r"[^a-zA-Z0-9_\-. ]", "", filename).strip()
        if not safe:
            return JSONResponse({"error": "Invalid filename."}, status_code=400)
        _LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
        path = _LIBRARY_DIR / safe
        path.write_text(body.content, encoding="utf-8")
        return JSONResponse({"ok": True, "filename": safe})

    @router.delete("/setup/library/{module_id}")
    async def library_delete(module_id: str) -> JSONResponse:
        from memory.library_store import LibraryStore
        store = LibraryStore(str(_LIBRARY_DIR))
        mod = store.get_by_id(module_id)
        if mod is None:
            return JSONResponse({"error": f"Module '{module_id}' not found."}, status_code=404)
        path = _LIBRARY_DIR / mod.filename
        if path.exists():
            path.unlink()
        return JSONResponse({"ok": True})

    # ---- Supporting agents config -------------------------------------------

    @router.get("/setup/agents")
    async def agents_get() -> JSONResponse:
        from core.persona import get_agent_config, get_default_config
        agent_cfg = get_agent_config() if _CONFIG_PATH.exists() else {}
        defaults = get_default_config()
        supporting = agent_cfg.get("supporting_agents", defaults.get("supporting_agents", {}))
        return JSONResponse(supporting)

    @router.post("/setup/agents")
    async def agents_save(body: _AgentsCfgBody) -> JSONResponse:
        from core.persona import get_agent_config
        agent_cfg = get_agent_config() if _CONFIG_PATH.exists() else {}
        agent_cfg["supporting_agents"] = body.supporting_agents
        _CONFIG_PATH.write_text(json.dumps(agent_cfg, indent=2, ensure_ascii=False), encoding="utf-8")
        from core.persona import reload_agent_config
        reload_agent_config()
        return JSONResponse({"ok": True})

    # ---- Companion CRUD -----------------------------------------------------

    @router.post("/setup/companion")
    async def create_companion(body: _CompanionCreateBody) -> JSONResponse:
        from core.persona import (
            _default_companion,
            _normalize_agent_id,
            get_agent_config,
            reload_agent_config,
        )
        cfg = copy.deepcopy(get_agent_config())
        agents = cfg.get("agents")
        if not isinstance(agents, dict):
            agents = {}
            cfg["agents"] = agents

        base = _normalize_agent_id(body.id or body.agent_name or "companion")
        agent_id = base
        suffix = 2
        while agent_id in agents:
            agent_id = f"{base}-{suffix}"
            suffix += 1

        companion = _default_companion(agent_id)
        if body.agent_name.strip():
            companion["agent_name"] = body.agent_name.strip()
        agents[agent_id] = companion

        _write_registry(cfg)
        _write_identities(cfg, {agent_id: {}})  # seed default identity files
        reload_agent_config()
        return JSONResponse({"ok": True, "id": agent_id, "agent_name": companion["agent_name"]})

    @router.delete("/setup/companion/{agent_id}")
    async def delete_companion(agent_id: str) -> JSONResponse:
        from core.persona import (
            _normalize_agent_id,
            get_agent_config,
            get_default_agent_id,
            reload_agent_config,
        )
        cfg = copy.deepcopy(get_agent_config())
        agents = cfg.get("agents")
        if not isinstance(agents, dict):
            agents = {}
        target = _normalize_agent_id(agent_id)
        if target not in agents:
            return JSONResponse({"ok": False, "error": f"Companion '{target}' not found."}, status_code=404)
        if len(agents) <= 1:
            return JSONResponse({"ok": False, "error": "Cannot delete the last companion."}, status_code=400)

        del agents[target]
        if _normalize_agent_id(str(cfg.get("default_agent_id"))) == target:
            cfg["default_agent_id"] = next(iter(agents))

        _write_registry(cfg)
        for path in (_AGENTS_DIR / target, _MEMORY_AGENTS_DIR / target, _NOTES_DIR / target):
            shutil.rmtree(path, ignore_errors=True)
        reload_agent_config()
        return JSONResponse({"ok": True, "default_agent_id": cfg["default_agent_id"]})

    return router


# ------------------------------------------------------------------ companion helpers

def _build_registry_from_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, dict]]:
    """Normalize a multi-companion wizard payload into the registry written to disk.

    Returns (registry, identities) where identities maps agent_id -> {agent_md, soul_md, user_md}.
    Identity blocks are stripped from the stored companions (they live as files, not in JSON).
    """
    from core.persona import _normalize_agent_id

    raw_agents = payload.get("agents") or {}
    agents: dict[str, Any] = {}
    identities: dict[str, dict] = {}
    for raw_id, raw in raw_agents.items():
        if not isinstance(raw, dict):
            continue
        aid = _normalize_agent_id(str(raw.get("id") or raw_id))
        companion = {k: v for k, v in raw.items() if k != "identity"}
        companion["id"] = aid
        agents[aid] = companion
        identity = raw.get("identity")
        if isinstance(identity, dict):
            identities[aid] = identity

    first_id = next(iter(agents), "aria")
    default_id = _normalize_agent_id(str(payload.get("default_agent_id") or first_id))
    if default_id not in agents:
        default_id = first_id

    registry = {
        "default_agent_id": default_id,
        "command_center_name": payload.get("command_center_name", "Command Center"),
        "agents": agents,
        "supporting_agents": payload.get("supporting_agents", {}),
    }
    return registry, identities


def _write_identities(registry: dict[str, Any], identities: dict[str, dict]) -> None:
    """Write each agent's identity files to its per-agent dir; mirror the default to the legacy dir."""
    from core.persona import get_default_identity

    defaults = get_default_identity()
    default_id = registry.get("default_agent_id")
    for aid, identity in identities.items():
        targets = [_AGENTS_DIR / aid / "identity"]
        if aid == default_id:
            targets.append(_IDENTITY_DIR)
        for identity_dir in targets:
            identity_dir.mkdir(parents=True, exist_ok=True)
            for fname in _IDENTITY_FILES:
                key = fname.replace(".", "_")
                content = (identity.get(key) or "").strip() or defaults.get(fname, "")
                (identity_dir / fname).write_text(content, encoding="utf-8")


def _write_registry(cfg: dict[str, Any]) -> None:
    """Write a clean registry (canonical keys only) to agent_config.json."""
    clean = {
        "default_agent_id": cfg.get("default_agent_id"),
        "command_center_name": cfg.get("command_center_name", "Command Center"),
        "agents": cfg.get("agents", {}),
        "supporting_agents": cfg.get("supporting_agents", {}),
    }
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    _CONFIG_PATH.write_text(json.dumps(clean, indent=2, ensure_ascii=False), encoding="utf-8")


# ------------------------------------------------------------------ .env helpers

def _read_dotenv() -> dict[str, str]:
    result: dict[str, str] = {}
    if not _ENV_PATH.exists():
        return result
    for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, val = stripped.partition("=")
        result[key.strip()] = val.strip()
    return result


def _migrate_owner_key() -> None:
    """Rename any non-SL_Notes key in person_map.json to SL_Notes, move notes folder."""
    if not _PERSON_MAP_PATH.exists():
        return
    try:
        data: dict = json.loads(_PERSON_MAP_PATH.read_text(encoding="utf-8"))
    except Exception:
        return
    old_keys = [k for k in data if k != _CANONICAL_OWNER]
    if not old_keys:
        return  # already correct or empty
    new_data: dict = {_CANONICAL_OWNER: data.get(_CANONICAL_OWNER, [])}
    for old_key in old_keys:
        # Merge user_ids (avoid duplicates)
        for uid in data[old_key]:
            if uid not in new_data[_CANONICAL_OWNER]:
                new_data[_CANONICAL_OWNER].append(uid)
        # Rename notes folder if it exists
        old_folder = _NOTES_DIR / old_key
        new_folder = _NOTES_DIR / _CANONICAL_OWNER
        if old_folder.exists() and not new_folder.exists():
            shutil.move(str(old_folder), str(new_folder))
        elif old_folder.exists() and new_folder.exists():
            # Both exist: move files from old into new (don't overwrite)
            for f in old_folder.iterdir():
                dest = new_folder / f.name
                if not dest.exists():
                    shutil.move(str(f), str(dest))
            shutil.rmtree(str(old_folder), ignore_errors=True)
    _PERSON_MAP_PATH.write_text(
        json.dumps(new_data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logger.info("Migrated person_map keys %s → %s", old_keys, _CANONICAL_OWNER)


def _write_dotenv(updates: dict[str, str]) -> None:
    existing_keys: set[str] = set()
    lines: list[str] = []

    if _ENV_PATH.exists():
        for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key = stripped.split("=", 1)[0].strip()
                existing_keys.add(key)
                if key in updates:
                    lines.append(f"{key}={updates[key]}")
                else:
                    lines.append(line)
            else:
                lines.append(line)

    for key, val in updates.items():
        if key not in existing_keys:
            lines.append(f"{key}={val}")

    _ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
