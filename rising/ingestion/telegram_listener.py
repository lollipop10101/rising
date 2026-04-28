from __future__ import annotations

from collections.abc import Awaitable, Callable

from loguru import logger
from telethon import TelegramClient, events


MessageHandler = Callable[[str, str | None], Awaitable[None]]


class TelegramSignalListener:
    def __init__(self, api_id: int, api_hash: str, session: str, source_chat: str | int) -> None:
        self.client = TelegramClient(session, api_id, api_hash)
        self.source_chat = source_chat

    async def run(self, handler: MessageHandler) -> None:
        @self.client.on(events.NewMessage(chats=self.source_chat))
        async def _on_message(event):
            text = event.raw_text or ""
            logger.info("Telegram message received: {}", text[:120].replace("\n", " "))
            await handler(text, str(self.source_chat))

        await self.client.start()
        logger.info("Listening to Telegram chat: {}", self.source_chat)
        await self.client.run_until_disconnected()
