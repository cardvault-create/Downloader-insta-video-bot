import logging
import os
import re
import subprocess
import shutil
import time
import json
import sys
import traceback
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
    def test_cookies():
        """Test if cookies are valid"""
        if not os.path.exists('cookies.txt'):
            return False, "cookies.txt file not found"
        
        with open('cookies.txt', 'r') as f:
            content = f.read()
        
        if 'sessionid' not in content:
            return False, "No sessionid in cookies"
        
        for line in content.split('\n'):
            if 'sessionid' in line and not line.startswith('#'):
                parts = line.split('\t')
                if len(parts) >= 5:
                    expiry = int(parts[4])
                    if expiry > 0 and expiry < time.time():
                        return False, f"sessionid EXPIRED! (expired: {time.strftime('%Y-%m-%d', time.localtime(expiry))})"
                    return True, f"Valid (expires: {time.strftime('%Y-%m-%d', time.localtime(expiry))})"
        
        return False, "Could not verify sessionid"
    
    @staticmethod
    def download_media(url):
        shortcode = InstaDownloader.get_shortcode(url)
        if not shortcode:
            return {"success": False, "error": "❌ Invalid URL"}
        
        is_reel = '/reel/' in url or '/tv/' in url
        
        # Clean old files
        for f in list(os.listdir(DOWNLOAD_DIR)):
            if shortcode in f:
                try: os.remove(os.path.join(DOWNLOAD_DIR, f))
                except: pass
        
        # Check cookies
        cookie_ok, cookie_msg = InstaDownloader.test_cookies()
        if not cookie_ok:
            return {"success": False, "error": f"❌ Cookies: {cookie_msg}"}
        
        print(f"\n{'='*50}")
        print(f"📥 Downloading: {shortcode}")
        print(f"🔐 Cookies: {cookie_msg}")
        print(f"📹 Type: {'Reel' if is_reel else 'Post'}")
        print(f"📦 yt-dlp version: {yt_dlp.version.__version__}")
        print(f"{'='*50}\n")
        
        try:
            if is_reel:
                return InstaDownloader._download_reel(shortcode, url)
            else:
                return InstaDownloader._download_post(shortcode, url)
                
        except Exception as e:
            error_details = traceback.format_exc()
            print(f"❌ FATAL ERROR:\n{error_details}")
            return {"success": False, "error": f"❌ {str(e)[:300]}", "debug": error_details[:500]}
    
    @staticmethod
    def _download_reel(shortcode, url):
        print("🎬 Downloading REEL...")
        
        ydl_opts = {
            'outtmpl': os.path.join(DOWNLOAD_DIR, f'{shortcode}.%(ext)s'),
            'format': 'bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/best',
            'cookiefile': 'cookies.txt',
            'retries': 5,
            'quiet': False,
            'no_warnings': False,
            'extractor_args': {'instagram': {'skip_invisible_stories': True}},
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                print(f"✅ Reel downloaded: {info.get('title', 'N/A')}")
            
            time.sleep(1)
            for f in os.listdir(DOWNLOAD_DIR):
                if shortcode in f and f.endswith('.mp4'):
                    fp = os.path.join(DOWNLOAD_DIR, f)
                    size_mb = os.path.getsize(fp) / (1024*1024)
                    print(f"✅ Found: {f} ({size_mb:.1f} MB)")
                    return {"success": True, "file_path": fp, "is_video": True, "size_mb": size_mb}
            
            return {"success": False, "error": "Reel file not found after download"}
            
        except Exception as e:
            error_str = str(e)
            print(f"❌ Reel error: {error_str}")
            
            if '403' in error_str or '401' in error_str:
                return {"success": False, "error": "🔒 Cookies EXPIRED! Fresh cookies banao."}
            
            return {"success": False, "error": f"Reel download failed: {error_str[:200]}"}
    
    @staticmethod
    def _download_post(shortcode, url):
        print("📸 Downloading POST photos...")
        
        # First, try to get info
        info_opts = {
            'cookiefile': 'cookies.txt',
            'quiet': True,
            'no_warnings': True,
        }
        
        try:
            with yt_dlp.YoutubeDL(info_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                entries = info.get('entries', [])
                if entries:
                    print(f"📸 Carousel detected: {len(entries)} photos")
                else:
                    print(f"📸 Single photo post")
        except Exception as e:
            print(f"⚠️ Info extraction failed: {e}")
        
        # Download with playlist mode (for carousel)
        ydl_opts = {
            'outtmpl': os.path.join(DOWNLOAD_DIR, f'{shortcode}_%(playlist_index)s.%(ext)s'),
            'format': 'best[ext=jpg]/best[ext=png]/best[ext=webp]/best',
            'cookiefile': 'cookies.txt',
            'retries': 5,
            'ignoreerrors': True,
            'no_playlist': False,
            'quiet': False,
            'no_warnings': False,
            'extract_flat': False,
        }
        
        try:
            print("📥 Downloading with playlist mode...")
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
                        print(f"  ✅ Found: {f} ({os.path.getsize(fp)} bytes)")
            
            # Remove duplicates
            if len(photos) > 1:
                unique = []
                sizes = set()
                for fp in photos:
                    s = os.path.getsize(fp)
                    if s not in sizes:
                        sizes.add(s)
                        unique.append(fp)
                    else:
                        os.remove(fp)
                photos = unique
            
            if photos:
                print(f"✅ Total photos: {len(photos)}")
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
            
            print("⚠️ No files in first attempt, trying fallback...")
            
        except Exception as e:
            print(f"⚠️ First attempt error: {e}")
        
        # Fallback: Simple download without playlist index
        print("📥 Fallback: Simple download mode...")
        ydl_opts2 = {
            'outtmpl': os.path.join(DOWNLOAD_DIR, f'{shortcode}.%(ext)s'),
            'format': 'best[ext=jpg]/best[ext=png]/best[ext=webp]/best',
            'cookiefile': 'cookies.txt',
            'retries': 5,
            'quiet': False,
            'no_warnings': False,
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
                        print(f"  ✅ Found: {f} ({os.path.getsize(fp)} bytes)")
            
            if photos:
                print(f"✅ Fallback found {len(photos)} photos")
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
            
            all_files = os.listdir(DOWNLOAD_DIR)
            print(f"❌ No photos found! Downloads folder: {all_files}")
            return {"success": False, "error": f"No photos downloaded. Downloads folder has {len(all_files)} files."}
            
        except Exception as e:
            error_str = str(e)
            print(f"❌ Fallback error: {error_str}")
            
            if '403' in error_str or '401' in error_str:
                return {"success": False, "error": "🔒 Cookies EXPIRED! Fresh cookies banao."}
            if 'login' in error_str.lower():
                return {"success": False, "error": "🔒 Login required! Cookies invalid."}
            
            return {"success": False, "error": f"Download error: {error_str[:300]}"}
    
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
            
            subprocess.run(['ffmpeg', '-i', video_path, '-vn', '-acodec', 'libmp3lame', '-ab', '192k', '-y', apath], 
                          capture_output=True, timeout=180)
            
            if os.path.exists(apath) and os.path.getsize(apath) > 1000:
                return {"success": True, "file_path": apath}
            return {"success": False, "error": "Extraction failed"}
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
    
    cookie_ok, cookie_msg = InstaDownloader.test_cookies()
    cookie_status = f"✅ {cookie_msg}" if cookie_ok else f"❌ {cookie_msg}"
    
    await update.message.reply_text(
        f"📥 **Instagram Downloader Bot**\n\n"
        f"🔐 **Cookies:** {cookie_status}\n"
        f"📦 **yt-dlp:** {yt_dlp.version.__version__}\n\n"
        f"✅ Reel → HD Video 🎬\n"
        f"✅ Post → ALL Photos 📸\n"
        f"✅ Carousel → 1-by-1 🔄\n"
        f"✅ Audio → MP3 ⚡\n\n"
        f"🔗 Sirf link bhejo!",
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
    shortcode = InstaDownloader.get_shortcode(url)
    
    msg = await update.message.reply_text(
        f"⏳ **Processing...**\n📋 `{shortcode}`",
        parse_mode="Markdown"
    )
    
    try:
        result = InstaDownloader.download_media(url)
        
        if not result.get("success"):
            error = result.get('error', 'Unknown error')
            debug = result.get('debug', '')
            
            error_msg = f"❌ **Failed!**\n\n{error}"
            if debug:
                error_msg += f"\n\n📝 **Debug:**\n```\n{debug[:300]}\n```"
            
            await msg.edit_text(error_msg, parse_mode="Markdown")
            return
        
        # Multiple photos
        if result.get("is_multiple"):
            photos = result["file_paths"]
            total = result.get("total", len(photos))
            
            await msg.edit_text(f"📤 **{total} Photos bhej raha hun...**")
            
            for i, fp in enumerate(photos, 1):
                if os.path.exists(fp):
                    try:
                        with open(fp, 'rb') as f:
                            caption = f"✅ **Photo {i}/{total}**"
                            if i == 1:
                                caption += f"\n🔗 [Post Link]({url})"
                            await update.message.reply_photo(photo=f, caption=caption, parse_mode="Markdown")
                        
                        if i < total:
                            await asyncio.sleep(0.3)
                    except Exception as e:
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
            await msg.edit_text(f"❌ File too large: {size_mb:.1f}MB")
            InstaDownloader.cleanup(fp)
            return
        
        is_video = result.get("is_video", False) or fp.endswith(('.mp4', '.mov', '.webm'))
        
        if is_video:
            await msg.edit_text(f"📤 **Uploading Video...** ({size_mb:.1f}MB)")
            kb = [[InlineKeyboardButton("🎵 Download Audio", callback_data="get_audio")]]
            with open(fp, 'rb') as f:
                await update.message.reply_video(
                    video=f, 
                    caption=f"✅ **Downloaded**\n🔗 [Link]({url})",
                    parse_mode="Markdown", 
                    reply_markup=InlineKeyboardMarkup(kb), 
                    supports_streaming=True
                )
        else:
            await msg.edit_text(f"📤 **Uploading Photo...** ({size_mb:.1f}MB)")
            with open(fp, 'rb') as f:
                await update.message.reply_photo(
                    photo=f, 
                    caption=f"✅ **Downloaded**\n🔗 [Link]({url})", 
                    parse_mode="Markdown"
                )
        
        await msg.delete()
        InstaDownloader.cleanup(fp)
        
    except Exception as e:
        error_details = traceback.format_exc()
        print(f"❌ HANDLER ERROR:\n{error_details}")
        await msg.edit_text(
            f"❌ **FATAL ERROR**\n\n```\n{error_details[:400]}\n```",
            parse_mode="Markdown"
        )

async def extract_audio_handler(update, context, url, name):
    msg = await update.message.reply_text(f"🎵 **{name}...**", parse_mode="Markdown")
    try:
        result = InstaDownloader.download_media(url)
        if not result.get("success"):
            await msg.edit_text(f"❌ Failed: {result.get('error')}")
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
    print("=" * 60)
    print("  INSTAGRAM BOT - RAILWAY v2")
    print(f"  yt-dlp: {yt_dlp.version.__version__}")
    print("=" * 60)
    
    # FFmpeg
    ffmpeg = shutil.which('ffmpeg')
    if ffmpeg:
        print(f"✅ FFmpeg: {ffmpeg}")
    else:
        print("⚠️ Installing FFmpeg...")
        os.system('apt-get update -qq && apt-get install ffmpeg -y -qq 2>/dev/null')
    
    # Cookies check
    cookie_ok, cookie_msg = InstaDownloader.test_cookies()
    print(f"{'✅' if cookie_ok else '❌'} Cookies: {cookie_msg}")
    
    # Clean
    for f in os.listdir(DOWNLOAD_DIR):
        try: os.remove(os.path.join(DOWNLOAD_DIR, f))
        except: pass
    
    print("✅ Bot Started!")
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.run_polling()

if __name__ == "__main__":
    main()
