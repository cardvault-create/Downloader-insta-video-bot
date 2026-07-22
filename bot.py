import os
import re
import uuid
import asyncio
import logging
import time
import subprocess
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============ CONFIG ============
API_ID = 35140329
API_HASH = "011f638e4acadee178c59afffc80193d"
BOT_TOKEN = "8518787964:AAHGimBKXfdtrI6UaASGsoI8Aj5Rj_WxF5I"

app = Client(
    "instagram_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True,
    sleep_threshold=60
)

DOWNLOAD_PATH = "./downloads"
os.makedirs(DOWNLOAD_PATH, exist_ok=True)

video_cache = {}
user_cooldown = {}

# Install yt-dlp if not present
try:
    subprocess.run(['yt-dlp', '--version'], capture_output=True, check=True)
    logger.info("✅ yt-dlp is installed")
except:
    logger.info("Installing yt-dlp...")
    subprocess.run(['pip', 'install', 'yt-dlp', '--quiet'], check=True)

# ============ DOWNLOAD USING YT-DLP ============

async def download_instagram(url):
    """Download Instagram media using yt-dlp"""
    try:
        file_id = str(uuid.uuid4())[:8]
        output_path = os.path.join(DOWNLOAD_PATH, f"%(title)s_{file_id}.%(ext)s")
        
        # yt-dlp command for best quality
        cmd = [
            'yt-dlp',
            '-f', 'best[ext=mp4]/best',  # Best quality video
            '--no-playlist',
            '--no-warnings',
            '--ignore-errors',
            '--no-check-certificate',
            '-o', output_path,
            url
        ]
        
        logger.info(f"Running: {' '.join(cmd)}")
        
        # Run yt-dlp
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
        
        logger.error(f"yt-dlp error: {stderr.decode()}")
        return None, None
        
    except Exception as e:
        logger.error(f"Download error: {e}")
        return None, None

# ============ BOT COMMANDS ============

@app.on_message(filters.command("start"))
async def start_cmd(client, message):
    await message.reply_text(
        "**🎬 Instagram Downloader Bot**\n\n"
        "Send me any Instagram post/reel link!\n\n"
        "✅ **Best Quality** (Original)\n"
        "✅ **Works with all public posts**\n"
        "✅ **Photos & Videos**\n"
        "✅ **Audio Extraction**\n\n"
        "**Just send the link!** 🚀"
    )

@app.on_message(filters.command("ping"))
async def ping_cmd(client, message):
    await message.reply_text("✅ **Bot is working!**")

@app.on_message(filters.text & filters.private)
async def handle_instagram(client, message):
    # Check for Instagram link
    if not re.search(r'instagram\.com/(?:p|reel|tv|stories)/', message.text):
        return
    
    user_id = message.from_user.id
    
    # Rate limit
    if user_id in user_cooldown:
        if time.time() - user_cooldown[user_id] < 15:
            await message.reply_text("⏳ **Please wait 15 seconds before sending another link!**")
            return
    
    user_cooldown[user_id] = time.time()
    
    status_msg = await message.reply_text("🔍 **Processing your request...**")
    
    try:
        url = message.text.strip()
        url = url.split('?')[0]
        url = url.split('#')[0]
        
        logger.info(f"Processing: {url}")
        
        await status_msg.edit_text("📥 **Downloading media...**")
        
        # Download using yt-dlp
        file_path, ext = await download_instagram(url)
        
        if not file_path or not os.path.exists(file_path):
            await status_msg.edit_text(
                "❌ **Could not download!**\n\n"
                "Possible reasons:\n"
                "• Post is **private**\n"
                "• Account is private\n"
                "• Invalid URL\n\n"
                "💡 **Try:**\n"
                "• Make sure post is public\n"
                "• Copy link from Instagram app\n"
                "• Try a different post"
            )
            return
        
        file_size = os.path.getsize(file_path) / (1024 * 1024)
        file_id = str(uuid.uuid4())[:8]
        
        # Cache
        video_cache[file_id] = {
            'path': file_path,
            'ext': ext,
            'time': time.time()
        }
        
        # Keyboard
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("📥 Download", callback_data=f"dl_{file_id}"),
                InlineKeyboardButton("🎵 Audio", callback_data=f"au_{file_id}")
            ]
        ])
        
        await status_msg.delete()
        
        # Send based on file type
        if ext in ['mp4', 'mov', 'avi', 'mkv']:
            caption = f"🎬 **Instagram Video**\n📦 {file_size:.1f} MB\n✨ **Original Quality**"
            
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
                caption="📸 **Instagram Photo**\n✨ **Original Quality**",
                reply_markup=keyboard
            )
            logger.info("✅ Photo sent")
            os.remove(file_path)
            del video_cache[file_id]
            
        else:
            await message.reply_document(
                document=file_path,
                caption=f"📎 **Instagram Media**",
                reply_markup=keyboard,
                file_name=f"instagram_{file_id}.{ext}"
            )
            logger.info("✅ File sent")
            
    except FloodWait as e:
        await status_msg.edit_text(f"⏳ **Rate limited! Wait {e.value}s**")
        await asyncio.sleep(e.value)
    except Exception as e:
        logger.error(f"Error: {e}")
        await status_msg.edit_text("❌ **Error! Please try again later**")

# ============ BUTTONS ============

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
                'ffmpeg', '-i', data['path'],
                '-vn', '-acodec', 'libmp3lame',
                '-ab', '192k', '-ar', '44100',
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
                await callback.answer("❌ No audio!", show_alert=True)
        except:
            await callback.answer("❌ FFmpeg missing!", show_alert=True)
            
    except Exception as e:
        logger.error(f"Audio error: {e}")
        await callback.answer("❌ Failed!", show_alert=True)

# ============ CLEANUP ============

async def cleanup():
    while True:
        try:
            for file_id, data in list(video_cache.items()):
                if time.time() - data['time'] > 600:
                    if os.path.exists(data['path']):
                        os.remove(data['path'])
                    del video_cache[file_id]
            await asyncio.sleep(300)
        except:
            await asyncio.sleep(60)

# ============ MAIN ============

async def main():
    print("🚀 Starting Instagram Downloader Bot...")
    asyncio.create_task(cleanup())
    print("✅ Bot is running! Send /start")
    await app.start()
    await app.idle()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n❌ Stopped!")
    except Exception as e:
        print(f"❌ Error: {e}")
