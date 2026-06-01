from __future__ import annotations

import asyncio
import logging
import os

import uvicorn
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from config.settings import load_settings
from core.agent import AgentCore
from core.librarian_agent import LibrarianAgent
from core.memory_curator import MemoryCuratorAgent
from core.model_adapter import create_adapter
from core.persona import get_agent_config
from core.rate_limiter import RateLimiter
from core.recall_agent import SemanticRecallAgent
from core.supporting_agent import make_supporting_adapter
from core.tools import ToolRegistry
from interfaces.command_center import create_command_center_router
from interfaces.discord_bot.bot import TrixxieBot
from interfaces.debug_server import create_debug_router, install_log_handler
from interfaces.setup_server import create_setup_router, patch_scripts_from_env
from interfaces.sl_bridge.sensor_store import SensorStore
from interfaces.sl_bridge.server import create_sl_app
from memory.consolidator import MemoryConsolidator
from memory.file_store import FileMemoryStore
from memory.avatar_store import AvatarStore
from memory.library_store import LibraryStore
from memory.location_store import LocationStore
from memory.person_map import PersonMap
from memory.session_index import SessionIndex
from memory.vector_store import VectorMemoryStore

PERSON_MAP_PATH = os.path.join(os.path.dirname(__file__), "data", "person_map.json")
CONSOLIDATION_INTERVAL_SECS = 6 * 3600  # every 6 hours

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def _backfill_vector_store(
    session_index: SessionIndex,
    vector_store: VectorMemoryStore,
    person_map: PersonMap,
) -> None:
    """Index all existing sessions.db rows into ChromaDB if not already there.
    Runs as a fire-and-forget background task on startup.
    Safe to re-run — ChromaDB upsert is idempotent by session_id doc id.
    """
    import aiosqlite
    db_path = session_index._db_path
    await session_index._ensure_ready()
    try:
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id, user_id, channel_id, platform, role, content, "
                "timestamp, display_name, importance FROM sessions ORDER BY id ASC"
            ) as cur:
                batch = []
                processed = 0
                async for row in cur:
                    batch.append(dict(row))
                    if len(batch) >= 100:
                        for r in batch:
                            # Resolve person_id from PersonMap
                            pid = person_map.get_person_id(r["user_id"]) or r["user_id"]
                            if not await vector_store.has_document(pid, r["id"]):
                                meta = {
                                    "user_id": r["user_id"],
                                    "channel_id": r["channel_id"],
                                    "platform": r["platform"],
                                    "role": r["role"],
                                    "timestamp": r["timestamp"],
                                    "display_name": r["display_name"],
                                    "importance": float(r["importance"]),
                                }
                                await vector_store.add_turn(pid, r["id"], r["content"], meta)
                        processed += len(batch)
                        if processed % 1000 == 0:
                            logger.info("Vector backfill: %d rows indexed", processed)
                        batch = []
                        await asyncio.sleep(0.1)
                # Final partial batch
                for r in batch:
                    pid = person_map.get_person_id(r["user_id"]) or r["user_id"]
                    if not await vector_store.has_document(pid, r["id"]):
                        meta = {
                            "user_id": r["user_id"],
                            "channel_id": r["channel_id"],
                            "platform": r["platform"],
                            "role": r["role"],
                            "timestamp": r["timestamp"],
                            "display_name": r["display_name"],
                            "importance": float(r["importance"]),
                        }
                        await vector_store.add_turn(pid, r["id"], r["content"], meta)
                processed += len(batch)
        if processed:
            logger.info("Vector backfill complete: %d rows processed", processed)
    except Exception as exc:
        logger.warning("Vector backfill failed: %s", exc)


async def _run_setup_wizard_only() -> None:
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(create_setup_router())
    app.mount(
        "/setup/static",
        StaticFiles(directory=str(Path(__file__).parent / "setup")),
        name="setup_static",
    )
    port = int(os.getenv("SL_BRIDGE_PORT", "8080"))
    host = os.getenv("SL_BRIDGE_HOST", "0.0.0.0")
    logger.warning(
        "Missing required config — wizard-only mode. Open http://%s:%s/setup to configure.",
        host,
        port,
    )
    config = uvicorn.Config(app, host=host, port=port, log_level="warning")
    server = uvicorn.Server(config)
    await server.serve()


async def main() -> None:
    try:
        settings = load_settings()
    except EnvironmentError as exc:
        logger.error("%s", exc)
        await _run_setup_wizard_only()
        return

    patch_scripts_from_env()

    os.makedirs(settings.memory_dir, exist_ok=True)
    os.makedirs(settings.notes_dir, exist_ok=True)
    os.makedirs(settings.library_dir, exist_ok=True)

    session_index = SessionIndex(db_path=Path(settings.memory_dir) / "sessions.db")
    vector_store = VectorMemoryStore(settings.memory_dir)
    memory = FileMemoryStore(
        settings.memory_dir, settings.memory_max_history, session_index, vector_store
    )
    sensor_store = SensorStore()
    location_store = LocationStore(settings.memory_dir)
    avatar_store = AvatarStore(settings.memory_dir)
    library_store = LibraryStore(settings.library_dir)

    # Backfill display names into any existing session rows that predate this field.
    known_avatars = await avatar_store.get_all()
    if known_avatars:
        avatar_map = {uid: entry["display_name"] for uid, entry in known_avatars.items() if entry.get("display_name")}
        await session_index.backfill_display_names(avatar_map)

    # Build per-agent adapters from agent_config.json["supporting_agents"]
    adapter = create_adapter(settings)
    agent_cfg = get_agent_config()

    curator_adapter = make_supporting_adapter(settings, agent_cfg, "memory_curator")
    curator = MemoryCuratorAgent(curator_adapter)

    librarian_adapter = make_supporting_adapter(settings, agent_cfg, "librarian")
    librarian_agent = LibrarianAgent(librarian_adapter, library_store)

    recall_adapter = make_supporting_adapter(settings, agent_cfg, "semantic_recall")
    recall_agent = SemanticRecallAgent(recall_adapter, vector_store)

    tool_registry = ToolRegistry(
        settings, session_index,
        librarian_agent=librarian_agent,
        recall_agent=recall_agent,
    )
    rate_limiter = RateLimiter(settings.rate_limit_capacity, settings.rate_limit_refill_rate)

    person_map = PersonMap.load(PERSON_MAP_PATH)
    logger.info("Person map loaded: %d person(s) linked", len(person_map.all_persons()))

    consolidator = MemoryConsolidator(
        adapter=adapter,
        memory_store=memory,
        person_map=person_map,
        notes_dir=settings.notes_dir,
        curator=curator,
        session_index=session_index,
        importance_threshold=settings.importance_threshold,
    )

    agent = AgentCore(
        adapter=adapter,
        memory=memory,
        tool_registry=tool_registry,
        rate_limiter=rate_limiter,
        settings=settings,
        person_map=person_map,
        library_store=library_store,
    )

    # Backfill existing sessions.db turns into ChromaDB (fire-and-forget)
    asyncio.create_task(_backfill_vector_store(session_index, vector_store, person_map))

    tasks = []

    # ---- Memory consolidation loop ----
    _last_consolidation_path = Path(settings.memory_dir) / ".last_consolidation"

    def _last_consolidation_time() -> float:
        try:
            return float(_last_consolidation_path.read_text().strip())
        except (OSError, ValueError):
            return 0.0

    def _record_consolidation_time() -> None:
        import time
        _last_consolidation_path.write_text(str(time.time()))

    async def consolidation_loop() -> None:
        import time
        # On startup, check how long ago the last run was and sleep only the remainder.
        # This prevents a 6-hour delay after every restart.
        elapsed = time.time() - _last_consolidation_time()
        initial_wait = max(0.0, CONSOLIDATION_INTERVAL_SECS - elapsed)
        if initial_wait < 60:
            initial_wait = 0.0  # overdue — run immediately
        if initial_wait > 0:
            logger.info(
                "Next memory consolidation in %.0f minutes.",
                initial_wait / 60,
            )
        await asyncio.sleep(initial_wait)
        while True:
            logger.info("Running scheduled memory consolidation...")
            await consolidator.run_all()
            _record_consolidation_time()
            await asyncio.sleep(CONSOLIDATION_INTERVAL_SECS)

    tasks.append(asyncio.create_task(consolidation_loop()))

    # ---- Discord bot ----
    if settings.discord_token:
        bot = TrixxieBot(agent, settings)
        tasks.append(asyncio.create_task(bot.start(settings.discord_token)))
        logger.info("Discord bot starting...")
    else:
        logger.warning("DISCORD_TOKEN not set — Discord bot will not start.")

    # ---- Second Life HTTP bridge (always runs) ----
    sl_app = create_sl_app(agent, settings, sensor_store, location_store, avatar_store, session_index)

    # ---- Debug page ----
    install_log_handler(asyncio.get_running_loop())
    sl_app.include_router(create_debug_router(sensor_store, agent, session_index))

    # ---- Setup wizard ----
    sl_app.include_router(create_setup_router())
    sl_app.include_router(create_command_center_router(agent, settings))
    sl_app.mount(
        "/setup/static",
        StaticFiles(directory=str(Path(__file__).parent / "setup")),
        name="setup_static",
    )
    sl_app.mount(
        "/command/static",
        StaticFiles(directory=str(Path(__file__).parent / "command")),
        name="command_static",
    )

    config = uvicorn.Config(
        sl_app,
        host=settings.sl_bridge_host,
        port=settings.sl_bridge_port,
        log_level="info",
    )
    server = uvicorn.Server(config)
    tasks.append(asyncio.create_task(server.serve()))
    logger.info(
        "SL HTTP bridge running at http://%s:%s",
        settings.sl_bridge_host,
        settings.sl_bridge_port,
    )

    if not tasks:
        logger.error("No services started. Check your .env file.")
        return

    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
