import os
import re
import asyncio
import logging
from pyrogram import Client, filters

logging.basicConfig(level=logging.INFO)

# ============ CONFIG ============
API_ID = 35140329
API_HASH = "011f638e4acadee178c59afffc80193d"
BOT_TOKEN = "8518787964:AAHGimBKXfdtrI6UaASGsoI8Aj5Rj_WxF5I"

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ============ SIMPLE COMMANDS ============

@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text("✅ Bot is working! Send Instagram link.")

@app.on_message(filters.command("ping"))
async def ping(client, message):
    await message.reply_text("🏓 Pong!")

@app.on_message(filters.text)
async def echo(client, message):
    # Reply to every message
    await message.reply_text(f"You said: {message.text}")

# ============ RUN ============
if __name__ == "__main__":
    print("🚀 Bot Starting...")
    app.run()
