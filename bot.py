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
        text = text.split('?')[0]  # Remove query params
        return bool(re.search(r'(instagram\.com|instagr\.am)/(p|reel|tv)/[a-zA-Z0-9_\-]+/?$', text))
    
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
        
        print(f"\n📥 {shortcode} | {'Reel' if is_reel else 'Post'}")
        
        try:
            if is_reel:
                return InstaDownloader._download_reel(shortcode, url)
            else:
                return InstaDownloader._download_post_photos(shortcode, url)
        except Exception as e:
            err = str(e)
            print(f"❌ Error: {err}")
            if '403' in err or '401' in err:
                return {"success": False, "error": "Cookies EXPIRED! Naya banao."}
            return {"success": False, "error": f"{err[:200]}"}
    
    @staticmethod
    def _download_reel(shortcode, url):
        """Reel download using yt-dlp (working)"""
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
    def _download_post_photos(shortcode, url):
        """
        POST PHOTOS - DIRECT URL METHOD
        yt-dlp se info extract karo, phir direct download
        """
        print("📸 Downloading post photos...")
        
        # Step 1: Extract info using yt-dlp with cookies
        info_opts = {
            'cookiefile': 'cookies.txt',
            'quiet': True,
            'no_warnings': True,
        }
        
        try:
            print("  📡 Fetching post info...")
            with yt_dlp.YoutubeDL(info_opts) as ydl:
                info = ydl.extract_info(url, download=False)
            
            if not info:
                return {"success": False, "error": "Could not get post info"}
            
            # Check if it's a carousel
            entries = info.get('entries', [])
            
            # Agar entries nahi hai to single post hai
            if not entries:
                # Single post - check if it has display_url
                if 'display_url' in info:
                    entries = [info]
                else:
                    # Try to find image in formats
                    entries = [info]
            
            print(f"  📸 Found {len(entries)} photo(s)")
            
            # Step 2: Extract all image URLs
            image_urls = []
            
            for entry in entries:
                img_url = None
                
                # Method 1: display_url (most common)
                if 'display_url' in entry:
                    img_url = entry['display_url']
                
                # Method 2: thumbnail
                elif 'thumbnail' in entry:
                    img_url = entry['thumbnail']
                
                # Method 3: Check in image_versions2
                elif 'image_versions2' in entry:
                    candidates = entry['image_versions2'].get('candidates', [])
                    if candidates:
                        img_url = candidates[0].get('url')
                
                # Method 4: Check in formats
                elif 'formats' in entry:
                    for fmt in entry['formats']:
                        if fmt.get('ext') in ['jpg', 'jpeg', 'png', 'webp']:
                            img_url = fmt.get('url')
                            break
                
                # Method 5: Direct url field
                elif 'url' in entry:
                    img_url = entry['url']
                
                if img_url:
                    image_urls.append(img_url)
                    print(f"    🔗 Found URL: {img_url[:80]}...")
            
            if not image_urls:
                # Last resort: Try yt-dlp download
                print("  ⚠️ No URLs found, trying yt-dlp direct download...")
                return InstaDownloader._fallback_ytdlp_download(shortcode, url)
            
            # Step 3: Download all images
            print(f"  📥 Downloading {len(image_urls)} photo(s)...")
            
            downloaded = []
            headers = {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
                'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
                'Referer': 'https://www.instagram.com/',
            }
            
            for i, img_url in enumerate(image_urls, 1):
                try:
                    # Determine extension
                    ext = 'jpg'
                    if '.png' in img_url.lower():
                        ext = 'png'
                    elif '.webp' in img_url.lower():
                        ext = 'webp'
                    
                    # Filename
                    if len(image_urls) > 1:
                        filename = f"{shortcode}_{i}.{ext}"
                    else:
                        filename = f"{shortcode}.{ext}"
                    
                    filepath = os.path.join(DOWNLOAD_DIR, filename)
                    
                    # Download with retries
                    for attempt in range(3):
                        try:
                            response = requests.get(img_url, headers=headers, timeout=30)
                            
                            if response.status_code == 200 and len(response.content) > 1000:
                                with open(filepath, 'wb') as f:
                                    f.write(response.content)
                                
                                if os.path.exists(filepath) and os.path.getsize(filepath) > 1000:
                                    downloaded.append(filepath)
                                    print(f"    ✅ Photo {i}: {filename} ({os.path.getsize(filepath)} bytes)")
                                    break
                                else:
                                    print(f"    ⚠️ Attempt {attempt+1}: File too small")
                            else:
                                print(f"    ⚠️ Attempt {attempt+1}: HTTP {response.status_code}")
                        except Exception as e:
                            print(f"    ⚠️ Attempt {attempt+1}: {e}")
                            time.sleep(0.5)
                    
                except Exception as e:
                    print(f"    ❌ Photo {i} error: {e}")
                    continue
            
            if downloaded:
                print(f"✅ Downloaded {len(downloaded)} photo(s)")
                
                if len(downloaded) == 1:
                    return {"success": True, "file_path": downloaded[0], "is_video": False}
                else:
                    return {
                        "success": True,
                        "file_paths": sorted(downloaded),
                        "is_video": False,
                        "is_multiple": True,
                        "total": len(downloaded)
                    }
            
            return {"success": False, "error": "Could not download photos"}
            
        except Exception as e:
            print(f"  ❌ Error: {e}")
            return {"success": False, "error": f"Error: {str(e)[:200]}"}
    
    @staticmethod
    def _fallback_ytdlp_download(shortcode, url):
        """Last resort - yt-dlp direct download"""
        print("  🔄 Fallback: yt-dlp direct download...")
        
        ydl_opts = {
            'outtmpl': os.path.join(DOWNLOAD_DIR, f'{shortcode}.%(ext)s'),
            'cookiefile': 'cookies.txt',
            'quiet': True,
            'no_warnings': True,
            'retries': 5,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            time.sleep(2)
            
            photos = []
            for f in os.listdir(DOWNLOAD_DIR):
                if shortcode in f and not f.endswith(('.mp4', '.mov', '.webm', '.part', '.ytdl')):
                    fp = os.path.join(DOWNLOAD_DIR, f)
                    if os.path.exists(fp) and os.path.getsize(fp) > 1000:
                        photos.append(fp)
            
            if photos:
                print(f"  ✅ Fallback: {len(photos)} photos")
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
            print(f"  ❌ Fallback error: {e}")
        
        return {"success": False, "error": "All methods failed"}
    
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
        "📥 **Instagram Downloader Bot**\n\n"
        "✅ **Reel** → HD Video 🎬\n"
        "✅ **Post** → ALL Photos 📸\n"
        "✅ **Carousel** → 1-by-1 🔄\n"
        "✅ **Audio** → MP3 ⚡\n\n"
        "🔗 **Link bhejo!**",
        parse_mode="Markdown"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in AUTHORIZED_USERS:
        return
    
    text = update.message.text.strip()
    if not text:
        return
    
    # Audio name input
    if context.user_data.get('awaiting_audio'):
        context.user_data['awaiting_audio'] = False
        url = context.user_data.get('current_url')
        if url:
            await extract_audio_handler(update, context, url, text)
        return
    
    # Clean URL - remove tracking params
    if '?' in text:
        text = text.split('?')[0]
    
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
            await msg.edit_text(f"❌ {size_mb:.1f}MB > 50MB limit")
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
    print("  INSTAGRAM BOT - FINAL v8")
    print(f"  yt-dlp: {yt_dlp.version.__version__}")
    print("=" * 50)
    
    if not shutil.which('ffmpeg'):
        os.system('apt-get update -qq && apt-get install ffmpeg -y -qq 2>/dev/null')
    print(f"✅ FFmpeg: {shutil.which('ffmpeg')}")
    
    for f in os.listdir(DOWNLOAD_DIR):
        try: os.remove(os.path.join(DOWNLOAD_DIR, f))
        except: pass
    
    print("✅ Bot Started!")
    print("📸 Photos: Direct URL download method")
    print("🎬 Reels: yt-dlp method")
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.run_polling()

if __name__ == "__main__":
    main()
