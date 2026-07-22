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
API_HASH = os.environ.get("API_HASH", "011f638e4acadee178c59afffc80193d")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8952730755:AAHhor54jekn60e8NflgIJa50cMHwPQ3dbU")

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)

DOWNLOAD_PATH = "/tmp/downloads"
os.makedirs(DOWNLOAD_PATH, exist_ok=True)

video_cache = {}
user_states = {}

# ============ API ENDPOINTS ============

APIS = [
    "https://api.davidcyriltech.my.id/instagram?url={}",
    "https://api.ahmmikun.lol/api/ig?url={}",
    "https://api.nyxs.pw/dl/ig?url={}",
]

async def try_all_apis(url):
    """Try multiple APIs until one works"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36',
        'Accept': 'application/json'
    }
    
    for api_url in APIS:
        try:
            full_url = api_url.format(url)
            logger.info(f"Trying: {full_url}")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(full_url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        data = json.loads(text)
                        
                        # Different API response formats
                        download_url = None
                        
                        if isinstance(data, dict):
                            # API 1: davidcyriltech
                            if data.get("success") and data.get("download_url"):
                                download_url = data["download_url"]
                            # API 2: ahmmikun
                            elif data.get("status") == 200:
                                download_url = data.get("url") or data.get("download_url")
                            # API 3: nyxs
                            elif data.get("result"):
                                download_url = data["result"].get("download_url") or data["result"].get("url")
                            # Generic
                            else:
                                download_url = data.get("url") or data.get("download_url") or data.get("link")
                        
                        if download_url:
                            logger.info(f"Got download URL: {download_url[:50]}...")
                            return download_url
                            
        except asyncio.TimeoutError:
            logger.warning(f"Timeout for {api_url}")
        except Exception as e:
            logger.error(f"API error: {e}")
    
    return None

async def download_media(download_url, file_path):
    """Download media file"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X)',
            'Accept': '*/*'
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(download_url, headers=headers, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                if resp.status == 200:
                    async with aiofiles.open(file_path, 'wb') as f:
                        downloaded = 0
                        async for chunk in resp.content.iter_chunked(512 * 1024):  # 512KB chunks
                            await f.write(chunk)
                            downloaded += len(chunk)
                    
                    if os.path.exists(file_path) and os.path.getsize(file_path) > 10000:
                        logger.info(f"Downloaded: {os.path.getsize(file_path)} bytes")
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
        "Send any public Instagram reel/post link!\n\n"
        "✅ HD Quality Video\n"
        "✅ Original Photos\n"
        "✅ Audio Extraction\n\n"
        "🚀 Send link now!"
    )

@app.on_message(filters.command("ping"))
async def ping(client, message):
    await message.reply_text("✅ Bot is working! Send Instagram link.")

@app.on_message(filters.regex(r'https?://(?:www\.)?instagram\.com/(?:p|reel|tv)/[^/?]+'))
async def handle_instagram(client, message):
    status = None
    try:
        url = message.text.strip().split('?')[0]
        
        status = await message.reply_text("🔍 **Searching...**")
        
        # Try all APIs
        download_url = await try_all_apis(url)
        
        if not download_url:
            await status.edit_text(
                "❌ **No download URL found!**\n\n"
                "Make sure the post is **public**.\n"
                "Private accounts won't work.\n\n"
                "Try another link."
            )
            return
        
        file_id = str(uuid.uuid4())[:12]
        file_path = os.path.join(DOWNLOAD_PATH, f"{file_id}.mp4")
        
        await status.edit_text("📥 **Downloading...**")
        
        # Download the media
        success = await download_media(download_url, file_path)
        
        if not success or not os.path.exists(file_path):
            await status.edit_text("❌ **Download failed!** Server issue. Try again.")
            return
        
        file_size = os.path.getsize(file_path)
        size_mb = file_size / (1024 * 1024)
        
        if size_mb < 0.01:  # Less than 10KB
            await status.edit_text("❌ **Empty file!** Instagram blocked. Try later.")
            os.remove(file_path)
            return
        
        # Check if video or photo
        is_video = file_path.endswith('.mp4') or size_mb > 0.5
        
        if is_video:
            # Store for buttons
            video_cache[file_id] = {
                'video_path': file_path,
                'owner_id': 'instagram'
            }
            
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📥 Download", callback_data=f"dl_{file_id}"),
                    InlineKeyboardButton("🎵 Audio", callback_data=f"au_{file_id}")
                ]
            ])
            
            await status.delete()
            
            if size_mb > 50:
                await message.reply_document(
                    document=file_path,
                    caption=f"🎬 **Instagram Video**\n📦 {size_mb:.1f}MB\n✨ HD Quality",
                    reply_markup=keyboard,
                    file_name=f"instagram_{file_id}.mp4"
                )
            else:
                await message.reply_video(
                    video=file_path,
                    caption=f"🎬 **Instagram Video**\n📦 {size_mb:.1f}MB\n✨ HD Quality",
                    reply_markup=keyboard,
                    supports_streaming=True
                )
            
            logger.info(f"✅ Video sent: {size_mb:.1f}MB")
            
        else:
            await status.delete()
            await message.reply_photo(
                photo=file_path,
                caption="📸 **Instagram Photo**\n✨ Original Quality"
            )
            os.remove(file_path)
            logger.info("✅ Photo sent")
            
    except FloodWait as e:
        logger.warning(f"Flood: {e.value}s")
        await asyncio.sleep(e.value + 1)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        if status:
            try:
                await status.edit_text("❌ **Error!** Please try again.")
            except:
                pass

# ============ BUTTONS ============

@app.on_callback_query(filters.regex(r'^dl_'))
async def download_video(client, callback):
    try:
        file_id = callback.data.replace('dl_', '')
        v = video_cache.get(file_id)
        
        if not v or not os.path.exists(v['video_path']):
            await callback.answer("❌ Expired! Send again.", show_alert=True)
            return
        
        await callback.message.reply_document(
            document=v['video_path'],
            caption="📹 Instagram Video",
            file_name=f"instagram_{file_id}.mp4"
        )
        await callback.answer("✅ Sent!")
    except Exception as e:
        logger.error(f"DL error: {e}")
        await callback.answer("❌ Failed!", show_alert=True)

@app.on_callback_query(filters.regex(r'^au_'))
async def audio_request(client, callback):
    try:
        file_id = callback.data.replace('au_', '')
        v = video_cache.get(file_id)
        if not v:
            await callback.answer("❌ Expired!", show_alert=True)
            return
        
        user_states[callback.from_user.id] = {
            'file_id': file_id,
            'ts': time.time()
        }
        await callback.message.reply_text("🎵 **Enter filename:**\nExample: my_song")
        await callback.answer()
    except:
        pass

@app.on_message(filters.text & filters.private & ~filters.command(["start", "ping"]))
async def audio_extract(client, message):
    try:
        uid = message.from_user.id
        if uid not in user_states:
            return
        if time.time() - user_states[uid]['ts'] > 120:
            del user_states[uid]
            return
        
        file_id = user_states[uid]['file_id']
        v = video_cache.get(file_id)
        if not v or not os.path.exists(v['video_path']):
            del user_states[uid]
            await message.reply_text("❌ Expired!")
            return
        
        name = message.text.strip().replace(' ', '_')[:50]
        if not name.endswith('.mp3'):
            name += '.mp3'
        
        status = await message.reply_text("🔄 **Extracting audio...**")
        
        audio_file = os.path.join(DOWNLOAD_PATH, f"audio_{file_id}.mp3")
        
        # Use subprocess ffmpeg
        import subprocess
        cmd = [
            'ffmpeg', '-i', v['video_path'],
            '-vn', '-acodec', 'libmp3lame',
            '-ab', '192k', '-ar', '44100',
            '-y', audio_file
        ]
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await proc.communicate()
        
        if os.path.exists(audio_file) and os.path.getsize(audio_file) > 1000:
            await status.edit_text("📤 **Uploading...**")
            await client.send_audio(
                chat_id=message.chat.id,
                audio=audio_file,
                caption=f"🎵 {name.replace('.mp3','')}\n📱 Instagram Audio",
                file_name=name,
                title=name.replace('.mp3','')
            )
            await status.delete()
            try:
                await message.delete()
            except:
                pass
            os.remove(audio_file)
        else:
            await status.edit_text("❌ No audio found in video!")
        
        del user_states[uid]
    except Exception as e:
        logger.error(f"Audio error: {e}")

# ============ RUN ============

def start_flask():
    port = int(os.environ.get('PORT', 8080))
    web_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

if __name__ == "__main__":
    logger.info("Starting Instagram Downloader Bot...")
    threading.Thread(target=start_flask, daemon=True).start()
    time.sleep(3)
    app.run()
