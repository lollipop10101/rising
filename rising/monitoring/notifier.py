from __future__ import annotations
import httpx
class TelegramNotifier:
    def __init__(self,bot_token:str|None=None,chat_id:str|int|None=None): self.bot_token=bot_token or ''; self.chat_id=str(chat_id) if chat_id is not None else ''
    @property
    def configured(self): return bool(self.bot_token and self.chat_id)
    async def send(self,text:str):
        if not self.configured: print('[notifier] not configured; skipping Telegram send'); return
        async with httpx.AsyncClient(timeout=10) as c:
            r=await c.post(f'https://api.telegram.org/bot{self.bot_token}/sendMessage',json={'chat_id':self.chat_id,'text':text}); r.raise_for_status()
