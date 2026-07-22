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
import shutil

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

# Check if yt-dlp is installed
def check_ytdlp():
    try:
        subprocess.run(['yt-dlp', '--version'], capture_output=True, check=True)
        return True
    except:
        return False

# Install yt-dlp if not present
if not check_ytdlp():
    logger.info("Installing yt-dlp...")
    subprocess.run(['pip', 'install', 'yt-dlp'], check=True)

async def download_instagram_with_ytdlp(url):
    """Download Instagram media using yt-dlp (best quality)"""
    try:
        file_id = str(uuid.uuid4())[:12]
        output_template = os.path.join(DOWNLOAD_PATH, f"instagram_{file_id}.%(ext)s")
        
        # yt-dlp command for best quality
        cmd = [
            'yt-dlp',
            '-f', 'best[ext=mp4]/best',  # Best quality
            '--no-playlist',
            '--no-warnings',
            '--ignore-errors',
            '--no-check-certificate',
            '-o', output_template,
            url
        ]
        
        logger.info(f"Running yt-dlp: {' '.join(cmd)}")
        
        # Run yt-dlp
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            logger.error(f"yt-dlp error: {stderr.decode()}")
            return None, None
        
        # Find downloaded file
        for file in os.listdir(DOWNLOAD_PATH):
            if file.startswith(f"instagram_{file_id}"):
                file_path = os.path.join(DOWNLOAD_PATH, file)
                ext = file.split('.')[-1].lower()
                return file_path, ext
        
        return None, None
        
    except Exception as e:
        logger.error(f"yt-dlp error: {e}")
        return None, None

async def download_instagram_with_cookies(url):
    """Alternative method using cookies for better success rate"""
    try:
        # Create cookies file
        cookies_file = os.path.join(DOWNLOAD_PATH, "cookies.txt")
        
        # Add some default cookies (optional - you can add your own)
        with open(cookies_file, 'w') as f:
            f.write("# Netscape HTTP Cookie File\n")
            f.write(".instagram.com\tTRUE\t/\tFALSE\t0\tmid\tYOUR_MID_HERE\n")
        
        file_id = str(uuid.uuid4())[:12]
        output_template = os.path.join(DOWNLOAD_PATH, f"insta_{file_id}.%(ext)s")
        
        cmd = [
            'yt-dlp',
            '--cookies', cookies_file,
            '-f', 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            '--no-playlist',
            '-o', output_template,
            url
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode == 0:
            for file in os.listdir(DOWNLOAD_PATH):
                if file.startswith(f"insta_{file_id}"):
                    file_path = os.path.join(DOWNLOAD_PATH, file)
                    ext = file.split('.')[-1].lower()
                    return file_path, ext
        
        return None, None
        
    except Exception as e:
        logger.error(f"Cookie method error: {e}")
        return None, None

# ============ COMMANDS ============

@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text(
        "**🎬 Instagram Downloader Bot**\n\n"
        "Send any Instagram post/reel/story link!\n\n"
        "✅ **Best Quality** (Original)\n"
        "✅ **Fast Download**\n"
        "✅ **Audio Extraction**\n"
        "✅ **Photos & Videos**\n\n"
        "📌 Works with:\n"
        "• Posts (p/)\n"
        "• Reels (reel/)\n"
        "• Stories (stories/)\n"
        "• TV (tv/)\n\n"
        "🚀 **Send link now!**"
    )

@app.on_message(filters.command("ping"))
async def ping(client, message):
    await message.reply_text("✅ **Bot is active!** Send Instagram link.")

@app.on_message(filters.regex(r'instagram\.com/(?:p|reel|tv|stories)/'))
async def handle_instagram(client, message):
    status_msg = None
    try:
        url = message.text.strip()
        # Clean URL
        url = re.sub(r'\?.*$', '', url)
        url = re.sub(r'#.*$', '', url)
        
        logger.info(f"Processing: {url}")
        
        status_msg = await message.reply_text("🔍 **Fetching media...**")
        
        # Try yt-dlp first
        file_path, ext = await download_instagram_with_ytdlp(url)
        
        # If failed, try with cookies
        if not file_path:
            await status_msg.edit_text("🔄 **Trying alternative method...**")
            file_path, ext = await download_instagram_with_cookies(url)
        
        if not file_path or not os.path.exists(file_path):
            await status_msg.edit_text(
                "❌ **Could not download!**\n\n"
                "Possible reasons:\n"
                "• Post is private\n"
                "• Account is private\n"
                "• Invalid URL\n\n"
                "💡 **Try:**\n"
                "• Make sure post is public\n"
                "• Send exact link from browser\n"
                "• Check URL format"
            )
            return
        
        file_size = os.path.getsize(file_path)
        size_mb = file_size / (1024 * 1024)
        
        if size_mb < 0.01:
            await status_msg.edit_text("❌ **Empty file!** Try again.")
            os.remove(file_path)
            return
        
        # Generate file ID for cache
        file_id = str(uuid.uuid4())[:12]
        
        # Store in cache
        video_cache[file_id] = {
            'path': file_path,
            'ext': ext,
            'size': file_size,
            'timestamp': time.time()
        }
        
        # Prepare keyboard
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📥 Download", callback_data=f"dl_{file_id}"),
                InlineKeyboardButton("🎵 Audio", callback_data=f"au_{file_id}")
            ]
        ])
        
        await status_msg.delete()
        
        # Send based on file type
        if ext in ['mp4', 'mov', 'avi', 'mkv']:
            # Video
            caption = f"🎬 **Instagram Video**\n📦 {size_mb:.1f} MB\n✨ **Original Quality**"
            
            if size_mb > 50:
                # Send as document if too large
                await message.reply_document(
                    document=file_path,
                    caption=caption,
                    reply_markup=keyboard,
                    file_name=f"instagram_{file_id}.{ext}"
                )
            else:
                # Send as video with streaming
                await message.reply_video(
                    video=file_path,
                    caption=caption,
                    reply_markup=keyboard,
                    supports_streaming=True,
                    width=720,
                    height=1280
                )
            logger.info(f"✅ Video sent: {size_mb:.1f} MB")
            
        elif ext in ['jpg', 'jpeg', 'png', 'gif', 'webp']:
            # Photo
            await message.reply_photo(
                photo=file_path,
                caption=f"📸 **Instagram Photo**\n✨ **Original Quality**",
                reply_markup=keyboard
            )
            logger.info("✅ Photo sent")
            # Remove photo immediately (not needed in cache)
            os.remove(file_path)
            
        else:
            # Other files
            await message.reply_document(
                document=file_path,
                caption=f"📎 **Instagram Media**\n📦 {size_mb:.1f} MB",
                reply_markup=keyboard,
                file_name=f"instagram_{file_id}.{ext}"
            )
            logger.info(f"✅ Document sent: {size_mb:.1f} MB")
            
    except FloodWait as e:
        logger.warning(f"Flood: {e.value}s")
        await asyncio.sleep(e.value + 1)
        if status_msg:
            await status_msg.edit_text("⏳ **Rate limited. Please wait...**")
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        if status_msg:
            try:
                await status_msg.edit_text("❌ **Error occurred!** Please try again.")
            except:
                pass

# ============ BUTTONS ============

@app.on_callback_query(filters.regex(r'^dl_'))
async def download_video(client, callback):
    try:
        file_id = callback.data.replace('dl_', '')
        data = video_cache.get(file_id)
        
        if not data or not os.path.exists(data['path']):
            await callback.answer("❌ **Expired!** Send again.", show_alert=True)
            return
        
        file_path = data['path']
        ext = data['ext']
        
        await callback.message.reply_document(
            document=file_path,
            caption="📹 **Instagram Video**\n✨ Original Quality",
            file_name=f"instagram_{file_id}.{ext}"
        )
        await callback.answer("✅ **Download started!**")
    except Exception as e:
        logger.error(f"DL error: {e}")
        await callback.answer("❌ Failed!", show_alert=True)

@app.on_callback_query(filters.regex(r'^au_'))
async def audio_request(client, callback):
    try:
        file_id = callback.data.replace('au_', '')
        data = video_cache.get(file_id)
        
        if not data or not os.path.exists(data['path']):
            await callback.answer("❌ **Expired!** Send again.", show_alert=True)
            return
        
        file_path = data['path']
        
        # Check if video contains audio
        audio_file = os.path.join(DOWNLOAD_PATH, f"audio_{file_id}.mp3")
        
        status = await callback.message.reply_text("🎵 **Extracting audio...**")
        
        # Extract audio using ffmpeg
        cmd = [
            'ffmpeg',
            '-i', file_path,
            '-vn',  # No video
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
                caption="🎵 **Instagram Audio**\n✨ Extracted from video",
                file_name=f"instagram_audio_{file_id}.mp3",
                title="Instagram Audio"
            )
            await status.delete()
            os.remove(audio_file)
            await callback.answer("✅ **Audio sent!**")
        else:
            await status.edit_text("❌ **No audio found in this video!**")
            await callback.answer("❌ No audio found", show_alert=True)
            
    except Exception as e:
        logger.error(f"Audio error: {e}")
        await callback.answer("❌ Failed!", show_alert=True)

# ============ CLEANUP ============

async def cleanup_old_files():
    """Remove old files from cache"""
    while True:
        try:
            current_time = time.time()
            to_remove = []
            
            for file_id, data in video_cache.items():
                if current_time - data['timestamp'] > 3600:  # 1 hour
                    to_remove.append(file_id)
                    if os.path.exists(data['path']):
                        try:
                            os.remove(data['path'])
                            logger.info(f"Removed old file: {data['path']}")
                        except:
                            pass
            
            for file_id in to_remove:
                del video_cache[file_id]
            
            # Also clean orphan files
            for file in os.listdir(DOWNLOAD_PATH):
                if file.startswith('instagram_') or file.startswith('insta_') or file.startswith('audio_'):
                    file_path = os.path.join(DOWNLOAD_PATH, file)
                    try:
                        if time.time() - os.path.getctime(file_path) > 7200:  # 2 hours
                            os.remove(file_path)
                            logger.info(f"Removed orphan file: {file}")
                    except:
                        pass
            
            await asyncio.sleep(3600)  # Run every hour
        except:
            await asyncio.sleep(60)

# ============ RUN ============

def start_flask():
    port = int(os.environ.get('PORT', 8080))
    web_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

if __name__ == "__main__":
    logger.info("🚀 Starting Instagram Downloader Bot...")
    
    # Start cleanup task
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.create_task(cleanup_old_files())
    
    # Start Flask
    threading.Thread(target=start_flask, daemon=True).start()
    time.sleep(2)
    
    # Start bot
    logger.info("✅ Bot started successfully!")
    app.run()
