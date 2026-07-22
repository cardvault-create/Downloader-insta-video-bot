import logging
import os
import re
import asyncio
import subprocess
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import yt_dlp
import browser_cookie3

# ═══════════════════════════════════
# 🔐 CONFIG
# ═══════════════════════════════════

BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
AUTHORIZED_USERS = [123456789]

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ═══════════════════════════════════
# 📥 FIXED DOWNLOAD ENGINE
# ═══════════════════════════════════

class InstaDownloader:
    @staticmethod
    def is_instagram_url(text):
        patterns = [
            r'(https?://)?(www\.)?instagram\.com/(p|reel|tv|stories|s)/[a-zA-Z0-9_\-]+',
            r'(https?://)?(www\.)?instagr\.am/(p|reel|tv)/[a-zA-Z0-9_\-]+',
        ]
        return any(re.search(p, text) for p in patterns)
    
    @staticmethod
    def extract_url(text):
        patterns = [
            r'(https?://)?(www\.)?instagram\.com/(p|reel|tv|stories|s)/[a-zA-Z0-9_\-]+/?',
            r'(https?://)?(www\.)?instagr\.am/(p|reel|tv)/[a-zA-Z0-9_\-]+/?',
        ]
        for p in patterns:
            m = re.search(p, text)
            if m:
                url = m.group(0)
                if not url.startswith('http'):
                    url = 'https://' + url
                return url
        return None
    
    @staticmethod
    def get_ydl_opts(download=True):
        """Get yt-dlp options with cookies support"""
        opts = {
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
            'extract_flat': False,
        }
        
        # Try to load cookies from browser
        try:
            # Load cookies from Chrome/Chromium
            cookies = browser_cookie3.chrome(domain_name='.instagram.com')
            opts['cookiefile'] = cookies
        except:
            pass
        
        # Try loading cookies.txt if exists
        if os.path.exists('cookies.txt'):
            opts['cookiefile'] = 'cookies.txt'
        
        if download:
            opts['outtmpl'] = os.path.join(DOWNLOAD_DIR, '%(id)s.%(ext)s')
        
        return opts
    
    @staticmethod
    def download_media(url):
        """Universal download - video or photo"""
        try:
            ydl_opts = InstaDownloader.get_ydl_opts(download=True)
            
            # Try with format best first
            ydl_opts['format'] = 'best[ext=mp4]/best'
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                
                if not info:
                    return {"success": False, "error": "No info extracted"}
                
                # Get file path
                file_id = info.get('id', 'unknown')
                ext = info.get('ext', 'mp4')
                
                # If it's a video, use mp4
                if info.get('is_video') or info.get('ext') in ['mp4', 'mov']:
                    ext = 'mp4'
                    is_video = True
                else:
                    # Photo - try jpg
                    is_video = False
                    ext = 'jpg'
                
                file_path = os.path.join(DOWNLOAD_DIR, f"{file_id}.{ext}")
                
                # Find the actual file
                if not os.path.exists(file_path):
                    for f in os.listdir(DOWNLOAD_DIR):
                        if file_id in f:
                            file_path = os.path.join(DOWNLOAD_DIR, f)
                            break
                    else:
                        # Check if there are entries (carousel)
                        entries = info.get('entries', [])
                        if entries and len(entries) > 0:
                            first = entries[0]
                            fid = first.get('id', file_id)
                            for f in os.listdir(DOWNLOAD_DIR):
                                if fid in f:
                                    file_path = os.path.join(DOWNLOAD_DIR, f)
                                    is_video = first.get('is_video', False)
                                    break
                
                return {
                    "success": True,
                    "file_path": file_path,
                    "is_video": is_video,
                    "title": info.get('title', 'Instagram'),
                }
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def extract_audio(video_path):
        """Extract audio using FFmpeg"""
        try:
            audio_path = video_path.rsplit('.', 1)[0] + '.mp3'
            
            cmd = [
                'ffmpeg', '-i', video_path,
                '-vn', '-acodec', 'libmp3lame',
                '-ab', '192k', '-y', audio_path
            ]
            
            subprocess.run(cmd, capture_output=True, timeout=120)
            
            if os.path.exists(audio_path):
                return {"success": True, "file_path": audio_path}
            return {"success": False, "error": "Audio file not created"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def get_info(url):
        """Get media info without downloading"""
        try:
            ydl_opts = InstaDownloader.get_ydl_opts(download=False)
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return info
        except:
            return None
    
    @staticmethod
    def cleanup(file_path):
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
            audio_path = file_path.rsplit('.', 1)[0] + '.mp3'
            if os.path.exists(audio_path):
                os.remove(audio_path)
        except:
            pass

# ═══════════════════════════════════
# 🤖 TELEGRAM HANDLERS
# ═══════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.id
    if user not in AUTHORIZED_USERS:
        await update.message.reply_text("❌ Unauthorized")
        return
    
    await update.message.reply_text(
        "📥 **Instagram Downloader Bot**\n\n"
        "✅ Sirf Instagram link bhejo\n"
        "✅ Video ho to video bhejunga\n"
        "✅ Photo ho to photo bhejunga\n"
        "✅ Video ke saath \"Download Audio\" button hoga\n\n"
        "**Example:**\n"
        "`https://www.instagram.com/reel/xyz123/`\n"
        "`https://www.instagram.com/p/xyz123/`",
        parse_mode="Markdown"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.id
    if user not in AUTHORIZED_USERS:
        return
    
    text = update.message.text
    if not text:
        return
    
    if not InstaDownloader.is_instagram_url(text):
        return
    
    url = InstaDownloader.extract_url(text)
    if not url:
        await update.message.reply_text("❌ Invalid Instagram URL")
        return
    
    msg = await update.message.reply_text("⏳ Downloading... Please wait")
    
    # Download media
    result = InstaDownloader.download_media(url)
    
    if not result.get("success"):
        # Try alternative method - use yt-dlp directly with subprocess
        await msg.edit_text("⏳ Trying alternative method...")
        
        try:
            output = os.path.join(DOWNLOAD_DIR, '%(id)s.%(ext)s')
            cmd = [
                'yt-dlp', 
                '-o', output,
                '--format', 'best[ext=mp4]/best',
                '--no-warnings',
                '--ignore-errors',
                url
            ]
            
            subprocess.run(cmd, capture_output=True, timeout=120)
            
            # Find the downloaded file
            files = [f for f in os.listdir(DOWNLOAD_DIR) if not f.startswith('.')]
            files.sort(key=lambda x: os.path.getctime(os.path.join(DOWNLOAD_DIR, x)), reverse=True)
            
            if files:
                file_path = os.path.join(DOWNLOAD_DIR, files[0])
                result = {
                    "success": True,
                    "file_path": file_path,
                    "is_video": file_path.endswith(('.mp4', '.mov', '.webm')),
                }
            else:
                await msg.edit_text(f"❌ Download failed: {result.get('error', 'Unknown error')}")
                return
        except Exception as e:
            await msg.edit_text(f"❌ Download failed: {str(e)}")
            return
    
    file_path = result["file_path"]
    
    if not os.path.exists(file_path):
        await msg.edit_text("❌ File not found after download")
        return
    
    file_size = os.path.getsize(file_path)
    if file_size > 50 * 1024 * 1024:
        await msg.edit_text("❌ File too large (>50MB)")
        InstaDownloader.cleanup(file_path)
        return
    
    is_video = result.get("is_video", False) or file_path.endswith(('.mp4', '.mov', '.webm', '.mkv'))
    
    try:
        if is_video:
            keyboard = [[InlineKeyboardButton("🎵 Download Audio", callback_data=f"audio_{url}")]]
            
            with open(file_path, 'rb') as f:
                await update.message.reply_video(
                    video=f,
                    caption=f"✅ Downloaded ✅\n\n🔗 [Instagram Link]({url})",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    supports_streaming=True
                )
        else:
            with open(file_path, 'rb') as f:
                await update.message.reply_photo(
                    photo=f,
                    caption=f"✅ Downloaded ✅\n\n🔗 [Instagram Link]({url})",
                    parse_mode="Markdown"
                )
        
        await msg.delete()
    except Exception as e:
        await msg.edit_text(f"❌ Error sending: {str(e)}")
    
    InstaDownloader.cleanup(file_path)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if data.startswith("audio_"):
        url = data.replace("audio_", "")
        
        await query.edit_message_reply_markup(reply_markup=None)
        status_msg = await query.message.reply_text("🎵 Extracting audio...")
        
        # Download video first
        result = InstaDownloader.download_media(url)
        
        if not result.get("success"):
            await status_msg.edit_text("❌ Audio failed: Could not download video")
            return
        
        video_path = result["file_path"]
        
        # Extract audio
        audio_result = InstaDownloader.extract_audio(video_path)
        
        if audio_result.get("success"):
            audio_path = audio_result["file_path"]
            
            with open(audio_path, 'rb') as f:
                await query.message.reply_audio(
                    audio=f,
                    title="Instagram Audio",
                    performer="Instagram",
                    caption=f"🎵 Audio extracted\n\n🔗 [Original]({url})",
                    parse_mode="Markdown"
                )
            await status_msg.edit_text("✅ Audio sent! 🎵")
            
            try: os.remove(audio_path)
            except: pass
        else:
            await status_msg.edit_text(f"❌ Audio failed: {audio_result.get('error')}")
        
        InstaDownloader.cleanup(video_path)

# ═══════════════════════════════════
# 🚀 MAIN
# ═══════════════════════════════════

def main():
    logging.basicConfig(level=logging.INFO)
    
    print("✅ Bot Started!")
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    app.run_polling()

if __name__ == "__main__":
    main()
