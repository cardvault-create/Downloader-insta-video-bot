import os
import re
import uuid
import asyncio
import logging
from datetime import datetime
import aiohttp
import aiofiles
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait
import yt_dlp
from flask import Flask
import threading
import time
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Bot Running ✅"

@web_app.route('/health')
def health():
    return {"status": "ok"}, 200

# ============ CONFIG ============
API_ID = int(os.environ.get("API_ID", "35140329"))
API_HASH = os.environ.get("API_HASH", "011f638e4acadee178c59afffc80193d"))
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8952730755:AAHhor54jekn60e8NflgIJa50cMHwPQ3dbU")

app = Client("bot_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)

DOWNLOAD_PATH = "/tmp/downloads"
os.makedirs(DOWNLOAD_PATH, exist_ok=True)

video_cache = {}
user_states = {}

# ============ INSTAGRAM API ============

async def get_instagram_media(url):
    """Fetch Instagram media using public API"""
    api_url = "https://api.davidcyriltech.my.id/instagram"
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, params={"url": url}, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("success") and data.get("download_url"):
                        return {
                            "url": data["download_url"],
                            "type": "video" if "video" in data.get("type", "") else "photo",
                            "username": data.get("username", "unknown"),
                            "caption": data.get("caption", ""),
                            "duration": data.get("duration", 0)
                        }
    except Exception as e:
        logger.error(f"API 1 error: {e}")
    
    # Fallback API
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://api.ahmmikun.lol/api/ig?url={url}", timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("status") == 200:
                        return {
                            "url": data.get("url", data.get("download_url", "")),
                            "type": "video",
                            "username": data.get("username", "unknown"),
                            "caption": data.get("title", ""),
                            "duration": 0
                        }
    except Exception as e:
        logger.error(f"API 2 error: {e}")
    
    return None

async def download_file(url, file_path):
    """Download file from URL"""
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15'
            }
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=300)) as resp:
                if resp.status == 200:
                    async with aiofiles.open(file_path, 'wb') as f:
                        async for chunk in resp.content.iter_chunked(8192):
                            await f.write(chunk)
                    return True
        return False
    except Exception as e:
        logger.error(f"Download error: {e}")
        return False

# ============ COMMANDS ============

@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text(
        "**🎬 Instagram Downloader Bot**\n\n"
        "Send any Instagram reel/post link!\n\n"
        "✅ **HD Video + Audio**\n"
        "✅ **Original Photos**\n"
        "✅ **Audio Extraction**\n"
        "✅ **Fast Download**\n\n"
        "Just paste a link! 🚀"
    )

@app.on_message(filters.command("ping"))
async def ping(client, message):
    await message.reply_text("🏓 Pong! Working perfectly!")

@app.on_message(filters.regex(r'https?://(?:www\.)?instagram\.com/(?:p|reel|tv)/[^/?]+'))
async def download(client, message):
    status = None
    try:
        url = message.text.strip().split('?')[0]
        
        status = await message.reply_text("🔄 **Fetching...**")
        
        # Get download URL from API
        media = await get_instagram_media(url)
        
        if not media or not media.get("url"):
            await status.edit_text("❌ **Failed to fetch!**\n\nTry another link or check if post is public.\n\nSometimes Instagram blocks, retry after few minutes.")
            return
        
        file_id = str(uuid.uuid4())[:12]
        
        if media["type"] == "video":
            file_path = os.path.join(DOWNLOAD_PATH, f"{file_id}.mp4")
            
            await status.edit_text("📥 **Downloading video...**")
            
            success = await download_file(media["url"], file_path)
            
            if not success or not os.path.exists(file_path):
                await status.edit_text("❌ **Download failed!** Please try again.")
                return
            
            size_mb = os.path.getsize(file_path) / (1024*1024)
            owner = media.get("username", "unknown")
            caption_text = (media.get("caption", "") or "Instagram Video")[:200]
            duration = media.get("duration", 0)
            
            # Store for buttons
            video_cache[file_id] = {
                'video_path': file_path,
                'video_url': url,
                'owner_id': owner,
                'duration': duration
            }
            
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📥 Download Video", callback_data=f"dl_{file_id}"),
                    InlineKeyboardButton("🎵 Extract Audio", callback_data=f"au_{file_id}")
                ]
            ])
            
            caption = f"**🎬 Instagram Video**\n\n"
            caption += f"👤 **@{owner}**\n"
            caption += f"📦 {size_mb:.1f}MB\n"
            if caption_text:
                caption += f"\n📝 {caption_text}"
            
            await status.delete()
            
            if size_mb > 50:
                await message.reply_document(
                    document=file_path,
                    caption=caption,
                    reply_markup=keyboard,
                    file_name=f"instagram_{file_id}.mp4"
                )
            else:
                await message.reply_video(
                    video=file_path,
                    caption=caption,
                    reply_markup=keyboard,
                    supports_streaming=True,
                    duration=duration
                )
            
            logger.info(f"Video sent: {file_id}")
            
        else:
            # Photo
            file_path = os.path.join(DOWNLOAD_PATH, f"{file_id}.jpg")
            
            await status.edit_text("📥 **Downloading photo...**")
            
            success = await download_file(media["url"], file_path)
            
            if not success or not os.path.exists(file_path):
                await status.edit_text("❌ **Failed!** Try again.")
                return
            
            owner = media.get("username", "unknown")
            caption_text = (media.get("caption", "") or "Instagram Photo")[:300]
            
            await status.delete()
            await message.reply_photo(
                photo=file_path,
                caption=f"**📸 Instagram Photo**\n\n👤 **@{owner}**\n\n📝 {caption_text}"
            )
            os.remove(file_path)
            
    except FloodWait as e:
        await asyncio.sleep(e.value + 1)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        if status:
            try:
                await status.edit_text("❌ **Something went wrong!** Try again later.")
            except:
                pass

# ============ BUTTONS ============

@app.on_callback_query(filters.regex(r'^dl_'))
async def dl_video(client, callback):
    try:
        file_id = callback.data.replace('dl_', '')
        v = video_cache.get(file_id)
        
        if not v or not os.path.exists(v['video_path']):
            await callback.answer("❌ Expired! Send link again.", show_alert=True)
            return
        
        await callback.answer("📥 Sending...")
        await callback.message.reply_document(
            document=v['video_path'],
            caption=f"📹 Video | 👤 @{v['owner_id']}",
            file_name=f"instagram_{file_id}.mp4"
        )
    except:
        await callback.answer("❌ Error!", show_alert=True)

@app.on_callback_query(filters.regex(r'^au_'))
async def audio_name(client, callback):
    try:
        file_id = callback.data.replace('au_', '')
        v = video_cache.get(file_id)
        
        if not v:
            await callback.answer("❌ Expired!", show_alert=True)
            return
        
        user_states[callback.from_user.id] = {
            'file_id': file_id,
            'ts': datetime.now().timestamp()
        }
        
        await callback.message.reply_text("🎵 **Audio filename bhejo:**\nExample: my_song")
        await callback.answer()
    except:
        pass

@app.on_message(filters.text & filters.private & ~filters.command(["start", "ping"]))
async def get_audio_name(client, message):
    try:
        uid = message.from_user.id
        if uid not in user_states:
            return
        if datetime.now().timestamp() - user_states[uid]['ts'] > 120:
            del user_states[uid]
            return
        
        file_id = user_states[uid]['file_id']
        v = video_cache.get(file_id)
        if not v or not os.path.exists(v['video_path']):
            del user_states[uid]
            return
        
        name = message.text.strip().replace(' ', '_')[:50]
        if not name.endswith('.mp3'):
            name += '.mp3'
        
        status = await message.reply_text("🔄 **Extracting...**")
        
        audio_out = os.path.join(DOWNLOAD_PATH, f"audio_{file_id}")
        
        # Extract from video file
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': audio_out,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([v['video_path']])
        
        audio_file = audio_out + '.mp3'
        
        if os.path.exists(audio_file):
            await status.edit_text("📤 **Uploading...**")
            await client.send_audio(
                chat_id=message.chat.id,
                audio=audio_file,
                caption=f"🎵 {name.replace('.mp3','')}\n👤 @{v['owner_id']}",
                file_name=name,
                performer=v['owner_id'],
                title=name.replace('.mp3','')
            )
            await status.delete()
            try:
                await message.delete()
            except:
                pass
            os.remove(audio_file)
        else:
            await status.edit_text("❌ Extraction failed!")
        
        del user_states[uid]
    except Exception as e:
        logger.error(f"Audio error: {e}")

# ============ RUN ============

def start_flask():
    port = int(os.environ.get('PORT', 8080))
    web_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

if __name__ == "__main__":
    logger.info("Bot starting...")
    threading.Thread(target=start_flask, daemon=True).start()
    time.sleep(3)
    app.run()
