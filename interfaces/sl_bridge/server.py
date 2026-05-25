from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from pydantic import BaseModel

from config.settings import Settings
from core.agent import AgentCore
from core.persona import MessageContext
from core.persona import get_agent_config
from interfaces.sl_bridge.formatters import cap_reply
from interfaces.sl_bridge.sensor_store import SensorStore
from memory.avatar_store import AvatarStore
from memory.location_store import LocationStore
from memory.session_index import SessionIndex

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------ payloads

class SLInboundPayload(BaseModel):
    user_id: str
    display_name: str
    message: str
    region: str
    channel: int = 0
    timestamp: int = 0
    grid: str = "sl"    # "sl" or "opensim" — controls reply size cap
    client: str = "lsl" # "lsl" (HUD /42) or "lua" (Cool VL Viewer automation script)
    secret: str = ""    # body-based auth for clients that cannot send custom headers (e.g. Lua PostHTTP)


class SLVoicePayload(BaseModel):
    user_id: str
    region: str = ""
    audio_base64: str = ""   # base64-encoded audio (WAV/PCM) from external capture tool
    grid: str = "sl"
    secret: str = ""


class SLSensorPayload(BaseModel):
    type: str           # avatars | environment | objects | clothing | chat
    region: str
    data: Any           # varies by type
    user_id: str = ""
    secret: str = ""


class SLOutboundResponse(BaseModel):
    reply: str
    actions: list[dict] = []


# ------------------------------------------------------------------ app factory

_TIERS = [
    (0,  "no prior history"),
    (1,  "new acquaintance"),
    (5,  "occasional visitor"),
    (15, "regular"),
]


def _relationship_tier(distinct_days: int) -> str:
    tier = "frequent regular"
    for threshold, label in _TIERS:
        if distinct_days <= threshold:
            tier = label
            break
    return tier


def _format_relationship(stats: dict, display_name: str) -> str:
    days = stats.get("distinct_days", 0)
    if not days:
        return ""
    first = (stats.get("first_seen") or "")[:10]
    last = (stats.get("last_seen") or "")[:10]
    since = stats.get("days_since_last", 0)

    if since == 0:
        recency = "today"
    elif since == 1:
        recency = "yesterday"
    else:
        recency = f"{since} days ago"

    tier = _relationship_tier(days)
    parts = [f"## Interaction History — {display_name}"]
    parts.append(
        f"Relationship: {tier} | {days} visit{'s' if days != 1 else ''} "
        f"| First: {first} | Last: {recency}"
    )
    return "\n".join(parts)


def create_sl_app(agent: AgentCore, settings: Settings, sensor_store: SensorStore, location_store: LocationStore | None = None, avatar_store: AvatarStore | None = None, session_index: SessionIndex | None = None) -> FastAPI:
    app = FastAPI(title="Trixxie SL Bridge", docs_url=None, redoc_url=None)

    # ---- Conversation endpoint ----

    @app.post("/sl/message", response_model=SLOutboundResponse)
    async def sl_message(request: Request, payload: SLInboundPayload) -> SLOutboundResponse:
        # Accept secret from X-SL-Secret header (LSL HUD) or request body (Lua PostHTTP).
        header_secret = request.headers.get("X-SL-Secret", "")
        secret = header_secret or payload.secret
        if settings.sl_bridge_secret and secret != settings.sl_bridge_secret:
            logger.warning("SL bridge: invalid secret from %s", payload.user_id)
            return SLOutboundResponse(reply="Authentication failed.", actions=[])

        sl_user_id = f"sl_{payload.user_id}"
        logger.debug("SL message: user=%s client=%s channel=%s", payload.user_id, payload.client, payload.channel)
        sensor_ctx = sensor_store.get_changes(payload.region, sl_user_id)
        recent_locations: list[dict] = []
        if location_store:
            recent_locations = await location_store.get_recent_visits(sl_user_id, limit=10)

        known_avatar: dict | None = None
        if avatar_store:
            await avatar_store.record_encounter(sl_user_id, payload.display_name, payload.channel)
            known_avatar = await avatar_store.get_avatar_async(sl_user_id)
            if known_avatar is not None:
                known_avatar = {**known_avatar, "sl_uuid": payload.user_id}

        relationship = ""
        if session_index:
            stats = await session_index.get_interaction_stats(sl_user_id)
            relationship = _format_relationship(stats, payload.display_name)

        context = MessageContext(
            platform="sl",
            user_id=sl_user_id,
            channel_id=f"sl_{payload.channel}",
            display_name=payload.display_name,
            sl_region=payload.region,
            sl_client=payload.client,
            sl_sensor_context=sensor_ctx,
            sl_recent_locations=recent_locations,
            sl_known_avatar=known_avatar,
            sl_relationship=relationship,
        )

        try:
            result = await agent.handle_message(payload.message, context)
        except Exception as exc:
            logger.exception("SL bridge error: %s", exc)
            return SLOutboundResponse(
                reply="Something went sideways. Try again in a moment.",
                actions=[],
            )

        logger.info("SL reply: client=%s actions=%s", payload.client, result.sl_actions)
        return SLOutboundResponse(
            reply=cap_reply(result.text, grid=payload.grid),
            actions=result.sl_actions[:5],
        )

    # ---- Sensor endpoint ----

    @app.post("/sl/sensor")
    async def sl_sensor(request: Request, payload: SLSensorPayload) -> dict:
        header_secret = request.headers.get("X-SL-Secret", "")
        secret = header_secret or payload.secret
        if settings.sl_bridge_secret and secret != settings.sl_bridge_secret:
            return {"status": "unauthorized"}

        sensor_store.update(payload.region, payload.type, payload.data)
        logger.debug("Sensor update: type=%s region=%s", payload.type, payload.region)

        if payload.type == "environment" and location_store and payload.user_id:
            data = payload.data if isinstance(payload.data, dict) else {}
            parcel = data.get("parcel", "")
            parcel_desc = data.get("parcel_desc", "")
            region = data.get("region", payload.region)
            if parcel:
                sl_user_id = f"sl_{payload.user_id}"
                is_new = await location_store.record_visit(sl_user_id, region, parcel, parcel_desc)
                if is_new:
                    logger.debug("Location recorded: %s / %s for %s", region, parcel, sl_user_id)

        return {"status": "ok"}

    # ---- Voice endpoint (stub) ----

    @app.post("/sl/voice")
    async def sl_voice(request: Request, payload: SLVoicePayload) -> dict:
        header_secret = request.headers.get("X-SL-Secret", "")
        secret = header_secret or payload.secret
        if settings.sl_bridge_secret and secret != settings.sl_bridge_secret:
            return {"status": "unauthorized", "reply": ""}

        cfg_tools = get_agent_config().get("tools", {})
        if not cfg_tools.get("voice", False):
            return {
                "status": "stub",
                "reply": (
                    "Voice input received. Voice processing isn't active in my current "
                    "configuration — a voice-capable model needs to be configured to use it."
                ),
            }

        # Future: decode payload.audio_base64, send to voice-capable model, return transcript + reply
        logger.info("Voice POST from sl_%s — voice model processing not yet implemented", payload.user_id)
        return {"status": "stub", "reply": "Voice model not implemented."}

    # ---- Health ----

    @app.get("/health")
    async def health() -> dict:
        return {"status": "ok", "name": "trixxie-sl-bridge"}

    return app
