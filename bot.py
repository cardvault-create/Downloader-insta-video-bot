import os
import re
import uuid
import asyncio
import logging
from datetime import datetime
import aiohttp
import aiofiles
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait
import time
import json
import subprocess

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============ CONFIG ============
API_ID = 35140329
API_HASH = "011f638e4acadee178c59afffc80193d"
BOT_TOKEN = "8518787964:AAHGimBKXfdtrI6UaASGsoI8Aj5Rj_WxF5I"

# Bot Client
app = Client(
    "instagram_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True,
    sleep_threshold=60
)

DOWNLOAD_PATH = "./downloads"
os.makedirs(DOWNLOAD_PATH, exist_ok=True)

video_cache = {}
user_cooldown = {}

# ============ INSTAGRAM APIS ============

INSTAGRAM_APIS = [
    "https://api.davidcyriltech.my.id/instagram?url={}",
    "https://api.nyxs.pw/dl/ig?url={}",
    "https://api.ahmmikun.lol/api/ig?url={}",
]

async def get_download_url(url):
    """Get Instagram download URL"""
    for api in INSTAGRAM_APIS:
        try:
            api_url = api.format(url)
            logger.info(f"Trying API: {api_url}")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        logger.info(f"API Response: {data}")
                        
                        # Parse different responses
                        if isinstance(data, dict):
                            # API 1
                            if data.get("success") and data.get("download_url"):
                                return data["download_url"]
                            # API 2
                            if data.get("result"):
                                result = data["result"]
                                if isinstance(result, dict):
                                    return result.get("download_url") or result.get("url")
                            # API 3
                            if data.get("status") == 200:
                                return data.get("url") or data.get("download_url")
                            # Generic
                            if data.get("url"):
                                return data["url"]
                            if data.get("download_url"):
                                return data["download_url"]
                                
        except Exception as e:
            logger.error(f"API error: {e}")
            continue
    
    return None

async def download_file(url, file_path):
    """Download file"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                if resp.status == 200:
                    async with aiofiles.open(file_path, 'wb') as f:
                        async for chunk in resp.content.iter_chunked(1024 * 1024):
                            await f.write(chunk)
                    
                    if os.path.exists(file_path) and os.path.getsize(file_path) > 10000:
                        return True
        return False
    except Exception as e:
        logger.error(f"Download error: {e}")
        return False

# ============ COMMANDS ============

@app.on_message(filters.command("start"))
async def start_command(client, message):
    try:
        await message.reply_text(
            "**🎬 Instagram Downloader Bot**\n\n"
            "Send any Instagram link (public post/reel)\n\n"
            "✅ HD Quality\n"
            "✅ Fast Download\n"
            "✅ Audio Extract\n\n"
            "**Just send the link!** 🚀"
        )
    except Exception as e:
        logger.error(f"Start error: {e}")

@app.on_message(filters.command("ping"))
async def ping_command(client, message):
    try:
        await message.reply_text("🏓 **Pong! Bot is working**")
    except Exception as e:
        logger.error(f"Ping error: {e}")

@app.on_message(filters.text & filters.private)
async def handle_instagram(client, message):
    try:
        # Check if Instagram link
        if not re.search(r'instagram\.com/(?:p|reel|tv)/', message.text):
            return
        
        user_id = message.from_user.id
        
        # Cooldown
        if user_id in user_cooldown:
            if time.time() - user_cooldown[user_id] < 5:
                await message.reply_text("⏳ **Please wait 5 seconds!**")
                return
        
        user_cooldown[user_id] = time.time()
        
        status_msg = await message.reply_text("🔍 **Processing...**")
        
        url = message.text.strip()
        url = url.split('?')[0]
        
        # Get download URL
        download_url = await get_download_url(url)
        
        if not download_url:
            await status_msg.edit_text(
                "❌ **Failed!**\n\n"
                "Make sure:\n"
                "• Post is **public**\n"
                "• Link is correct\n"
                "• Try again later"
            )
            return
        
        # Download
        file_id = str(uuid.uuid4())[:8]
        ext = 'mp4' if 'mp4' in download_url.lower() else 'jpg'
        file_path = os.path.join(DOWNLOAD_PATH, f"{file_id}.{ext}")
        
        await status_msg.edit_text("📥 **Downloading...**")
        
        if not await download_file(download_url, file_path):
            await status_msg.edit_text("❌ **Download failed!**")
            return
        
        file_size = os.path.getsize(file_path) / (1024 * 1024)
        
        # Cache
        video_cache[file_id] = {
            'path': file_path,
            'ext': ext,
            'time': time.time()
        }
        
        # Keyboard
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📥 Download", callback_data=f"dl_{file_id}"),
                InlineKeyboardButton("🎵 Audio", callback_data=f"au_{file_id}")
            ]
        ])
        
        await status_msg.delete()
        
        # Send file
        if ext == 'mp4':
            await message.reply_video(
                video=file_path,
                caption=f"🎬 **Instagram Video**\n📦 {file_size:.1f} MB",
                reply_markup=keyboard,
                supports_streaming=True
            )
        else:
            await message.reply_photo(
                photo=file_path,
                caption="📸 **Instagram Photo**",
                reply_markup=keyboard
            )
            os.remove(file_path)
            del video_cache[file_id]
            
        logger.info(f"✅ Sent: {file_size:.1f} MB")
        
    except FloodWait as e:
        logger.warning(f"Flood wait: {e.value}s")
        try:
            await status_msg.edit_text(f"⏳ **Wait {e.value}s**")
        except:
            pass
        await asyncio.sleep(e.value)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        try:
            await status_msg.edit_text("❌ **Error! Try again.**")
        except:
            pass

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
            file_name=f"instagram_{file_id}.{data['ext']}"
        )
        await callback.answer("✅ Download started!")
    except Exception as e:
        logger.error(f"DL callback error: {e}")
        await callback.answer("❌ Failed!", show_alert=True)

@app.on_callback_query(filters.regex(r'^au_'))
async def audio_callback(client, callback):
    try:
        file_id = callback.data.replace('au_', '')
        data = video_cache.get(file_id)
        
        if not data or not os.path.exists(data['path']):
            await callback.answer("❌ Expired!", show_alert=True)
            return
        
        await callback.answer("🎵 Extracting...")
        
        audio_file = os.path.join(DOWNLOAD_PATH, f"audio_{file_id}.mp3")
        
        # Extract audio
        try:
            subprocess.run([
                'ffmpeg', '-i', data['path'],
                '-vn', '-acodec', 'libmp3lame',
                '-ab', '192k', '-y', audio_file
            ], capture_output=True, check=True, timeout=30)
            
            if os.path.exists(audio_file) and os.path.getsize(audio_file) > 1000:
                await client.send_audio(
                    chat_id=callback.message.chat.id,
                    audio=audio_file,
                    caption="🎵 Instagram Audio",
                    file_name=f"instagram_audio_{file_id}.mp3"
                )
                os.remove(audio_file)
                await callback.answer("✅ Audio sent!")
            else:
                await callback.answer("❌ No audio!", show_alert=True)
        except subprocess.TimeoutExpired:
            await callback.answer("❌ Timeout!", show_alert=True)
        except:
            await callback.answer("❌ FFmpeg missing!", show_alert=True)
            
    except Exception as e:
        logger.error(f"Audio error: {e}")
        await callback.answer("❌ Failed!", show_alert=True)

# ============ CLEANUP ============

async def cleanup():
    while True:
        try:
            current_time = time.time()
            for file_id, data in list(video_cache.items()):
                if current_time - data.get('time', 0) > 600:
                    if os.path.exists(data['path']):
                        os.remove(data['path'])
                    del video_cache[file_id]
            await asyncio.sleep(300)
        except:
            await asyncio.sleep(60)

# ============ RUN ============

async def main():
    """Main function to run bot"""
    print("🚀 Starting Instagram Bot...")
    
    # Start cleanup task
    asyncio.create_task(cleanup())
    
    print("✅ Bot is running!")
    await app.start()
    await app.idle()

if __name__ == "__main__":
    try:
        # Run the bot
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n❌ Bot stopped!")
    except Exception as e:
        print(f"❌ Error: {e}")
