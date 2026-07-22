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
API_HASH = os.environ.get("API_HASH", "011f638e4acadee178c59afffc80193d")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8952730755:AAHhor54jekn60e8NflgIJa50cMHwPQ3dbU")

app = Client(
    "bot_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True
)

DOWNLOAD_PATH = "/tmp/downloads"
os.makedirs(DOWNLOAD_PATH, exist_ok=True)

video_cache = {}
user_states = {}

# ============ INSTAGRAM DOWNLOADER USING YT-DLP ============

def get_instagram_info(url):
    """Get Instagram post info using yt-dlp"""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'force_generic_extractor': False,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            return info
    except Exception as e:
        logger.error(f"yt-dlp extract error: {e}")
        return None

def download_instagram_media(url, file_path, media_type='video'):
    """Download Instagram media using yt-dlp"""
    if media_type == 'video':
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': file_path,
            'quiet': True,
            'no_warnings': True,
            'merge_output_format': 'mp4',
        }
    else:  # photo
        ydl_opts = {
            'format': 'best',
            'outtmpl': file_path,
            'quiet': True,
            'no_warnings': True,
        }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        return True
    except Exception as e:
        logger.error(f"yt-dlp download error: {e}")
        return False

# ============ COMMANDS ============

@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text(
        "**🎬 Instagram Downloader Bot**\n\n"
        "Send Instagram reel/post link!\n"
        "HD Video/Photo download ✅\n"
        "Audio extraction ✅\n\n"
        "**Supported:**\n"
        "• Reels\n"
        "• Posts\n"
        "• IGTV\n\n"
        "Just paste a link 🚀"
    )

@app.on_message(filters.command("ping"))
async def ping(client, message):
    await message.reply_text("🏓 Pong! Bot is working!")

@app.on_message(filters.regex(r'https?://(?:www\.)?instagram\.com/(?:p|reel|tv)/[^/?]+'))
async def download(client, message):
    status = None
    try:
        url = message.text.strip().split('?')[0]  # Remove query params
        
        status = await message.reply_text("🔄 **Processing...**\n⏳ Fetching media info...")
        
        # Get media info
        info = get_instagram_info(url)
        
        if not info:
            await status.edit_text("❌ **Failed to fetch!**\n\nPossible reasons:\n• Invalid/private link\n• Instagram blocked request\n• Try another link\n\nPlease try again!")
            return
        
        # Check if video or photo
        is_video = info.get('duration') or info.get('ext') in ['mp4', 'webm']
        
        file_id = str(uuid.uuid4())[:12]
        owner = info.get('uploader', info.get('channel', 'unknown'))
        description = (info.get('description', '') or '')[:300]
        
        if is_video:
            # Video download
            file_path = os.path.join(DOWNLOAD_PATH, f"{file_id}.mp4")
            
            await status.edit_text("📥 **Downloading video...**\n⬇️ Please wait...")
            
            success = download_instagram_media(url, file_path, 'video')
            
            if not success or not os.path.exists(file_path):
                # Try alternative download
                alt_path = file_path.replace('.mp4', '')
                for ext in ['.mp4', '.webm', '.mkv']:
                    if os.path.exists(alt_path + ext):
                        file_path = alt_path + ext
                        success = True
                        break
                
                if not success:
                    await status.edit_text("❌ **Download failed!** Instagram may have blocked. Try another link.")
                    return
            
            size_mb = os.path.getsize(file_path) / (1024*1024)
            duration = int(info.get('duration', 0))
            
            # Store in cache
            video_cache[file_id] = {
                'video_path': file_path,
                'video_url': url,
                'owner_id': owner,
                'duration': duration
            }
            
            # Create buttons
            keyboard = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("📥 Download Video", callback_data=f"dl_{file_id}"),
                    InlineKeyboardButton("🎵 Audio", callback_data=f"au_{file_id}")
                ]
            ])
            
            caption = f"**🎬 Instagram Video**\n\n👤 **@{owner}**\n⏱️ Duration: {duration}s\n📦 Size: {size_mb:.1f}MB"
            if description:
                caption += f"\n\n📝 {description[:200]}"
            
            await status.delete()
            
            # Send video
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
                    duration=duration,
                    width=720,
                    height=1280
                )
            
            logger.info(f"Video sent: {file_id}")
            
        else:
            # Photo download
            file_path = os.path.join(DOWNLOAD_PATH, f"{file_id}.jpg")
            
            await status.edit_text("📥 **Downloading photo...**")
            
            success = download_instagram_media(url, file_path, 'photo')
            
            if not success:
                # Try to get thumbnail
                thumbnail = info.get('thumbnail')
                if thumbnail:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(thumbnail) as resp:
                            if resp.status == 200:
                                async with aiofiles.open(file_path, 'wb') as f:
                                    await f.write(await resp.read())
                                    success = True
            
            if not success or not os.path.exists(file_path):
                await status.edit_text("❌ **Download failed!** Try again.")
                return
            
            caption = f"**📸 Instagram Photo**\n\n👤 **@{owner}**"
            if description:
                caption += f"\n\n📝 {description[:200]}"
            
            await status.delete()
            await message.reply_photo(photo=file_path, caption=caption)
            os.remove(file_path)
            logger.info(f"Photo sent: {file_id}")
            
    except FloodWait as e:
        logger.warning(f"FloodWait: {e.value}s")
        await asyncio.sleep(e.value + 1)
    except Exception as e:
        logger.error(f"Download error: {e}", exc_info=True)
        if status:
            try:
                await status.edit_text(f"❌ **Error:** {str(e)[:200]}")
            except:
                pass

# ============ BUTTON HANDLERS ============

@app.on_callback_query(filters.regex(r'^dl_'))
async def dl_video(client, callback):
    try:
        file_id = callback.data.replace('dl_', '')
        v = video_cache.get(file_id)
        
        if not v or not os.path.exists(v['video_path']):
            await callback.answer("❌ File expired! Send link again.", show_alert=True)
            return
        
        await callback.answer("📥 Sending file...")
        await callback.message.reply_document(
            document=v['video_path'],
            caption=f"📹 **Video File**\n👤 @{v['owner_id']}\n✨ HD Quality",
            file_name=f"instagram_video_{file_id}.mp4"
        )
        
    except Exception as e:
        logger.error(f"DL callback error: {e}")
        await callback.answer("❌ Error!", show_alert=True)

@app.on_callback_query(filters.regex(r'^au_'))
async def audio_name(client, callback):
    try:
        file_id = callback.data.replace('au_', '')
        v = video_cache.get(file_id)
        
        if not v:
            await callback.answer("❌ Session expired!", show_alert=True)
            return
        
        user_states[callback.from_user.id] = {
            'file_id': file_id,
            'ts': datetime.now().timestamp()
        }
        
        await callback.message.reply_text(
            "🎵 **Enter filename for audio:**\n\n"
            "📝 Example: `my_song`\n"
            "💡 Extension auto-added\n\n"
            "⏰ 2 minutes timeout"
        )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Audio callback error: {e}")

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
        
        if not v:
            del user_states[uid]
            return
        
        name = message.text.strip().replace(' ', '_')[:50]
        if not name.endswith('.mp3'):
            name += '.mp3'
        
        status = await message.reply_text("🔄 **Extracting audio...**")
        
        # Extract audio from video
        temp = os.path.join(DOWNLOAD_PATH, f"audio_{file_id}")
        opts = {
            'format': 'bestaudio/best',
            'outtmpl': temp,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': True,
        }
        
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([v['video_path']])
            
            audio_file = temp + '.mp3'
            
            if not os.path.exists(audio_file):
                raise Exception("Audio file not created")
            
            await status.edit_text("📤 **Uploading audio...**")
            
            await client.send_audio(
                chat_id=message.chat.id,
                audio=audio_file,
                caption=f"🎵 **{name.replace('.mp3', '')}**\n\n👤 @{v['owner_id']}\n📱 Extracted from Instagram",
                file_name=name,
                performer=v['owner_id'],
                title=name.replace('.mp3', ''),
                duration=v.get('duration', 0)
            )
            
            await status.delete()
            
            try:
                await message.delete()
            except:
                pass
            
            os.remove(audio_file)
            del user_states[uid]
            
        except Exception as e:
            await status.edit_text(f"❌ **Extraction failed:** {str(e)[:150]}")
            del user_states[uid]
            
    except Exception as e:
        logger.error(f"Audio handler error: {e}")

# ============ RUNNER ============

def start_flask():
    port = int(os.environ.get('PORT', 8080))
    web_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

if __name__ == "__main__":
    logger.info("Starting Bot...")
    threading.Thread(target=start_flask, daemon=True).start()
    time.sleep(3)
    app.run()
