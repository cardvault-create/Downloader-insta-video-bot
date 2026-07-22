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

app = Client("bot_session", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, in_memory=True)

DOWNLOAD_PATH = "/tmp/downloads"
os.makedirs(DOWNLOAD_PATH, exist_ok=True)

video_cache = {}
user_states = {}

# ============ DOWNLOAD USING SUBPROCESS ============

def download_instagram_media(url, output_path):
    """Download Instagram using yt-dlp subprocess (most reliable)"""
    try:
        cmd = [
            'yt-dlp',
            '-f', 'best[ext=mp4]/best',
            '--merge-output-format', 'mp4',
            '-o', output_path,
            '--no-check-certificate',
            '--no-warnings',
            '--quiet',
            '--ignore-errors',
            url
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        
        # Check if file exists
        for ext in ['.mp4', '.webm', '.mkv', '.jpg', '.jpeg', '.png']:
            test_path = output_path + ext
            if os.path.exists(test_path) and os.path.getsize(test_path) > 10000:
                return test_path
        
        # Check for partial filename match
        base_dir = os.path.dirname(output_path)
        base_name = os.path.basename(output_path)
        for f in os.listdir(base_dir):
            if f.startswith(base_name) and not f.endswith('.part'):
                full_path = os.path.join(base_dir, f)
                if os.path.getsize(full_path) > 10000:
                    return full_path
        
        logger.error(f"yt-dlp stderr: {result.stderr}")
        return None
        
    except Exception as e:
        logger.error(f"Download error: {e}")
        return None

# ============ COMMANDS ============

@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text(
        "**🎬 Instagram Downloader Bot**\n\n"
        "Send any Instagram reel/post link!\n\n"
        "✅ HD Video + Audio\n"
        "✅ Original Photos\n"
        "✅ Audio Extraction\n\n"
        "🚀 Paste link now!"
    )

@app.on_message(filters.command("ping"))
async def ping(client, message):
    await message.reply_text("🏓 Pong! Ready!")

@app.on_message(filters.regex(r'https?://(?:www\.)?instagram\.com/(?:p|reel|tv)/[^/?]+'))
async def download(client, message):
    status = None
    try:
        url = message.text.strip().split('?')[0]
        
        status = await message.reply_text("🔄 **Downloading...**\n⏳ This may take 10-20 seconds...")
        
        file_id = str(uuid.uuid4())[:12]
        output_template = os.path.join(DOWNLOAD_PATH, file_id)
        
        # Download using subprocess
        downloaded_file = await asyncio.get_event_loop().run_in_executor(
            None, download_instagram_media, url, output_template
        )
        
        if not downloaded_file:
            await status.edit_text(
                "❌ **Download Failed!**\n\n"
                "**Possible reasons:**\n"
                "• Post is private\n"
                "• Invalid link\n"
                "• Instagram rate limit\n\n"
                "Please try another public post/reel."
            )
            return
        
        file_size = os.path.getsize(downloaded_file)
        if file_size < 5000:  # Less than 5KB = probably error
            await status.edit_text("❌ **Downloaded file is empty!** Try another link.")
            os.remove(downloaded_file)
            return
        
        is_video = downloaded_file.endswith(('.mp4', '.webm', '.mkv'))
        
        if is_video:
            size_mb = file_size / (1024 * 1024)
            
            video_cache[file_id] = {
                'video_path': downloaded_file,
                'owner_id': 'instagram'
            }
            
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📥 Download Video", callback_data=f"dl_{file_id}"),
                    InlineKeyboardButton("🎵 Extract Audio", callback_data=f"au_{file_id}")
                ]
            ])
            
            await status.delete()
            
            if size_mb > 50:
                await message.reply_document(
                    document=downloaded_file,
                    caption=f"🎬 **Instagram Video**\n📦 {size_mb:.1f}MB",
                    reply_markup=keyboard,
                    file_name=f"instagram_{file_id}.mp4"
                )
            else:
                await message.reply_video(
                    video=downloaded_file,
                    caption=f"🎬 **Instagram Video**\n📦 {size_mb:.1f}MB",
                    reply_markup=keyboard,
                    supports_streaming=True
                )
            
            logger.info(f"Video sent: {file_id} ({size_mb:.1f}MB)")
            
        else:
            # Photo
            await status.delete()
            await message.reply_photo(
                photo=downloaded_file,
                caption="📸 **Instagram Photo**"
            )
            os.remove(downloaded_file)
            logger.info(f"Photo sent: {file_id}")
            
    except FloodWait as e:
        await asyncio.sleep(e.value + 1)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        if status:
            try:
                await status.edit_text(f"❌ **Error!** Try again later.")
            except:
                pass

# ============ BUTTONS ============

@app.on_callback_query(filters.regex(r'^dl_'))
async def dl_video(client, callback):
    try:
        file_id = callback.data.replace('dl_', '')
        v = video_cache.get(file_id)
        
        if not v or not os.path.exists(v['video_path']):
            await callback.answer("❌ File expired! Send link again.", show_alert=True)
            return
        
        await callback.message.reply_document(
            document=v['video_path'],
            caption="📹 Instagram Video",
            file_name=f"instagram_{file_id}.mp4"
        )
        await callback.answer("✅ Sent!")
    except Exception as e:
        logger.error(f"DL error: {e}")

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
            'ts': time.time()
        }
        await callback.message.reply_text("🎵 **Enter filename:**\nExample: my_song")
        await callback.answer()
    except:
        pass

@app.on_message(filters.text & filters.private & ~filters.command(["start", "ping"]))
async def get_audio_name(client, message):
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
            return
        
        name = message.text.strip().replace(' ', '_')[:50]
        if not name.endswith('.mp3'):
            name += '.mp3'
        
        status = await message.reply_text("🔄 **Extracting audio...**")
        
        audio_output = os.path.join(DOWNLOAD_PATH, f"audio_{file_id}")
        
        # Extract audio using FFmpeg directly
        cmd = [
            'ffmpeg', '-i', v['video_path'],
            '-vn', '-acodec', 'libmp3lame',
            '-ab', '192k', '-ar', '44100',
            '-y', audio_output + '.mp3'
        ]
        
        result = await asyncio.get_event_loop().run_in_executor(
            None, lambda: subprocess.run(cmd, capture_output=True, text=True)
        )
        
        audio_file = audio_output + '.mp3'
        
        if os.path.exists(audio_file) and os.path.getsize(audio_file) > 1000:
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
            await status.edit_text("❌ **Extraction failed!** No audio in video.")
        
        del user_states[uid]
    except Exception as e:
        logger.error(f"Audio error: {e}")

# ============ RUN ============

def start_flask():
    port = int(os.environ.get('PORT', 8080))
    web_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

if __name__ == "__main__":
    logger.info("Starting bot with subprocess yt-dlp...")
    threading.Thread(target=start_flask, daemon=True).start()
    time.sleep(3)
    app.run()
