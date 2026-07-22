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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Bot Running"

def run_web():
    web_app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))

def keep_alive():
    Thread(target=run_web, daemon=True).start()

API_ID = int(os.environ.get("API_ID"))
API_HASH = os.environ.get("API_HASH")
BOT_TOKEN = os.environ.get("BOT_TOKEN")

app = Client("bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN, workers=50)
loader = instaloader.Instaloader(download_pictures=False, download_videos=False, download_video_thumbnails=False, save_metadata=False, max_connection_attempts=3)

DOWNLOAD_PATH = "/tmp/downloads"
os.makedirs(DOWNLOAD_PATH, exist_ok=True)

video_cache = {}
user_states = {}

@app.on_message(filters.command("start"))
async def start(client, message):
    await message.reply_text("**🎬 Instagram Downloader Bot**\n\nSend Instagram reel/post link to download!\n\nVideo/Photo/Reels supported ✅")

@app.on_message(filters.regex(r'https?://(?:www\.)?instagram\.com/(?:p|reel|tv)/[^/]+'))
async def download(client, message):
    status = None
    try:
        url = message.text.strip()
        match = re.search(r'instagram\.com/(?:p|reel|tv)/([a-zA-Z0-9_-]+)', url)
        if not match:
            await message.reply_text("❌ Invalid link!")
            return
        
        shortcode = match.group(1)
        status = await message.reply_text("🔄 Processing...")
        
        try:
            post = instaloader.Post.from_shortcode(loader.context, shortcode)
        except:
            await status.edit_text("❌ Failed to fetch post. May be private or invalid.")
            return
        
        if post.is_video:
            video_url = str(post.video_url)
            file_id = str(uuid.uuid4())[:12]
            file_path = os.path.join(DOWNLOAD_PATH, f"{file_id}.mp4")
            
            await status.edit_text("📥 Downloading video...")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(video_url, timeout=aiohttp.ClientTimeout(total=300)) as resp:
                    if resp.status == 200:
                        async with aiofiles.open(file_path, 'wb') as f:
                            await f.write(await resp.read())
            
            size_mb = os.path.getsize(file_path) / (1024*1024)
            owner = post.owner_username or "unknown"
            caption = post.caption[:200] if post.caption else "Instagram Video"
            duration = int(post.video_duration) if post.video_duration else 0
            
            video_cache[file_id] = {
                'video_path': file_path,
                'video_url': video_url,
                'owner_id': owner,
                'duration': duration
            }
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📥 Download Video", callback_data=f"dl_{file_id}"),
                 InlineKeyboardButton("🎵 Audio", callback_data=f"au_{file_id}")]
            ])
            
            await status.delete()
            
            if size_mb > 50:
                await message.reply_document(document=file_path, caption=f"**🎬 {caption}**\n👤 @{owner}", reply_markup=keyboard, file_name=f"instagram_{shortcode}.mp4")
            else:
                await message.reply_video(video=file_path, caption=f"**🎬 {caption}**\n👤 @{owner}", reply_markup=keyboard, supports_streaming=True, duration=duration)
        else:
            await status.edit_text("📥 Downloading photo...")
            photo_url = str(post.url)
            file_path = os.path.join(DOWNLOAD_PATH, f"{shortcode}.jpg")
            
            async with aiohttp.ClientSession() as session:
                async with session.get(photo_url) as resp:
                    if resp.status == 200:
                        async with aiofiles.open(file_path, 'wb') as f:
                            await f.write(await resp.read())
            
            owner = post.owner_username or "unknown"
            await status.delete()
            await message.reply_photo(photo=file_path, caption=f"**📸 Instagram Photo**\n👤 @{owner}")
            os.remove(file_path)
            
    except FloodWait as e:
        await asyncio.sleep(e.value)
    except Exception as e:
        if status:
            await status.edit_text(f"❌ Error: {str(e)[:200]}")

@app.on_callback_query(filters.regex(r'^dl_'))
async def dl_video(client, callback):
    try:
        file_id = callback.data.replace('dl_', '')
        v = video_cache.get(file_id)
        if not v or not os.path.exists(v['video_path']):
            await callback.answer("❌ Expired! Send link again.", show_alert=True)
            return
        await callback.message.reply_document(document=v['video_path'], caption=f"📹 Video | 👤 @{v['owner_id']}", file_name=f"video_{file_id}.mp4")
        await callback.answer("✅ Sent!")
    except:
        pass

@app.on_callback_query(filters.regex(r'^au_'))
async def audio_name(client, callback):
    try:
        file_id = callback.data.replace('au_', '')
        v = video_cache.get(file_id)
        if not v:
            await callback.answer("❌ Expired!", show_alert=True)
            return
        user_states[callback.from_user.id] = {'file_id': file_id, 'ts': datetime.now().timestamp()}
        await callback.message.reply_text("🎵 **Audio filename bhejo:**\nExample: my_song")
        await callback.answer()
    except:
        pass

@app.on_message(filters.text & filters.private & ~filters.command(["start"]))
async def get_audio_name(client, message):
    try:
        uid = message.from_user.id
        if uid not in user_states:
            return
        if datetime.now().timestamp() - user_states[uid]['ts'] > 120:
            del user_states[uid]
            await message.reply_text("⏰ Timeout!")
            return
        
        file_id = user_states[uid]['file_id']
        v = video_cache.get(file_id)
        if not v:
            del user_states[uid]
            return
        
        name = message.text.strip().replace(' ', '_')[:50]
        if not name.endswith('.mp3'):
            name += '.mp3'
        
        status = await message.reply_text("🔄 Extracting audio...")
        
        temp = os.path.join(DOWNLOAD_PATH, f"audio_{file_id}")
        opts = {'format': 'bestaudio/best', 'outtmpl': temp, 'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}], 'quiet': True}
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([v['video_url']])
        
        audio_file = temp + '.mp3'
        await status.edit_text("📤 Uploading audio...")
        await client.send_audio(chat_id=message.chat.id, audio=audio_file, caption=f"🎵 {name.replace('.mp3','')}\n👤 @{v['owner_id']}", file_name=name, performer=v['owner_id'], title=name.replace('.mp3',''), duration=v.get('duration', 0))
        
        await status.delete()
        try:
            await message.delete()
        except:
            pass
        try:
            os.remove(audio_file)
        except:
            pass
        del user_states[uid]
    except Exception as e:
        await message.reply_text(f"❌ {str(e)[:100]}")
        if uid in user_states:
            del user_states[uid]

if __name__ == "__main__":
    keep_alive()
    app.run()
