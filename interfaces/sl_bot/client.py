from __future__ import annotations

"""
OpenPalAI — Second Life Bot Avatar Client

Connects the agent to SL as a real avatar using a pure-Python protocol
implementation (no third-party SL libraries required).

SETUP:
  Set SL_BOT_FIRSTNAME, SL_BOT_LASTNAME, SL_BOT_PASSWORD in .env
  Then run: python main.py
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from config.settings import Settings
from core.agent import AgentCore
from core.persona import MessageContext
from interfaces.sl_bot.sl_protocol import IncomingIM, SLProtocol, sl_login

logger = logging.getLogger(__name__)

SL_IM_LIMIT = 1023


class SLBotClient:
    """Connects OpenPalAI to Second Life as a real avatar account."""

    def __init__(self, agent: AgentCore, settings: Settings) -> None:
        self._agent = agent
        self._settings = settings
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sl-login")
        self._protocol: SLProtocol | None = None
        self._login_result = None

    async def start(self) -> None:
        """Log OpenPalAI into SL and start listening for IMs."""
        logger.info(
            "Logging into Second Life as %s %s...",
            self._settings.sl_bot_firstname,
            self._settings.sl_bot_lastname,
        )

        # Login is synchronous XMLRPC — run in thread pool
        loop = asyncio.get_running_loop()
        try:
            self._login_result = await loop.run_in_executor(
                self._executor,
                sl_login,
                self._settings.sl_bot_firstname,
                self._settings.sl_bot_lastname,
                self._settings.sl_bot_password,
            )
        except Exception as exc:
            logger.error("SL login failed: %s", exc)
            return

        logger.info(
            "OpenPalAI logged in. Region: %s | Agent: %s",
            self._login_result.region_name,
            self._login_result.agent_id,
        )

        # Open UDP connection to the sim
        transport, self._protocol = await loop.create_datagram_endpoint(
            lambda: SLProtocol(self._login_result, self._handle_im),
            remote_addr=(self._login_result.sim_ip, self._login_result.sim_port),
        )

        # Keep running until cancelled
        try:
            await asyncio.Future()  # run forever
        except asyncio.CancelledError:
            transport.close()
            logger.info("SL bot disconnected.")

    # --------------------------------------------------------- IM handling

    async def _handle_im(self, im: IncomingIM) -> None:
        """Process an incoming IM through AgentCore and send reply."""
        logger.info("IM from %s (%s): %s", im.from_name, im.from_agent_id, im.message[:80])

        context = MessageContext(
            platform="sl",
            user_id=f"sl_{im.from_agent_id}",
            channel_id=f"sl_im_{im.from_agent_id}",
            display_name=im.from_name,
            sl_region=self._login_result.region_name if self._login_result else "",
        )

        try:
            result = await self._agent.handle_message(im.message, context)
        except Exception:
            logger.exception("AgentCore error handling IM from %s", im.from_name)
            self._send_im(im.from_agent_id, "Something went sideways on my end. Try again?")
            return

        if result.text:
            self._send_im(im.from_agent_id, result.text)

        for action in result.sl_actions[:5]:
            self._execute_action(im.from_agent_id, action)

    def _send_im(self, to_agent_id: str, message: str) -> None:
        if self._protocol is None:
            return
        # Trim to SL limit
        if len(message) > SL_IM_LIMIT:
            message = message[:SL_IM_LIMIT - 3] + "..."
        self._protocol.send_instant_message(to_agent_id, message)

    def _execute_action(self, target_id: str, action: dict) -> None:
        action_type = action.get("action_type", "")
        text = action.get("text", "")

        if action_type in ("im", "emote"):
            if action_type == "emote" and not text.startswith("*"):
                text = f"*{text}*"
            self._send_im(target_id, text)
        elif action_type == "anim_trigger":
            # Animation triggering requires additional permission packets
            # This is a future enhancement — log for now
            logger.debug("anim_trigger '%s' not yet implemented in minimal client", text)
