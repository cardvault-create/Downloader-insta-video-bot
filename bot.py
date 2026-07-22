import logging
import os 
import re
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import yt_dlp
import subprocess

# ═══════════════════════════════════
# 🔐 CONFIG — YAHI APNI VALUES DALO
# ═══════════════════════════════════

BOT_TOKEN = "8518787964:AAHGimBKXfdtrI6UaASGsoI8Aj5Rj_WxF5I"     # ← @BotFather se lo
AUTHORIZED_USERS = [1987818347]        # ← Apna Telegram ID

# Download folder
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ═══════════════════════════════════
# 📥 DOWNLOAD ENGINE
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
    def download_video(url):
        """Download video from Instagram"""
        try:
            output = os.path.join(DOWNLOAD_DIR, '%(id)s.%(ext)s')
            
            ydl_opts = {
                'outtmpl': output,
                'format': 'best[ext=mp4]/best',
                'quiet': True,
                'no_warnings': True,
                'ignoreerrors': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info:
                    return {"success": False, "error": "No info extracted"}
                
                file_id = info.get('id', 'unknown')
                ext = 'mp4'
                file_path = os.path.join(DOWNLOAD_DIR, f"{file_id}.{ext}")
                
                # Agar file nahi mili to search karo
                if not os.path.exists(file_path):
                    for f in os.listdir(DOWNLOAD_DIR):
                        if file_id in f:
                            file_path = os.path.join(DOWNLOAD_DIR, f)
                            break
                
                return {
                    "success": True,
                    "file_path": file_path,
                    "title": info.get('title', 'Instagram'),
                    "is_video": True,
                }
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def download_photo(url):
        """Download photo from Instagram"""
        try:
            output = os.path.join(DOWNLOAD_DIR, '%(id)s.%(ext)s')
            
            ydl_opts = {
                'outtmpl': output,
                'format': 'best',
                'quiet': True,
                'no_warnings': True,
                'ignoreerrors': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info:
                    return {"success": False, "error": "No info extracted"}
                
                file_id = info.get('id', 'unknown')
                ext = 'jpg'
                file_path = os.path.join(DOWNLOAD_DIR, f"{file_id}.{ext}")
                
                if not os.path.exists(file_path):
                    for f in os.listdir(DOWNLOAD_DIR):
                        if file_id in f:
                            file_path = os.path.join(DOWNLOAD_DIR, f)
                            break
                
                return {
                    "success": True,
                    "file_path": file_path,
                    "title": info.get('title', 'Instagram'),
                    "is_video": False,
                    "is_photo": True,
                }
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def extract_audio(video_path):
        """Extract audio from video using FFmpeg"""
        try:
            audio_path = video_path.rsplit('.', 1)[0] + '.mp3'
            
            cmd = [
                'ffmpeg', '-i', video_path,
                '-vn', '-acodec', 'libmp3lame',
                '-ab', '192k',
                '-y', audio_path
            ]
            
            subprocess.run(cmd, capture_output=True, timeout=60)
            
            if os.path.exists(audio_path):
                return {"success": True, "file_path": audio_path}
            else:
                return {"success": False, "error": "Audio extraction failed"}
                
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @staticmethod
    def check_if_video(url):
        """Check if Instagram post is video or photo"""
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                return info.get('is_video', False) or info.get('ext', '') in ['mp4', 'mov']
        except:
            return True  # Default to video if can't determine
    
    @staticmethod
    def cleanup(file_path):
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
            # Also remove audio file if exists
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
        "✅ Sirf Instagram ka link bhejo\n"
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
    
    # Check if Instagram link
    if not InstaDownloader.is_instagram_url(text):
        return  # Ignore non-Instagram messages
    
    url = InstaDownloader.extract_url(text)
    if not url:
        await update.message.reply_text("❌ Invalid Instagram URL")
        return
    
    msg = await update.message.reply_text("⏳ Downloading... Please wait")
    
    # Step 1: Check if video or photo
    is_video = InstaDownloader.check_if_video(url)
    
    if is_video:
        # ─── VIDEO DOWNLOAD ───
        result = InstaDownloader.download_video(url)
        
        if not result.get("success"):
            await msg.edit_text(f"❌ Download failed: {result.get('error', 'Unknown error')}")
            return
        
        file_path = result["file_path"]
        
        # Check file size (Telegram limit ~50MB)
        file_size = os.path.getsize(file_path) if os.path.exists(file_path) else 0
        if file_size > 50 * 1024 * 1024:
            await msg.edit_text("❌ File too large (>50MB)")
            InstaDownloader.cleanup(file_path)
            return
        
        # Send video with audio button
        keyboard = [[InlineKeyboardButton("🎵 Download Audio", callback_data=f"audio_{url}")]]
        
        try:
            with open(file_path, 'rb') as f:
                await update.message.reply_video(
                    video=f,
                    caption=f"✅ Downloaded ✅\n\n🔗 [Instagram Link]({url})",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    supports_streaming=True
                )
            await msg.delete()
        except Exception as e:
            await msg.edit_text(f"❌ Error sending: {str(e)}")
        
        InstaDownloader.cleanup(file_path)
        
    else:
        # ─── PHOTO DOWNLOAD ───
        result = InstaDownloader.download_photo(url)
        
        if not result.get("success"):
            await msg.edit_text(f"❌ Download failed: {result.get('error', 'Unknown error')}")
            return
        
        file_path = result["file_path"]
        
        try:
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
    """Handle Download Audio button click"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data.startswith("audio_"):
        url = data.replace("audio_", "")
        
        await query.edit_message_reply_markup(reply_markup=None)
        status_msg = await query.message.reply_text("🎵 Extracting audio... Please wait")
        
        # Pehle video download karo (audio extract karne ke liye)
        vid_result = InstaDownloader.download_video(url)
        
        if not vid_result.get("success"):
            await status_msg.edit_text(f"❌ Audio extraction failed: {vid_result.get('error')}")
            return
        
        video_path = vid_result["file_path"]
        
        # Audio extract karo
        audio_result = InstaDownloader.extract_audio(video_path)
        
        if audio_result.get("success"):
            audio_path = audio_result["file_path"]
            
            try:
                with open(audio_path, 'rb') as f:
                    await query.message.reply_audio(
                        audio=f,
                        title="Instagram Audio",
                        performer="Instagram",
                        caption=f"🎵 Audio extracted\n\n🔗 [Original]({url})",
                        parse_mode="Markdown"
                    )
                await status_msg.edit_text("✅ Audio sent successfully! 🎵")
            except Exception as e:
                await status_msg.edit_text(f"❌ Error sending audio: {str(e)}")
            
            # Cleanup audio file
            try:
                os.remove(audio_path)
            except:
                pass
        else:
            await status_msg.edit_text(f"❌ Failed: {audio_result.get('error')}")
        
        # Cleanup video file
        InstaDownloader.cleanup(video_path)

# ═══════════════════════════════════
# 🚀 MAIN
# ═══════════════════════════════════

def main():
    logging.basicConfig(level=logging.INFO)
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    print("✅ Bot Started!")
    print("📥 Instagram Downloader Bot is running...")
    print(f"👥 Authorized users: {AUTHORIZED_USERS}")
    
    app.run_polling()

if __name__ == "__main__":
    main()
