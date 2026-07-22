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
from flask import Flask
import threading
import time
import json
import subprocess
import sys

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

# ============ SIMPLE API BASED DOWNLOAD ============

# Working Instagram APIs (Updated)
INSTAGRAM_APIS = [
    {
        'url': 'https://api.davidcyriltech.my.id/instagram?url={}',
        'parser': lambda d: d.get('download_url') if d.get('success') else None
    },
    {
        'url': 'https://api.nyxs.pw/dl/ig?url={}',
        'parser': lambda d: d.get('result', {}).get('download_url') or d.get('result', {}).get('url')
    },
    {
        'url': 'https://api.siputzx.my.id/api/d/ig?url={}',
        'parser': lambda d: d.get('data', {}).get('download')
    }
]

async def get_instagram_media(url):
    """Get Instagram media using multiple APIs"""
    
    for api_info in INSTAGRAM_APIS:
        try:
            api_url = api_info['url'].format(url)
            logger.info(f"Trying API: {api_url}")
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        download_url = api_info['parser'](data)
                        
                        if download_url:
                            logger.info(f"Found download URL: {download_url[:50]}...")
                            return download_url
                            
        except asyncio.TimeoutError:
            logger.warning(f"Timeout for API")
        except Exception as e:
            logger.error(f"API error: {e}")
    
    return None

async def download_media(url, file_path):
    """Download media file"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': '*/*',
            'Connection': 'keep-alive'
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                if resp.status == 200:
                    async with aiofiles.open(file_path, 'wb') as f:
                        downloaded = 0
                        async for chunk in resp.content.iter_chunked(1024 * 1024):
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
        "Send any public Instagram link!\n\n"
        "✅ **Works with:**\n"
        "• Posts (p/)\n"
        "• Reels (reel/)\n"
        "• TV (tv/)\n\n"
        "🚀 **Send link now!**"
    )

@app.on_message(filters.command("ping"))
async def ping(client, message):
    await message.reply_text("✅ **Bot is working!**")

@app.on_message(filters.text & filters.private)
async def handle_message(client, message):
    # Check if it's an Instagram link
    if not re.search(r'instagram\.com/(?:p|reel|tv)/', message.text):
        return
    
    status_msg = None
    try:
        url = message.text.strip()
        # Clean URL
        url = re.sub(r'\?.*$', '', url)
        url = re.sub(r'#.*$', '', url)
        
        logger.info(f"Processing: {url}")
        
        status_msg = await message.reply_text("🔍 **Searching for media...**")
        
        # Get download URL
        download_url = await get_instagram_media(url)
        
        if not download_url:
            await status_msg.edit_text(
                "❌ **Could not fetch media!**\n\n"
                "Make sure:\n"
                "• Post is **public**\n"
                "• Link is correct\n"
                "• Try another link\n\n"
                "🔄 **Still not working?**\n"
                "Try sending the link from Instagram app"
            )
            return
        
        # Generate file info
        file_id = str(uuid.uuid4())[:12]
        
        # Determine file extension from URL
        if '.mp4' in download_url.lower():
            ext = 'mp4'
        elif '.jpg' in download_url.lower() or '.jpeg' in download_url.lower():
            ext = 'jpg'
        elif '.png' in download_url.lower():
            ext = 'png'
        else:
            ext = 'mp4'  # Default
        
        file_path = os.path.join(DOWNLOAD_PATH, f"{file_id}.{ext}")
        
        await status_msg.edit_text("📥 **Downloading media...**")
        
        # Download
        success = await download_media(download_url, file_path)
        
        if not success or not os.path.exists(file_path):
            await status_msg.edit_text("❌ **Download failed!** Please try again.")
            return
        
        file_size = os.path.getsize(file_path)
        size_mb = file_size / (1024 * 1024)
        
        if size_mb < 0.01:
            await status_msg.edit_text("❌ **Invalid file!** Try again.")
            os.remove(file_path)
            return
        
        # Cache for later use
        video_cache[file_id] = {
            'path': file_path,
            'ext': ext,
            'size': file_size,
            'timestamp': time.time()
        }
        
        # Keyboard
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📥 Download", callback_data=f"dl_{file_id}"),
                InlineKeyboardButton("🎵 Audio", callback_data=f"au_{file_id}")
            ]
        ])
        
        await status_msg.delete()
        
        # Send based on type
        if ext in ['mp4', 'mov', 'avi', 'mkv']:
            caption = f"🎬 **Instagram Video**\n📦 {size_mb:.1f} MB"
            
            if size_mb > 50:
                await message.reply_document(
                    document=file_path,
                    caption=caption,
                    reply_markup=keyboard,
                    file_name=f"instagram_{file_id}.{ext}"
                )
            else:
                await message.reply_video(
                    video=file_path,
                    caption=caption,
                    reply_markup=keyboard,
                    supports_streaming=True
                )
            logger.info(f"✅ Video sent: {size_mb:.1f} MB")
            
        elif ext in ['jpg', 'jpeg', 'png', 'gif']:
            await message.reply_photo(
                photo=file_path,
                caption=f"📸 **Instagram Photo**\n✨ Original Quality",
                reply_markup=keyboard
            )
            logger.info("✅ Photo sent")
            # Photo is small, remove it
            os.remove(file_path)
            del video_cache[file_id]
            
        else:
            await message.reply_document(
                document=file_path,
                caption=f"📎 **Instagram Media**",
                reply_markup=keyboard,
                file_name=f"instagram_{file_id}.{ext}"
            )
            
    except FloodWait as e:
        logger.warning(f"Flood: {e.value}s")
        await asyncio.sleep(e.value + 1)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        if status_msg:
            try:
                await status_msg.edit_text("❌ **Error!** Please try again.")
            except:
                pass

# ============ BUTTONS ============

@app.on_callback_query(filters.regex(r'^dl_'))
async def download_video(client, callback):
    try:
        file_id = callback.data.replace('dl_', '')
        data = video_cache.get(file_id)
        
        if not data or not os.path.exists(data['path']):
            await callback.answer("❌ Expired! Send again.", show_alert=True)
            return
        
        file_path = data['path']
        ext = data['ext']
        
        await callback.message.reply_document(
            document=file_path,
            caption="📹 Instagram Video",
            file_name=f"instagram_{file_id}.{ext}"
        )
        await callback.answer("✅ Download started!")
    except Exception as e:
        logger.error(f"DL error: {e}")
        await callback.answer("❌ Failed!", show_alert=True)

@app.on_callback_query(filters.regex(r'^au_'))
async def audio_request(client, callback):
    try:
        file_id = callback.data.replace('au_', '')
        data = video_cache.get(file_id)
        
        if not data or not os.path.exists(data['path']):
            await callback.answer("❌ Expired!", show_alert=True)
            return
        
        # Check if ffmpeg is available
        try:
            subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
        except:
            await callback.answer("❌ FFmpeg not installed!", show_alert=True)
            return
        
        file_path = data['path']
        audio_file = os.path.join(DOWNLOAD_PATH, f"audio_{file_id}.mp3")
        
        status = await callback.message.reply_text("🎵 **Extracting audio...**")
        
        # Extract audio
        cmd = [
            'ffmpeg',
            '-i', file_path,
            '-vn',
            '-acodec', 'libmp3lame',
            '-ab', '192k',
            '-ar', '44100',
            '-y', audio_file
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()
        
        if os.path.exists(audio_file) and os.path.getsize(audio_file) > 1000:
            await status.edit_text("📤 **Uploading audio...**")
            
            await client.send_audio(
                chat_id=callback.message.chat.id,
                audio=audio_file,
                caption="🎵 Instagram Audio",
                file_name=f"instagram_audio_{file_id}.mp3",
                title="Instagram Audio"
            )
            await status.delete()
            os.remove(audio_file)
            await callback.answer("✅ Audio sent!")
        else:
            await status.edit_text("❌ No audio found!")
            
    except Exception as e:
        logger.error(f"Audio error: {e}")
        await callback.answer("❌ Failed!", show_alert=True)

# ============ CLEANUP ============

async def cleanup_old_files():
    """Remove old files"""
    while True:
        try:
            current_time = time.time()
            to_remove = []
            
            for file_id, data in video_cache.items():
                if current_time - data.get('timestamp', 0) > 1800:  # 30 minutes
                    to_remove.append(file_id)
                    if os.path.exists(data['path']):
                        try:
                            os.remove(data['path'])
                        except:
                            pass
            
            for file_id in to_remove:
                del video_cache[file_id]
            
            await asyncio.sleep(1800)
        except:
            await asyncio.sleep(60)

# ============ RUN ============

def start_flask():
    port = int(os.environ.get('PORT', 8080))
    web_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

if __name__ == "__main__":
    logger.info("🚀 Starting Instagram Downloader Bot...")
    
    # Start cleanup
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(cleanup_old_files())
    
    # Start Flask
    threading.Thread(target=start_flask, daemon=True).start()
    time.sleep(2)
    
    # Start bot
    logger.info("✅ Bot started!")
    app.run()
