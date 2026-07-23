import logging
import os
import re
import subprocess
import shutil
import time
import json
import sys
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import yt_dlp
import asyncio

# ═══════════════════════════
# 🔐 CONFIG
# ═══════════════════════════

BOT_TOKEN = "8518787964:AAHGimBKXfdtrI6UaASGsoI8Aj5Rj_WxF5I"
AUTHORIZED_USERS = [1987818347]

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Enable yt-dlp verbose logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot_debug.log')
    ]
)
logger = logging.getLogger(__name__)

# ═══════════════════════════
# 📥 INSTAGRAM DOWNLOADER
# ═══════════════════════════

class InstaDownloader:
    
    @staticmethod
    def is_instagram_url(text):
        return bool(re.search(r'(instagram\.com|instagr\.am)/(p|reel|tv)/[a-zA-Z0-9_\-]+', text or ''))
    
    @staticmethod
    def extract_url(text):
        m = re.search(r'(instagram\.com|instagr\.am)/(p|reel|tv)/([a-zA-Z0-9_\-]+)', text or '')
        return f"https://www.instagram.com/{m.group(2)}/{m.group(3)}/" if m else None
    
    @staticmethod
    def get_shortcode(url):
        m = re.search(r'/(p|reel|tv)/([a-zA-Z0-9_\-]+)', url)
        return m.group(2) if m else None
    
    @staticmethod
    def download_media(url):
        shortcode = InstaDownloader.get_shortcode(url)
        if not shortcode:
            return {"success": False, "error": "Invalid URL"}
        
        is_reel = '/reel/' in url or '/tv/' in url
        
        # Clean old files
        for f in list(os.listdir(DOWNLOAD_DIR)):
            if shortcode in f:
                try: os.remove(os.path.join(DOWNLOAD_DIR, f))
                except: pass
        
        # Check cookies
        if not os.path.exists('cookies.txt'):
            return {"success": False, "error": "❌ cookies.txt not found!"}
        
        # Verify cookies have sessionid
        with open('cookies.txt', 'r') as f:
            cookie_content = f.read()
            if 'sessionid' not in cookie_content:
                return {"success": False, "error": "❌ cookies.txt has NO sessionid!"}
        
        logger.info(f"Downloading: {shortcode} (Reel: {is_reel})")
        
        try:
            if is_reel:
                return InstaDownloader._download_reel(shortcode, url)
            else:
                return InstaDownloader._download_post(shortcode, url)
                
        except Exception as e:
            logger.error(f"Download error: {e}")
            return {"success": False, "error": f"Error: {str(e)[:200]}"}
    
    @staticmethod
    def _download_reel(shortcode, url):
        """Download reel with verbose logging"""
        ydl_opts = {
            'outtmpl': os.path.join(DOWNLOAD_DIR, f'{shortcode}.%(ext)s'),
            'format': 'best[ext=mp4]/best',
            'cookiefile': 'cookies.txt',
            'retries': 3,
            'quiet': False,
            'no_warnings': False,
            'verbose': True,
            'progress_hooks': [lambda d: logger.debug(f"Progress: {d.get('status')} - {d.get('filename', 'N/A')}")],
        }
        
        try:
            logger.info(f"Downloading reel: {url}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                logger.info(f"Download complete: {info.get('title', 'N/A')}")
            
            time.sleep(1)
            for f in os.listdir(DOWNLOAD_DIR):
                if shortcode in f and f.endswith('.mp4'):
                    fp = os.path.join(DOWNLOAD_DIR, f)
                    if os.path.getsize(fp) > 5000:
                        logger.info(f"✅ Reel: {f}")
                        return {"success": True, "file_path": fp, "is_video": True}
            
            return {"success": False, "error": "Reel file not found after download"}
            
        except Exception as e:
            logger.error(f"Reel error: {e}")
            return {"success": False, "error": f"Reel: {str(e)[:150]}"}
    
    @staticmethod
    def _download_post(shortcode, url):
        """Download post photos with verbose logging"""
        
        # First attempt: With playlist (for carousel)
        ydl_opts = {
            'outtmpl': os.path.join(DOWNLOAD_DIR, f'{shortcode}_%(playlist_index)s.%(ext)s'),
            'format': 'best[ext=jpg]/best[ext=png]/best[ext=webp]/best',
            'cookiefile': 'cookies.txt',
            'retries': 5,
            'ignoreerrors': True,
            'no_playlist': False,
            'quiet': False,
            'no_warnings': False,
            'verbose': True,
            'progress_hooks': [lambda d: logger.debug(f"Progress: {d.get('status')} - {d.get('filename', 'N/A')}")],
            'logger': logger,
        }
        
        try:
            logger.info(f"Attempt 1: Downloading with playlist mode...")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            time.sleep(2)
            
            # Collect photos
            photos = []
            for f in sorted(os.listdir(DOWNLOAD_DIR)):
                if shortcode in f and not f.endswith(('.mp4', '.mov', '.webm', '.part', '.ytdl')):
                    fp = os.path.join(DOWNLOAD_DIR, f)
                    if os.path.exists(fp) and os.path.getsize(fp) > 1000:
                        photos.append(fp)
                        logger.info(f"  Found: {f} ({os.path.getsize(fp)} bytes)")
            
            if photos:
                # Remove duplicates
                unique = []
                sizes = set()
                for fp in photos:
                    s = os.path.getsize(fp)
                    if s not in sizes:
                        sizes.add(s)
                        unique.append(fp)
                    else:
                        os.remove(fp)
                        logger.debug(f"  Removed duplicate: {fp}")
                
                logger.info(f"✅ Total unique photos: {len(unique)}")
                
                if len(unique) == 1:
                    return {"success": True, "file_path": unique[0], "is_video": False}
                else:
                    return {
                        "success": True,
                        "file_paths": sorted(unique),
                        "is_video": False,
                        "is_multiple": True,
                        "total": len(unique)
                    }
            
            logger.warning("No photos found in first attempt, trying fallback...")
            
        except Exception as e:
            logger.error(f"Attempt 1 failed: {e}")
        
        # Fallback: Without playlist index
        logger.info("Attempt 2: Simple download...")
        
        ydl_opts2 = {
            'outtmpl': os.path.join(DOWNLOAD_DIR, f'{shortcode}.%(ext)s'),
            'format': 'best[ext=jpg]/best[ext=png]/best[ext=webp]/best',
            'cookiefile': 'cookies.txt',
            'retries': 5,
            'quiet': False,
            'no_warnings': False,
            'verbose': True,
            'progress_hooks': [lambda d: logger.debug(f"Progress: {d.get('status')} - {d.get('filename', 'N/A')}")],
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts2) as ydl:
                ydl.download([url])
            
            time.sleep(2)
            
            photos = []
            for f in sorted(os.listdir(DOWNLOAD_DIR)):
                if shortcode in f and not f.endswith(('.mp4', '.mov', '.webm', '.part', '.ytdl')):
                    fp = os.path.join(DOWNLOAD_DIR, f)
                    if os.path.exists(fp) and os.path.getsize(fp) > 1000:
                        photos.append(fp)
                        logger.info(f"  Found: {f} ({os.path.getsize(fp)} bytes)")
            
            if photos:
                logger.info(f"✅ Fallback found {len(photos)} photos")
                if len(photos) == 1:
                    return {"success": True, "file_path": photos[0], "is_video": False}
                else:
                    return {
                        "success": True,
                        "file_paths": sorted(photos),
                        "is_video": False,
                        "is_multiple": True,
                        "total": len(photos)
                    }
            
            logger.error("No photos found in both attempts!")
            
            # Check downloads folder
            all_files = os.listdir(DOWNLOAD_DIR)
            logger.debug(f"All files in downloads: {all_files}")
            
            return {"success": False, "error": f"No photos found. Downloads folder has {len(all_files)} files. Check bot_debug.log"}
            
        except Exception as e:
            logger.error(f"Fallback error: {e}")
            return {"success": False, "error": f"Download error: {str(e)[:200]}"}
    
    @staticmethod
    def extract_audio(video_path, name=None):
        try:
            if name and name != "skip":
                safe = re.sub(r'[^\w\s-]', '', name).strip()[:50] or "Audio"
                apath = os.path.join(DOWNLOAD_DIR, f"{safe}.mp3")
            else:
                apath = os.path.join(DOWNLOAD_DIR, f"{os.path.splitext(os.path.basename(video_path))[0]}.mp3")
            
            ffmpeg = shutil.which('ffmpeg')
            if not ffmpeg:
                return {"success": False, "error": "FFmpeg not found"}
            
            result = subprocess.run(
                ['ffmpeg', '-i', video_path, '-vn', '-acodec', 'libmp3lame', '-ab', '192k', '-y', apath],
                capture_output=True, text=True, timeout=180
            )
            
            if os.path.exists(apath) and os.path.getsize(apath) > 1000:
                return {"success": True, "file_path": apath}
            
            return {"success": False, "error": f"FFmpeg: {result.stderr[:100]}"}
        except Exception as e:
            return {"success": False, "error": str(e)[:50]}
    
    @staticmethod
    def cleanup(fp):
        try:
            if fp and os.path.exists(fp):
                os.remove(fp)
        except:
            pass

# ═══════════════════════════
# 🤖 TELEGRAM HANDLERS
# ═══════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in AUTHORIZED_USERS:
        return
    
    has_cookies = "✅ Found" if os.path.exists('cookies.txt') else "❌ Missing!"
    
    await update.message.reply_text(
        f"📥 **Instagram Downloader Bot v5**\n\n"
        f"🔐 **cookies.txt:** {has_cookies}\n\n"
        f"✅ **Reel** → HD Video 🎬\n"
        f"✅ **Post** → ALL Photos 📸\n"
        f"✅ **Carousel** → 1-by-1 photos 🔄\n"
        f"✅ **Audio** → MP3 ⚡\n\n"
        f"🔍 **Debug log:** bot_debug.log",
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
        url = context.user_data.get('current_url')
        if url:
            await extract_audio_handler(update, context, url, text.strip())
        return
    
    if not InstaDownloader.is_instagram_url(text):
        return
    
    url = InstaDownloader.extract_url(text)
    if not url:
        return
    
    context.user_data['current_url'] = url
    msg = await update.message.reply_text("⏳ **Processing...**\n🔍 Check bot_debug.log for details", parse_mode="Markdown")
    
    try:
        logger.info(f"Processing URL: {url}")
        result = InstaDownloader.download_media(url)
        
        if not result.get("success"):
            error = result.get('error', 'Unknown')
            logger.error(f"Failed: {error}")
            await msg.edit_text(
                f"❌ **Failed!**\n\n{error}\n\n"
                f"📝 **Debug info:** Check `bot_debug.log` file",
                parse_mode="Markdown"
            )
            return
        
        # Multiple photos
        if result.get("is_multiple"):
            photos = result["file_paths"]
            total = result.get("total", len(photos))
            
            logger.info(f"Sending {total} photos")
            await msg.edit_text(f"📤 **{total} Photos bhej raha hun...**")
            
            for i, fp in enumerate(photos, 1):
                if os.path.exists(fp):
                    try:
                        with open(fp, 'rb') as f:
                            caption = f"✅ **Photo {i}/{total}**"
                            if i == 1:
                                caption += f"\n🔗 [Post Link]({url})"
                            await update.message.reply_photo(photo=f, caption=caption, parse_mode="Markdown")
                            logger.info(f"Sent photo {i}/{total}")
                        
                        if i < total:
                            await asyncio.sleep(0.3)
                    except Exception as e:
                        logger.error(f"Photo {i} send error: {e}")
                        await update.message.reply_text(f"❌ Photo {i}: {str(e)[:50]}")
                    InstaDownloader.cleanup(fp)
            
            await msg.edit_text(f"✅ **{total} Photos sent!** 🔥")
            return
        
        # Single file
        fp = result["file_path"]
        if not os.path.exists(fp):
            await msg.edit_text("❌ File not found")
            return
        
        size_mb = os.path.getsize(fp) / (1024*1024)
        if size_mb > 50:
            await msg.edit_text(f"❌ {size_mb:.1f}MB > 50MB limit")
            InstaDownloader.cleanup(fp)
            return
        
        is_video = result.get("is_video", False) or fp.endswith(('.mp4', '.mov', '.webm'))
        
        if is_video:
            logger.info(f"Uploading video: {fp}")
            await msg.edit_text("📤 **Uploading Video...**")
            kb = [[InlineKeyboardButton("🎵 Download Audio", callback_data="get_audio")]]
            with open(fp, 'rb') as f:
                await update.message.reply_video(video=f, caption=f"✅ Done\n🔗 [Link]({url})",
                    parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb), supports_streaming=True)
        else:
            logger.info(f"Uploading photo: {fp}")
            await msg.edit_text("📤 **Uploading Photo...**")
            with open(fp, 'rb') as f:
                await update.message.reply_photo(photo=f, caption=f"✅ Done\n🔗 [Link]({url})", parse_mode="Markdown")
        
        await msg.delete()
        InstaDownloader.cleanup(fp)
        
    except Exception as e:
        logger.error(f"Handler error: {e}", exc_info=True)
        await msg.edit_text(f"❌ **Error:** {str(e)[:100]}")

async def extract_audio_handler(update, context, url, name):
    msg = await update.message.reply_text(f"🎵 **{name}...**", parse_mode="Markdown")
    try:
        result = InstaDownloader.download_media(url)
        if not result.get("success"):
            await msg.edit_text("❌ Failed")
            return
        
        vp = result["file_paths"][0] if result.get("is_multiple") else result["file_path"]
        ar = InstaDownloader.extract_audio(vp, name)
        
        if ar.get("success"):
            await msg.edit_text("📤 **Uploading...**")
            with open(ar["file_path"], 'rb') as f:
                await update.message.reply_audio(audio=f, title=name, performer="Instagram", caption=f"🎵 {name}")
            await msg.edit_text(f"✅ **{name} sent!**")
            os.remove(ar["file_path"])
        else:
            await msg.edit_text(f"❌ {ar.get('error')}")
        InstaDownloader.cleanup(vp)
    except Exception as e:
        await msg.edit_text(f"❌ {str(e)[:80]}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "get_audio":
        await q.edit_message_reply_markup(reply_markup=None)
        await q.message.reply_text("🎵 **Naam likho:**\n\n`Mera Song` ya `skip`", parse_mode="Markdown")
        context.user_data['awaiting_audio'] = True

def main():
    print("="*50)
    print("  INSTAGRAM BOT v5 - DEBUG MODE")
    print("="*50)
    
    if not shutil.which('ffmpeg'):
        print("⚠️ Installing FFmpeg...")
        os.system('apt-get update && apt-get install ffmpeg -y 2>/dev/null')
    print(f"✅ FFmpeg: {shutil.which('ffmpeg')}")
    
    # Check cookies
    if os.path.exists('cookies.txt'):
        with open('cookies.txt', 'r') as f:
            content = f.read()
            has_session = 'sessionid' in content
            print(f"✅ cookies.txt ({os.path.getsize('cookies.txt')} bytes)")
            print(f"   sessionid: {'✅ Found' if has_session else '❌ MISSING!'}")
    else:
        print("❌ cookies.txt NOT FOUND!")
    
    # Clean
    for f in os.listdir(DOWNLOAD_DIR):
        try: os.remove(os.path.join(DOWNLOAD_DIR, f))
        except: pass
    
    print(f"📝 Debug log: bot_debug.log")
    print("✅ Bot Started!")
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.run_polling()

if __name__ == "__main__":
    main()
