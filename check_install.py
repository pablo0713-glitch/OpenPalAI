#!/usr/bin/env python3
"""
Installation smoke test — verifies all modules import and the data directory
structure can be created. Does NOT start any servers or write to data/.

Usage:
    python check_install.py
    ./check_install.py

Exit 0 = all good. Exit 1 = something is missing or broken.
"""

import sys
import importlib

REQUIRED_MODULES = [
    # stdlib (sanity)
    "asyncio", "pathlib", "json", "logging",
    # third-party
    "anthropic", "openai", "aiosqlite", "aiofiles",
    "fastapi", "uvicorn", "pydantic", "dotenv",
    "chromadb",
    # project — config
    ("config.settings", "load_settings"),
    ("config.paths",    "data_dir"),
    # project — core
    ("core.model_adapter", "ModelAdapter"),
    ("core.persona",       "build_system_prompt_blocks"),
    ("core.agent",         "AgentCore"),
    ("core.tools",         "ToolRegistry"),
    ("core.supporting_agent", "SupportingAgent"),
    ("core.memory_curator",   "MemoryCuratorAgent"),
    ("core.librarian_agent",  "LibrarianAgent"),
    ("core.recall_agent",     "SemanticRecallAgent"),
    # project — memory
    ("memory.file_store",     "FileMemoryStore"),
    ("memory.session_index",  "SessionIndex"),
    ("memory.vector_store",   "VectorMemoryStore"),
    ("memory.library_store",  "LibraryStore"),
    ("memory.consolidator",   "MemoryConsolidator"),
    ("memory.person_map",     "PersonMap"),
    ("memory.location_store", "LocationStore"),
    # project — tool handlers
    "core.tool_handlers.memory",
    "core.tool_handlers.notes",
    "core.tool_handlers.web_search",
    "core.tool_handlers.sl_action",
    "core.tool_handlers.library",
    "core.tool_handlers.semantic_recall",
    # project — interfaces
    "interfaces.setup_server",
    "interfaces.debug_server",
]

REQUIRED_FILES = [
    "main.py",
    "requirements.txt",
    "config/settings.py",
    "core/agent.py",
    "core/model_adapter.py",
    "core/persona.py",
    "core/tools.py",
    "core/supporting_agent.py",
    "core/memory_curator.py",
    "core/librarian_agent.py",
    "core/recall_agent.py",
    "memory/file_store.py",
    "memory/session_index.py",
    "memory/vector_store.py",
    "memory/library_store.py",
    "memory/consolidator.py",
    "lsl/companion_bridge.lsl.template",
    "lua/agent_companion.lua.template",
    "setup/index.html",
    "setup/wizard.js",
    "Containerfile",
    "compose.yml",
    "compose.sandbox.yml",
    "scripts/check_updates.sh",
    "scripts/sandbox-linux.sh",
    "scripts/sandbox-windows.ps1",
    "scripts/pull-live-data.sh",
    "scripts/pull-live-data-windows.ps1",
    "SANDBOXES.md",
]


def check_files() -> list[str]:
    import platform
    from pathlib import Path
    root = Path(__file__).parent
    missing = []
    # run.sh is Linux/Mac only; run.bat covers Windows
    if platform.system() == "Windows":
        launcher = "run.bat"
    else:
        launcher = "run.sh"
    for f in REQUIRED_FILES + [launcher]:
        if not (root / f).exists():
            missing.append(f)
    return missing


def check_imports() -> list[str]:
    failures = []
    for entry in REQUIRED_MODULES:
        if isinstance(entry, tuple):
            mod_path, attr = entry
        else:
            mod_path, attr = entry, None
        try:
            mod = importlib.import_module(mod_path)
            if attr and not hasattr(mod, attr):
                failures.append(f"{mod_path}.{attr} (attribute missing)")
        except Exception as exc:
            failures.append(f"{mod_path}: {exc}")
    return failures


def main() -> int:
    ok = True

    print("Checking required files...")
    missing_files = check_files()
    if missing_files:
        ok = False
        for f in missing_files:
            print(f"  MISSING  {f}")
    else:
        print(f"  OK  ({len(REQUIRED_FILES)} files present)")

    print("\nChecking imports...")
    failed_imports = check_imports()
    if failed_imports:
        ok = False
        for f in failed_imports:
            print(f"  FAIL  {f}")
    else:
        print(f"  OK  ({len(REQUIRED_MODULES)} modules importable)")

    print()
    if ok:
        print("Installation OK")
        return 0
    else:
        print("Installation check FAILED — see above")
        return 1


if __name__ == "__main__":
    sys.exit(main())
