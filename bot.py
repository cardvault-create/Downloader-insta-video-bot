import os
import re
import uuid
import asyncio
import logging
import time
import json
import aiohttp
import aiofiles
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.errors import FloodWait

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============ CONFIG ============
API_ID = 35140329
API_HASH = "011f638e4acadee178c59afffc80193d"
BOT_TOKEN = "8518787964:AAHGimBKXfdtrI6UaASGsoI8Aj5Rj_WxF5I"

# Create bot client
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

# ============ SIMPLE INSTAGRAM API ============

async def get_instagram_url(url):
    """Get download URL from Instagram"""
    try:
        # Using a single working API
        api_url = f"https://api.davidcyriltech.my.id/instagram?url={url}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("success") and data.get("download_url"):
                        return data["download_url"]
    except:
        pass
    
    return None

async def download_media(url, file_path):
    """Download media"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=60) as resp:
                if resp.status == 200:
                    async with aiofiles.open(file_path, 'wb') as f:
                        async for chunk in resp.content.iter_chunked(1024*1024):
                            await f.write(chunk)
                    return True
    except:
        pass
    return False

# ============ BOT COMMANDS ============

@app.on_message(filters.command("start"))
async def start_cmd(client, message):
    await message.reply_text(
        "**🎬 Instagram Downloader Bot**\n\n"
        "Send me any Instagram post/reel link!\n\n"
        "✅ Works with public posts\n"
        "✅ High quality videos\n"
        "✅ Photo download\n\n"
        "**Just send the link!** 🚀"
    )

@app.on_message(filters.command("ping"))
async def ping_cmd(client, message):
    await message.reply_text("✅ **Bot is alive!**")

@app.on_message(filters.text & filters.private)
async def handle_instagram(client, message):
    # Check if message is Instagram link
    if not re.search(r'instagram\.com/(?:p|reel|tv)/', message.text):
        return
    
    user_id = message.from_user.id
    
    # Rate limit
    if user_id in user_cooldown:
        if time.time() - user_cooldown[user_id] < 10:
            await message.reply_text("⏳ **Please wait 10 seconds!**")
            return
    
    user_cooldown[user_id] = time.time()
    
    status = await message.reply_text("🔍 **Processing...**")
    
    try:
        url = message.text.strip()
        url = url.split('?')[0]
        
        # Get download URL
        download_url = await get_instagram_url(url)
        
        if not download_url:
            await status.edit_text(
                "❌ **Failed to fetch!**\n\n"
                "Make sure:\n"
                "• Post is **public**\n"
                "• Link is correct\n"
                "• Try another link"
            )
            return
        
        # Download
        file_id = str(uuid.uuid4())[:8]
        is_video = 'mp4' in download_url.lower()
        ext = 'mp4' if is_video else 'jpg'
        file_path = os.path.join(DOWNLOAD_PATH, f"{file_id}.{ext}")
        
        await status.edit_text("📥 **Downloading...**")
        
        if not await download_media(download_url, file_path):
            await status.edit_text("❌ **Download failed!**")
            return
        
        file_size = os.path.getsize(file_path) / (1024 * 1024)
        
        # Cache for buttons
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
        
        await status.delete()
        
        # Send file
        if is_video:
            await message.reply_video(
                video=file_path,
                caption=f"🎬 **Instagram Video**\n📦 {file_size:.1f} MB",
                reply_markup=keyboard,
                supports_streaming=True
            )
        else:
            await message.reply_photo(
                photo=file_path,
                caption="📸 **Instagram Photo**",
                reply_markup=keyboard
            )
            os.remove(file_path)
            del video_cache[file_id]
            
        logger.info(f"✅ Sent: {file_size:.1f} MB")
        
    except FloodWait as e:
        await status.edit_text(f"⏳ **Wait {e.value}s**")
        await asyncio.sleep(e.value)
    except Exception as e:
        logger.error(f"Error: {e}")
        await status.edit_text("❌ **Error! Please try again**")

# ============ BUTTON HANDLERS ============

@app.on_callback_query(filters.regex(r'^dl_'))
async def dl_callback(client, callback):
    try:
        file_id = callback.data.replace('dl_', '')
        data = video_cache.get(file_id)
        
        if not data or not os.path.exists(data['path']):
            await callback.answer("❌ Expired!", show_alert=True)
            return
        
        await callback.message.reply_document(
            document=data['path'],
            caption="📹 Instagram Video",
            file_name=f"instagram_{file_id}.{data['ext']}"
        )
        await callback.answer("✅ Download started!")
    except Exception as e:
        await callback.answer("❌ Failed!", show_alert=True)

@app.on_callback_query(filters.regex(r'^au_'))
async def au_callback(client, callback):
    try:
        file_id = callback.data.replace('au_', '')
        data = video_cache.get(file_id)
        
        if not data or not os.path.exists(data['path']):
            await callback.answer("❌ Expired!", show_alert=True)
            return
        
        await callback.answer("🎵 Extracting...")
        
        audio_file = os.path.join(DOWNLOAD_PATH, f"audio_{file_id}.mp3")
        
        # Try ffmpeg
        import subprocess
        try:
            subprocess.run([
                'ffmpeg', '-i', data['path'],
                '-vn', '-acodec', 'libmp3lame',
                '-ab', '192k', '-y', audio_file
            ], capture_output=True, check=True, timeout=30)
            
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
        await callback.answer("❌ Failed!", show_alert=True)

# ============ CLEANUP ============

async def cleanup_old_files():
    """Remove old files"""
    while True:
        try:
            for file_id, data in list(video_cache.items()):
                if time.time() - data.get('time', 0) > 600:
                    if os.path.exists(data['path']):
                        os.remove(data['path'])
                    del video_cache[file_id]
            await asyncio.sleep(300)
        except:
            await asyncio.sleep(60)

# ============ MAIN ============

def main():
    """Main function"""
    print("🚀 Starting Instagram Downloader Bot...")
    
    # Start cleanup in background
    loop = asyncio.get_event_loop()
    loop.create_task(cleanup_old_files())
    
    print("✅ Bot is running! Send /start to test.")
    
    # Run bot
    app.run()

if __name__ == "__main__":
    main()
