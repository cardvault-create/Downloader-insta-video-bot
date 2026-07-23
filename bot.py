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
        if not text: return False
        return bool(re.search(r'(instagram\.com|instagr\.am)/(p|reel|tv)/[a-zA-Z0-9_\-]+', text))
    
    @staticmethod
    def extract_url(text):
        if not text: return None
        m = re.search(r'(instagram\.com|instagr\.am)/(p|reel|tv)/([a-zA-Z0-9_\-]+)', text)
        if m: return f"https://www.instagram.com/{m.group(2)}/{m.group(3)}/"
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
    # 🎬 MAIN
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
            print(f"📸 Downloading Photo: {shortcode}")
            return InstaDownloader._download_photo(shortcode)
    
    # ═══════════════════════════
    # 🎬 VIDEO (yt-dlp direct)
    # ═══════════════════════════
    
    @staticmethod
    def _download_video(shortcode, url):
        try:
            ydl_opts = {
                'quiet': True, 'no_warnings': True,
                'outtmpl': os.path.join(DOWNLOAD_DIR, f'{shortcode}.%(ext)s'),
                'format': 'best[ext=mp4]/best',
                'retries': 3,
            }
            if os.path.exists('cookies.txt'):
                ydl_opts['cookiefile'] = 'cookies.txt'
            ffmpeg = shutil.which('ffmpeg')
            if ffmpeg:
                ydl_opts['ffmpeg_location'] = ffmpeg
                ydl_opts['postprocessors'] = [{'key': 'FFmpegVideoConvertor', 'preferedformat': 'mp4'}]
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info: return {"success": False, "error": "No response"}
                
                file_path = None
                for f in os.listdir(DOWNLOAD_DIR):
                    if shortcode in f and f.endswith('.mp4'):
                        file_path = os.path.join(DOWNLOAD_DIR, f); break
                if not file_path:
                    mp4_files = sorted([f for f in os.listdir(DOWNLOAD_DIR) if f.endswith('.mp4')],
                        key=lambda x: os.path.getmtime(os.path.join(DOWNLOAD_DIR, x)), reverse=True)
                    if mp4_files: file_path = os.path.join(DOWNLOAD_DIR, mp4_files[0])
                
                if file_path and os.path.exists(file_path) and os.path.getsize(file_path) > 5000:
                    return {"success": True, "file_path": file_path, "is_video": True}
                return {"success": False, "error": "File not found"}
        except Exception as e:
            err = str(e)
            if 'HTTP Error 403' in err: return {"success": False, "error": "❌ cookies.txt expired!"}
            return {"success": False, "error": f"❌ {err[:80]}"}
    
    # ═══════════════════════════
    # 📸 PHOTO - 5 METHODS (100% WORKING)
    # ═══════════════════════════
    
    @staticmethod
    def _download_photo(shortcode):
        """Photo download - yt-dlp se URL nikalta hoon, phir requests se download"""
        print(f"\n📸 Photo: {shortcode}")
        
        # ⭐ METHOD 1: yt-dlp info extraction + requests download (BEST!)
        print("📥 Method 1: yt-dlp info + requests")
        result = InstaDownloader._ytdlp_info_download(shortcode)
        if result.get("success"):
            print(f"✅ Method 1 worked!")
            return result
        
        # ⭐ METHOD 2: __a=1 API endpoint
        print("📥 Method 2: Instagram __a=1 API")
        result = InstaDownloader._instagram_api(shortcode)
        if result.get("success"):
            print(f"✅ Method 2 worked!")
            return result
        
        # ⭐ METHOD 3: oEmbed API
        print("📥 Method 3: oEmbed API")
        result = InstaDownloader._oembed_api(shortcode)
        if result.get("success"):
            print(f"✅ Method 3 worked!")
            return result
        
        # ⭐ METHOD 4: Page scrape
        print("📥 Method 4: Page scrape")
        result = InstaDownloader._page_scrape(shortcode)
        if result.get("success"):
            print(f"✅ Method 4 worked!")
            return result
        
        # ⭐ METHOD 5: yt-dlp direct download
        print("📥 Method 5: yt-dlp direct")
        result = InstaDownloader._ytdlp_direct(shortcode)
        if result.get("success"):
            print(f"✅ Method 5 worked!")
            return result
        
        return {"success": False, "error": "Photo download failed. Instagram blocking from cloud."}
    
    @staticmethod
    def _get_ydl_info(shortcode):
        """Get yt-dlp info for a post"""
        try:
            url = f"https://www.instagram.com/p/{shortcode}/"
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'ignoreerrors': True,
            }
            if os.path.exists('cookies.txt'):
                ydl_opts['cookiefile'] = 'cookies.txt'
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                return ydl.extract_info(url, download=False)
        except:
            return None
    
    @staticmethod
    def _download_image(img_url, file_path, referer='https://www.instagram.com/'):
        """Download single image from URL"""
        try:
            if img_url.startswith('//'): img_url = 'https:' + img_url
            if img_url.startswith('http://'): img_url = img_url.replace('http://', 'https://')
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
                'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
                'Referer': referer,
                'Sec-Fetch-Dest': 'image',
                'Sec-Fetch-Mode': 'no-cors',
                'Sec-Fetch-Site': 'cross-site',
            }
            
            r = requests.get(img_url, headers=headers, stream=True, timeout=30)
            if r.status_code == 200:
                with open(file_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk: f.write(chunk)
                
                if os.path.exists(file_path) and os.path.getsize(file_path) > 1000:
                    return True
            return False
        except:
            return False
    
    @staticmethod
    def _ytdlp_info_download(shortcode):
        """METHOD 1: yt-dlp info extraction → requests download"""
        try:
            info = InstaDownloader._get_ydl_info(shortcode)
            if not info:
                return {"success": False}
            
            # Collect all image URLs
            image_urls = []
            
            # Check entries (carousel)
            entries = info.get('entries', [])
            if entries:
                for entry in entries:
                    if not entry: continue
                    # Try various URL fields
                    url = (entry.get('thumbnail') or entry.get('display_url') or 
                           entry.get('url') or entry.get('webpage_url') or '')
                    if url and url.startswith('http') and '.mp4' not in url:
                        image_urls.append(url)
            else:
                # Single post
                url = (info.get('thumbnail') or info.get('display_url') or 
                       info.get('url') or info.get('webpage_url') or '')
                if url and url.startswith('http') and '.mp4' not in url:
                    image_urls.append(url)
            
            # Also check formats for images (vcodec='none', acodec='none')
            formats = info.get('formats', [])
            for fmt in formats:
                vcodec = fmt.get('vcodec', '')
                acodec = fmt.get('acodec', '')
                url = fmt.get('url', '')
                
                # Image format has no video and no audio
                if (vcodec == 'none' or vcodec == '') and (acodec == 'none' or acodec == ''):
                    if url and url.startswith('http') and url not in image_urls:
                        image_urls.append(url)
                # Also check if it's just a thumbnail/image URL
                if fmt.get('resolution') == '160x160' or 'thumbnail' in fmt.get('format_id', ''):
                    if url and url.startswith('http') and url not in image_urls:
                        image_urls.append(url)
            
            # Also try the 'thumbnails' field
            thumbnails = info.get('thumbnails', [])
            for thumb in thumbnails:
                url = thumb.get('url', '')
                if url and url.startswith('http') and url not in image_urls:
                    image_urls.append(url)
            
            # Also check the 'requested_formats' field
            req_formats = info.get('requested_formats', [])
            for fmt in req_formats:
                url = fmt.get('url', '')
                if url and url.startswith('http') and url not in image_urls:
                    image_urls.append(url)
            
            if not image_urls:
                print("⚠️ No image URLs found in yt-dlp info")
                return {"success": False}
            
            # Remove duplicates
            seen = set()
            unique_urls = []
            for u in image_urls:
                if u not in seen:
                    seen.add(u)
                    unique_urls.append(u)
            
            # Also try to get HD version by removing size constraints
            hd_urls = []
            for u in unique_urls:
                hd = re.sub(r'/s\d+x\d+/', '/', u)
                if hd != u:
                    hd_urls.append(hd)
                hd_urls.append(u)
            
            print(f"🔍 Found {len(unique_urls)} image URLs")
            
            # Download
            downloaded = []
            for i, img_url in enumerate(hd_urls[:10]):
                try:
                    ext = 'jpg'
                    if '.png' in img_url: ext = 'png'
                    elif '.webp' in img_url: ext = 'webp'
                    
                    file_name = f"{shortcode}_{i+1}.{ext}" if len(unique_urls) > 1 else f"{shortcode}.{ext}"
                    file_path = os.path.join(DOWNLOAD_DIR, file_name)
                    
                    if InstaDownloader._download_image(img_url, file_path):
                        downloaded.append(file_path)
                        print(f"✅ Photo {len(downloaded)}: {os.path.basename(file_path)}")
                        if len(unique_urls) == 1: break
                except:
                    continue
            
            if downloaded:
                if len(downloaded) == 1:
                    return {"success": True, "file_path": downloaded[0], "is_video": False}
                else:
                    return {"success": True, "file_paths": downloaded, "is_video": False, "is_multiple": True}
            
            return {"success": False}
            
        except Exception as e:
            print(f"⚠️ Method 1 error: {e}")
            return {"success": False}
    
    @staticmethod
    def _instagram_api(shortcode):
        """METHOD 2: Instagram __a=1 API - sometimes works without cookies"""
        try:
            url = f"https://www.instagram.com/p/{shortcode}/"
            api_url = f"{url}?__a=1&__d=1"
            
            # Try with various query params
            api_urls = [
                f"https://www.instagram.com/p/{shortcode}/?__a=1",
                f"https://www.instagram.com/p/{shortcode}/?__a=1&__d=1",
                f"https://www.instagram.com/p/{shortcode}/?__a=1&__d=dis",
            ]
            
            session = requests.Session()
            
            # Load cookies if available
            if os.path.exists('cookies.txt'):
                with open('cookies.txt', 'r') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'): continue
                        parts = line.split('\t')
                        if len(parts) >= 7:
                            session.cookies.set(parts[5], parts[6], domain='.instagram.com')
            
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'en-US,en;q=0.9',
                'X-Requested-With': 'XMLHttpRequest',
                'Referer': f'https://www.instagram.com/p/{shortcode}/',
            })
            
            for api_url in api_urls:
                try:
                    resp = session.get(api_url, timeout=15)
                    if resp.status_code == 200:
                        try:
                            data = resp.json()
                            
                            # Navigate through the data to find images
                            image_urls = []
                            
                            def extract_images(obj, depth=0):
                                if depth > 10: return
                                if isinstance(obj, dict):
                                    du = obj.get('display_url') or obj.get('display_src') or ''
                                    if du and du.startswith('http') and '.mp4' not in du:
                                        image_urls.append(du)
                                    
                                    # Carousel
                                    edges = obj.get('edge_sidecar_to_children', {}).get('edges', [])
                                    for edge in edges:
                                        node = edge.get('node', {})
                                        ndu = node.get('display_url') or ''
                                        if ndu: image_urls.append(ndu)
                                    
                                    for v in obj.values():
                                        extract_images(v, depth + 1)
                                elif isinstance(obj, list):
                                    for item in obj:
                                        extract_images(item, depth + 1)
                            
                            extract_images(data)
                            
                            if image_urls:
                                downloaded = []
                                for i, img_url in enumerate(image_urls[:10]):
                                    ext = 'jpg'
                                    if '.png' in img_url: ext = 'png'
                                    elif '.webp' in img_url: ext = 'webp'
                                    
                                    file_name = f"{shortcode}_{i+1}.{ext}" if len(image_urls) > 1 else f"{shortcode}.{ext}"
                                    file_path = os.path.join(DOWNLOAD_DIR, file_name)
                                    
                                    if InstaDownloader._download_image(img_url, file_path):
                                        downloaded.append(file_path)
                                        if len(image_urls) == 1: break
                                
                                if downloaded:
                                    if len(downloaded) == 1:
                                        return {"success": True, "file_path": downloaded[0], "is_video": False}
                                    else:
                                        return {"success": True, "file_paths": downloaded, "is_video": False, "is_multiple": True}
                        except json.JSONDecodeError:
                            continue
                except:
                    continue
            
            return {"success": False}
        except:
            return {"success": False}
    
    @staticmethod
    def _oembed_api(shortcode):
        """METHOD 3: Instagram oEmbed public API"""
        try:
            post_url = f"https://www.instagram.com/p/{shortcode}/"
            api_url = f"https://api.instagram.com/oembed?url={urllib.parse.quote(post_url)}&maxwidth=1080"
            
            resp = requests.get(api_url, timeout=15)
            if resp.status_code != 200: return {"success": False}
            
            data = resp.json()
            thumbnail = data.get('thumbnail_url', '')
            
            if thumbnail:
                hd_url = re.sub(r'/s\d+x\d+/', '/', thumbnail)
                hd_url = hd_url.split('?')[0]
                
                ext = 'jpg'
                if '.png' in hd_url: ext = 'png'
                elif '.webp' in hd_url: ext = 'webp'
                
                file_path = os.path.join(DOWNLOAD_DIR, f"{shortcode}.{ext}")
                if InstaDownloader._download_image(hd_url, file_path):
                    return {"success": True, "file_path": file_path, "is_video": False}
                
                if InstaDownloader._download_image(thumbnail, file_path):
                    return {"success": True, "file_path": file_path, "is_video": False}
            
            return {"success": False}
        except:
            return {"success": False}
    
    @staticmethod
    def _page_scrape(shortcode):
        """METHOD 4: Direct page scrape"""
        try:
            session = requests.Session()
            
            if os.path.exists('cookies.txt'):
                with open('cookies.txt', 'r') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'): continue
                        parts = line.split('\t')
                        if len(parts) >= 7:
                            session.cookies.set(parts[5], parts[6], domain='.instagram.com')
            
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Linux; Android 13; SM-S908B) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml',
            })
            
            page_url = f"https://www.instagram.com/p/{shortcode}/"
            resp = session.get(page_url, timeout=15)
            
            if resp.status_code != 200: return {"success": False}
            
            html = resp.text
            image_urls = []
            
            # __NEXT_DATA__
            nd = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.DOTALL)
            if nd:
                try:
                    data = json.loads(nd.group(1))
                    def extract(obj, depth=0):
                        if depth > 8: return []
                        urls = []
                        if isinstance(obj, dict):
                            edges = obj.get('edge_sidecar_to_children', {}).get('edges', [])
                            for edge in edges:
                                node = edge.get('node', {})
                                du = node.get('display_url') or ''
                                if du: urls.append(du)
                            du = obj.get('display_url') or obj.get('display_src') or ''
                            if du and '.mp4' not in du: urls.append(du)
                            for v in obj.values():
                                urls.extend(extract(v, depth + 1))
                        elif isinstance(obj, list):
                            for item in obj:
                                urls.extend(extract(item, depth + 1))
                        return urls
                    image_urls = list(dict.fromkeys(extract(data)))
                except: pass
            
            # Regex
            if not image_urls:
                urls = re.findall(r'"display_url":"([^"]+)"', html)
                seen = set()
                for u in urls:
                    u = u.replace('\\u0026', '&')
                    if u not in seen: seen.add(u); image_urls.append(u)
            
            if not image_urls:
                urls = re.findall(r'"display_src":"([^"]+)"', html)
                for u in urls:
                    u = u.replace('\\u0026', '&')
                    if u not in image_urls: image_urls.append(u)
            
            if not image_urls:
                og = re.findall(r'<meta\s+property="og:image"\s+content="([^"]+)"', html)
                image_urls = list(set(og))
            
            if not image_urls: return {"success": False}
            
            # Filter out videos
            image_urls = [u for u in image_urls if '.mp4' not in u]
            if not image_urls: return {"success": False}
            
            downloaded = []
            for i, img_url in enumerate(image_urls[:10]):
                try:
                    ext = 'jpg'
                    if '.png' in img_url: ext = 'png'
                    elif '.webp' in img_url: ext = 'webp'
                    
                    file_name = f"{shortcode}_{i+1}.{ext}" if len(image_urls) > 1 else f"{shortcode}.{ext}"
                    file_path = os.path.join(DOWNLOAD_DIR, file_name)
                    
                    # Try HD first
                    hd_url = re.sub(r'/s\d+x\d+/', '/', img_url)
                    if InstaDownloader._download_image(hd_url, file_path):
                        downloaded.append(file_path)
                    elif InstaDownloader._download_image(img_url, file_path):
                        downloaded.append(file_path)
                    
                    if len(image_urls) == 1: break
                except: continue
            
            if downloaded:
                if len(downloaded) == 1:
                    return {"success": True, "file_path": downloaded[0], "is_video": False}
                else:
                    return {"success": True, "file_paths": downloaded, "is_video": False, "is_multiple": True}
            
            return {"success": False}
        except:
            return {"success": False}
    
    @staticmethod
    def _ytdlp_direct(shortcode):
        """METHOD 5: yt-dlp direct download (last resort)"""
        try:
            url = f"https://www.instagram.com/p/{shortcode}/"
            ydl_opts = {
                'quiet': True, 'no_warnings': True,
                'outtmpl': os.path.join(DOWNLOAD_DIR, f'{shortcode}.%(ext)s'),
                'format': 'best',
            }
            if os.path.exists('cookies.txt'): ydl_opts['cookiefile'] = 'cookies.txt'
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if info:
                    import time
                    time.sleep(1)
                    for f in os.listdir(DOWNLOAD_DIR):
                        if shortcode in f and not f.endswith(('.mp4', '.mov', '.webm')):
                            fp = os.path.join(DOWNLOAD_DIR, f)
                            if os.path.exists(fp) and os.path.getsize(fp) > 1000:
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
            if not ffmpeg: return {"success": False, "error": "FFmpeg not installed!"}
            
            probe = subprocess.run(
                ['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_entries', 'stream=codec_type', '-of', 'csv=p=0', video_path],
                capture_output=True, text=True, timeout=30
            )
            if not probe.stdout.strip(): return {"success": False, "error": "❌ No audio track"}
            
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
            if file_path and os.path.exists(file_path): os.remove(file_path)
        except: pass

# ═══════════════════════════
# 🤖 TELEGRAM HANDLERS
# ═══════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.id
    if user not in AUTHORIZED_USERS: return
    
    await update.message.reply_text(
        "📥 **Instagram Downloader Bot**\n\n"
        "✅ **Reel** → HD Video + Audio 🎬\n"
        "✅ **Post** → **SABHI Photos** 1-1 karke 📸\n"
        "✅ **Carousel (multiple)** → **Sab aayenge!** 🔄\n"
        "✅ **Audio button** → Naam → MP3 ⚡\n\n"
        "**Bas link bhejo!** 🔗",
        parse_mode="Markdown"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.id
    if user not in AUTHORIZED_USERS: return
    
    text = update.message.text
    if not text: return
    
    if context.user_data.get('awaiting_audio'):
        context.user_data['awaiting_audio'] = False
        audio_name = text.strip()
        url = context.user_data.get('current_url')
        if url: await extract_and_send_audio(update, context, url, audio_name)
        return
    
    if not InstaDownloader.is_instagram_url(text): return
    
    url = InstaDownloader.extract_url(text)
    if not url:
        await update.message.reply_text("❌ Invalid URL")
        return
    
    context.user_data['current_url'] = url
    msg = await update.message.reply_text("⏳ **Processing...**", parse_mode="Markdown")
    
    try:
        is_reel = '/reel/' in url or '/tv/' in url
        await msg.edit_text("📥 **Downloading Video...**" if is_reel else "📥 **Downloading Photo(s)...**")
        
        result = InstaDownloader.download_media(url)
        
        if not result.get("success"):
            await msg.edit_text(
                f"❌ **Failed!**\n\n{result.get('error', 'Unknown')}\n\n"
                f"💡 **Solution:**\n"
                f"1. Chrome se naya cookies.txt banao\n"
                f"2. GitHub pe upload karo\n"
                f"3. Railway redeploy karo",
                parse_mode="Markdown"
            )
            return
        
        # ⭐ MULTIPLE PHOTOS - sab 1-1 karke
        if result.get("is_multiple"):
            photo_paths = result.get("file_paths", [])
            total = len(photo_paths)
            await msg.edit_text(f"📤 **Uploading {total} photos...**")
            
            for i, fp in enumerate(photo_paths):
                if os.path.exists(fp) and os.path.getsize(fp) > 1000:
                    try:
                        with open(fp, 'rb') as f:
                            await update.message.reply_photo(
                                photo=f,
                                caption=f"✅ **Photo {i+1}/{total}** ✅\n🔗 [Instagram Link]({url})",
                                parse_mode="Markdown"
                            )
                        print(f"📤 Sent photo {i+1}/{total}")
                    except Exception as e:
                        await update.message.reply_text(f"❌ Photo {i+1} error: {str(e)[:50]}")
                    try: os.remove(fp)
                    except: pass
            
            await msg.delete()
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
                    caption=f"✅ **Video + Audio** ✅\n🔗 [Instagram Link]({url})",
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
            await status_msg.edit_text("❌ Video download failed")
            return
        vp = result["file_path"]
        audio_result = InstaDownloader.extract_audio(vp, audio_name)
        if audio_result.get("success"):
            ap = audio_result["file_path"]
            await status_msg.edit_text("📤 **Uploading Audio...**")
            with open(ap, 'rb') as f:
                await update.message.reply_audio(audio=f, title=audio_name, performer="Instagram", caption=f"🎵 **{audio_name}** ✅")
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
            "🎵 **Audio ka naam likhein:**\n\nJaise: `Meri Song`\nYa: `skip`\n\n⬇️ Type karo:",
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
    
    if shutil.which('ffmpeg'):
        print(f"✅ FFmpeg: {shutil.which('ffmpeg')}")
    else:
        print("⚠️ Installing FFmpeg...")
        os.system('apt-get update && apt-get install ffmpeg -y 2>/dev/null')
    
    if os.path.exists('cookies.txt'):
        size = os.path.getsize('cookies.txt')
        has_session = 'sessionid' in open('cookies.txt').read()
        print(f"✅ cookies.txt ({size} bytes) - sessionid: {'✅' if has_session else '❌'}")
    else:
        print("ℹ️ cookies.txt not found")
    
    for f in os.listdir(DOWNLOAD_DIR):
        try: os.remove(os.path.join(DOWNLOAD_DIR, f))
        except: pass
    
    print("✅ Bot Started! 🚀")
    print("📸 Photos: yt-dlp info + requests download (5 methods)")
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.run_polling()

if __name__ == "__main__":
    main()
