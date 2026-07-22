import os
import re
import uuid
import asyncio
import logging
import time
import subprocess
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait

# Simple logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============ CONFIG ============
API_ID = 35140329
API_HASH = "011f638e4acadee178c59afffc80193d"
BOT_TOKEN = "8518787964:AAHGimBKXfdtrI6UaASGsoI8Aj5Rj_WxF5I"

# Create bot
app = Client(
    "my_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True
)

DOWNLOAD_PATH = "./downloads"
os.makedirs(DOWNLOAD_PATH, exist_ok=True)

video_cache = {}

# ============ COMMANDS ============

@app.on_message(filters.command("start"))
async def start_command(client, message):
    await message.reply_text(
        "**🎬 Instagram Downloader Bot**\n\n"
        "Send me any Instagram link!\n"
        "I will download and send it to you.\n\n"
        "✅ Public posts only\n"
        "✅ HD Quality\n\n"
        "**Send link now!**"
    )

@app.on_message(filters.command("ping"))
async def ping_command(client, message):
    await message.reply_text("🏓 Pong! Bot is working!")

@app.on_message(filters.text)
async def handle_text(client, message):
    # Check if it's Instagram link
    if "instagram.com" in message.text:
        await message.reply_text("📥 Downloading your Instagram media...")
        return
    
    # Ignore other messages
    if not message.text.startswith('/'):
        await message.reply_text("Send me an Instagram link!")

# ============ MAIN ============

if __name__ == "__main__":
    print("🚀 Bot Starting...")
    print("✅ Bot is running! Send /start")
    app.run()
