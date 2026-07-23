import os
import re
import subprocess
import shutil
import time
import sys
import requests
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
        if not text:
            return False
        text = text.split('?')[0]
        return bool(re.search(r'(instagram\.com|instagr\.am)/(p|reel|tv)/[a-zA-Z0-9_\-]+', text))
    
    @staticmethod
    def extract_url(text):
        if not text:
            return None
        text = text.split('?')[0]
        m = re.search(r'(instagram\.com|instagr\.am)/(p|reel|tv)/([a-zA-Z0-9_\-]+)', text)
        if m:
            return f"https://www.instagram.com/{m.group(2)}/{m.group(3)}/"
        return None
    
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
        
        print(f"\n📥 {shortcode} | {'Reel' if is_reel else 'Post'}")
        
        try:
            if is_reel:
                return InstaDownloader._download_reel(shortcode, url)
            else:
                return InstaDownloader._download_post_instaloader(shortcode)
        except Exception as e:
            err = str(e)
            print(f"❌ Error: {err}")
            return {"success": False, "error": f"{err[:200]}"}
    
    @staticmethod
    def _download_reel(shortcode, url):
        """Reel download using yt-dlp"""
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
        
        return {"success": False, "error": "Reel not found"}
    
    @staticmethod
    def _download_post_instaloader(shortcode):
        """Photos using instaloader - MOST RELIABLE"""
        print("📸 Downloading photos via instaloader...")
        
        try:
            from instaloader import Instaloader, Post
            
            # Create instaloader instance
            L = Instaloader(
                download_pictures=True,
                download_videos=False,
                download_video_thumbnails=False,
                download_geotags=False,
                download_comments=False,
                save_metadata=False,
                compress_json=False,
                dirname_pattern=DOWNLOAD_DIR,
                filename_pattern='{shortcode}',
                max_connection_attempts=3,
            )
            
            # Load cookies from file
            if os.path.exists('cookies.txt'):
                import http.cookiejar
                cj = http.cookiejar.MozillaCookieJar('cookies.txt')
                cj.load(ignore_discard=True, ignore_expires=True)
                
                # Convert to requests cookies
                cookie_dict = {}
                for cookie in cj:
                    if 'instagram' in cookie.domain:
                        cookie_dict[cookie.name] = cookie.value
                
                # Login with cookies
                L.context._session.cookies.update(cookie_dict)
            
            # Download post
            post = Post.from_shortcode(L.context, shortcode)
            
            if post.is_video:
                print("⚠️ This is a video post, not photo!")
                return {"success": False, "error": "This is a video, send as reel link"}
            
            # Download all photos
            L.download_post(post, target=shortcode)
            
            # Move files to downloads folder
            time.sleep(2)
            
            # Find downloaded photos
            photos = []
            
            # Check main downloads folder
            for f in sorted(os.listdir(DOWNLOAD_DIR)):
                if shortcode in f and not f.endswith(('.mp4', '.mov', '.webm', '.txt', '.json', '.xz')):
                    fp = os.path.join(DOWNLOAD_DIR, f)
                    if os.path.exists(fp) and os.path.getsize(fp) > 1000:
                        photos.append(fp)
                        print(f"  ✅ Found: {f} ({os.path.getsize(fp)} bytes)")
            
            # Check subfolder
            subfolder = os.path.join(DOWNLOAD_DIR, shortcode)
            if os.path.exists(subfolder):
                for f in sorted(os.listdir(subfolder)):
                    if not f.endswith(('.mp4', '.mov', '.webm', '.txt', '.json', '.xz')):
                        fp = os.path.join(subfolder, f)
                        if os.path.exists(fp) and os.path.getsize(fp) > 1000:
                            # Move to main folder
                            new_fp = os.path.join(DOWNLOAD_DIR, f"{shortcode}_{f}")
                            shutil.move(fp, new_fp)
                            photos.append(new_fp)
                            print(f"  ✅ Found in subfolder: {f} ({os.path.getsize(new_fp)} bytes)")
                
                # Clean subfolder
                try:
                    shutil.rmtree(subfolder)
                except:
                    pass
            
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
            
            return {"success": False, "error": "No photos found"}
            
        except ImportError:
            print("❌ instaloader not installed, trying fallback...")
            return InstaDownloader._download_post_fallback(shortcode)
        except Exception as e:
            print(f"❌ instaloader error: {e}")
            return InstaDownloader._download_post_fallback(shortcode)
    
    @staticmethod
    def _download_post_fallback(shortcode):
        """Fallback: Direct URL method using cookies"""
        print("🔄 Fallback: Direct URL method...")
        
        # Load cookies
        cookies = {}
        if os.path.exists('cookies.txt'):
            with open('cookies.txt', 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    parts = line.split('\t')
                    if len(parts) >= 7:
                        cookies[parts[5]] = parts[6]
        
        session = requests.Session()
        for name, value in cookies.items():
            session.cookies.set(name, value, domain='.instagram.com')
        
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'X-IG-App-ID': '936619743392459',
            'X-Requested-With': 'XMLHttpRequest',
        })
        
        # Try oEmbed first
        try:
            api_url = f"https://api.instagram.com/oembed?url=https://www.instagram.com/p/{shortcode}/"
            resp = session.get(api_url, timeout=15)
            
            if resp.status_code == 200:
                data = resp.json()
                thumbnail = data.get('thumbnail_url', '')
                
                if thumbnail:
                    hd_url = re.sub(r'/s\d+x\d+/', '/s1080x1080/', thumbnail).split('?')[0]
                    
                    filepath = os.path.join(DOWNLOAD_DIR, f"{shortcode}.jpg")
                    
                    img_resp = session.get(hd_url, timeout=30)
                    if img_resp.status_code == 200 and len(img_resp.content) > 1000:
                        with open(filepath, 'wb') as f:
                            f.write(img_resp.content)
                        
                        print(f"✅ Fallback photo: {os.path.getsize(filepath)} bytes")
                        return {"success": True, "file_path": filepath, "is_video": False}
        except Exception as e:
            print(f"⚠️ oEmbed fallback: {e}")
        
        # Try direct Instagram page
        try:
            page_url = f"https://www.instagram.com/p/{shortcode}/"
            resp = session.get(page_url, timeout=15)
            
            if resp.status_code == 200:
                html = resp.text
                
                # Find display_url
                urls = re.findall(r'"display_url"\s*:\s*"([^"]+)"', html)
                
                photos = []
                for i, url in enumerate(urls):
                    url = url.replace('\\u0026', '&').split('?')[0]
                    if '.mp4' in url:
                        continue
                    
                    ext = 'jpg'
                    if '.png' in url: ext = 'png'
                    elif '.webp' in url: ext = 'webp'
                    
                    filename = f"{shortcode}_{i+1}.{ext}" if len(urls) > 1 else f"{shortcode}.{ext}"
                    filepath = os.path.join(DOWNLOAD_DIR, filename)
                    
                    img_resp = session.get(url, timeout=30)
                    if img_resp.status_code == 200 and len(img_resp.content) > 1000:
                        with open(filepath, 'wb') as f:
                            f.write(img_resp.content)
                        photos.append(filepath)
                        print(f"  ✅ {filename} ({os.path.getsize(filepath)} bytes)")
                
                if photos:
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
        except Exception as e:
            print(f"⚠️ Page scrape fallback: {e}")
        
        return {"success": False, "error": "All methods failed. Try fresh cookies.txt"}
    
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
        "🔗 **Link bhejo!**",
        parse_mode="Markdown"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in AUTHORIZED_USERS:
        return
    
    text = update.message.text.strip()
    if not text:
        return
    
    if context.user_data.get('awaiting_audio'):
        context.user_data['awaiting_audio'] = False
        url = context.user_data.get('current_url')
        if url:
            await extract_audio_handler(update, context, url, text)
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
            await msg.edit_text(f"❌ **Failed!**\n\n{result.get('error', 'Unknown')}", parse_mode="Markdown")
            return
        
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
                                caption += f"\n🔗 [Post]({url})"
                            await update.message.reply_photo(photo=f, caption=caption, parse_mode="Markdown")
                        
                        if i < total:
                            await asyncio.sleep(0.3)
                    except Exception as e:
                        await update.message.reply_text(f"❌ Photo {i}: {str(e)[:50]}")
                    InstaDownloader.cleanup(fp)
            
            await msg.edit_text(f"✅ **{total} Photos sent!** 🔥")
            return
        
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
    print("  INSTAGRAM BOT - instaloader")
    print("=" * 50)
    
    if not shutil.which('ffmpeg'):
        os.system('apt-get update -qq && apt-get install ffmpeg -y -qq 2>/dev/null')
    
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
