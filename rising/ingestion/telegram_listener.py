from __future__ import annotations
from datetime import timezone
from loguru import logger
from telethon import TelegramClient, events
from rising.parsing.address_extractor import extract_solana_addresses, is_signal_address

class TelegramSignalListener:
    def __init__(self, api_id: int, api_hash: str, session_name: str, source_chats: list[str], on_token):
        self.client = TelegramClient(session_name, api_id, api_hash)
        self.source_chats = source_chats or None
        self.on_token = on_token

    async def start(self):
        await self.client.start()
        logger.info("Telegram listener started")

        @self.client.on(events.NewMessage(chats=self.source_chats))
        async def handler(event):
            text = event.raw_text or ""
            # Only trigger on pure signal addresses (standalone address, no other content)
            if not is_signal_address(text):
                return
            addresses = extract_solana_addresses(text)
            if not addresses:
                return
            msg_time = event.message.date.astimezone(timezone.utc)
            chat_id = str(event.chat_id or "")
            sender_id = str(event.sender_id or "")
            for address in addresses:
                await self.on_token(address, text, msg_time, chat_id, sender_id)

        await self.client.run_until_disconnected()
