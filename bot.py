import logging
import os
import re
import subprocess
import shutil
import time
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
# 📥 DOWNLOAD ENGINE
# ═══════════════════════════

class InstaDownloader:
    
    @staticmethod
    def is_instagram_url(text):
        """Check if text contains Instagram URL"""
        if not text:
            return False
        patterns = [
            r'instagram\.com/(p|reel|tv)/[a-zA-Z0-9_\-]+',
            r'instagr\.am/(p|reel|tv)/[a-zA-Z0-9_\-]+',
        ]
        return any(re.search(p, text) for p in patterns)
    
    @staticmethod
    def extract_url(text):
        """Extract clean Instagram URL from text"""
        if not text:
            return None
        
        # Pattern to find Instagram URL
        m = re.search(r'(https?://)?(www\.)?(instagram\.com|instagr\.am)/(p|reel|tv)/([a-zA-Z0-9_\-]+)', text)
        if m:
            domain = m.group(3)  # instagram.com or instagr.am
            post_type = m.group(4)  # p, reel, or tv
            shortcode = m.group(5)  # the actual post/reel ID
            
            url = f"https://www.{domain}/{post_type}/{shortcode}/"
            return url
        
        return None
    
    @staticmethod
    def get_shortcode(url):
        """Extract shortcode from URL"""
        m = re.search(r'/(p|reel|tv)/([a-zA-Z0-9_\-]+)', url)
        return m.group(2) if m else None
    
    # ═══════════════════════════
    # 🎬 MAIN DOWNLOAD
    # ═══════════════════════════
    
    @staticmethod
    def download_media(url):
        """Detect video/photo and download"""
        shortcode = InstaDownloader.get_shortcode(url)
        if not shortcode:
            return {"success": False, "error": "Shortcode not found"}
        
        is_reel = '/reel/' in url or '/tv/' in url
        
        if is_reel:
            print(f"🎬 Downloading Reel: {shortcode}")
            return InstaDownloader._download_video(url, shortcode)
        else:
            print(f"📸 Downloading Photo: {shortcode}")
            return InstaDownloader._download_photo(shortcode)
    
    # ═══════════════════════════
    # 🎬 VIDEO DOWNLOAD
    # ═══════════════════════════
    
    @staticmethod
    def _download_video(url, shortcode):
        """Download video with audio"""
        try:
            # Simple best format
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'outtmpl': os.path.join(DOWNLOAD_DIR, f'{shortcode}.%(ext)s'),
                'format': 'best[ext=mp4]/best',
            }
            
            # Add cookies if available
            if os.path.exists('cookies.txt'):
                ydl_opts['cookiefile'] = 'cookies.txt'
                print("✅ Using cookies.txt")
            else:
                print("⚠️ No cookies.txt - video may fail")
            
            # FFmpeg for merging if needed
            if shutil.which('ffmpeg'):
                ydl_opts['ffmpeg_location'] = shutil.which('ffmpeg')
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                
                if not info:
                    return {"success": False, "error": "No info from Instagram"}
                
                # Find downloaded file
                file_path = None
                for f in os.listdir(DOWNLOAD_DIR):
                    if shortcode in f:
                        file_path = os.path.join(DOWNLOAD_DIR, f)
                        break
                
                # If not found by shortcode, get most recent mp4
                if not file_path or not os.path.exists(file_path):
                    mp4_files = [f for f in os.listdir(DOWNLOAD_DIR) if f.endswith('.mp4')]
                    if mp4_files:
                        mp4_files.sort(key=lambda x: os.path.getmtime(os.path.join(DOWNLOAD_DIR, x)), reverse=True)
                        file_path = os.path.join(DOWNLOAD_DIR, mp4_files[0])
                
                if file_path and os.path.exists(file_path) and os.path.getsize(file_path) > 5000:
                    print(f"✅ Video: {os.path.basename(file_path)} ({os.path.getsize(file_path)} bytes)")
                    
                    # Check if audio present
                    probe = subprocess.run(
                        ['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_entries', 'stream=codec_type', '-of', 'csv=p=0', file_path],
                        capture_output=True, text=True, timeout=30
                    )
                    has_audio = bool(probe.stdout.strip())
                    print(f"🎵 Audio: {'✅' if has_audio else '❌'}")
                    
                    return {"success": True, "file_path": file_path, "is_video": True}
                
                return {"success": False, "error": "File not found after download"}
                
        except Exception as e:
            error_msg = str(e)
            print(f"❌ Video error: {error_msg[:100]}")
            if 'HTTP Error 403' in error_msg or 'HTTP Error 401' in error_msg:
                return {"success": False, "error": "❌ cookies.txt expire ho gayi. Naya banao!"}
            if 'ffmpeg' in error_msg.lower():
                return {"success": False, "error": "FFmpeg missing. apt install ffmpeg"}
            return {"success": False, "error": f"Error: {error_msg[:80]}"}
    
    # ═══════════════════════════
    # 📸 PHOTO DOWNLOAD
    # ═══════════════════════════
    
    @staticmethod
    def _download_photo(shortcode):
        """Photo download - 3 methods"""
        
        # Method 1: oEmbed API (no cookies needed)
        print(f"📸 Method 1: oEmbed API")
        result = InstaDownloader._oembed_photo(shortcode)
        if result.get("success"):
            return result
        
        # Method 2: yt-dlp
        print(f"📸 Method 2: yt-dlp")
        result = InstaDownloader._ytdlp_photo(shortcode)
        if result.get("success"):
            return result
        
        # Method 3: Direct scrape
        print(f"📸 Method 3: Direct scrape")
        result = InstaDownloader._scrape_photo(shortcode)
        if result.get("success"):
            return result
        
        return {"success": False, "error": "Photo download failed"}
    
    @staticmethod
    def _oembed_photo(shortcode):
        """oEmbed API - public, no cookies needed"""
        try:
            url = f"https://www.instagram.com/p/{shortcode}/"
            api_url = f"https://api.instagram.com/oembed?url={url}"
            
            resp = requests.get(api_url, timeout=15)
            if resp.status_code != 200:
                return {"success": False}
            
            data = resp.json()
            thumbnail = data.get('thumbnail_url', '')
            if not thumbnail:
                return {"success": False}
            
            print(f"🔗 oEmbed URL: {thumbnail[:60]}...")
            
            # Get HD version
            hd_url = re.sub(r'/s\d+x\d+/', '/', thumbnail)
            hd_url = hd_url.split('?')[0]
            
            # Download
            headers = {
                'User-Agent': 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36',
                'Accept': 'image/*',
                'Referer': 'https://www.instagram.com/',
            }
            
            # Try HD first
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
            
        except Exception as e:
            print(f"⚠️ oEmbed error: {e}")
        
        return {"success": False}
    
    @staticmethod
    def _ytdlp_photo(shortcode):
        """yt-dlp for photo"""
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
                        if shortcode in f and not f.endswith('.mp4') and not f.endswith('.mov'):
                            fp = os.path.join(DOWNLOAD_DIR, f)
                            if os.path.getsize(fp) > 1000:
                                return {"success": True, "file_path": fp, "is_video": False}
        except:
            pass
        return {"success": False}
    
    @staticmethod
    def _scrape_photo(shortcode):
        """Direct page scrape"""
        try:
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
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml',
            }
            
            page_url = f"https://www.instagram.com/p/{shortcode}/"
            resp = requests.get(page_url, headers=headers, cookies=cookies, timeout=15)
            html = resp.text
            
            # Find image URLs
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
                urls = re.findall(r'"display_src":"([^"]+)"', html)
                for u in urls:
                    image_urls.append(u.replace('\\u0026', '&'))
            
            if not image_urls:
                og = re.findall(r'<meta property="og:image" content="([^"]+)"', html)
                image_urls = og
            
            if not image_urls:
                return {"success": False}
            
            # Download images
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
            
        except Exception as e:
            print(f"⚠️ Scrape error: {e}")
        
        return {"success": False}
    
    # ═══════════════════════════
    # 🎵 AUDIO EXTRACTION
    # ═══════════════════════════
    
    @staticmethod
    def extract_audio(video_path, custom_name=None):
        try:
            if custom_name:
                safe_name = re.sub(r'[^\w\s-]', '', custom_name).strip()[:50] or "Instagram_Audio"
                audio_path = os.path.join(DOWNLOAD_DIR, f"{safe_name}.mp3")
            else:
                base = os.path.splitext(os.path.basename(video_path))[0]
                audio_path = os.path.join(DOWNLOAD_DIR, f"{base}.mp3")
            
            ffmpeg = shutil.which('ffmpeg')
            if not ffmpeg:
                return {"success": False, "error": "FFmpeg nahi mila"}
            
            # Check audio exists
            probe = subprocess.run(
                ['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_entries', 'stream=codec_type', '-of', 'csv=p=0', video_path],
                capture_output=True, text=True, timeout=30
            )
            
            if not probe.stdout.strip():
                return {"success": False, "error": "❌ Video mein audio nahi hai"}
            
            cmd = ['ffmpeg', '-i', video_path, '-vn', '-acodec', 'libmp3lame', '-ab', '192k', '-y', audio_path]
            subprocess.run(cmd, capture_output=True, timeout=180)
            
            if os.path.exists(audio_path) and os.path.getsize(audio_path) > 1000:
                return {"success": True, "file_path": audio_path}
            
            return {"success": False, "error": "Audio extract fail"}
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
        await update.message.reply_text("❌ Unauthorized")
        return
    
    await update.message.reply_text(
        "📥 **Instagram Downloader Bot**\n\n"
        "✅ **Reel** → Video + Audio 🎬\n"
        "✅ **Post** → Photo(s) 📸\n"
        "✅ **Multiple photos** → 1-1 karke 🔄\n"
        "✅ **Audio button** → Naam do → MP3 ⚡\n\n"
        "**Bus link bhejo!** ✅",
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
        await update.message.reply_text("❌ Invalid URL format")
        return
    
    context.user_data['current_url'] = url
    
    msg = await update.message.reply_text("⏳ **Processing...**", parse_mode="Markdown")
    
    try:
        is_reel = '/reel/' in url or '/tv/' in url
        
        await msg.edit_text("📥 **Downloading Video...**" if is_reel else "📥 **Downloading Photo...**")
        
        result = InstaDownloader.download_media(url)
        
        if not result.get("success"):
            error_text = result.get('error', 'Unknown error')
            await msg.edit_text(
                f"❌ **Failed!**\n\n{error_text}\n\n"
                f"💡 **Solutions:**\n"
                f"• Naya cookies.txt banao (Chrome extension)\n"
                f"• GitHub par upload karo\n"
                f"• Railway redeploy karo",
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
                                caption=f"✅ **Photo {i+1}/{len(photo_paths)}** ✅\n🔗 [Instagram Link]({url})",
                                parse_mode="Markdown"
                            )
                    except Exception as e:
                        await update.message.reply_text(f"❌ Error: {str(e)}")
                    InstaDownloader.cleanup(fp)
            await msg.delete()
            return
        
        # Single file
        fp = result["file_path"]
        if not os.path.exists(fp) or os.path.getsize(fp) < 1000:
            await msg.edit_text("❌ File not found")
            return
        
        file_size_mb = os.path.getsize(fp) / (1024 * 1024)
        if file_size_mb > 50:
            await msg.edit_text(f"❌ File too large ({file_size_mb:.1f}MB > 50MB)")
            InstaDownloader.cleanup(fp)
            return
        
        is_video = result.get("is_video", False) or fp.endswith(('.mp4', '.mov', '.webm'))
        
        if is_video:
            await msg.edit_text("📤 **Uploading Video...**")
            keyboard = [[InlineKeyboardButton("🎵 Download Audio", callback_data="get_audio")]]
            
            with open(fp, 'rb') as f:
                await update.message.reply_video(
                    video=f,
                    caption=f"✅ **Video Downloaded** ✅\n🔗 [Instagram Link]({url})",
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
                    caption=f"✅ **Photo Downloaded** ✅\n🔗 [Instagram Link]({url})",
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
            await status_msg.edit_text("❌ Video download fail")
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
            "🎵 **Audio Ka Naam Likhein**\n\n"
            "Jaise: `Meri Song`\n"
            "Ya: `skip`\n\n"
            "⬇️ **Type karein:**",
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
    if shutil.which('ffmpeg'):
        print(f"✅ FFmpeg: {shutil.which('ffmpeg')}")
    else:
        print("⚠️ Installing ffmpeg...")
        os.system('apt-get update && apt-get install ffmpeg -y 2>/dev/null')
        print("✅ Done" if shutil.which('ffmpeg') else "❌ Failed")
    
    # cookies.txt
    if os.path.exists('cookies.txt'):
        print(f"✅ cookies.txt ({os.path.getsize('cookies.txt')} bytes)")
        with open('cookies.txt') as f:
            c = f.read()
        print("✅ sessionid present" if 'sessionid' in c else "⚠️ sessionid missing")
    else:
        print("ℹ️ cookies.txt not found (photos will use oEmbed API)")
    
    # Clean
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
