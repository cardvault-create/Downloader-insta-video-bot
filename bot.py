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

# ============ INSTAGRAM DOWNLOADER ============

def download_instagram(url, output_path):
    """Download Instagram video/photo with audio"""
    ydl_opts = {
        'outtmpl': output_path,
        'format': 'bv*+ba/b',  # Best video + best audio merged
        'merge_output_format': 'mp4',
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return info
    except:
        # Fallback: try best format
        ydl_opts['format'] = 'best'
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return info
        except Exception as e:
            logger.error(f"Download error: {e}")
            return None

# ============ COMMANDS ============

@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text(
        "**🎬 Instagram Downloader Bot**\n\n"
        "Send any Instagram reel/post link!\n\n"
        "✅ **Video with Audio**\n"
        "✅ **HD Quality**\n"
        "✅ **Original Photos**\n"
        "✅ **Audio Extraction**\n\n"
        "Just paste link! 🚀"
    )

@app.on_message(filters.command("ping"))
async def ping(client, message):
    await message.reply_text("🏓 Pong!")

@app.on_message(filters.regex(r'https?://(?:www\.)?instagram\.com/(?:p|reel|tv)/[^/?]+'))
async def download(client, message):
    status = None
    try:
        url = message.text.strip().split('?')[0]
        
        status = await message.reply_text("🔄 **Processing...**")
        
        file_id = str(uuid.uuid4())[:12]
        output_template = os.path.join(DOWNLOAD_PATH, f"{file_id}")
        
        # Download with yt-dlp
        info = download_instagram(url, output_template)
        
        if not info:
            await status.edit_text("❌ **Failed!** Try another link or check if post is public.")
            return
        
        # Find downloaded file
        downloaded_file = None
        for ext in ['.mp4', '.webm', '.mkv', '.jpg', '.jpeg', '.png']:
            test_path = output_template + ext
            if os.path.exists(test_path):
                downloaded_file = test_path
                break
        
        if not downloaded_file:
            # Check for files starting with template name
            for f in os.listdir(DOWNLOAD_PATH):
                if f.startswith(file_id) and not f.endswith('.part'):
                    downloaded_file = os.path.join(DOWNLOAD_PATH, f)
                    break
        
        if not downloaded_file:
            await status.edit_text("❌ **No file found!** Please try again.")
            return
        
        # Get info
        is_video = info.get('duration') or downloaded_file.endswith(('.mp4', '.webm', '.mkv'))
        owner = info.get('uploader', info.get('channel', 'unknown'))
        description = (info.get('description', '') or '')[:300]
        
        if is_video:
            duration = int(info.get('duration', 0))
            size_mb = os.path.getsize(downloaded_file) / (1024*1024)
            
            video_cache[file_id] = {
                'video_path': downloaded_file,
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
            
            caption = f"**🎬 Instagram {'Reel' if 'reel' in url else 'Video'}**\n\n"
            caption += f"👤 **@{owner}**\n"
            caption += f"⏱️ {duration}s\n"
            caption += f"📦 {size_mb:.1f}MB\n"
            if description:
                caption += f"\n📝 {description[:200]}"
            
            await status.delete()
            
            if size_mb > 50:
                await message.reply_document(
                    document=downloaded_file,
                    caption=caption,
                    reply_markup=keyboard,
                    file_name=f"instagram_{file_id}.mp4",
                    thumb=None
                )
            else:
                await message.reply_video(
                    video=downloaded_file,
                    caption=caption,
                    reply_markup=keyboard,
                    supports_streaming=True,
                    duration=duration,
                    width=720,
                    height=1280,
                    thumb=None
                )
        else:
            caption = f"**📸 Instagram Photo**\n\n👤 **@{owner}**"
            if description:
                caption += f"\n\n📝 {description[:200]}"
            
            await status.delete()
            await message.reply_photo(photo=downloaded_file, caption=caption)
            os.remove(downloaded_file)
        
        logger.info(f"Sent: {file_id}")
        
    except FloodWait as e:
        await asyncio.sleep(e.value + 1)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
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
            caption=f"📹 **Video**\n👤 @{v['owner_id']}\n✨ Original Quality",
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
        
        await callback.message.reply_text(
            "🎵 **Audio filename bhejo:**\n\n"
            "Example: `my_song`\n"
            "Extension auto-add hogi\n\n"
            "⏰ 2 min timeout"
        )
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
        
        status = await message.reply_text("🔄 **Extracting audio...**")
        
        audio_output = os.path.join(DOWNLOAD_PATH, f"audio_{file_id}")
        
        # Extract audio from downloaded video
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': audio_output,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': True,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([v['video_path']])
            
            audio_file = audio_output + '.mp3'
            
            if not os.path.exists(audio_file):
                raise Exception("Audio extraction failed")
            
            await status.edit_text("📤 **Uploading...**")
            
            await client.send_audio(
                chat_id=message.chat.id,
                audio=audio_file,
                caption=f"🎵 **{name.replace('.mp3', '')}**\n\n👤 @{v['owner_id']}",
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
            
        except Exception as e:
            await status.edit_text(f"❌ **Failed:** {str(e)[:150]}")
        
        finally:
            if uid in user_states:
                del user_states[uid]
                
    except Exception as e:
        logger.error(f"Audio error: {e}")

# ============ RUN ============

def start_flask():
    port = int(os.environ.get('PORT', 8080))
    web_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

if __name__ == "__main__":
    logger.info("Starting bot...")
    threading.Thread(target=start_flask, daemon=True).start()
    time.sleep(3)
    app.run()
