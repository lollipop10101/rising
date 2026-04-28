from __future__ import annotations

import aiohttp
from loguru import logger


class TelegramNotifier:
    def __init__(self, bot_token: str | None, chat_id: str | int | None) -> None:
        self.bot_token = bot_token
        self.chat_id = chat_id

    async def send(self, text: str) -> None:
        if not self.bot_token or not self.chat_id:
            logger.info("Notifier disabled: {}", text)
            return
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={"chat_id": self.chat_id, "text": text, "disable_web_page_preview": True}) as resp:
                if resp.status >= 400:
                    logger.warning("Telegram notify failed {}: {}", resp.status, await resp.text())
