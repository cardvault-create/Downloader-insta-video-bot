#!/usr/bin/env python3
"""
Instagram Downloader Bot for Railway.app
Downloads Instagram Reels, Videos, Photos in High Quality
"""

import os
import re
import uuid
import asyncio
import logging
from datetime import datetime

# Third-party imports
import aiohttp
import aiofiles
import instaloader
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.errors import FloodWait, MessageNotModified
import yt_dlp

# Flask for keep-alive
from flask import Flask
from threading import Thread

# ============ LOGGING SETUP ============
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============ FLASK KEEP-ALIVE ============
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return """
    <html>
        <head>
            <title>Instagram Bot</title>
            <style>
                body { 
                    font-family: Arial; 
                    text-align: center; 
                    padding: 50px; 
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                }
                h1 { font-size: 48px; }
                p { font-size: 24px; }
            </style>
        </head>
        <body>
            <h1>🤖 Bot is Running!</h1>
            <p>Instagram Downloader Bot Active ✅</p>
            <p>Server Time: {}</p>
        </body>
    </html>
    """.format(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

@web_app.route('/health')
def health():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

def run_web_server():
    """Run Flask server for Railway health checks"""
    port = int(os.environ.get('PORT', 8080))
    web_app.run(host='0.0.0.0', port=port, debug=False)

def keep_alive():
    """Start keep-alive thread"""
    thread = Thread(target=run_web_server)
    thread.daemon = True
    thread.start()
    logger.info("🌐 Web server started for health checks")

# ============ BOT CONFIGURATION ============
# Environment Variables (Set in Railway Dashboard)
API_ID = int(os.environ.get("API_ID", "35140329"))
API_HASH = os.environ.get("API_HASH", "011f638e4acadee178c59afffc80193d")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "8952730755:AAHhor54jekn60e8NflgIJa50cMHwPQ3dbU")

# Validate environment variables
if not all([API_ID, API_HASH, BOT_TOKEN]):
    logger.error("❌ Missing environment variables! Please set API_ID, API_HASH, BOT_TOKEN")
    exit(1)

# ============ DOWNLOAD CONFIG ============
DOWNLOAD_PATH = "/tmp/insta_downloads"
TEMP_PATH = "/tmp/insta_temp"
os.makedirs(DOWNLOAD_PATH, exist_ok=True)
os.makedirs(TEMP_PATH, exist_ok=True)

# ============ INITIALIZE PYROGRAM CLIENT ============
app = Client(
    "insta_bot_session",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    workers=100,
    workdir=TEMP_PATH,
    sleep_threshold=60
)

# ============ INITIALIZE INSTALOADER ============
loader = instaloader.Instaloader(
    download_pictures=False,
    download_videos=False,
    download_video_thumbnails=False,
    save_metadata=False,
    compress_json=False,
    max_connection_attempts=3,
    request_timeout=30
)

# ============ MEMORY STORAGE ============
video_cache = {}  # Store video metadata temporarily
user_states = {}  # Store user states for audio naming

# ============ START COMMAND ============
@app.on_message(filters.command("start"))
async def start_command(client, message):
    """Handle /start command"""
    await message.reply_text(
        f"**🎬 Instagram Downloader Bot**\n\n"
        f"👋 Hello {message.from_user.first_name}!\n\n"
        f"**Features:**\n"
        f"• 📹 Download Instagram Reels/Videos in HD\n"
        f"• 📸 Download Photos in Original Quality\n"
        f"• 🎵 Extract Audio from Videos\n"
        f"• 📁 Multiple Photos Support\n\n"
        f"**How to Use:**\n"
        f"1️⃣ Copy Instagram post/reel link\n"
        f"2️⃣ Send link here\n"
        f"3️⃣ Get your content!\n\n"
        f"**Supported Links:**\n"
        f"• instagram.com/reel/xxx\n"
        f"• instagram.com/p/xxx\n"
        f"• instagram.com/tv/xxx\n\n"
        f"Send any Instagram link to start! 🚀"
    )

# ============ HELP COMMAND ============
@app.on_message(filters.command("help"))
async def help_command(client, message):
    """Handle /help command"""
    await message.reply_text(
        "**📖 Help Guide**\n\n"
        "**Step 1:** Find any Instagram post/reel\n"
        "**Step 2:** Copy link from Instagram\n"
        "**Step 3:** Paste link in this chat\n"
        "**Step 4:** Bot will send video/photo\n"
        "**Step 5:** Click buttons for extra options\n\n"
        "**Buttons:**\n"
        "📥 Download Video - Save as file\n"
        "🎵 Audio - Extract & download MP3\n\n"
        "**Commands:**\n"
        "/start - Start bot\n"
        "/help - This message\n"
        "/stats - Bot statistics\n"
        "/cleanup - Clear temporary files\n\n"
        "**Note:** Some private accounts may not work"
    )

# ============ STATS COMMAND ============
@app.on_message(filters.command("stats"))
async def stats_command(client, message):
    """Show bot statistics"""
    active_downloads = len(video_cache)
    waiting_users = len(user_states)
    
    await message.reply_text(
        f"**📊 Bot Statistics**\n\n"
        f"🔹 Active Downloads: {active_downloads}\n"
        f"🔹 Waiting Users: {waiting_users}\n"
        f"🔹 Server Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        f"✅ Bot is running smoothly!"
    )

# ============ CLEANUP COMMAND ============
@app.on_message(filters.command("cleanup"))
async def cleanup_command(client, message):
    """Clean temporary files"""
    try:
        deleted = 0
        for folder in [DOWNLOAD_PATH, TEMP_PATH]:
            for filename in os.listdir(folder):
                file_path = os.path.join(folder, filename)
                try:
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                        deleted += 1
                except Exception as e:
                    logger.error(f"Error deleting {file_path}: {e}")
        
        # Clear caches
        video_cache.clear()
        user_states.clear()
        
        await message.reply_text(f"✅ Cleanup Complete!\n🗑️ {deleted} files deleted\n🔄 Caches cleared")
    except Exception as e:
        await message.reply_text(f"❌ Cleanup Error: {str(e)[:200]}")

# ============ INSTAGRAM LINK HANDLER ============
@app.on_message(filters.regex(r'https?://(?:www\.)?instagram\.com/(?:p|reel|tv|stories)/[^/]+/?.*'))
async def handle_instagram_link(client, message):
    """Main handler for Instagram links"""
    status_message = None
    try:
        url = message.text.strip()
        
        # Extract shortcode from URL
        pattern = r'instagram\.com/(?:p|reel|tv)/([a-zA-Z0-9_-]+)'
        match = re.search(pattern, url)
        
        if not match:
            await message.reply_text("❌ **Invalid Instagram Link!**\n\nPlease send a valid post/reel link.")
            return
        
        shortcode = match.group(1)
        logger.info(f"Processing shortcode: {shortcode}")
        
        # Send processing message
        status_message = await message.reply_text("🔄 **Processing your link...**\n⏳ Please wait...")
        
        # Fetch post using Instaloader
        try:
            post = instaloader.Post.from_shortcode(loader.context, shortcode)
        except instaloader.exceptions.InstaloaderException as e:
            logger.error(f"Instaloader error: {e}")
            await status_message.edit_text(
                "❌ **Failed to fetch post!**\n\n"
                "Possible reasons:\n"
                "• Post is from private account\n"
                "• Invalid or broken link\n"
                "• Instagram rate limit\n\n"
                "Please try again later or check the link."
            )
            return
        
        if post.is_video:
            await handle_video_download(client, message, status_message, post, shortcode)
        else:
            await handle_photo_download(client, message, status_message, post, shortcode)
            
    except FloodWait as e:
        logger.warning(f"FloodWait: {e.value} seconds")
        await asyncio.sleep(e.value + 1)
        # Retry logic if needed
    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        if status_message:
            try:
                await status_message.edit_text(f"❌ **Unexpected Error!**\n\n`{str(e)[:200]}`\n\nPlease try again later.")
            except:
                pass

# ============ VIDEO DOWNLOAD HANDLER ============
async def handle_video_download(client, message, status_message, post, shortcode):
    """Handle video download and sending"""
    try:
        video_url = str(post.video_url)
        file_id = str(uuid.uuid4())[:12]
        file_path = os.path.join(DOWNLOAD_PATH, f"{file_id}.mp4")
        
        await status_message.edit_text("📥 **Downloading video...**\n⬇️ Fetching from Instagram...")
        
        # Download video with progress tracking
        async with aiohttp.ClientSession() as session:
            async with session.get(video_url, timeout=aiohttp.ClientTimeout(total=300)) as response:
                if response.status != 200:
                    await status_message.edit_text("❌ **Download Failed!**\nInstagram server error. Try again.")
                    return
                
                total_size = int(response.headers.get('content-length', 0))
                downloaded = 0
                
                async with aiofiles.open(file_path, 'wb') as f:
                    async for chunk in response.content.iter_chunked(1024 * 1024):  # 1MB chunks
                        await f.write(chunk)
                        downloaded += len(chunk)
                        
                        # Update progress every 5MB
                        if total_size and downloaded % (5 * 1024 * 1024) == 0:
                            percent = (downloaded / total_size) * 100
                            try:
                                await status_message.edit_text(
                                    f"📥 **Downloading video...**\n"
                                    f"⬇️ Progress: {percent:.1f}%\n"
                                    f"📦 {downloaded/1024/1024:.1f}MB / {total_size/1024/1024:.1f}MB"
                                )
                            except:
                                pass
        
        # Get video info
        video_size = os.path.getsize(file_path) / (1024 * 1024)  # MB
        duration = int(post.video_duration) if post.video_duration else 0
        owner = post.owner_username if post.owner_username else "unknown"
        caption_text = post.caption[:500] if post.caption else "Instagram Video"
        
        # Store in cache
        video_cache[file_id] = {
            'video_path': file_path,
            'video_url': video_url,
            'caption': caption_text[:100],
            'owner_id': owner,
            'duration': duration,
            'timestamp': datetime.now().timestamp()
        }
        
        # Create buttons
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📥 Download Video", callback_data=f"dlvid_{file_id}"),
                InlineKeyboardButton("🎵 Extract Audio", callback_data=f"audio_{file_id}")
            ],
            [
                InlineKeyboardButton("❌ Close", callback_data=f"close_{file_id}")
            ]
        ])
        
        # Prepare caption
        final_caption = (
            f"**🎬 {caption_text[:300]}**\n\n"
            f"👤 **@{owner}**\n"
            f"⏱️ **Duration:** {duration} seconds\n"
            f"📦 **Size:** {video_size:.1f}MB\n"
            f"✨ **Quality:** HD\n\n"
            f"🔽 Use buttons below for options:"
        )
        
        await status_message.delete()
        
        # Send video based on size
        if video_size > 50:  # Telegram bot limit for videos
            await message.reply_document(
                document=file_path,
                caption=final_caption,
                reply_markup=keyboard,
                file_name=f"Instagram_{shortcode}.mp4"
            )
        else:
            await message.reply_video(
                video=file_path,
                caption=final_caption,
                reply_markup=keyboard,
                supports_streaming=True,
                duration=duration,
                width=1280,
                height=720,
                file_name=f"Instagram_{shortcode}.mp4"
            )
            
        logger.info(f"Video sent successfully: {shortcode}")
        
        # Schedule cleanup after 30 minutes
        asyncio.create_task(schedule_cleanup(file_id, 1800))
        
    except Exception as e:
        logger.error(f"Video download error: {e}", exc_info=True)
        await status_message.edit_text(f"❌ **Video Download Failed!**\n\n`{str(e)[:200]}`")

# ============ PHOTO DOWNLOAD HANDLER ============
async def handle_photo_download(client, message, status_message, post, shortcode):
    """Handle photo download and sending"""
    try:
        owner = post.owner_username if post.owner_username else "unknown"
        
        if hasattr(post, 'typename') and post.typename == "GraphSidecar":
            # Multiple photos (Album/Carousel)
            sidecar_nodes = list(post.get_sidecar_nodes())
            photo_count = sum(1 for node in sidecar_nodes if not node.is_video)
            
            await status_message.edit_text(f"📥 **Downloading {photo_count} photos...**")
            
            media_group = []
            for idx, node in enumerate(sidecar_nodes, 1):
                if node.is_video:
                    continue
                    
                photo_url = str(node.display_url)
                file_path = os.path.join(DOWNLOAD_PATH, f"{shortcode}_{idx}.jpg")
                
                # Download photo
                async with aiohttp.ClientSession() as session:
                    async with session.get(photo_url) as response:
                        if response.status == 200:
                            async with aiofiles.open(file_path, 'wb') as f:
                                await f.write(await response.read())
                
                caption = f"**📸 Photo {idx}/{photo_count}**\n👤 @{owner}" if idx == 1 else ""
                
                # Send as photo
                await message.reply_photo(
                    photo=file_path,
                    caption=caption
                )
                
                # Cleanup
                os.remove(file_path)
                await asyncio.sleep(0.5)  # Avoid flood
            
            await status_message.delete()
            
        else:
            # Single photo
            await status_message.edit_text("📥 **Downloading photo...**")
            
            photo_url = str(post.url)
            file_path = os.path.join(DOWNLOAD_PATH, f"{shortcode}.jpg")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(photo_url) as response:
                    if response.status == 200:
                        async with aiofiles.open(file_path, 'wb') as f:
                            await f.write(await response.read())
            
            caption_text = post.caption[:500] if post.caption else "Instagram Photo"
            
            await status_message.delete()
            await message.reply_photo(
                photo=file_path,
                caption=f"**📸 Instagram Photo**\n\n👤 **@{owner}**\n\n{caption_text[:300]}"
            )
            
            os.remove(file_path)
            
        logger.info(f"Photo(s) sent successfully: {shortcode}")
        
    except Exception as e:
        logger.error(f"Photo download error: {e}", exc_info=True)
        await status_message.edit_text(f"❌ **Photo Download Failed!**\n\n`{str(e)[:200]}`")

# ============ BUTTON CALLBACK HANDLERS ============

@app.on_callback_query(filters.regex(r'^dlvid_'))
async def download_video_callback(client, callback_query: CallbackQuery):
    """Handle Download Video button"""
    try:
        file_id = callback_query.data.replace('dlvid_', '')
        video_info = video_cache.get(file_id)
        
        if not video_info or not os.path.exists(video_info['video_path']):
            await callback_query.answer("❌ Video expired! Please send the link again.", show_alert=True)
            return
        
        await callback_query.answer("📥 Sending video file...")
        
        # Send video as document (file)
        await callback_query.message.reply_document(
            document=video_info['video_path'],
            caption=f"📹 **Downloaded Video**\n👤 @{video_info['owner_id']}\n✨ High Quality",
            file_name=f"Instagram_Video_{file_id}.mp4"
        )
        
    except Exception as e:
        logger.error(f"Download callback error: {e}")
        await callback_query.answer("❌ Error sending video!", show_alert=True)

@app.on_callback_query(filters.regex(r'^audio_'))
async def audio_callback(client, callback_query: CallbackQuery):
    """Handle Audio button - Ask for filename"""
    try:
        file_id = callback_query.data.replace('audio_', '')
        video_info = video_cache.get(file_id)
        
        if not video_info:
            await callback_query.answer("❌ Session expired! Send the link again.", show_alert=True)
            return
        
        # Set user state
        user_states[callback_query.from_user.id] = {
            'file_id': file_id,
            'timestamp': datetime.now().timestamp(),
            'message_id': callback_query.message.id
        }
        
        # Ask for audio filename
        prompt = await callback_query.message.reply_text(
            "🎵 **Enter filename for audio:**\n\n"
            "📝 Example: `my_song` or `best_audio`\n"
            "💡 Extension will be added automatically\n\n"
            "⏰ You have 2 minutes to respond!"
        )
        
        # Store prompt message ID for cleanup
        user_states[callback_query.from_user.id]['prompt_id'] = prompt.id
        
        await callback_query.answer("Enter filename below 👇")
        
    except Exception as e:
        logger.error(f"Audio callback error: {e}")
        await callback_query.answer("❌ Error!", show_alert=True)

@app.on_callback_query(filters.regex(r'^close_'))
async def close_callback(client, callback_query: CallbackQuery):
    """Handle Close button"""
    try:
        await callback_query.message.delete()
    except:
        await callback_query.answer("Can't delete message")

# ============ TEXT MESSAGE HANDLER (FOR AUDIO FILENAME) ============
@app.on_message(filters.text & filters.private & ~filters.command(["start", "help", "stats", "cleanup"]))
async def handle_audio_filename(client, message):
    """Handle audio filename input"""
    user_id = message.from_user.id
    
    # Check if user is in audio naming state
    if user_id not in user_states:
        return  # Not waiting for filename, ignore
    
    state_data = user_states[user_id]
    
    # Check timeout (2 minutes)
    if datetime.now().timestamp() - state_data['timestamp'] > 120:
        del user_states[user_id]
        await message.reply_text("⏰ **Timeout!** Please try again.")
        return
    
    file_id = state_data['file_id']
    video_info = video_cache.get(file_id)
    
    if not video_info:
        del user_states[user_id]
        await message.reply_text("❌ **Session expired!** Send link again.")
        return
    
    # Get filename from user
    audio_name = message.text.strip().replace(' ', '_')[:50]  # Clean filename
    
    if not audio_name.endswith(('.mp3', '.m4a', '.wav', '.ogg')):
        audio_name += '.mp3'
    
    # Send processing message
    status_msg = await message.reply_text("🔄 **Extracting audio...**\n🎵 Please wait...")
    
    try:
        # Extract audio using yt-dlp
        temp_audio = os.path.join(DOWNLOAD_PATH, f"audio_{file_id}")
        
        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': temp_audio,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': True,
            'no_warnings': True,
            'extract_audio': True,
        }
        
        # Download and extract
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: extract_audio_sync(video_info['video_url'], ydl_opts))
        
        actual_audio_file = temp_audio + '.mp3'
        
        if not os.path.exists(actual_audio_file):
            raise Exception("Audio extraction failed")
        
        await status_msg.edit_text("📤 **Uploading audio...**")
        
        # Send audio
        await client.send_audio(
            chat_id=message.chat.id,
            audio=actual_audio_file,
            caption=f"🎵 **{audio_name.replace('.mp3', '')}**\n\n"
                   f"👤 @{video_info['owner_id']}\n"
                   f"📱 Extracted from Instagram",
            file_name=audio_name,
            performer=video_info['owner_id'],
            title=audio_name.replace('.mp3', ''),
            duration=video_info.get('duration', 0)
        )
        
        await status_msg.delete()
        
        # Delete user messages
        try:
            await message.delete()  # Filename message
            # Try to delete prompt message
            if 'prompt_id' in state_data:
                await client.delete_messages(message.chat.id, state_data['prompt_id'])
        except:
            pass
        
        # Cleanup audio file
        try:
            os.remove(actual_audio_file)
        except:
            pass
        
        logger.info(f"Audio sent successfully for {file_id}")
        
    except Exception as e:
        logger.error(f"Audio extraction error: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ **Audio Extraction Failed!**\n\n`{str(e)[:200]}`")
    
    finally:
        # Cleanup state
        del user_states[user_id]

def extract_audio_sync(video_url, ydl_opts):
    """Synchronous audio extraction using yt-dlp"""
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url])
    except Exception as e:
        logger.error(f"yt-dlp error: {e}")
        raise

# ============ SCHEDULED CLEANUP ============
async def schedule_cleanup(file_id, delay_seconds):
    """Schedule cleanup of video files after delay"""
    await asyncio.sleep(delay_seconds)
    
    if file_id in video_cache:
        video_path = video_cache[file_id].get('video_path')
        if video_path and os.path.exists(video_path):
            try:
                os.remove(video_path)
                logger.info(f"Cleaned up: {video_path}")
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
        
        del video_cache[file_id]

# ============ ERROR HANDLER ============
@app.on_callback_query()
async def handle_unknown_callback(client, callback_query: CallbackQuery):
    """Handle unknown callbacks"""
    await callback_query.answer("This button has expired!", show_alert=True)

# ============ MAIN ============
if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("🤖 Instagram Downloader Bot Starting...")
    logger.info("=" * 50)
    
    # Start web server for Railway
    keep_alive()
    
    # Start bot
    try:
        logger.info("✅ Bot is running...")
        app.run()
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Bot crashed: {e}", exc_info=True)
