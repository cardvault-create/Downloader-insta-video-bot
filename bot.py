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
    
    # ═══════════════════════════
    # 🎬 MAIN DOWNLOAD
    # ═══════════════════════════
    
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
            print(f"📸 Downloading Photo(s): {shortcode}")
            return InstaDownloader._download_photos_new(shortcode, url)
    
    # ═══════════════════════════
    # 🎬 VIDEO DOWNLOAD
    # ═══════════════════════════
    
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
                
                if not info:
                    return {"success": False, "error": "No response from Instagram"}
                
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
                    print(f"✅ Video: {os.path.basename(file_path)}")
                    return {"success": True, "file_path": file_path, "is_video": True}
                
                return {"success": False, "error": "File not found"}
                
        except Exception as e:
            err = str(e)
            if 'HTTP Error 403' in err or 'HTTP Error 401' in err:
                return {"success": False, "error": "❌ cookies.txt expired!"}
            return {"success": False, "error": f"❌ {err[:80]}"}
    
    # ═══════════════════════════
    # 📸 NEW PHOTO DOWNLOAD - 100% CAROUSEL SUPPORT
    # ═══════════════════════════
    
    @staticmethod
    def _download_photos_new(shortcode, url):
        """Naya method - Pehle carousel detect karo, phir saari photos download karo"""
        
        # Step 1: Post ka data nikalo using Instagram's embed API
        print("🔍 Step 1: Checking if post has multiple photos...")
        
        # Try Instagram's oEmbed API first (gives media type info)
        carousel_photos = InstaDownloader._get_carousel_photos(shortcode)
        
        if carousel_photos and len(carousel_photos) > 1:
            print(f"📸 Carousel detected! Found {len(carousel_photos)} photos")
            
            # Download all carousel photos
            downloaded = []
            for i, photo_url in enumerate(carousel_photos, 1):
                try:
                    file_name = f"{shortcode}_{i}.jpg"
                    file_path = os.path.join(DOWNLOAD_DIR, file_name)
                    
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                        'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
                        'Referer': 'https://www.instagram.com/',
                    }
                    
                    response = requests.get(photo_url, headers=headers, stream=True, timeout=30)
                    if response.status_code == 200:
                        with open(file_path, 'wb') as f:
                            for chunk in response.iter_content(chunk_size=8192):
                                if chunk: f.write(chunk)
                        
                        if os.path.exists(file_path) and os.path.getsize(file_path) > 1000:
                            downloaded.append(file_path)
                            print(f"✅ Downloaded photo {i}/{len(carousel_photos)}")
                except Exception as e:
                    print(f"⚠️ Error downloading photo {i}: {e}")
                    continue
            
            if downloaded:
                if len(downloaded) > 1:
                    return {
                        "success": True, 
                        "file_paths": sorted(downloaded), 
                        "is_video": False, 
                        "is_multiple": True,
                        "total_photos": len(downloaded)
                    }
                else:
                    return {"success": True, "file_path": downloaded[0], "is_video": False}
        
        # Step 2: Agar carousel nahi mila, to single photo try karo
        print("📸 Single photo post detected")
        return InstaDownloader._download_single_photo(shortcode, url)
    
    @staticmethod
    def _get_carousel_photos(shortcode):
        """Instagram ke embedded post se saari carousel photos nikalo"""
        
        all_photos = []
        
        try:
            # Method 1: Instagram Basic Display API style
            embed_url = f"https://www.instagram.com/p/{shortcode}/?__a=1&__d=1"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'application/json',
                'Accept-Language': 'en-US,en;q=0.9',
                'X-Requested-With': 'XMLHttpRequest',
                'X-IG-App-ID': '936619743392459',
            }
            
            # Add cookies if available
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
            
            response = requests.get(embed_url, headers=headers, cookies=cookies, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                
                # Navigate through Instagram's JSON structure
                def extract_all_photos(obj, depth=0):
                    if depth > 15:
                        return []
                    photos = []
                    
                    if isinstance(obj, dict):
                        # Check for carousel_media (main carousel photos)
                        if 'carousel_media' in obj:
                            carousel = obj['carousel_media']
                            if isinstance(carousel, list):
                                print(f"🎯 Found carousel with {len(carousel)} items")
                                for item in carousel:
                                    if isinstance(item, dict):
                                        # Try different ways to get image URL
                                        # 1. image_versions2
                                        if 'image_versions2' in item:
                                            candidates = item['image_versions2'].get('candidates', [])
                                            if candidates:
                                                # Get highest resolution
                                                photos.append(candidates[0]['url'])
                                        
                                        # 2. Direct in images
                                        elif 'images' in item:
                                            for img_type, img_data in item['images'].items():
                                                if isinstance(img_data, dict) and 'url' in img_data:
                                                    photos.append(img_data['url'])
                                                    break
                                        
                                        # 3. display_url
                                        elif 'display_url' in item:
                                            photos.append(item['display_url'])
                        
                        # Check for edge_sidecar (another carousel format)
                        if 'edge_sidecar_to_children' in obj:
                            edges = obj['edge_sidecar_to_children'].get('edges', [])
                            print(f"🎯 Found edge_sidecar with {len(edges)} items")
                            for edge in edges:
                                node = edge.get('node', {})
                                # Try different image URL locations
                                if 'display_url' in node:
                                    photos.append(node['display_url'])
                                elif 'image_versions2' in node:
                                    candidates = node['image_versions2'].get('candidates', [])
                                    if candidates:
                                        photos.append(candidates[0]['url'])
                        
                        # Recursively search
                        for key, value in obj.items():
                            if key not in ['carousel_media', 'edge_sidecar_to_children']:
                                photos.extend(extract_all_photos(value, depth + 1))
                    
                    elif isinstance(obj, list):
                        for item in obj:
                            photos.extend(extract_all_photos(item, depth + 1))
                    
                    return photos
                
                all_photos = extract_all_photos(data)
                
                if all_photos:
                    # Remove duplicates and clean URLs
                    seen = set()
                    unique_photos = []
                    for url in all_photos:
                        url = url.split('?')[0]  # Remove query parameters
                        if url not in seen and '.mp4' not in url and '.mov' not in url:
                            seen.add(url)
                            unique_photos.append(url)
                    
                    all_photos = unique_photos
                    print(f"📸 Extracted {len(all_photos)} unique photo URLs")
            
            # Method 2: Agar pehla method fail ho, to embed page se try karo
            if not all_photos:
                print("⚠️ Method 1 failed, trying embed page...")
                embed_html_url = f"https://www.instagram.com/p/{shortcode}/embed/captioned"
                html_response = requests.get(embed_html_url, headers=headers, timeout=15)
                
                if html_response.status_code == 200:
                    html = html_response.text
                    
                    # Search for JSON data in script tags
                    json_matches = re.findall(r'<script[^>]*>({.*?})</script>', html, re.DOTALL)
                    
                    for json_str in json_matches:
                        try:
                            data = json.loads(json_str)
                            # Look for carousel data
                            if 'shortcode_media' in data:
                                media = data['shortcode_media']
                                if 'edge_sidecar_to_children' in media:
                                    edges = media['edge_sidecar_to_children']['edges']
                                    for edge in edges:
                                        node = edge['node']
                                        if 'display_url' in node:
                                            all_photos.append(node['display_url'])
                        except:
                            continue
        
        except Exception as e:
            print(f"⚠️ Error getting carousel photos: {e}")
        
        return all_photos
    
    @staticmethod
    def _download_single_photo(shortcode, url):
        """Download single photo using multiple methods"""
        
        # Method 1: yt-dlp
        print("📥 Trying yt-dlp for single photo...")
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'outtmpl': os.path.join(DOWNLOAD_DIR, f'{shortcode}.%(ext)s'),
                'format': 'best[ext=jpg]/best[ext=png]/best[ext=webp]/best',
                'retries': 3,
            }
            if os.path.exists('cookies.txt'):
                ydl_opts['cookiefile'] = 'cookies.txt'
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            time.sleep(1)
            
            for f in os.listdir(DOWNLOAD_DIR):
                if shortcode in f and not f.endswith(('.mp4', '.mov', '.webm', '.gif')):
                    fp = os.path.join(DOWNLOAD_DIR, f)
                    if os.path.exists(fp) and os.path.getsize(fp) > 1000:
                        print(f"✅ Single photo via yt-dlp: {f}")
                        return {"success": True, "file_path": fp, "is_video": False}
        except Exception as e:
            print(f"⚠️ yt-dlp single photo error: {e}")
        
        # Method 2: Direct embed API
        print("📥 Trying embed API for single photo...")
        try:
            embed_url = f"https://www.instagram.com/p/{shortcode}/?__a=1&__d=1"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'X-Requested-With': 'XMLHttpRequest',
            }
            
            response = requests.get(embed_url, headers=headers, timeout=15)
            if response.status_code == 200:
                data = response.json()
                
                # Find display_url in JSON
                def find_url(obj, depth=0):
                    if depth > 10:
                        return None
                    if isinstance(obj, dict):
                        if 'display_url' in obj:
                            return obj['display_url']
                        for v in obj.values():
                            result = find_url(v, depth + 1)
                            if result:
                                return result
                    elif isinstance(obj, list):
                        for item in obj:
                            result = find_url(item, depth + 1)
                            if result:
                                return result
                    return None
                
                photo_url = find_url(data)
                if photo_url:
                    file_path = os.path.join(DOWNLOAD_DIR, f"{shortcode}.jpg")
                    
                    img_response = requests.get(photo_url, headers=headers, stream=True, timeout=30)
                    if img_response.status_code == 200:
                        with open(file_path, 'wb') as f:
                            for chunk in img_response.iter_content(chunk_size=8192):
                                if chunk: f.write(chunk)
                        
                        if os.path.exists(file_path) and os.path.getsize(file_path) > 1000:
                            print(f"✅ Single photo via embed API")
                            return {"success": True, "file_path": file_path, "is_video": False}
        except Exception as e:
            print(f"⚠️ Embed API error: {e}")
        
        return {"success": False, "error": "Could not download photo"}
    
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
            
            probe = subprocess.run(
                ['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_entries', 'stream=codec_type', '-of', 'csv=p=0', video_path],
                capture_output=True, text=True, timeout=30
            )
            
            if not probe.stdout.strip():
                return {"success": False, "error": "❌ No audio track in this video"}
            
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
        "📥 **Instagram Downloader Bot v3.0**\n\n"
        "✅ **Reel link** → HD Video + Audio 🎬\n"
        "✅ **Post link** → ALL HD Photos 📸\n"
        "✅ **Carousel/Album** → Ek ek karke saari photos! 🔄\n"
        "✅ **Audio button** → Naam do → MP3 ⚡\n\n"
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
    
    # Audio name handling
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
        
        if is_reel:
            await msg.edit_text("📥 **Downloading Video...**")
        else:
            await msg.edit_text("📥 **Downloading Photo(s)...**")
        
        result = InstaDownloader.download_media(url)
        
        if not result.get("success"):
            error = result.get('error', 'Unknown error')
            await msg.edit_text(
                f"❌ **Failed!**\n\n{error}\n\n"
                f"💡 **Tip:** Fresh cookies.txt banao agar zaroorat ho.",
                parse_mode="Markdown"
            )
            return
        
        # Handle multiple photos (CAROUSEL)
        if result.get("is_multiple"):
            photo_paths = result.get("file_paths", [])
            total = result.get("total_photos", len(photo_paths))
            
            await msg.edit_text(f"📤 **{total} Photos mil gaye! Ek ek karke bhej raha hun...**")
            
            for i, fp in enumerate(photo_paths, 1):
                if os.path.exists(fp) and os.path.getsize(fp) > 1000:
                    try:
                        with open(fp, 'rb') as f:
                            if i == 1:
                                await update.message.reply_photo(
                                    photo=f,
                                    caption=f"✅ **Photo {i}/{total}**\n🔗 [Instagram Post]({url})",
                                    parse_mode="Markdown"
                                )
                            else:
                                await update.message.reply_photo(
                                    photo=f,
                                    caption=f"✅ **Photo {i}/{total}**",
                                    parse_mode="Markdown"
                                )
                        
                        # Small delay to avoid rate limiting
                        if i < total:
                            await asyncio.sleep(0.5)
                            
                    except Exception as e:
                        await update.message.reply_text(f"❌ Photo {i} error: {str(e)[:50]}")
                    
                    InstaDownloader.cleanup(fp)
            
            # Final success message
            try:
                await msg.edit_text(f"✅ **Sab {total} Photos bhej diye!** 🔥")
                await asyncio.sleep(2)
                await msg.delete()
            except:
                pass
            
            return
        
        # Handle single file (video or photo)
        fp = result["file_path"]
        if not os.path.exists(fp) or os.path.getsize(fp) < 1000:
            await msg.edit_text("❌ File not found or too small")
            return
        
        size_mb = os.path.getsize(fp) / (1024 * 1024)
        if size_mb > 50:
            await msg.edit_text(f"❌ File >50MB ({size_mb:.1f}MB), Telegram limit exceeded")
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
        # Cleanup
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
        
        # Get video path (first if multiple)
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
                    audio=f, 
                    title=audio_name, 
                    performer="Instagram",
                    caption=f"🎵 **{audio_name}** ✅"
                )
            
            await status_msg.edit_text(f"✅ **{audio_name} sent!** 🎵")
            try: os.remove(ap)
            except: pass
        else:
            await status_msg.edit_text(f"❌ {audio_result.get('error', 'Audio extraction failed')}")
        
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
            "Ya: `skip` for default name\n\n"
            "⬇️ Type karo:",
            parse_mode="Markdown"
        )
        context.user_data['awaiting_audio'] = True

# ═══════════════════════════
# 🚀 MAIN
# ═══════════════════════════

def main():
    logging.basicConfig(level=logging.INFO)
    
    print("╔══════════════════════════════╗")
    print("║  🤖 INSTAGRAM BOT v3.0      ║")
    print("║  ✅ Carousel Fix Applied!   ║")
    print("╚══════════════════════════════╝")
    
    # FFmpeg check
    ffmpeg = shutil.which('ffmpeg')
    if ffmpeg:
        print(f"✅ FFmpeg: {ffmpeg}")
    else:
        print("⚠️ Installing FFmpeg...")
        os.system('apt-get update && apt-get install ffmpeg -y 2>/dev/null')
    
    # Cookies check
    if os.path.exists('cookies.txt'):
        size = os.path.getsize('cookies.txt')
        print(f"✅ cookies.txt ({size} bytes)")
    else:
        print("ℹ️ cookies.txt not found (will work without it for public posts)")
    
    # Clean downloads folder
    for f in os.listdir(DOWNLOAD_DIR):
        try: os.remove(os.path.join(DOWNLOAD_DIR, f))
        except: pass
    
    print("✅ Bot Started! 🚀")
    print("📸 Carousel/Album: ALL photos will be sent one by one!")
    print("📸 Single Photo: Will be sent directly!")
    print("🎬 Reels/Videos: HD quality with audio extraction!")
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    app.run_polling()

if __name__ == "__main__":
    main()
