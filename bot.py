import logging
import os
import re
import subprocess
import shutil
import json
import urllib.parse
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.error import TimedOut
import yt_dlp
import requests

# ══════════════════════════════════════
# 🔐 CONFIG
# ══════════════════════════════════════

BOT_TOKEN = "8518787964:AAHGimBKXfdtrI6UaASGsoI8Aj5Rj_WxF5I"
AUTHORIZED_USERS = [1987818347]

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ══════════════════════════════════════
# 📥 DOWNLOAD ENGINE — FIXED
# ══════════════════════════════════════

class InstaDownloader:
    @staticmethod
    def is_instagram_url(text):
        return bool(re.search(r'(https?://)?(www\.)?(instagram\.com|instagr\.am)/(p|reel|tv|stories|s)/[a-zA-Z0-9_\-]+', text))
    
    @staticmethod
    def extract_url(text):
        m = re.search(r'(https?://)?(www\.)?(instagram\.com|instagr\.am)/(p|reel|tv|stories|s)/[a-zA-Z0-9_\-]+/?', text)
        if m:
            url = m.group(0)
            return 'https://' + url if not url.startswith('http') else url
        return None

    @staticmethod
    def get_shortcode(url):
        """Extract shortcode from Instagram URL"""
        m = re.search(r'/(p|reel|tv)/([a-zA-Z0-9_\-]+)', url)
        return m.group(2) if m else None

    @staticmethod
    def load_cookies_dict():
        """Load cookies.txt as dictionary"""
        cookies = {}
        if not os.path.exists('cookies.txt'):
            return cookies
        try:
            with open('cookies.txt', 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    parts = line.split('\t')
                    if len(parts) >= 7:
                        name = parts[5]
                        value = parts[6]
                        cookies[name] = value
        except:
            pass
        return cookies

    @staticmethod
    def get_headers():
        return {
            'User-Agent': 'Mozilla/5.0 (Linux; Android 13; SM-S908B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
        }

    @staticmethod
    def download_media(url):
        """Main download — photo/video both"""
        shortcode = InstaDownloader.get_shortcode(url)
        if not shortcode:
            return {"success": False, "error": "Invalid URL"}
        
        # ⭐ CHECK IF IT'S VIDEO OR PHOTO FIRST
        is_reel = '/reel/' in url or '/tv/' in url
        
        if is_reel:
            # VIDEO — yt-dlp with best quality (video+audio combined)
            return InstaDownloader._download_video(url, shortcode)
        else:
            # PHOTO — Direct API scraping (more reliable than yt-dlp for photos)
            return InstaDownloader._download_photo(shortcode)

    # ══════════════════════════════════
    # 🎬 VIDEO DOWNLOAD (WITH AUDIO)
    # ══════════════════════════════════

    @staticmethod
    def _download_video(url, shortcode):
        """Download Instagram Reel with audio"""
        try:
            if not os.path.exists('cookies.txt'):
                return {"success": False, "error": "❌ cookies.txt not found!\n\n💡 Chrome extension se cookies.txt banao aur GitHub pe upload karo"}
            
            # ⭐ FIX: Use 'best' format — yeh single file me video+audio dono lata hai
            # Agar 'best' fail ho to 'bestvideo+bestaudio' try karo
            formats_to_try = [
                'best',                    # Best single file (video+audio combined)
                'best[ext=mp4]',           # Best mp4 with audio
                'bestvideo+bestaudio',     # Separate streams (ffmpeg merge)
            ]
            
            for fmt in formats_to_try:
                try:
                    ydl_opts = {
                        'quiet': True,
                        'no_warnings': True,
                        'ignoreerrors': True,
                        'outtmpl': os.path.join(DOWNLOAD_DIR, f'{shortcode}.%(ext)s'),
                        'format': fmt,
                        'cookiefile': 'cookies.txt',
                        'merge_output_format': 'mp4',
                        'postprocessors': [{
                            'key': 'FFmpegVideoConvertor',
                            'preferedformat': 'mp4',
                        }],
                    }
                    
                    # Agar ffmpeg available hai to use karo
                    if shutil.which('ffmpeg'):
                        ydl_opts['ffmpeg_location'] = shutil.which('ffmpeg')
                    
                    print(f"🎬 Trying format: {fmt}")
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=True)
                        if info:
                            # Find downloaded file
                            file_path = None
                            for f in os.listdir(DOWNLOAD_DIR):
                                if shortcode in f and f.endswith('.mp4'):
                                    file_path = os.path.join(DOWNLOAD_DIR, f)
                                    break
                            
                            if file_path and os.path.getsize(file_path) > 5000:
                                # ✅ VERIFY: Check if audio exists in video
                                probe_cmd = [
                                    'ffprobe', '-v', 'error', 
                                    '-select_streams', 'a:0', 
                                    '-show_entries', 'stream=codec_type', 
                                    '-of', 'csv=p=0', 
                                    file_path
                                ]
                                probe = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=30)
                                
                                has_audio = bool(probe.stdout.strip())
                                print(f"✅ Video found: {file_path} | Audio: {has_audio}")
                                
                                if has_audio:
                                    return {"success": True, "file_path": file_path, "is_video": True}
                                else:
                                    # ⭐ Video without audio — delete and try next format
                                    print(f"⚠️ No audio in {fmt}, trying next format")
                                    try: os.remove(file_path)
                                    except: pass
                                    continue
                except Exception as e:
                    print(f"⚠️ Format {fmt} failed: {e}")
                    continue
            
            # ⭐ FINAL FALLBACK: Direct API se video download
            print("🔄 Trying direct API for video...")
            return InstaDownloader._download_video_api(url, shortcode)
            
        except Exception as e:
            print(f"❌ Video error: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def _download_video_api(url, shortcode):
        """Direct Instagram API for video"""
        try:
            cookies = InstaDownloader.load_cookies_dict()
            headers = InstaDownloader.get_headers()
            
            # Get page
            page_url = f"https://www.instagram.com/p/{shortcode}/"
            resp = requests.get(page_url, headers=headers, cookies=cookies, timeout=15)
            
            # Find video URL in page
            # Method 1: video_url in JSON
            video_urls = re.findall(r'"video_url":"([^"]+)"', resp.text)
            if video_urls:
                video_url = video_urls[0].replace('\\u0026', '&')
                if video_url.startswith('//'):
                    video_url = 'https:' + video_url
                
                file_path = os.path.join(DOWNLOAD_DIR, f"{shortcode}.mp4")
                vr = requests.get(video_url, headers=headers, stream=True, timeout=60)
                with open(file_path, 'wb') as f:
                    for chunk in vr.iter_content(chunk_size=8192):
                        if chunk: f.write(chunk)
                
                if os.path.getsize(file_path) > 5000:
                    print(f"✅ Video downloaded via API: {file_path}")
                    return {"success": True, "file_path": file_path, "is_video": True}
            
            return {"success": False, "error": "Video download failed"}
        except Exception as e:
            return {"success": False, "error": f"API error: {e}"}

    # ══════════════════════════════════
    # 📸 PHOTO DOWNLOAD (FULL FIX)
    # ══════════════════════════════════

    @staticmethod
    def _download_photo(shortcode):
        """Download Instagram photo using direct page scraping"""
        try:
            if not os.path.exists('cookies.txt'):
                return {"success": False, "error": "❌ cookies.txt not found!"}
            
            cookies = InstaDownloader.load_cookies_dict()
            headers = InstaDownloader.get_headers()
            
            if not cookies.get('sessionid'):
                return {"success": False, "error": "❌ cookies.txt me 'sessionid' nahi hai! Naya cookies.txt banao."}
            
            print(f"📸 Fetching photo: {shortcode}")
            
            # Page URL
            page_url = f"https://www.instagram.com/p/{shortcode}/"
            resp = requests.get(page_url, headers=headers, cookies=cookies, timeout=15)
            
            if resp.status_code != 200:
                return {"success": False, "error": f"HTTP {resp.status_code}"}
            
            html = resp.text
            
            # ⭐ METHOD 1: JSON data from page
            image_urls = []
            
            # Try to find __NEXT_DATA__ (new Instagram)
            next_data = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.DOTALL)
            if next_data:
                try:
                    data = json.loads(next_data.group(1))
                    # Extract from __NEXT_DATA__
                    def extract_images(obj):
                        urls = []
                        if isinstance(obj, dict):
                            if obj.get('__typename') == 'GraphImage' and obj.get('display_url'):
                                urls.append(obj['display_url'])
                            if 'display_url' in obj and obj['display_url']:
                                urls.append(obj['display_url'])
                            for key, val in obj.items():
                                if key in ('display_url', 'display_src', 'src'):
                                    if isinstance(val, str) and val.startswith('http'):
                                        urls.append(val)
                                else:
                                    urls.extend(extract_images(val))
                        elif isinstance(obj, list):
                            for item in obj:
                                urls.extend(extract_images(item))
                        return urls
                    
                    image_urls = extract_images(data)
                except:
                    pass
            
            # ⭐ METHOD 2: Shared data
            if not image_urls:
                shared = re.search(r'window\._sharedData\s*=\s*({.*?});', html, re.DOTALL)
                if shared:
                    try:
                        data = json.loads(shared.group(1))
                        entries = data.get('entry_data', {}).get('PostPage', [])
                        for entry in entries:
                            media = entry.get('graphql', {}).get('shortcode_media', {})
                            if media.get('display_url'):
                                image_urls.append(media['display_url'])
                            # Carousel
                            edges = media.get('edge_sidecar_to_children', {}).get('edges', [])
                            for edge in edges:
                                node = edge.get('node', {})
                                if node.get('display_url'):
                                    image_urls.append(node['display_url'])
                    except:
                        pass
            
            # ⭐ METHOD 3: Regex display_url
            if not image_urls:
                urls = re.findall(r'"display_url":"([^"]+)"', html)
                for u in urls:
                    u = u.replace('\\u0026', '&')
                    if u not in image_urls:
                        image_urls.append(u)
            
            # ⭐ METHOD 4: og:image
            if not image_urls:
                og = re.findall(r'<meta property="og:image" content="([^"]+)"', html)
                for u in og:
                    if u not in image_urls:
                        image_urls.append(u)
            
            if not image_urls:
                return {"success": False, "error": "❌ Photo URL nahi mila!\n\n💡 cookies.txt expire ho gayi? Naya cookies.txt banao."}
            
            # ⭐ DOWNLOAD Images
            downloaded = []
            for i, img_url in enumerate(image_urls[:10]):
                try:
                    if img_url.startswith('//'):
                        img_url = 'https:' + img_url
                    
                    # Clean URL
                    img_url = img_url.split('?')[0]
                    
                    # Determine extension
                    ext = 'jpg'
                    if '.png' in img_url:
                        ext = 'png'
                    elif '.webp' in img_url:
                        ext = 'webp'
                    
                    file_name = f"{shortcode}_{i+1}.{ext}" if len(image_urls) > 1 else f"{shortcode}.{ext}"
                    file_path = os.path.join(DOWNLOAD_DIR, file_name)
                    
                    print(f"📥 Downloading photo {i+1}: {img_url[:50]}...")
                    
                    img_headers = {
                        'User-Agent': 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36',
                        'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
                        'Referer': 'https://www.instagram.com/',
                    }
                    
                    ir = requests.get(img_url, headers=img_headers, stream=True, timeout=30)
                    if ir.status_code == 200:
                        with open(file_path, 'wb') as f:
                            for chunk in ir.iter_content(chunk_size=8192):
                                if chunk: f.write(chunk)
                        
                        if os.path.exists(file_path) and os.path.getsize(file_path) > 1000:
                            downloaded.append(file_path)
                            print(f"✅ Photo {i+1} saved: {os.path.getsize(file_path)} bytes")
                except Exception as e:
                    print(f"⚠️ Error downloading photo {i+1}: {e}")
                    continue
            
            if downloaded:
                if len(downloaded) == 1:
                    return {"success": True, "file_path": downloaded[0], "is_video": False}
                else:
                    return {"success": True, "file_paths": downloaded, "is_video": False, "is_multiple": True}
            
            return {"success": False, "error": "❌ Photo download nahi hua"}
            
        except Exception as e:
            print(f"❌ Photo error: {e}")
            return {"success": False, "error": str(e)}

    # ══════════════════════════════════
    # 🎵 AUDIO EXTRACTION
    # ══════════════════════════════════

    @staticmethod
    def extract_audio(video_path, custom_name=None):
        """Extract audio with custom name"""
        try:
            # Audio file path
            if custom_name:
                safe_name = re.sub(r'[^\w\s-]', '', custom_name).strip()[:50]
                if not safe_name:
                    safe_name = "Instagram_Audio"
                file_name = f"{safe_name}.mp3"
            else:
                base = os.path.splitext(os.path.basename(video_path))[0]
                file_name = f"{base}.mp3"
            
            audio_path = os.path.join(DOWNLOAD_DIR, file_name)
            
            # Check if ffmpeg is available
            if not shutil.which('ffmpeg'):
                return {"success": False, "error": "❌ FFmpeg nahi mila! Install karo:\n`sudo apt install ffmpeg -y`"}
            
            # Check audio exists
            probe_cmd = ['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_entries', 'stream=codec_type', '-of', 'csv=p=0', video_path]
            probe = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=30)
            
            if not probe.stdout.strip():
                return {"success": False, "error": "❌ Is video main audio track nahi hai!"}
            
            # Extract audio
            cmd = ['ffmpeg', '-i', video_path, '-vn', '-acodec', 'libmp3lame', '-ab', '192k', '-ar', '44100', '-y', audio_path]
            process = subprocess.run(cmd, capture_output=True, timeout=180)
            
            if os.path.exists(audio_path) and os.path.getsize(audio_path) > 1000:
                print(f"✅ Audio extracted: {audio_path} ({os.path.getsize(audio_path)} bytes)")
                return {"success": True, "file_path": audio_path}
            
            return {"success": False, "error": "❌ Audio extract fail hua"}
            
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "❌ Timeout! File bahut badi hai"}
        except Exception as e:
            return {"success": False, "error": f"❌ Error: {str(e)}"}
    
    @staticmethod
    def cleanup(file_path):
        """Clean up downloaded files"""
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
                print(f"🗑️ Deleted: {file_path}")
        except:
            pass
    
    @staticmethod
    def cleanup_dir():
        """Clean entire download directory"""
        try:
            for f in os.listdir(DOWNLOAD_DIR):
                fp = os.path.join(DOWNLOAD_DIR, f)
                try: os.remove(fp)
                except: pass
        except:
            pass

# ══════════════════════════════════════
# 🤖 TELEGRAM HANDLERS
# ══════════════════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.id
    if user not in AUTHORIZED_USERS:
        await update.message.reply_text("❌ Unauthorized")
        return
    
    await update.message.reply_text(
        "📥 **Instagram Downloader Bot**\n\n"
        "✅ **Reel link** → Video (with audio) 🎬\n"
        "✅ **Post link** → High Quality Photo 📸\n"
        "✅ **Multiple photos** → Ek ek karke 🖼️\n"
        "✅ **Audio button** → Click → Naam do → MP3 ⚡\n\n"
        "**Example:**\n"
        "`https://www.instagram.com/reel/xyz123/`\n"
        "`https://www.instagram.com/p/xyz123/`\n\n"
        "🔹 **Try karo!** Bas link paste karo.",
        parse_mode="Markdown"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.id
    if user not in AUTHORIZED_USERS:
        return
    
    text = update.message.text
    if not text:
        return
    
    # ⭐ Check if user is giving audio name
    if context.user_data.get('awaiting_audio'):
        context.user_data['awaiting_audio'] = False
        audio_name = text.strip()
        context.user_data['audio_name'] = audio_name
        
        # Start audio extraction immediately
        url = context.user_data.get('current_url')
        if url:
            await extract_and_send_audio(update, context, url, audio_name)
        return
    
    # Check Instagram URL
    if not InstaDownloader.is_instagram_url(text):
        return
    
    url = InstaDownloader.extract_url(text)
    if not url:
        await update.message.reply_text("❌ Invalid URL")
        return
    
    # Store URL for audio extraction
    context.user_data['current_url'] = url
    
    msg = await update.message.reply_text("⏳ **Processing...**", parse_mode="Markdown")
    
    try:
        shortcode = InstaDownloader.get_shortcode(url)
        is_reel = '/reel/' in url or '/tv/' in url
        
        if is_reel:
            await msg.edit_text("📥 **Downloading Reel Video...**")
        else:
            await msg.edit_text("📥 **Downloading Photo...**")
        
        result = InstaDownloader.download_media(url)
        
        if not result.get("success"):
            error_msg = result.get('error', 'Unknown error')
            await msg.edit_text(
                f"❌ **Failed!**\n\n{error_msg}\n\n"
                f"💡 **Solution:**\n"
                f"1. cookies.txt expire ho gayi?\n"
                f"2. Instagram se logout → login karein\n"
                f"3. Chrome extension se naya cookies.txt banao\n"
                f"4. GitHub par cookies.txt update karo\n"
                f"5. Railway redeploy karo",
                parse_mode="Markdown"
            )
            return
        
        # ⭐ MULTIPLE PHOTOS
        if result.get("is_multiple"):
            photo_paths = result.get("file_paths", [])
            if photo_paths:
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
        
        # ⭐ SINGLE FILE
        fp = result["file_path"]
        if not os.path.exists(fp) or os.path.getsize(fp) < 1000:
            await msg.edit_text("❌ Download incomplete (file too small)")
            return
        
        file_size = os.path.getsize(fp)
        if file_size > 50 * 1024 * 1024:
            await msg.edit_text("❌ File >50MB — Telegram limit")
            InstaDownloader.cleanup(fp)
            return
        
        is_video = result.get("is_video", False) or fp.endswith(('.mp4', '.mov', '.webm'))
        
        if is_video:
            await msg.edit_text("📤 **Uploading Video...**")
            keyboard = [[InlineKeyboardButton("🎵 Download Audio", callback_data=f"get_audio")]]
            
            with open(fp, 'rb') as f:
                await update.message.reply_video(
                    video=f,
                    caption=f"✅ **Video Downloaded** ✅\n🔗 [Instagram Link]({url})\n\n🎵 Audio ke liye neeche button dabao",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    supports_streaming=True,
                    read_timeout=60,
                    write_timeout=60,
                    connect_timeout=60,
                    pool_timeout=60
                )
            await msg.delete()
        else:
            await msg.edit_text("📤 **Uploading Photo...**")
            with open(fp, 'rb') as f:
                await update.message.reply_photo(
                    photo=f,
                    caption=f"✅ **Photo Downloaded** ✅\n🔗 [Instagram Link]({url})",
                    parse_mode="Markdown",
                    read_timeout=60,
                    write_timeout=60,
                    connect_timeout=60,
                    pool_timeout=60
                )
            await msg.delete()
        
        # Cleanup
        InstaDownloader.cleanup(fp)
        
    except TimedOut:
        await msg.edit_text("⏰ **Timeout!** Dobara try karo.")
    except Exception as e:
        await msg.edit_text(f"❌ **Error:** {str(e)}")
        InstaDownloader.cleanup_dir()

async def extract_and_send_audio(update, context, url, audio_name):
    """Extract audio and send immediately"""
    status_msg = await update.message.reply_text(f"🎵 **Extracting Audio: {audio_name}...**", parse_mode="Markdown")
    
    try:
        # Download video
        result = InstaDownloader.download_media(url)
        if not result.get("success"):
            await status_msg.edit_text("❌ Video download fail hua. Audio extract nahi ho paya.")
            return
        
        vp = result["file_path"]
        
        # Extract audio
        audio_result = InstaDownloader.extract_audio(vp, audio_name)
        
        if audio_result.get("success"):
            ap = audio_result["file_path"]
            await status_msg.edit_text("📤 **Uploading Audio...**")
            try:
                with open(ap, 'rb') as f:
                    await update.message.reply_audio(
                        audio=f,
                        title=audio_name,
                        performer="Instagram",
                        caption=f"🎵 **{audio_name}** ✅",
                        read_timeout=60,
                        write_timeout=60
                    )
                await status_msg.edit_text(f"✅ **{audio_name}** sent! 🎵")
            except Exception as e:
                await status_msg.edit_text(f"❌ Send error: {str(e)}")
            try: os.remove(ap)
            except: pass
        else:
            await status_msg.edit_text(f"❌ {audio_result.get('error')}")
        
        InstaDownloader.cleanup(vp)
        
    except Exception as e:
        await status_msg.edit_text(f"❌ Error: {str(e)}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "get_audio":
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            "🎵 **Audio Ka Naam Likhein** 🎵\n\n"
            "Jaise: `Meri Pyaari Song`\n"
            "Ya: `skip` (default naam ke liye)\n\n"
            "⬇️ **Neeche type karein:**",
            parse_mode="Markdown"
        )
        context.user_data['awaiting_audio'] = True

# ══════════════════════════════════════
# 🚀 MAIN
# ══════════════════════════════════════

def main():
    logging.basicConfig(level=logging.INFO)
    
    print("╔══════════════════════════════╗")
    print("║  🤖 INSTAGRAM DOWNLOADER    ║")
    print("╚══════════════════════════════╝")
    
    # Check FFmpeg
    ffmpeg_path = shutil.which('ffmpeg')
    if ffmpeg_path:
        print(f"✅ FFmpeg: {ffmpeg_path}")
    else:
        print("⚠️ FFmpeg not found!")
        print("   Installing ffmpeg...")
        os.system('apt-get update && apt-get install ffmpeg -y')
        if shutil.which('ffmpeg'):
            print("✅ FFmpeg installed!")
        else:
            print("❌ FFmpeg installation failed")
    
    # Check cookies.txt
    if os.path.exists('cookies.txt'):
        print(f"✅ cookies.txt found ({os.path.getsize('cookies.txt')} bytes)")
        with open('cookies.txt') as f:
            content = f.read()
        if 'sessionid' in content:
            print("✅ sessionid found — cookies are valid!")
        else:
            print("⚠️ sessionid missing — cookies expired!")
    else:
        print("❌ cookies.txt NOT FOUND!")
        print("   Create cookies.txt using Chrome extension!")
    
    # Clean download directory
    InstaDownloader.cleanup_dir()
    print("✅ Download directory cleaned")
    
    print("✅ Bot Started! 🚀")
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    app.run_polling()

if __name__ == "__main__":
    main()
