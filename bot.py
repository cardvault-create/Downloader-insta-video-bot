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
import subprocess

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

# ============ BETTER APIS ============

APIS = [
    "https://api.davidcyriltech.my.id/instagram?url={}",
    "https://www.instagramsave.com/instagram-video-downloader?url={}",
    "https://api.hybrids.id/api/instagram?url={}",
]

# New reliable APIs
RELIABLE_APIS = [
    "https://tikwm.com/api/instagram/?url={}",
    "https://api.azhar32.net/instagram?url={}",
]

async def get_instagram_media(url):
    """Get Instagram media using multiple APIs"""
    
    # Method 1: Using instagram-save.com
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # Try Instagram Save
        async with aiohttp.ClientSession() as session:
            # Get cookies first
            async with session.get("https://www.instagramsave.com/", headers=headers) as resp:
                html = await resp.text()
                # Extract token
                token_match = re.search(r'name="csrf_token" value="([^"]+)"', html)
                csrf_token = token_match.group(1) if token_match else ""
            
            # Post request
            post_data = {
                'url': url,
                'action': 'post',
                'csrf_token': csrf_token
            }
            
            async with session.post(
                "https://www.instagramsave.com/instagram-video-downloader",
                data=post_data,
                headers=headers
            ) as resp:
                html = await resp.text()
                # Extract download URLs
                video_matches = re.findall(r'href="([^"]+\.mp4[^"]*)"', html)
                if video_matches:
                    return video_matches[0]
                
                image_matches = re.findall(r'href="([^"]+\.jpg[^"]*)"', html)
                if image_matches:
                    return image_matches[0]
    
    except Exception as e:
        logger.error(f"Instagram Save error: {e}")
    
    # Method 2: Using davidcyriltech
    try:
        async with aiohttp.ClientSession() as session:
            response = await session.get(
                f"https://api.davidcyriltech.my.id/instagram?url={url}",
                timeout=aiohttp.ClientTimeout(total=10)
            )
            if response.status == 200:
                data = await response.json()
                if data.get('success') and data.get('download_url'):
                    return data['download_url']
    except:
        pass
    
    # Method 3: Using alternative API
    try:
        async with aiohttp.ClientSession() as session:
            response = await session.get(
                f"https://api.azhar32.net/instagram?url={url}",
                timeout=aiohttp.ClientTimeout(total=10)
            )
            if response.status == 200:
                data = await response.json()
                if data.get('result'):
                    return data['result']
    except:
        pass
    
    return None

async def download_media(download_url, file_path):
    """Download media file with progress"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'video/mp4,image/jpeg,*/*',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive'
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(download_url, headers=headers, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                if resp.status == 200:
                    async with aiofiles.open(file_path, 'wb') as f:
                        downloaded = 0
                        async for chunk in resp.content.iter_chunked(1024 * 1024):  # 1MB chunks
                            await f.write(chunk)
                            downloaded += len(chunk)
                    
                    if os.path.exists(file_path) and os.path.getsize(file_path) > 10000:
                        logger.info(f"Downloaded: {os.path.getsize(file_path)} bytes")
                        return True
                    
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

@app.on_message(filters.regex(r'https?://(?:www\.)?instagram\.com/(?:p|reel|tv|stories)/[^/?]+'))
async def handle_instagram(client, message):
    status_msg = None
    try:
        url = message.text.strip().split('?')[0]
        logger.info(f"Processing: {url}")
        
        status_msg = await message.reply_text("🔍 **Searching for media...**")
        
        # Get download URL
        download_url = await get_instagram_media(url)
        
        if not download_url:
            await status_msg.edit_text(
                "❌ **Could not fetch media!**\n\n"
                "Possible reasons:\n"
                "• Post is private\n"
                "• Instagram blocked the request\n"
                "• Invalid URL\n\n"
                "Try:\n"
                "1. Make sure post is public\n"
                "2. Use a different link\n"
                "3. Try again later"
            )
            return
        
        # Generate file name
        file_id = str(uuid.uuid4())[:12]
        ext = '.mp4' if 'mp4' in download_url else '.jpg'
        file_path = os.path.join(DOWNLOAD_PATH, f"{file_id}{ext}")
        
        await status_msg.edit_text("📥 **Downloading media...**")
        
        # Download
        success = await download_media(download_url, file_path)
        
        if not success or not os.path.exists(file_path):
            await status_msg.edit_text("❌ **Download failed!** Please try again.")
            return
        
        file_size = os.path.getsize(file_path)
        size_mb = file_size / (1024 * 1024)
        
        if size_mb < 0.01:
            await status_msg.edit_text("❌ **Empty file received!** Try again.")
            os.remove(file_path)
            return
        
        # Determine if video or photo
        is_video = file_path.endswith('.mp4') or size_mb > 0.5
        
        if is_video:
            # Store for buttons
            video_cache[file_id] = {
                'video_path': file_path,
                'owner_id': 'instagram',
                'timestamp': time.time()
            }
            
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📥 Download", callback_data=f"dl_{file_id}"),
                    InlineKeyboardButton("🎵 Audio", callback_data=f"au_{file_id}")
                ]
            ])
            
            await status_msg.delete()
            
            # Send based on size
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
                    supports_streaming=True,
                    width=720,
                    height=1280
                )
            
            logger.info(f"✅ Video sent: {size_mb:.1f}MB")
            
        else:
            await status_msg.delete()
            await message.reply_photo(
                photo=file_path,
                caption="📸 **Instagram Photo**\n✨ Original Quality"
            )
            os.remove(file_path)
            logger.info("✅ Photo sent")
            
    except FloodWait as e:
        logger.warning(f"Flood: {e.value}s")
        await asyncio.sleep(e.value + 1)
        if status_msg:
            await status_msg.edit_text("⏳ Rate limited. Please wait...")
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        if status_msg:
            try:
                await status_msg.edit_text("❌ **Error!** Please try again later.")
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
        await callback.answer("✅ Download started!")
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
        await callback.message.reply_text("🎵 **Enter filename for audio:**\nExample: my_song")
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
            await message.reply_text("❌ Video expired!")
            return
        
        name = message.text.strip().replace(' ', '_')[:50]
        if not name.endswith('.mp3'):
            name += '.mp3'
        
        status = await message.reply_text("🔄 **Extracting audio...**")
        
        audio_file = os.path.join(DOWNLOAD_PATH, f"audio_{file_id}.mp3")
        
        # Extract audio using ffmpeg
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
            await status.edit_text("📤 **Uploading audio...**")
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
