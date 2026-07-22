import os
import re
import uuid
import asyncio
import logging
import time
import subprocess
import aiohttp
import aiofiles
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait

# Simple logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============ CONFIG ============
API_ID = 35140329
API_HASH = "011f638e4acadee178c59afffc80193d"
BOT_TOKEN = "8518787964:AAHGimBKXfdtrI6UaASGsoI8Aj5Rj_WxF5I"

# Create bot
app = Client(
    "my_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True
)

DOWNLOAD_PATH = "./downloads"
os.makedirs(DOWNLOAD_PATH, exist_ok=True)

video_cache = {}
user_cooldown = {}

# ============ INSTAGRAM DOWNLOAD FUNCTION ============

async def download_instagram(url):
    """Download Instagram video/photo using multiple methods"""
    
    # Method 1: Try yt-dlp first
    try:
        file_id = str(uuid.uuid4())[:8]
        output_template = os.path.join(DOWNLOAD_PATH, f"%(title)s_{file_id}.%(ext)s")
        
        cmd = [
            'yt-dlp',
            '-f', 'best[ext=mp4]/best',
            '--no-playlist',
            '--no-warnings',
            '--ignore-errors',
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
            # Find downloaded file
            for file in os.listdir(DOWNLOAD_PATH):
                if file_id in file:
                    file_path = os.path.join(DOWNLOAD_PATH, file)
                    ext = file.split('.')[-1].lower()
                    return file_path, ext
        else:
            logger.error(f"yt-dlp error: {stderr.decode()}")
    except Exception as e:
        logger.error(f"yt-dlp method error: {e}")
    
    # Method 2: Try API
    try:
        api_url = f"https://api.davidcyriltech.my.id/instagram?url={url}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("success") and data.get("download_url"):
                        download_url = data["download_url"]
                        
                        # Download file
                        file_id = str(uuid.uuid4())[:8]
                        ext = 'mp4' if 'mp4' in download_url else 'jpg'
                        file_path = os.path.join(DOWNLOAD_PATH, f"{file_id}.{ext}")
                        
                        async with aiohttp.ClientSession() as session2:
                            async with session2.get(download_url, timeout=60) as resp2:
                                if resp2.status == 200:
                                    async with aiofiles.open(file_path, 'wb') as f:
                                        async for chunk in resp2.content.iter_chunked(1024*1024):
                                            await f.write(chunk)
                                    
                                    if os.path.exists(file_path) and os.path.getsize(file_path) > 10000:
                                        return file_path, ext
    except Exception as e:
        logger.error(f"API method error: {e}")
    
    return None, None

# ============ COMMANDS ============

@app.on_message(filters.command("start"))
async def start_command(client, message):
    await message.reply_text(
        "**🎬 Instagram Downloader Bot**\n\n"
        "Send me any Instagram link!\n"
        "I will download and send it to you.\n\n"
        "✅ Public posts only\n"
        "✅ HD Quality\n"
        "✅ Video & Photos\n\n"
        "**Send link now!** 🚀"
    )

@app.on_message(filters.command("ping"))
async def ping_command(client, message):
    await message.reply_text("🏓 Pong! Bot is working!")

@app.on_message(filters.text & filters.private)
async def handle_instagram(client, message):
    # Check if Instagram link
    if not re.search(r'instagram\.com/(?:p|reel|tv|stories)/', message.text):
        if not message.text.startswith('/'):
            await message.reply_text("❌ Please send an Instagram link!")
        return
    
    # Rate limiting
    user_id = message.from_user.id
    if user_id in user_cooldown:
        if time.time() - user_cooldown[user_id] < 10:
            await message.reply_text("⏳ Please wait 10 seconds before sending another link!")
            return
    
    user_cooldown[user_id] = time.time()
    
    # Send processing message
    status_msg = await message.reply_text("🔍 **Processing your request...**")
    
    try:
        url = message.text.strip()
        url = url.split('?')[0]  # Remove query parameters
        
        logger.info(f"Processing: {url}")
        
        await status_msg.edit_text("📥 **Downloading media...**")
        
        # Download
        file_path, ext = await download_instagram(url)
        
        if not file_path or not os.path.exists(file_path):
            await status_msg.edit_text(
                "❌ **Download failed!**\n\n"
                "Possible reasons:\n"
                "• Post is **private**\n"
                "• Invalid URL\n"
                "• Instagram blocked the request\n\n"
                "💡 Try:\n"
                "• Make sure post is public\n"
                "• Copy link from Instagram app\n"
                "• Try a different post"
            )
            return
        
        file_size = os.path.getsize(file_path) / (1024 * 1024)
        file_id = str(uuid.uuid4())[:8]
        
        # Cache for buttons
        video_cache[file_id] = {
            'path': file_path,
            'ext': ext,
            'time': time.time()
        }
        
        # Create keyboard
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📥 Download", callback_data=f"dl_{file_id}"),
                InlineKeyboardButton("🎵 Audio", callback_data=f"au_{file_id}")
            ]
        ])
        
        await status_msg.delete()
        
        # Send based on file type
        if ext in ['mp4', 'mov', 'mkv', 'avi']:
            caption = f"🎬 **Instagram Video**\n📦 {file_size:.1f} MB"
            
            if file_size > 50:
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
            logger.info(f"✅ Video sent: {file_size:.1f} MB")
            
        elif ext in ['jpg', 'jpeg', 'png', 'gif']:
            await message.reply_photo(
                photo=file_path,
                caption="📸 **Instagram Photo**",
                reply_markup=keyboard
            )
            logger.info("✅ Photo sent")
            # Remove photo immediately
            os.remove(file_path)
            del video_cache[file_id]
            
        else:
            await message.reply_document(
                document=file_path,
                caption="📎 **Instagram Media**",
                reply_markup=keyboard,
                file_name=f"instagram_{file_id}.{ext}"
            )
            
    except FloodWait as e:
        await status_msg.edit_text(f"⏳ Rate limited! Wait {e.value} seconds")
        await asyncio.sleep(e.value)
    except Exception as e:
        logger.error(f"Error: {e}")
        await status_msg.edit_text("❌ **Error! Please try again later**")

# ============ CALLBACKS ============

@app.on_callback_query(filters.regex(r'^dl_'))
async def download_callback(client, callback):
    try:
        file_id = callback.data.replace('dl_', '')
        data = video_cache.get(file_id)
        
        if not data or not os.path.exists(data['path']):
            await callback.answer("❌ Expired! Send again.", show_alert=True)
            return
        
        await callback.message.reply_document(
            document=data['path'],
            caption="📹 Instagram Video",
            file_name=f"instagram_{file_id}.{data['ext']}"
        )
        await callback.answer("✅ Download started!")
    except Exception as e:
        logger.error(f"DL error: {e}")
        await callback.answer("❌ Failed!", show_alert=True)

@app.on_callback_query(filters.regex(r'^au_'))
async def audio_callback(client, callback):
    try:
        file_id = callback.data.replace('au_', '')
        data = video_cache.get(file_id)
        
        if not data or not os.path.exists(data['path']):
            await callback.answer("❌ Expired!", show_alert=True)
            return
        
        await callback.answer("🎵 Extracting audio...")
        
        audio_file = os.path.join(DOWNLOAD_PATH, f"audio_{file_id}.mp3")
        
        # Extract audio using ffmpeg
        try:
            cmd = [
                'ffmpeg',
                '-i', data['path'],
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
                await client.send_audio(
                    chat_id=callback.message.chat.id,
                    audio=audio_file,
                    caption="🎵 Instagram Audio",
                    file_name=f"instagram_audio_{file_id}.mp3"
                )
                os.remove(audio_file)
                await callback.answer("✅ Audio sent!")
            else:
                await callback.answer("❌ No audio found!", show_alert=True)
        except:
            await callback.answer("❌ FFmpeg not installed!", show_alert=True)
            
    except Exception as e:
        logger.error(f"Audio error: {e}")
        await callback.answer("❌ Failed!", show_alert=True)

# ============ CLEANUP ============

async def cleanup_old_files():
    """Remove old files after 10 minutes"""
    while True:
        try:
            current_time = time.time()
            to_remove = []
            
            for file_id, data in video_cache.items():
                if current_time - data.get('time', 0) > 600:
                    to_remove.append(file_id)
                    if os.path.exists(data['path']):
                        try:
                            os.remove(data['path'])
                        except:
                            pass
            
            for file_id in to_remove:
                del video_cache[file_id]
            
            await asyncio.sleep(300)
        except:
            await asyncio.sleep(60)

# ============ MAIN ============

async def main():
    print("🚀 Starting Instagram Downloader Bot...")
    
    # Start cleanup task
    asyncio.create_task(cleanup_old_files())
    
    print("✅ Bot is running! Send /start")
    
    # Start bot
    await app.start()
    await app.idle()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n❌ Bot stopped!")
    except Exception as e:
        print(f"❌ Error: {e}")
