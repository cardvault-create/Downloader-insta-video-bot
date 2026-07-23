import os
import re
import subprocess
import shutil
import time
import sys
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import yt_dlp
import asyncio

# ═══════════════════════════
# CONFIG
# ═══════════════════════════

BOT_TOKEN = "8518787964:AAHGimBKXfdtrI6UaASGsoI8Aj5Rj_WxF5I"
AUTHORIZED_USERS = [1987818347]
DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ═══════════════════════════
# INSTAGRAM DOWNLOADER
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
    def test_post(shortcode):
        """Test karega ki post download ho sakti hai ya nahi"""
        url = f"https://www.instagram.com/p/{shortcode}/"
        result = []
        
        result.append(f"🔍 **Testing:** `{shortcode}`\n")
        
        # Check cookies
        if not os.path.exists('cookies.txt'):
            result.append("❌ cookies.txt not found!")
            return "\n".join(result)
        
        result.append("✅ cookies.txt found")
        
        # Try to get info
        try:
            ydl_opts = {
                'cookiefile': 'cookies.txt',
                'quiet': True,
                'no_warnings': True,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                result.append(f"✅ Info extracted!")
                result.append(f"📌 Title: `{info.get('title', 'N/A')[:80]}`")
                result.append(f"📌 Uploader: `{info.get('uploader', 'N/A')}`")
                
                # Check entries (carousel)
                entries = info.get('entries', [])
                if entries:
                    result.append(f"\n📸 **Carousel detected! {len(entries)} items:**")
                    for i, entry in enumerate(entries[:10], 1):
                        entry_type = entry.get('_type', 'unknown')
                        formats = entry.get('formats', [])
                        ext_list = list(set([f.get('ext', '?') for f in formats]))
                        result.append(f"  {i}. Type: `{entry_type}` | Ext: {ext_list}")
                else:
                    result.append(f"\n📸 **Single post**")
                    formats = info.get('formats', [])
                    ext_list = list(set([f.get('ext', '?') for f in formats]))
                    result.append(f"  Formats: {ext_list}")
                
                # Try actual download
                result.append(f"\n📥 **Trying download...**")
                
                download_opts = {
                    'outtmpl': os.path.join(DOWNLOAD_DIR, 'test_%(id)s.%(ext)s'),
                    'cookiefile': 'cookies.txt',
                    'quiet': True,
                    'no_warnings': True,
                }
                
                with yt_dlp.YoutubeDL(download_opts) as ydl:
                    ydl.download([url])
                
                time.sleep(2)
                
                # Check what was downloaded
                downloaded = []
                for f in os.listdir(DOWNLOAD_DIR):
                    if 'test_' in f:
                        fp = os.path.join(DOWNLOAD_DIR, f)
                        size = os.path.getsize(fp)
                        downloaded.append(f"{f} ({size} bytes)")
                
                if downloaded:
                    result.append(f"✅ **Downloaded files:**")
                    for d in downloaded:
                        result.append(f"  📁 {d}")
                else:
                    result.append(f"❌ No files downloaded!")
                    result.append(f"  Downloads folder: {os.listdir(DOWNLOAD_DIR)}")
                
                # Cleanup
                for f in os.listdir(DOWNLOAD_DIR):
                    if 'test_' in f:
                        os.remove(os.path.join(DOWNLOAD_DIR, f))
                
        except Exception as e:
            result.append(f"❌ **Error:** `{str(e)[:300]}`")
        
        return "\n".join(result)
    
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
        
        if not os.path.exists('cookies.txt'):
            return {"success": False, "error": "cookies.txt not found!"}
        
        print(f"\n📥 {shortcode} | Type: {'Reel' if is_reel else 'Post'}")
        
        try:
            if is_reel:
                return InstaDownloader._download_reel(shortcode, url)
            else:
                return InstaDownloader._download_post(shortcode, url)
                
        except Exception as e:
            err = str(e)
            print(f"❌ Error: {err}")
            if '403' in err or '401' in err:
                return {"success": False, "error": "Cookies EXPIRED!"}
            return {"success": False, "error": f"{err[:200]}"}
    
    @staticmethod
    def _download_reel(shortcode, url):
        print("🎬 Downloading reel...")
        
        ydl_opts = {
            'outtmpl': os.path.join(DOWNLOAD_DIR, f'{shortcode}.%(ext)s'),
            'format': 'bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/best',
            'cookiefile': 'cookies.txt',
            'quiet': True,
            'no_warnings': True,
            'retries': 5,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
        
        time.sleep(1)
        for f in os.listdir(DOWNLOAD_DIR):
            if shortcode in f and f.endswith('.mp4'):
                fp = os.path.join(DOWNLOAD_DIR, f)
                if os.path.getsize(fp) > 5000:
                    print(f"✅ Reel: {f}")
                    return {"success": True, "file_path": fp, "is_video": True}
        
        return {"success": False, "error": "Reel file not found"}
    
    @staticmethod
    def _download_post(shortcode, url):
        print("📸 Downloading photos...")
        
        photos = []
        
        # Method 1: Simple download
        print("  Method 1: Simple download...")
        try:
            ydl_opts = {
                'outtmpl': os.path.join(DOWNLOAD_DIR, f'{shortcode}.%(ext)s'),
                'cookiefile': 'cookies.txt',
                'quiet': True,
                'no_warnings': True,
                'retries': 5,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            time.sleep(2)
            
            for f in os.listdir(DOWNLOAD_DIR):
                if shortcode in f:
                    fp = os.path.join(DOWNLOAD_DIR, f)
                    if os.path.exists(fp) and os.path.getsize(fp) > 1000:
                        if f.endswith(('.mp4', '.mov', '.webm')):
                            os.remove(fp)
                            continue
                        photos.append(fp)
                        print(f"    ✅ {f} ({os.path.getsize(fp)} bytes)")
        except Exception as e:
            print(f"    ⚠️ Method 1: {e}")
        
        # Method 2: Retry
        if not photos:
            print("  Method 2: Retry...")
            try:
                ydl_opts = {
                    'outtmpl': os.path.join(DOWNLOAD_DIR, f'{shortcode}_retry.%(ext)s'),
                    'cookiefile': 'cookies.txt',
                    'quiet': True,
                    'no_warnings': True,
                    'retries': 5,
                }
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                
                time.sleep(2)
                
                for f in os.listdir(DOWNLOAD_DIR):
                    if shortcode in f:
                        fp = os.path.join(DOWNLOAD_DIR, f)
                        if os.path.exists(fp) and os.path.getsize(fp) > 1000:
                            if f.endswith(('.mp4', '.mov', '.webm')):
                                os.remove(fp)
                                continue
                            photos.append(fp)
                            print(f"    ✅ {f} ({os.path.getsize(fp)} bytes)")
            except Exception as e:
                print(f"    ⚠️ Method 2: {e}")
        
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
            photos = sorted(unique)
        
        if photos:
            print(f"✅ Total: {len(photos)} photos")
            if len(photos) == 1:
                return {"success": True, "file_path": photos[0], "is_video": False}
            else:
                return {
                    "success": True,
                    "file_paths": photos,
                    "is_video": False,
                    "is_multiple": True,
                    "total": len(photos)
                }
        
        all_files = os.listdir(DOWNLOAD_DIR)
        print(f"❌ No photos! Downloads: {all_files}")
        return {"success": False, "error": f"No photos found. Downloads: {all_files}"}
    
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
# TELEGRAM HANDLERS
# ═══════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in AUTHORIZED_USERS:
        return
    
    await update.message.reply_text(
        "📥 **Instagram Downloader**\n\n"
        "✅ Reel → HD Video 🎬\n"
        "✅ Post → ALL Photos 📸\n"
        "✅ Carousel → 1-by-1 🔄\n"
        "✅ Audio → MP3 ⚡\n\n"
        "🔍 `/test SHORTCODE` - Test post\n"
        "🔗 **Link bhejo!**",
        parse_mode="Markdown"
    )

async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Test command - /test SHORTCODE"""
    if update.effective_user.id not in AUTHORIZED_USERS:
        return
    
    if not context.args:
        await update.message.reply_text("❌ Usage: `/test SHORTCODE`\n\nExample: `/test ABC123xyz`", parse_mode="Markdown")
        return
    
    shortcode = context.args[0].strip()
    
    msg = await update.message.reply_text(f"🔍 **Testing `{shortcode}`...**", parse_mode="Markdown")
    
    result = InstaDownloader.test_post(shortcode)
    
    # Split if too long
    if len(result) > 4000:
        parts = [result[i:i+4000] for i in range(0, len(result), 4000)]
        await msg.edit_text(parts[0], parse_mode="Markdown")
        for part in parts[1:]:
            await update.message.reply_text(part, parse_mode="Markdown")
    else:
        await msg.edit_text(result, parse_mode="Markdown")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in AUTHORIZED_USERS:
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
    
    msg = await update.message.reply_text("⏳ **Processing...**", parse_mode="Markdown")
    
    try:
        result = InstaDownloader.download_media(url)
        
        if not result.get("success"):
            err_msg = result.get('error', 'Unknown')
            # Agar error aata hai to test bhi karo
            shortcode = InstaDownloader.get_shortcode(url)
            await msg.edit_text(
                f"❌ **Failed!**\n\n{err_msg}\n\n"
                f"🔍 Test ke liye: `/test {shortcode}`",
                parse_mode="Markdown"
            )
            return
        
        # Multiple photos
        if result.get("is_multiple"):
            photos = result["file_paths"]
            total = result.get("total", len(photos))
            
            await msg.edit_text(f"📤 **Sending {total} photos...**")
            
            for i, fp in enumerate(photos, 1):
                if os.path.exists(fp):
                    try:
                        with open(fp, 'rb') as f:
                            caption = f"✅ **Photo {i}/{total}**"
                            if i == 1:
                                caption += f"\n🔗 [Instagram Post]({url})"
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
            await msg.edit_text(f"❌ {size_mb:.1f}MB > 50MB")
            InstaDownloader.cleanup(fp)
            return
        
        is_video = result.get("is_video", False) or fp.endswith(('.mp4', '.mov', '.webm'))
        
        if is_video:
            kb = [[InlineKeyboardButton("🎵 Download Audio", callback_data="get_audio")]]
            with open(fp, 'rb') as f:
                await update.message.reply_video(
                    video=f, caption=f"✅ Downloaded\n🔗 [Link]({url})",
                    parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb), supports_streaming=True
                )
        else:
            with open(fp, 'rb') as f:
                await update.message.reply_photo(
                    photo=f, caption=f"✅ Downloaded\n🔗 [Link]({url})", parse_mode="Markdown"
                )
        
        await msg.delete()
        InstaDownloader.cleanup(fp)
        
    except Exception as e:
        await msg.edit_text(f"❌ Error: {str(e)[:100]}", parse_mode="Markdown")

async def extract_audio_handler(update, context, url, name):
    msg = await update.message.reply_text(f"🎵 **{name}...**", parse_mode="Markdown")
    try:
        result = InstaDownloader.download_media(url)
        if not result.get("success"):
            await msg.edit_text(f"❌ {result.get('error')}")
            return
        
        vp = result["file_paths"][0] if result.get("is_multiple") else result["file_path"]
        ar = InstaDownloader.extract_audio(vp, name)
        
        if ar.get("success"):
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
    print("=" * 50)
    print("  INSTAGRAM BOT v7 - TEST MODE")
    print(f"  yt-dlp: {yt_dlp.version.__version__}")
    print("=" * 50)
    
    if not shutil.which('ffmpeg'):
        os.system('apt-get update -qq && apt-get install ffmpeg -y -qq 2>/dev/null')
    
    for f in os.listdir(DOWNLOAD_DIR):
        try: os.remove(os.path.join(DOWNLOAD_DIR, f))
        except: pass
    
    print("✅ Bot Started!")
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("test", test_command))  # NEW TEST COMMAND
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.run_polling()

if __name__ == "__main__":
    main()
