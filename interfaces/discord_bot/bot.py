from __future__ import annotations

import logging

import discord

from config.settings import Settings
from core.agent import AgentCore
from core.persona import MessageContext, resolve_platform_agent_id
from interfaces.discord_bot.formatters import chunk_text

logger = logging.getLogger(__name__)


class OpenPalAIBot(discord.Client):
    def __init__(self, agent: AgentCore, settings: Settings) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self._agent = agent
        self._settings = settings

    async def on_ready(self) -> None:
        logger.info("OpenPalAI is online as %s (id: %s)", self.user, self.user.id)

    async def on_message(self, message: discord.Message) -> None:
        # Never respond to ourselves
        if message.author == self.user:
            return

        # Guild restrictions
        if self._settings.discord_allowed_guild_ids and message.guild:
            if message.guild.id not in self._settings.discord_allowed_guild_ids:
                return

        # Respond to: DMs always, @mentions always, active channels without @mention
        is_dm = isinstance(message.channel, discord.DMChannel)
        is_mentioned = self.user in message.mentions
        is_active_channel = message.channel.id in self._settings.discord_active_channel_ids

        if not is_dm and not is_mentioned and not is_active_channel:
            return

        # Strip the @mention prefix from the message text
        content = message.content
        if self.user.mention in content:
            content = content.replace(self.user.mention, "").strip()
        if not content:
            content = "(no message)"

        context = MessageContext(
            platform="discord",
            user_id=f"discord_{message.author.id}",
            channel_id=f"discord_{message.channel.id}",
            display_name=message.author.display_name,
            agent_id=resolve_platform_agent_id("discord"),
            guild_id=message.guild.id if message.guild else None,
        )

        async with message.channel.typing():
            try:
                result = await self._agent.handle_message(content, context)
            except Exception as exc:
                logger.exception("Discord handler error: %s", exc)
                await message.channel.send(
                    "Something went sideways on my end. Try again in a moment."
                )
                return

        if not result.text:
            return

        chunks = chunk_text(result.text)
        for chunk in chunks:
            await message.channel.send(chunk)
