import os
import re
import uuid
import asyncio
import logging
from datetime import datetime
import aiohttp
import aiofiles
import instaloader
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait
import yt_dlp
from flask import Flask
from threading import Thread
import sys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask app - IMMEDIATELY CREATE
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "✅ Bot is Running! All systems operational."

@web_app.route('/health')
def health():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

def run_web():
    """Run Flask in main thread"""
    port = int(os.environ.get('PORT', 8080))
    logger.info(f"🌐 Starting web server on port {port}")
    web_app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

# Bot configuration
API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

# Initialize bot
app = Client(
    "bot_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=50,
    in_memory=True  # Session memory mein rakhe
)

# Initialize instaloader
loader = instaloader.Instaloader(
    download_pictures=False,
    download_videos=False,
    download_video_thumbnails=False,
    save_metadata=False,
    max_connection_attempts=3
)

DOWNLOAD_PATH = "/tmp/downloads"
os.makedirs(DOWNLOAD_PATH, exist_ok=True)

video_cache = {}
user_states = {}

# ============ BOT HANDLERS ============

@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text(
        "**🎬 Instagram Downloader Bot**\n\n"
        "✨ **Ready to Download!**\n\n"
        "Send Instagram reel/post link to download!\n"
        "Video/Photo/Reels supported ✅\n\n"
        "**Features:**\n"
        "• 📹 HD Video Download\n"
        "• 📸 Original Quality Photos\n"
        "• 🎵 Audio Extraction (MP3)\n"
        "• 📥 Direct Download Button\n\n"
        "Just send a link! 🚀"
    )

@app.on_message(filters.command("ping"))
async def ping(client, message):
    await message.reply_text("🏓 Pong! Bot is alive!")

@app.on_message(filters.regex(r'https?://(?:www\.)?instagram\.com/(?:p|reel|tv)/[^/]+'))
async def download(client, message):
    status = None
    try:
        url = message.text.strip()
        match = re.search(r'instagram\.com/(?:p|reel|tv)/([a-zA-Z0-9_-]+)', url)
        if not match:
            await message.reply_text("❌ Invalid Instagram link!")
            return
        
        shortcode = match.group(1)
        status = await message.reply_text("🔄 **Processing your link...**")
        
        try:
            post = instaloader.Post.from_shortcode(loader.context, shortcode)
        except Exception as e:
            logger.error(f"Instaloader fetch error: {e}")
            await status.edit_text("❌ **Failed to fetch post!**\n\nPossible reasons:\n• Private account\n• Invalid link\n• Instagram rate limit\n\nTry again later.")
            return
        
        if post.is_video:
            # Handle video
            video_url = str(post.video_url)
            file_id = str(uuid.uuid4())[:12]
            file_path = os.path.join(DOWNLOAD_PATH, f"{file_id}.mp4")
            
            await status.edit_text("📥 **Downloading video...**")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(video_url, timeout=aiohttp.ClientTimeout(total=300)) as resp:
                    if resp.status != 200:
                        await status.edit_text("❌ Download failed! Try again.")
                        return
                    async with aiofiles.open(file_path, 'wb') as f:
                        await f.write(await resp.read())
            
            size_mb = os.path.getsize(file_path) / (1024 * 1024)
            owner = post.owner_username or "unknown"
            caption = (post.caption or "Instagram Video")[:200]
            duration = int(post.video_duration) if post.video_duration else 0
            
            video_cache[file_id] = {
                'video_path': file_path,
                'video_url': video_url,
                'owner_id': owner,
                'duration': duration
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
                    document=file_path,
                    caption=f"**🎬 {caption}**\n\n👤 @{owner}\n📦 {size_mb:.1f}MB",
                    reply_markup=keyboard,
                    file_name=f"instagram_{shortcode}.mp4"
                )
            else:
                await message.reply_video(
                    video=file_path,
                    caption=f"**🎬 {caption}**\n\n👤 @{owner}",
                    reply_markup=keyboard,
                    supports_streaming=True,
                    duration=duration
                )
            
            logger.info(f"Video sent: {shortcode}")
            
        else:
            # Handle photo
            await status.edit_text("📥 **Downloading photo...**")
            photo_url = str(post.url)
            file_path = os.path.join(DOWNLOAD_PATH, f"{shortcode}.jpg")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(photo_url) as resp:
                    if resp.status != 200:
                        await status.edit_text("❌ Download failed!")
                        return
                    async with aiofiles.open(file_path, 'wb') as f:
                        await f.write(await resp.read())
            
            owner = post.owner_username or "unknown"
            caption = (post.caption or "Instagram Photo")[:500]
            
            await status.delete()
            await message.reply_photo(
                photo=file_path,
                caption=f"**📸 Instagram Photo**\n\n👤 @{owner}\n\n{caption}"
            )
            os.remove(file_path)
            logger.info(f"Photo sent: {shortcode}")
            
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
            caption=f"📹 **Video File**\n👤 @{v['owner_id']}\n✨ High Quality",
            file_name=f"instagram_video_{file_id}.mp4"
        )
        
    except Exception as e:
        logger.error(f"Download callback error: {e}")
        await callback.answer("❌ Error sending file!", show_alert=True)

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
        
        prompt = await callback.message.reply_text(
            "🎵 **Enter filename for audio:**\n\n"
            "📝 Example: `my_song` or `best_track`\n"
            "💡 Extension (.mp3) will be added automatically\n\n"
            "⏰ You have 2 minutes!"
        )
        
        user_states[callback.from_user.id]['prompt_id'] = prompt.id
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Audio callback error: {e}")

@app.on_message(filters.text & filters.private & ~filters.command(["start", "ping"]))
async def get_audio_name(client, message):
    try:
        uid = message.from_user.id
        
        if uid not in user_states:
            return
        
        # Check timeout
        if datetime.now().timestamp() - user_states[uid]['ts'] > 120:
            del user_states[uid]
            await message.reply_text("⏰ **Timeout!** Please try again.")
            return
        
        file_id = user_states[uid]['file_id']
        v = video_cache.get(file_id)
        
        if not v:
            del user_states[uid]
            await message.reply_text("❌ Session expired! Send link again.")
            return
        
        # Clean filename
        name = message.text.strip().replace(' ', '_')[:50]
        if not name.endswith('.mp3'):
            name += '.mp3'
        
        status = await message.reply_text("🔄 **Extracting audio...**\n⏳ Please wait...")
        
        # Extract audio
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
            'no_warnings': True,
        }
        
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([v['video_url']])
            
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
            
            # Cleanup
            try:
                await message.delete()
                if 'prompt_id' in user_states[uid]:
                    await client.delete_messages(message.chat.id, user_states[uid]['prompt_id'])
            except:
                pass
            
            try:
                os.remove(audio_file)
            except:
                pass
            
            logger.info(f"Audio sent: {name}")
            
        except Exception as e:
            logger.error(f"Audio extraction error: {e}")
            await status.edit_text(f"❌ **Extraction failed:** {str(e)[:150]}")
        
        finally:
            if uid in user_states:
                del user_states[uid]
                
    except Exception as e:
        logger.error(f"Audio handler error: {e}")

# ============ MAIN RUNNER ============

async def main():
    """Main async function"""
    logger.info("🤖 Starting Instagram Downloader Bot...")
    
    # Start bot
    await app.start()
    logger.info("✅ Bot started successfully!")
    
    # Keep running
    await asyncio.Event().wait()

if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("Starting application...")
    logger.info("=" * 50)
    
    # Start Flask in separate thread
    flask_thread = Thread(target=run_web, daemon=True)
    flask_thread.start()
    logger.info("🌐 Flask server started in background")
    
    # Run bot in main thread
    try:
        app.run()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot error: {e}", exc_info=True)
