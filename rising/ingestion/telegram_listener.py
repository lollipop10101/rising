from __future__ import annotations
from collections.abc import Awaitable, Callable
from loguru import logger

MessageHandler = Callable[[str, str | None], Awaitable[None]]

class TelegramSignalListener:
    def __init__(self, api_id: int, api_hash: str, session: str, source_chat: str | int, bot_token: str | None = None):
        self.api_id = api_id
        self.api_hash = api_hash
        self.session = session
        self.source_chat = source_chat
        self.bot_token = bot_token
        self.client = None

    async def run(self, handler: MessageHandler) -> None:
        try:
            from telethon import TelegramClient, events
        except ImportError as exc:
            raise RuntimeError("telethon is required for telegram mode. Run: pip install -r requirements.txt") from exc
        self.client = TelegramClient(self.session, self.api_id, self.api_hash)
        @self.client.on(events.NewMessage(chats=self.source_chat))
        async def _on_message(event):
            text = event.raw_text or ""
            logger.info("Telegram message received: {}", text[:120].replace("\n", " "))
            await handler(text, str(self.source_chat))
        if self.bot_token:
            await self.client.start(bot_token=self.bot_token)
        else:
            await self.client.start()
        logger.info("Listening to Telegram chat: {}", self.source_chat)
        await self.client.run_until_disconnected()
