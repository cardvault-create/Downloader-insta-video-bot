import os
import re
import uuid
import asyncio
import logging
import time
import aiohttp
import aiofiles
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton

logging.basicConfig(level=logging.INFO)

# ============ CONFIG ============
API_ID = 35140329
API_HASH = "011f638e4acadee178c59afffc80193d"
BOT_TOKEN = "8518787964:AAHGimBKXfdtrI6UaASGsoI8Aj5Rj_WxF5I"

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

DOWNLOAD_PATH = "./downloads"
os.makedirs(DOWNLOAD_PATH, exist_ok=True)

video_cache = {}

# ============ INSTAGRAM API ============

async def get_instagram_video(url):
    """Get Instagram video download URL"""
    try:
        api_url = f"https://api.davidcyriltech.my.id/instagram?url={url}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, timeout=15) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("success") and data.get("download_url"):
                        return data["download_url"]
    except Exception as e:
        logging.error(f"API error: {e}")
    
    return None

async def download_file(url, file_path):
    """Download file"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=120) as resp:
                if resp.status == 200:
                    async with aiofiles.open(file_path, 'wb') as f:
                        async for chunk in resp.content.iter_chunked(1024*1024):
                            await f.write(chunk)
                    return True
    except Exception as e:
        logging.error(f"Download error: {e}")
    return False

# ============ COMMANDS ============

@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text(
        "**🎬 Instagram Downloader Bot**\n\n"
        "Send me any Instagram video/reel link!\n"
        "I will download and send it to you.\n\n"
        "✅ Public posts only\n"
        "✅ HD Quality\n\n"
        "**Send link now!** 🚀"
    )

@app.on_message(filters.command("ping"))
async def ping(client, message):
    await message.reply_text("🏓 Pong! Bot is working!")

@app.on_message(filters.text & filters.private)
async def handle_instagram(client, message):
    # Check if Instagram link
    if not re.search(r'instagram\.com/(?:p|reel|tv)/', message.text):
        if not message.text.startswith('/'):
            await message.reply_text("❌ Please send an Instagram link!")
        return
    
    status = await message.reply_text("🔍 **Processing...**")
    
    try:
        url = message.text.strip()
        url = url.split('?')[0]
        
        logging.info(f"Processing: {url}")
        
        # Get download URL
        download_url = await get_instagram_video(url)
        
        if not download_url:
            await status.edit_text(
                "❌ **Failed to download!**\n\n"
                "Reasons:\n"
                "• Post is private\n"
                "• Invalid link\n"
                "• Try another video"
            )
            return
        
        # Download
        file_id = str(uuid.uuid4())[:8]
        file_path = os.path.join(DOWNLOAD_PATH, f"{file_id}.mp4")
        
        await status.edit_text("📥 **Downloading...**")
        
        if not await download_file(download_url, file_path):
            await status.edit_text("❌ **Download failed! Try again.**")
            return
        
        file_size = os.path.getsize(file_path) / (1024 * 1024)
        
        # Cache
        video_cache[file_id] = {
            'path': file_path,
            'time': time.time()
        }
        
        # Keyboard
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📥 Download", callback_data=f"dl_{file_id}"),
                InlineKeyboardButton("🎵 Audio", callback_data=f"au_{file_id}")
            ]
        ])
        
        await status.delete()
        
        # Send video
        if file_size > 50:
            await message.reply_document(
                document=file_path,
                caption=f"🎬 **Instagram Video**\n📦 {file_size:.1f} MB",
                reply_markup=keyboard,
                file_name=f"instagram_{file_id}.mp4"
            )
        else:
            await message.reply_video(
                video=file_path,
                caption=f"🎬 **Instagram Video**\n📦 {file_size:.1f} MB",
                reply_markup=keyboard,
                supports_streaming=True
            )
        
        logging.info(f"✅ Video sent: {file_size:.1f} MB")
        
    except Exception as e:
        logging.error(f"Error: {e}")
        await status.edit_text("❌ **Error! Please try again**")

# ============ BUTTONS ============

@app.on_callback_query(filters.regex(r'^dl_'))
async def download_callback(client, callback):
    try:
        file_id = callback.data.replace('dl_', '')
        data = video_cache.get(file_id)
        
        if not data or not os.path.exists(data['path']):
            await callback.answer("❌ Expired!", show_alert=True)
            return
        
        await callback.message.reply_document(
            document=data['path'],
            caption="📹 Instagram Video",
            file_name=f"instagram_{file_id}.mp4"
        )
        await callback.answer("✅ Download started!")
    except Exception as e:
        await callback.answer("❌ Failed!", show_alert=True)

@app.on_callback_query(filters.regex(r'^au_'))
async def audio_callback(client, callback):
    await callback.answer("🎵 Coming soon!", show_alert=True)

# ============ CLEANUP ============

async def cleanup():
    while True:
        try:
            for file_id, data in list(video_cache.items()):
                if time.time() - data['time'] > 600:
                    if os.path.exists(data['path']):
                        os.remove(data['path'])
                    del video_cache[file_id]
            await asyncio.sleep(300)
        except:
            await asyncio.sleep(60)

# ============ RUN ============

if __name__ == "__main__":
    print("🚀 Starting Instagram Downloader Bot...")
    print("✅ Bot is running! Send /start")
    
    # Simple run - no event loop issues
    app.run()
