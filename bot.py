import logging
import os
import re
import subprocess
import shutil
import json
import urllib.parse
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import yt_dlp
import requests

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
    
    # ═══════════════════════════
    # 🎬 MAIN
    # ═══════════════════════════
    
    @staticmethod
    def download_media(url):
        shortcode = InstaDownloader.get_shortcode(url)
        if not shortcode:
            return {"success": False, "error": "Invalid shortcode"}
        
        is_reel = '/reel/' in url or '/tv/' in url
        
        if is_reel:
            return InstaDownloader._download_video(shortcode)
        else:
            return InstaDownloader._download_photo(shortcode)
    
    # ═══════════════════════════
    # 🎬 VIDEO (with audio)
    # ═══════════════════════════
    
    @staticmethod
    def _download_video(shortcode):
        """Simple video download using yt-dlp"""
        try:
            url = f"https://www.instagram.com/reel/{shortcode}/"
            
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'outtmpl': os.path.join(DOWNLOAD_DIR, f'{shortcode}.%(ext)s'),
                'format': 'best[ext=mp4]/best',  # Best format with audio
            }
            
            # Add cookies
            if os.path.exists('cookies.txt'):
                ydl_opts['cookiefile'] = 'cookies.txt'
            
            # Add ffmpeg
            ffmpeg = shutil.which('ffmpeg')
            if ffmpeg:
                ydl_opts['ffmpeg_location'] = ffmpeg
                ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4',
                }]
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                
                if not info:
                    return {"success": False, "error": "No response from Instagram"}
                
                # Find file
                file_path = None
                for f in os.listdir(DOWNLOAD_DIR):
                    if shortcode in f:
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
                    # Check audio
                    probe = subprocess.run(
                        ['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_entries', 'stream=codec_type', '-of', 'csv=p=0', file_path],
                        capture_output=True, text=True, timeout=30
                    )
                    has_audio = bool(probe.stdout.strip())
                    
                    if has_audio:
                        print(f"✅ Video + Audio: {os.path.basename(file_path)}")
                        return {"success": True, "file_path": file_path, "is_video": True}
                    else:
                        print(f"⚠️ No audio in downloaded video, trying alternative...")
                        # Delete and try again with different format
                        try: os.remove(file_path)
                        except: pass
                        
                        # Try with explicit audio
                        ydl_opts2 = {
                            'quiet': True,
                            'no_warnings': True,
                            'outtmpl': os.path.join(DOWNLOAD_DIR, f'{shortcode}.%(ext)s'),
                            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                            'merge_output_format': 'mp4',
                        }
                        if os.path.exists('cookies.txt'):
                            ydl_opts2['cookiefile'] = 'cookies.txt'
                        if ffmpeg:
                            ydl_opts2['ffmpeg_location'] = ffmpeg
                        
                        with yt_dlp.YoutubeDL(ydl_opts2) as ydl2:
                            info2 = ydl2.extract_info(url, download=True)
                            for f in os.listdir(DOWNLOAD_DIR):
                                if shortcode in f and f.endswith('.mp4'):
                                    fp2 = os.path.join(DOWNLOAD_DIR, f)
                                    if os.path.exists(fp2) and os.path.getsize(fp2) > 5000:
                                        return {"success": True, "file_path": fp2, "is_video": True}
                
                return {"success": False, "error": "Download failed"}
                
        except Exception as e:
            err = str(e)
            if 'HTTP Error 403' in err:
                return {"success": False, "error": "❌ cookies.txt expired! Make new one."}
            if 'ffmpeg' in err.lower():
                return {"success": False, "error": "❌ FFmpeg not installed!"}
            return {"success": False, "error": f"❌ {err[:80]}"}
    
    # ═══════════════════════════
    # 📸 PHOTO (4 SIMPLE METHODS)
    # ═══════════════════════════
    
    @staticmethod
    def _download_photo(shortcode):
        """Photo download - multiple simple methods"""
        
        print(f"\n📸 Photo: {shortcode}")
        
        # METHOD 1: Direct Instagram embed (og:image) - FASTEST
        result = InstaDownloader._embed_photo(shortcode)
        if result.get("success"):
            return result
        
        # METHOD 2: oEmbed API (public)
        result = InstaDownloader._oembed_photo(shortcode)
        if result.get("success"):
            return result
        
        # METHOD 3: Instagram page scrape
        result = InstaDownloader._scrape_photo(shortcode)
        if result.get("success"):
            return result
        
        # METHOD 4: yt-dlp
        result = InstaDownloader._ytdlp_photo(shortcode)
        if result.get("success"):
            return result
        
        return {"success": False, "error": "All photo methods failed. Instagram blocking?"}
    
    @staticmethod
    def _embed_photo(shortcode):
        """Method 1: Get image from embed page (og:image)"""
        try:
            url = f"https://www.instagram.com/p/{shortcode}/"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml',
            }
            
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                return {"success": False}
            
            html = resp.text
            
            # Try to find og:image (highest quality)
            og_match = re.search(r'<meta\s+property="og:image"\s+content="([^"]+)"', html)
            if og_match:
                img_url = og_match.group(1)
                
                # Download
                img_headers = {
                    'User-Agent': 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36',
                    'Accept': 'image/*',
                    'Referer': 'https://www.instagram.com/',
                }
                
                r = requests.get(img_url, headers=img_headers, stream=True, timeout=30)
                if r.status_code == 200:
                    ext = 'jpg'
                    ct = r.headers.get('content-type', '')
                    if 'png' in ct: ext = 'png'
                    elif 'webp' in ct: ext = 'webp'
                    
                    file_path = os.path.join(DOWNLOAD_DIR, f"{shortcode}.{ext}")
                    with open(file_path, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk: f.write(chunk)
                    
                    if os.path.exists(file_path) and os.path.getsize(file_path) > 1000:
                        print(f"✅ Photo via og:image: {os.path.basename(file_path)} ({os.path.getsize(file_path)} bytes)")
                        return {"success": True, "file_path": file_path, "is_video": False}
            
            return {"success": False}
        except:
            return {"success": False}
    
    @staticmethod
    def _oembed_photo(shortcode):
        """Method 2: oEmbed API - public"""
        try:
            post_url = f"https://www.instagram.com/p/{shortcode}/"
            api_url = f"https://api.instagram.com/oembed?url={urllib.parse.quote(post_url)}"
            
            resp = requests.get(api_url, timeout=15)
            if resp.status_code != 200:
                return {"success": False}
            
            data = resp.json()
            thumbnail = data.get('thumbnail_url', '')
            if not thumbnail:
                return {"success": False}
            
            print(f"🔗 oEmbed: {thumbnail[:60]}...")
            
            # Try HD version
            hd_url = re.sub(r'/s\d+x\d+/', '/', thumbnail)
            hd_url = hd_url.split('?')[0]
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36',
                'Accept': 'image/*',
                'Referer': 'https://www.instagram.com/',
            }
            
            r = requests.get(hd_url, headers=headers, stream=True, timeout=30)
            if r.status_code != 200:
                r = requests.get(thumbnail, headers=headers, stream=True, timeout=30)
            
            if r.status_code == 200:
                ext = 'jpg'
                ct = r.headers.get('content-type', '')
                if 'png' in ct: ext = 'png'
                elif 'webp' in ct: ext = 'webp'
                
                file_path = os.path.join(DOWNLOAD_DIR, f"{shortcode}.{ext}")
                with open(file_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk: f.write(chunk)
                
                if os.path.exists(file_path) and os.path.getsize(file_path) > 1000:
                    print(f"✅ Photo via oEmbed: {os.path.basename(file_path)}")
                    return {"success": True, "file_path": file_path, "is_video": False}
            
            return {"success": False}
        except:
            return {"success": False}
    
    @staticmethod
    def _scrape_photo(shortcode):
        """Method 3: Page scrape"""
        try:
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
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml',
            }
            
            page_url = f"https://www.instagram.com/p/{shortcode}/"
            resp = requests.get(page_url, headers=headers, cookies=cookies, timeout=15)
            html = resp.text
            
            image_urls = []
            
            # __NEXT_DATA__
            nd = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.DOTALL)
            if nd:
                try:
                    data = json.loads(nd.group(1))
                    def find_urls(obj):
                        urls = []
                        if isinstance(obj, dict):
                            du = obj.get('display_url') or ''
                            if du and du.startswith('http'):
                                urls.append(du)
                            for v in obj.values():
                                urls.extend(find_urls(v))
                        elif isinstance(obj, list):
                            for item in obj:
                                urls.extend(find_urls(item))
                        return urls
                    image_urls = find_urls(data)
                except:
                    pass
            
            # Regex
            if not image_urls:
                urls = re.findall(r'"display_url":"([^"]+)"', html)
                for u in urls:
                    image_urls.append(u.replace('\\u0026', '&'))
            
            if not image_urls:
                return {"success": False}
            
            # Download
            downloaded = []
            for i, img_url in enumerate(image_urls[:10]):
                try:
                    if img_url.startswith('//'):
                        img_url = 'https:' + img_url
                    img_url = img_url.split('?')[0]
                    
                    ext = 'jpg'
                    if '.png' in img_url: ext = 'png'
                    elif '.webp' in img_url: ext = 'webp'
                    
                    file_name = f"{shortcode}_{i+1}.{ext}" if len(image_urls) > 1 else f"{shortcode}.{ext}"
                    file_path = os.path.join(DOWNLOAD_DIR, file_name)
                    
                    img_headers = {
                        'User-Agent': 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36',
                        'Accept': 'image/*',
                        'Referer': 'https://www.instagram.com/',
                    }
                    
                    ir = requests.get(img_url, headers=img_headers, stream=True, timeout=30)
                    if ir.status_code == 200:
                        with open(file_path, 'wb') as f:
                            for chunk in ir.iter_content(chunk_size=8192):
                                if chunk: f.write(chunk)
                        
                        if os.path.exists(file_path) and os.path.getsize(file_path) > 1000:
                            downloaded.append(file_path)
                            if len(image_urls) == 1:
                                break
                except:
                    continue
            
            if downloaded:
                if len(downloaded) == 1:
                    return {"success": True, "file_path": downloaded[0], "is_video": False}
                else:
                    return {"success": True, "file_paths": downloaded, "is_video": False, "is_multiple": True}
            
        except:
            pass
        return {"success": False}
    
    @staticmethod
    def _ytdlp_photo(shortcode):
        """Method 4: yt-dlp"""
        try:
            url = f"https://www.instagram.com/p/{shortcode}/"
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'outtmpl': os.path.join(DOWNLOAD_DIR, f'{shortcode}.%(ext)s'),
                'format': 'best',
            }
            if os.path.exists('cookies.txt'):
                ydl_opts['cookiefile'] = 'cookies.txt'
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if info:
                    for f in os.listdir(DOWNLOAD_DIR):
                        if shortcode in f and not f.endswith(('.mp4', '.mov')):
                            fp = os.path.join(DOWNLOAD_DIR, f)
                            if os.path.getsize(fp) > 1000:
                                return {"success": True, "file_path": fp, "is_video": False}
        except:
            pass
        return {"success": False}
    
    # ═══════════════════════════
    # 🎵 AUDIO
    # ═══════════════════════════
    
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
            
            # Check audio
            probe = subprocess.run(
                ['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_entries', 'stream=codec_type', '-of', 'csv=p=0', video_path],
                capture_output=True, text=True, timeout=30
            )
            
            if not probe.stdout.strip():
                return {"success": False, "error": "❌ No audio track in video"}
            
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
    
    await update.message.reply_text(
        "📥 **Instagram Downloader Bot**\n\n"
        "✅ **Reel link** → Full HD Video + Audio 🎬\n"
        "✅ **Post link** → HD Photo(s) 📸\n"
        "✅ **Multiple photos** → All photos 1 by 1 🔄\n"
        "✅ **Audio button** → Name it → Instant MP3 ⚡\n\n"
        "**Just send the Instagram link!** 🔗",
        parse_mode="Markdown"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.id
    if user not in AUTHORIZED_USERS:
        return
    
    text = update.message.text
    if not text:
        return
    
    # Audio name input
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
        await update.message.reply_text("❌ Could not extract URL from text")
        return
    
    context.user_data['current_url'] = url
    shortcode = InstaDownloader.get_shortcode(url)
    
    msg = await update.message.reply_text("⏳ **Processing...**", parse_mode="Markdown")
    
    try:
        is_reel = '/reel/' in url or '/tv/' in url
        
        await msg.edit_text("📥 **Downloading Video...**" if is_reel else "📥 **Downloading Photo...**")
        
        result = InstaDownloader.download_media(url)
        
        if not result.get("success"):
            error = result.get('error', 'Unknown error')
            await msg.edit_text(
                f"❌ **Failed!**\n\n{error}\n\n"
                f"💡 **Try:**\n"
                f"1. Make fresh cookies.txt\n"
                f"2. Upload to GitHub\n"
                f"3. Redeploy on Railway",
                parse_mode="Markdown"
            )
            return
        
        # Multiple photos
        if result.get("is_multiple"):
            photo_paths = result.get("file_paths", [])
            await msg.edit_text(f"📤 **Uploading {len(photo_paths)} photos...**")
            for i, fp in enumerate(photo_paths):
                if os.path.exists(fp) and os.path.getsize(fp) > 1000:
                    try:
                        with open(fp, 'rb') as f:
                            await update.message.reply_photo(
                                photo=f,
                                caption=f"✅ **Photo {i+1}/{len(photo_paths)}** ✅\n🔗 [View on Instagram]({url})",
                                parse_mode="Markdown"
                            )
                    except Exception as e:
                        await update.message.reply_text(f"❌ Photo {i+1} error: {str(e)[:50]}")
                    InstaDownloader.cleanup(fp)
            await msg.delete()
            return
        
        # Single file
        fp = result["file_path"]
        if not os.path.exists(fp) or os.path.getsize(fp) < 1000:
            await msg.edit_text("❌ File not found")
            return
        
        size_mb = os.path.getsize(fp) / (1024 * 1024)
        if size_mb > 50:
            await msg.edit_text(f"❌ File too large ({size_mb:.1f}MB)")
            InstaDownloader.cleanup(fp)
            return
        
        is_video = result.get("is_video", False) or fp.endswith(('.mp4', '.mov', '.webm'))
        
        if is_video:
            await msg.edit_text("📤 **Uploading Video...**")
            keyboard = [[InlineKeyboardButton("🎵 Download Audio", callback_data="get_audio")]]
            
            with open(fp, 'rb') as f:
                await update.message.reply_video(
                    video=f,
                    caption=f"✅ **Video + Audio** ✅\n🔗 [View on Instagram]({url})",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    supports_streaming=True
                )
            await msg.delete()
        else:
            await msg.edit_text("📤 **Uploading Photo...**")
            with open(fp, 'rb') as f:
                await update.message.reply_photo(
                    photo=f,
                    caption=f"✅ **Photo Downloaded** ✅\n🔗 [View on Instagram]({url})",
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
    status_msg = await update.message.reply_text(f"🎵 **Extracting Audio: {audio_name}...**", parse_mode="Markdown")
    
    try:
        result = InstaDownloader.download_media(url)
        if not result.get("success"):
            await status_msg.edit_text("❌ Video download failed")
            return
        
        vp = result["file_path"]
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
            await status_msg.edit_text(f"❌ {audio_result.get('error')}")
        
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
            "Ya: `skip`\n\n"
            "⬇️ **Type karo:**",
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
    ffmpeg = shutil.which('ffmpeg')
    if ffmpeg:
        print(f"✅ FFmpeg: {ffmpeg}")
    else:
        print("⚠️ Installing FFmpeg...")
        os.system('apt-get update && apt-get install ffmpeg -y 2>/dev/null')
        print("✅ FFmpeg installed" if shutil.which('ffmpeg') else "❌ FFmpeg failed")
    
    # cookies.txt
    if os.path.exists('cookies.txt'):
        content = open('cookies.txt').read()
        lines = [l for l in content.split('\n') if l and not l.startswith('#')]
        print(f"✅ cookies.txt: {len(lines)} cookies")
        if 'sessionid' in content:
            print("✅ sessionid ✅")
    else:
        print("ℹ️ cookies.txt missing (photos will use og:image method)")
    
    # Cleanup
    for f in os.listdir(DOWNLOAD_DIR):
        try: os.remove(os.path.join(DOWNLOAD_DIR, f))
        except: pass
    
    print("✅ Bot Started! 🚀")
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    app.run_polling()

if __name__ == "__main__":
    main()
