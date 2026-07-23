import logging
import os
import re
import subprocess
import shutil
import time
import json
import urllib.parse
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import yt_dlp
import requests
import asyncio

# ═══════════════════════════
# 🔐 CONFIG
# ═══════════════════════════

BOT_TOKEN = "8518787964:AAHGimBKXfdtrI6UaASGsoI8Aj5Rj_WxF5I"
AUTHORIZED_USERS = [1987818347]

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ═══════════════════════════
# 📥 INSTAGRAM DOWNLOADER
# ═══════════════════════════

class InstaDownloader:
    
    @staticmethod
    def is_instagram_url(text):
        if not text:
            return False
        return bool(re.search(r'(instagram\.com|instagr\.am)/(p|reel|tv)/[a-zA-Z0-9_\-]+', text))
    
    @staticmethod
    def extract_url(text):
        if not text:
            return None
        m = re.search(r'(instagram\.com|instagr\.am)/(p|reel|tv)/([a-zA-Z0-9_\-]+)', text)
        if m:
            return f"https://www.instagram.com/{m.group(2)}/{m.group(3)}/"
        return None
    
    @staticmethod
    def get_shortcode(url):
        m = re.search(r'/(p|reel|tv)/([a-zA-Z0-9_\-]+)', url)
        return m.group(2) if m else None
    
    @staticmethod
    def get_type(url):
        m = re.search(r'/(p|reel|tv)/', url)
        return m.group(1) if m else 'p'
    
    @staticmethod
    def load_cookies():
        """Load cookies from file as string"""
        if not os.path.exists('cookies.txt'):
            return None
        
        cookies = {}
        try:
            with open('cookies.txt', 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    # Netscape format
                    if '\t' in line:
                        parts = line.split('\t')
                        if len(parts) >= 7:
                            cookies[parts[5]] = parts[6]
                    # JSON format
                    elif line.startswith('['):
                        try:
                            cookie_list = json.loads(line)
                            for cookie in cookie_list:
                                cookies[cookie.get('name')] = cookie.get('value')
                        except:
                            pass
            return cookies if cookies else None
        except:
            return None
    
    @staticmethod
    def _download_video(shortcode, url):
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'outtmpl': os.path.join(DOWNLOAD_DIR, f'{shortcode}.%(ext)s'),
                'format': 'best[ext=mp4]/best',
                'retries': 3,
            }
            
            if os.path.exists('cookies.txt'):
                ydl_opts['cookiefile'] = 'cookies.txt'
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                
                file_path = None
                for f in os.listdir(DOWNLOAD_DIR):
                    if shortcode in f and f.endswith('.mp4'):
                        file_path = os.path.join(DOWNLOAD_DIR, f)
                        break
                
                if not file_path:
                    mp4_files = sorted(
                        [f for f in os.listdir(DOWNLOAD_DIR) if f.endswith('.mp4')],
                        key=lambda x: os.path.getmtime(os.path.join(DOWNLOAD_DIR, x)),
                        reverse=True
                    )
                    if mp4_files:
                        file_path = os.path.join(DOWNLOAD_DIR, mp4_files[0])
                
                if file_path and os.path.exists(file_path) and os.path.getsize(file_path) > 5000:
                    return {"success": True, "file_path": file_path, "is_video": True}
                
                return {"success": False, "error": "File not found"}
                
        except Exception as e:
            err = str(e)
            if 'HTTP Error 403' in err or 'HTTP Error 401' in err:
                return {"success": False, "error": "❌ cookies.txt expired! Naya banao."}
            return {"success": False, "error": f"❌ {err[:80]}"}
    
    @staticmethod
    def download_media(url):
        shortcode = InstaDownloader.get_shortcode(url)
        if not shortcode:
            return {"success": False, "error": "Invalid shortcode"}
        
        media_type = InstaDownloader.get_type(url)
        is_reel = media_type in ('reel', 'tv')
        
        if is_reel:
            print(f"🎬 Downloading Reel: {shortcode}")
            return InstaDownloader._download_video(shortcode, url)
        else:
            print(f"📸 Downloading Photos: {shortcode}")
            return InstaDownloader._download_photos(shortcode, url)
    
    @staticmethod
    def _download_photos(shortcode, url):
        """yt-dlp se saari photos download karo - BEST METHOD"""
        
        # Check if cookies.txt exists
        if not os.path.exists('cookies.txt'):
            print("⚠️ No cookies.txt - trying without authentication...")
        
        try:
            # yt-dlp with --extract-audio disabled, just get all images
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'outtmpl': os.path.join(DOWNLOAD_DIR, f'{shortcode}_%(playlist_index)s.%(ext)s'),
                'format': 'best',
                'retries': 5,
                'ignoreerrors': True,
                'no_playlist': False,
                'extract_flat': False,
                'writeinfojson': False,
                'writethumbnail': False,
                'write_all_thumbnails': False,
                'writesubtitles': False,
                'writeautomaticsub': False,
                'postprocessors': [],
            }
            
            if os.path.exists('cookies.txt'):
                ydl_opts['cookiefile'] = 'cookies.txt'
            
            print("📥 Downloading with yt-dlp (getting ALL media)...")
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            # Wait for files
            time.sleep(2)
            
            # Collect all downloaded photo files
            photo_files = []
            video_files = []
            
            for f in sorted(os.listdir(DOWNLOAD_DIR)):
                if shortcode in f:
                    fp = os.path.join(DOWNLOAD_DIR, f)
                    if not os.path.exists(fp) or os.path.getsize(fp) < 1000:
                        continue
                    
                    if f.endswith(('.mp4', '.mov', '.webm')):
                        video_files.append(fp)
                    elif f.endswith(('.jpg', '.jpeg', '.png', '.webp')):
                        photo_files.append(fp)
            
            # Remove video files if this is a photo post
            for vf in video_files:
                try:
                    os.remove(vf)
                    print(f"🗑️ Removed video: {os.path.basename(vf)}")
                except:
                    pass
            
            if photo_files:
                print(f"✅ Found {len(photo_files)} photos")
                
                if len(photo_files) == 1:
                    return {"success": True, "file_path": photo_files[0], "is_video": False}
                else:
                    return {
                        "success": True,
                        "file_paths": sorted(photo_files),
                        "is_video": False,
                        "is_multiple": True,
                        "total_photos": len(photo_files)
                    }
            
            # Fallback: Try without playlist index
            print("⚠️ No files with playlist index, trying single download...")
            ydl_opts2 = {
                'quiet': True,
                'no_warnings': True,
                'outtmpl': os.path.join(DOWNLOAD_DIR, f'{shortcode}.%(ext)s'),
                'format': 'best',
                'retries': 3,
            }
            if os.path.exists('cookies.txt'):
                ydl_opts2['cookiefile'] = 'cookies.txt'
            
            with yt_dlp.YoutubeDL(ydl_opts2) as ydl2:
                ydl2.download([url])
            
            time.sleep(1)
            
            for f in os.listdir(DOWNLOAD_DIR):
                if shortcode in f and not f.endswith(('.mp4', '.mov', '.webm')):
                    fp = os.path.join(DOWNLOAD_DIR, f)
                    if os.path.exists(fp) and os.path.getsize(fp) > 1000:
                        print(f"✅ Single photo: {f}")
                        return {"success": True, "file_path": fp, "is_video": False}
            
            return {"success": False, "error": "No photos found. Cookies.txt required!"}
            
        except Exception as e:
            print(f"❌ Download error: {e}")
            return {"success": False, "error": f"Download failed: {str(e)[:100]}"}
    
    @staticmethod
    def extract_audio(video_path, custom_name=None):
        try:
            if custom_name and custom_name != "skip":
                safe_name = re.sub(r'[^\w\s-]', '', custom_name).strip()[:50] or "Instagram_Audio"
                audio_path = os.path.join(DOWNLOAD_DIR, f"{safe_name}.mp3")
            else:
                base = os.path.splitext(os.path.basename(video_path))[0]
                audio_path = os.path.join(DOWNLOAD_DIR, f"{base}.mp3")
            
            ffmpeg = shutil.which('ffmpeg')
            if not ffmpeg:
                return {"success": False, "error": "FFmpeg not installed!"}
            
            cmd = ['ffmpeg', '-i', video_path, '-vn', '-acodec', 'libmp3lame', '-ab', '192k', '-y', audio_path]
            subprocess.run(cmd, capture_output=True, timeout=180)
            
            if os.path.exists(audio_path) and os.path.getsize(audio_path) > 1000:
                return {"success": True, "file_path": audio_path}
            
            return {"success": False, "error": "Audio extraction failed"}
        except Exception as e:
            return {"success": False, "error": f"Error: {str(e)[:50]}"}
    
    @staticmethod
    def cleanup(file_path):
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
        except:
            pass

# ═══════════════════════════
# 🤖 TELEGRAM HANDLERS
# ═══════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.id
    if user not in AUTHORIZED_USERS:
        return
    
    cookie_status = "✅ Working" if os.path.exists('cookies.txt') else "❌ Missing! Carousel won't work"
    
    await update.message.reply_text(
        f"📥 **Instagram Downloader Bot**\n\n"
        f"🔐 **cookies.txt:** {cookie_status}\n\n"
        "✅ **Reel link** → HD Video + Audio 🎬\n"
        "✅ **Post link** → HD Photos 📸\n"
        "✅ **Carousel** → All photos (cookies needed!) 🔄\n"
        "✅ **Audio button** → MP3 ⚡\n\n"
        "**Sirf link bhejo!** 🔗",
        parse_mode="Markdown"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.id
    if user not in AUTHORIZED_USERS:
        return
    
    text = update.message.text
    if not text:
        return
    
    if context.user_data.get('awaiting_audio'):
        context.user_data['awaiting_audio'] = False
        audio_name = text.strip()
        url = context.user_data.get('current_url')
        if url:
            await extract_and_send_audio(update, context, url, audio_name)
        return
    
    if not InstaDownloader.is_instagram_url(text):
        return
    
    url = InstaDownloader.extract_url(text)
    if not url:
        await update.message.reply_text("❌ Could not extract URL")
        return
    
    context.user_data['current_url'] = url
    
    msg = await update.message.reply_text("⏳ **Processing...**", parse_mode="Markdown")
    
    try:
        is_reel = '/reel/' in url or '/tv/' in url
        
        await msg.edit_text("📥 **Downloading...**")
        
        result = InstaDownloader.download_media(url)
        
        if not result.get("success"):
            error = result.get('error', 'Unknown error')
            
            # Specific guidance for cookies
            if 'cookies' in error.lower() or 'login' in error.lower():
                await msg.edit_text(
                    f"❌ **cookies.txt CHAHIYE!**\n\n"
                    f"📌 **Carousel/Album posts ke liye cookies.txt zaroori hai**\n\n"
                    f"**Kaise banaye:**\n"
                    f"1. Chrome mein 'EditThisCookie' extension install karo\n"
                    f"2. Instagram.com pe login karo\n"
                    f"3. Extension se cookies export karo\n"
                    f"4. File ka naam 'cookies.txt' rakho\n"
                    f"5. Bot ke folder mein daalo\n\n"
                    f"Error: {error}",
                    parse_mode="Markdown"
                )
            else:
                await msg.edit_text(f"❌ **Failed!**\n\n{error}", parse_mode="Markdown")
            return
        
        # Multiple photos
        if result.get("is_multiple"):
            photo_paths = result.get("file_paths", [])
            total = result.get("total_photos", len(photo_paths))
            
            await msg.edit_text(f"📤 **{total} Photos uploading...**")
            
            for i, fp in enumerate(photo_paths, 1):
                if os.path.exists(fp) and os.path.getsize(fp) > 1000:
                    try:
                        with open(fp, 'rb') as f:
                            caption = f"✅ **Photo {i}/{total}**"
                            if i == 1:
                                caption += f"\n🔗 [Instagram Post]({url})"
                            
                            await update.message.reply_photo(
                                photo=f,
                                caption=caption,
                                parse_mode="Markdown"
                            )
                        
                        if i < total:
                            await asyncio.sleep(0.3)
                    except Exception as e:
                        await update.message.reply_text(f"❌ Photo {i}: {str(e)[:50]}")
                    
                    InstaDownloader.cleanup(fp)
            
            try:
                await msg.edit_text(f"✅ **{total} Photos sent!** 🔥")
                await asyncio.sleep(2)
                await msg.delete()
            except:
                pass
            return
        
        # Single file
        fp = result["file_path"]
        if not os.path.exists(fp) or os.path.getsize(fp) < 1000:
            await msg.edit_text("❌ File not found")
            return
        
        size_mb = os.path.getsize(fp) / (1024 * 1024)
        if size_mb > 50:
            await msg.edit_text(f"❌ File >50MB ({size_mb:.1f}MB)")
            InstaDownloader.cleanup(fp)
            return
        
        is_video = result.get("is_video", False) or fp.endswith(('.mp4', '.mov', '.webm'))
        
        if is_video:
            await msg.edit_text("📤 **Uploading Video...**")
            keyboard = [[InlineKeyboardButton("🎵 Download Audio", callback_data="get_audio")]]
            
            with open(fp, 'rb') as f:
                await update.message.reply_video(
                    video=f,
                    caption=f"✅ **Video Downloaded** ✅\n🔗 [Link]({url})",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    supports_streaming=True
                )
        else:
            await msg.edit_text("📤 **Uploading Photo...**")
            with open(fp, 'rb') as f:
                await update.message.reply_photo(
                    photo=f,
                    caption=f"✅ **Photo Downloaded** ✅\n🔗 [Link]({url})",
                    parse_mode="Markdown"
                )
        
        await msg.delete()
        InstaDownloader.cleanup(fp)
        
    except Exception as e:
        await msg.edit_text(f"❌ **Error:** {str(e)[:100]}")
        for f in os.listdir(DOWNLOAD_DIR):
            try: os.remove(os.path.join(DOWNLOAD_DIR, f))
            except: pass

async def extract_and_send_audio(update, context, url, audio_name):
    status_msg = await update.message.reply_text(f"🎵 **Extracting: {audio_name}...**", parse_mode="Markdown")
    
    try:
        result = InstaDownloader.download_media(url)
        if not result.get("success"):
            await status_msg.edit_text("❌ Download failed")
            return
        
        if result.get("is_multiple"):
            vp = result["file_paths"][0] if result["file_paths"] else None
        else:
            vp = result["file_path"]
        
        if not vp or not os.path.exists(vp):
            await status_msg.edit_text("❌ Video file not found")
            return
        
        audio_result = InstaDownloader.extract_audio(vp, audio_name)
        
        if audio_result.get("success"):
            ap = audio_result["file_path"]
            await status_msg.edit_text("📤 **Uploading Audio...**")
            
            with open(ap, 'rb') as f:
                await update.message.reply_audio(
                    audio=f, title=audio_name, performer="Instagram",
                    caption=f"🎵 **{audio_name}** ✅"
                )
            
            await status_msg.edit_text(f"✅ **{audio_name} sent!** 🎵")
            try: os.remove(ap)
            except: pass
        else:
            await status_msg.edit_text(f"❌ {audio_result.get('error', 'Failed')}")
        
        InstaDownloader.cleanup(vp)
    except Exception as e:
        await status_msg.edit_text(f"❌ Error: {str(e)[:80]}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "get_audio":
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            "🎵 **Audio ka naam likhein:**\n\n"
            "Jaise: `Meri Song`\n"
            "Ya: `skip` for default\n\n"
            "⬇️ Type karo:",
            parse_mode="Markdown"
        )
        context.user_data['awaiting_audio'] = True

# ═══════════════════════════
# 🚀 MAIN
# ═══════════════════════════

def main():
    logging.basicConfig(level=logging.INFO)
    
    print("╔══════════════════════════╗")
    print("║  🤖 INSTAGRAM BOT       ║")
    print("╚══════════════════════════╝")
    
    # FFmpeg
    if not shutil.which('ffmpeg'):
        print("⚠️ Installing FFmpeg...")
        os.system('apt-get update && apt-get install ffmpeg -y 2>/dev/null')
    print(f"✅ FFmpeg: {shutil.which('ffmpeg')}")
    
    # Cookies
    if os.path.exists('cookies.txt'):
        print(f"✅ cookies.txt found ({os.path.getsize('cookies.txt')} bytes)")
    else:
        print("⚠️ NO cookies.txt! Carousel/Album posts won't work!")
        print("📌 Create cookies.txt for full functionality")
    
    # Clean
    for f in os.listdir(DOWNLOAD_DIR):
        try: os.remove(os.path.join(DOWNLOAD_DIR, f))
        except: pass
    
    print("✅ Bot Started!")
    print("📸 With cookies.txt: ALL photos (including carousel)")
    print("📸 Without cookies.txt: Only first photo")
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    app.run_polling()

if __name__ == "__main__":
    main()
