#!/usr/bin/env python3
"""Run this directly — it asks for the code interactively."""
import os
from dotenv import load_dotenv
load_dotenv()
from telethon import TelegramClient
import asyncio

api_id = int(os.getenv('TELEGRAM_API_ID'))
api_hash = os.getenv('TELEGRAM_API_HASH')
session = os.getenv('TELEGRAM_SESSION')

async def main():
    client = TelegramClient(session, api_id, api_hash)
    await client.start(phone='+66879198942')
    me = await client.get_me()
    print(f'✅ Logged in as: {me.first_name} {me.last_name or ""} (@{me.username})')
    print('Session saved! You can now run the bot.')
    await client.disconnect()

asyncio.run(main())
