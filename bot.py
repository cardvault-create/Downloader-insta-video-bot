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
# 📥 DOWNLOAD ENGINE — PHOTO KE 7 METHODS
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
        m = re.search(r'/(p|reel|tv)/([a-zA-Z0-9_\-]+)', url)
        return m.group(2) if m else None

    @staticmethod
    def load_cookies_dict():
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
                        cookies[parts[5]] = parts[6]
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
        }

    # ═══════════════════════════════════
    # 🎬 MAIN FUNCTION
    # ═══════════════════════════════════

    @staticmethod
    def download_media(url):
        shortcode = InstaDownloader.get_shortcode(url)
        if not shortcode:
            return {"success": False, "error": "Invalid URL"}
        
        is_reel = '/reel/' in url or '/tv/' in url
        
        if is_reel:
            return InstaDownloader._download_video(url, shortcode)
        else:
            # ⭐ PHOTO KE LIYE 7 METHODS TRY KAREGA
            return InstaDownloader._download_photo(shortcode)

    # ═══════════════════════════════════
    # 🎬 VIDEO DOWNLOAD (already working)
    # ═══════════════════════════════════

    @staticmethod
    def _download_video(url, shortcode):
        try:
            if not os.path.exists('cookies.txt'):
                return {"success": False, "error": "cookies.txt not found"}
            
            formats_to_try = [
                'best',
                'best[ext=mp4]',
                'bestvideo+bestaudio',
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
                    }
                    if shutil.which('ffmpeg'):
                        ydl_opts['ffmpeg_location'] = shutil.which('ffmpeg')
                    
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=True)
                        if info:
                            file_path = None
                            for f in os.listdir(DOWNLOAD_DIR):
                                if shortcode in f and f.endswith('.mp4'):
                                    file_path = os.path.join(DOWNLOAD_DIR, f)
                                    break
                            
                            if file_path and os.path.getsize(file_path) > 5000:
                                probe = subprocess.run(
                                    ['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_entries', 'stream=codec_type', '-of', 'csv=p=0', file_path],
                                    capture_output=True, text=True, timeout=30
                                )
                                if probe.stdout.strip():
                                    return {"success": True, "file_path": file_path, "is_video": True}
                                try: os.remove(file_path)
                                except: pass
                except:
                    continue
            
            return {"success": False, "error": "Video download failed"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ═══════════════════════════════════
    # 📸 PHOTO DOWNLOAD — 7 METHODS
    # ═══════════════════════════════════

    @staticmethod
    def _download_photo(shortcode):
        """Photo download with 7 fallback methods"""
        print(f"\n🔍 Downloading photo: {shortcode}")
        
        # ─── METHOD 1: yt-dlp ───
        print(f"📥 Method 1: yt-dlp")
        result = InstaDownloader._method_ytdlp(shortcode)
        if result.get("success"):
            return result
        
        # ─── METHOD 2: Direct page scrape with cookies ───
        print(f"📥 Method 2: Direct scrape")
        result = InstaDownloader._method_direct_scrape(shortcode)
        if result.get("success"):
            return result
        
        # ─── METHOD 3: oEmbed API (no login needed!) ───
        print(f"📥 Method 3: oEmbed")
        result = InstaDownloader._method_oembed(shortcode)
        if result.get("success"):
            return result
        
        # ─── METHOD 4: Instagram Basic Display API ───
        print(f"📥 Method 4: Basic Display API")
        result = InstaDownloader._method_basic_display(shortcode)
        if result.get("success"):
            return result
        
        # ─── METHOD 5: Third-party scrapers (Dumpor/Imginn) ───
        print(f"📥 Method 5: Third-party")
        result = InstaDownloader._method_third_party(shortcode)
        if result.get("success"):
            return result
        
        # ─── METHOD 6: GraphQL API ───
        print(f"📥 Method 6: GraphQL")
        result = InstaDownloader._method_graphql(shortcode)
        if result.get("success"):
            return result
        
        # ─── METHOD 7: Direct JSON embed ───
        print(f"📥 Method 7: Embed JSON")
        result = InstaDownloader._method_embed_json(shortcode)
        if result.get("success"):
            return result
        
        return {"success": False, "error": "❌ Saare 7 methods fail! cookies.txt naya banao."}

    @staticmethod
    def _method_ytdlp(shortcode):
        """Method 1: yt-dlp"""
        try:
            url = f"https://www.instagram.com/p/{shortcode}/"
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'ignoreerrors': True,
                'outtmpl': os.path.join(DOWNLOAD_DIR, f'{shortcode}.%(ext)s'),
                'format': 'best',
                'cookiefile': 'cookies.txt' if os.path.exists('cookies.txt') else None,
            }
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if info:
                    for f in os.listdir(DOWNLOAD_DIR):
                        if shortcode in f and f.endswith(('.jpg', '.jpeg', '.png', '.webp')):
                            fp = os.path.join(DOWNLOAD_DIR, f)
                            if os.path.getsize(fp) > 1000:
                                return {"success": True, "file_path": fp, "is_video": False}
        except:
            pass
        return {"success": False}

    @staticmethod
    def _method_direct_scrape(shortcode):
        """Method 2: Direct page scrape"""
        try:
            cookies = InstaDownloader.load_cookies_dict()
            headers = InstaDownloader.get_headers()
            page_url = f"https://www.instagram.com/p/{shortcode}/"
            
            resp = requests.get(page_url, headers=headers, cookies=cookies, timeout=15)
            html = resp.text
            
            image_urls = []
            
            # __NEXT_DATA__
            nd = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.DOTALL)
            if nd:
                try:
                    data = json.loads(nd.group(1))
                    def extract(obj):
                        urls = []
                        if isinstance(obj, dict):
                            if obj.get('display_url'):
                                urls.append(obj['display_url'])
                            if obj.get('__typename') == 'GraphImage' and obj.get('display_url'):
                                urls.append(obj['display_url'])
                            for k, v in obj.items():
                                if k in ('display_url', 'display_src', 'src') and isinstance(v, str) and 'http' in v:
                                    urls.append(v)
                                else:
                                    urls.extend(extract(v))
                        elif isinstance(obj, list):
                            for item in obj:
                                urls.extend(extract(item))
                        return urls
                    image_urls = extract(data)
                except:
                    pass
            
            # _sharedData
            if not image_urls:
                sd = re.search(r'window\._sharedData\s*=\s*({.*?});', html, re.DOTALL)
                if sd:
                    try:
                        data = json.loads(sd.group(1))
                        entries = data.get('entry_data', {}).get('PostPage', [])
                        for entry in entries:
                            media = entry.get('graphql', {}).get('shortcode_media', {})
                            if media.get('display_url'):
                                image_urls.append(media['display_url'])
                            edges = media.get('edge_sidecar_to_children', {}).get('edges', [])
                            for edge in edges:
                                node = edge.get('node', {})
                                if node.get('display_url'):
                                    image_urls.append(node['display_url'])
                    except:
                        pass
            
            # Regex
            if not image_urls:
                urls = re.findall(r'"display_url":"([^"]+)"', html)
                for u in urls:
                    image_urls.append(u.replace('\\u0026', '&'))
            
            # og:image
            if not image_urls:
                og = re.findall(r'<meta property="og:image" content="([^"]+)"', html)
                image_urls = list(set(og))
            
            if image_urls:
                return InstaDownloader._save_images(image_urls, shortcode)
                
        except:
            pass
        return {"success": False}

    @staticmethod
    def _method_oembed(shortcode):
        """Method 3: oEmbed API — NO LOGIN NEEDED"""
        try:
            url = f"https://www.instagram.com/p/{shortcode}/"
            oembed_url = f"https://api.instagram.com/oembed?url={urllib.parse.quote(url)}"
            
            resp = requests.get(oembed_url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                thumbnail_url = data.get('thumbnail_url', '')
                if thumbnail_url:
                    # Try to get HD version
                    hd_url = thumbnail_url.replace('/s150x150/', '/').replace('/s320x320/', '/').replace('/s640x640/', '/')
                    # Try full resolution
                    hd_url2 = re.sub(r'/s\d+x\d+/', '/', thumbnail_url)
                    
                    image_urls = [hd_url2, hd_url, thumbnail_url]
                    return InstaDownloader._save_images(image_urls, shortcode)
        except:
            pass
        return {"success": False}

    @staticmethod
    def _method_basic_display(shortcode):
        """Method 4: Instagram Basic Display API"""
        try:
            # Use the public embed page
            embed_url = f"https://www.instagram.com/p/{shortcode}/embed/"
            resp = requests.get(embed_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
            if resp.status_code == 200:
                # Find image in embed
                imgs = re.findall(r'<img[^>]+src="([^"]+)"', resp.text)
                for img_url in imgs:
                    if 'instagram.com' in img_url and ('p' in img_url or shortcode in img_url):
                        # Try to get highest quality
                        clean_url = img_url.split('?')[0]
                        hd_url = re.sub(r'/s\d+x\d+/', '/', clean_url)
                        return InstaDownloader._save_images([hd_url, clean_url], shortcode)
        except:
            pass
        return {"success": False}

    @staticmethod
    def _method_third_party(shortcode):
        """Method 5: Third-party scrapers"""
        scrapers = [
            f"https://imginn.com/p/{shortcode}/",
            f"https://dumpor.com/v/{shortcode}",
            f"https://instasave.io/instagram/{shortcode}",
        ]
        
        for scraper_url in scrapers:
            try:
                resp = requests.get(scraper_url, headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                    'Accept': 'text/html,application/xhtml+xml',
                }, timeout=15)
                
                if resp.status_code == 200:
                    # Find image URLs
                    imgs = re.findall(r'(https?://[^"\']+\.(?:jpg|jpeg|png|webp)[^"\']*)', resp.text)
                    valid_imgs = [u for u in imgs if 'instagram' in u or 'cdn' in u or 'media' in u or 'img' in u]
                    
                    if valid_imgs:
                        return InstaDownloader._save_images(valid_imgs[:5], shortcode)
            except:
                continue
        
        return {"success": False}

    @staticmethod
    def _method_graphql(shortcode):
        """Method 6: Instagram GraphQL API"""
        try:
            cookies = InstaDownloader.load_cookies_dict()
            if not cookies.get('sessionid'):
                return {"success": False}
            
            # GraphQL query
            query_hash = "56a7068fea504063273cc2120ffd54f3"
            variables = json.dumps({"shortcode": shortcode, "child_comment_count": 3, "fetch_comment_count": 2, "parent_comment_count": 2, "has_threaded_comments": True})
            
            graphql_url = f"https://www.instagram.com/graphql/query/?query_hash={query_hash}&variables={urllib.parse.quote(variables)}"
            
            resp = requests.get(graphql_url, headers=InstaDownloader.get_headers(), cookies=cookies, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                media = data.get('data', {}).get('shortcode_media', {})
                if media.get('display_url'):
                    image_urls = [media['display_url']]
                    
                    # Check for carousel
                    edges = media.get('edge_sidecar_to_children', {}).get('edges', [])
                    for edge in edges:
                        node = edge.get('node', {})
                        if node.get('display_url'):
                            image_urls.append(node['display_url'])
                    
                    if image_urls:
                        return InstaDownloader._save_images(image_urls, shortcode)
        except:
            pass
        return {"success": False}

    @staticmethod
    def _method_embed_json(shortcode):
        """Method 7: Direct JSON embed"""
        try:
            # Instagram's public embed API
            embed_js = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
            resp = requests.get(embed_js, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
            
            if resp.status_code == 200:
                # window.__INITIAL_STATE__
                init = re.search(r'window\.__INITIAL_STATE__\s*=\s*({.*?});', resp.text, re.DOTALL)
                if init:
                    data = json.loads(init.group(1))
                    # Navigate to find display_url
                    for key in data:
                        val = data[key]
                        if isinstance(val, dict):
                            for k2, v2 in val.items():
                                if isinstance(v2, dict) and v2.get('display_url'):
                                    sh = re.search(r'/([^/]+)/?$', shortcode)
                                    sc = sh.group(1) if sh else shortcode
                                    return InstaDownloader._save_images([v2['display_url']], sc)
        except:
            pass
        return {"success": False}

    @staticmethod
    def _save_images(image_urls, shortcode):
        """Download and save image URLs"""
        downloaded = []
        
        for i, img_url in enumerate(image_urls):
            try:
                if img_url.startswith('//'):
                    img_url = 'https:' + img_url
                
                img_url = img_url.split('?')[0]
                img_url = re.sub(r'/s\d+x\d+/', '/', img_url)  # HD quality
                
                ext = 'jpg'
                if '.png' in img_url:
                    ext = 'png'
                elif '.webp' in img_url:
                    ext = 'webp'
                
                file_name = f"{shortcode}_{i+1}.{ext}" if len(image_urls) > 1 else f"{shortcode}.{ext}"
                file_path = os.path.join(DOWNLOAD_DIR, file_name)
                
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36',
                    'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
                    'Referer': 'https://www.instagram.com/',
                }
                
                ir = requests.get(img_url, headers=headers, stream=True, timeout=30)
                if ir.status_code == 200:
                    with open(file_path, 'wb') as f:
                        for chunk in ir.iter_content(chunk_size=8192):
                            if chunk: f.write(chunk)
                    
                    if os.path.exists(file_path) and os.path.getsize(file_path) > 1000:
                        downloaded.append(file_path)
                        print(f"✅ Saved: {file_path} ({os.path.getsize(file_path)} bytes)")
                        if len(image_urls) == 1:
                            break
            except Exception as e:
                print(f"⚠️ Save error: {e}")
                continue
        
        if downloaded:
            if len(downloaded) == 1:
                return {"success": True, "file_path": downloaded[0], "is_video": False}
            else:
                return {"success": True, "file_paths": downloaded, "is_video": False, "is_multiple": True}
        
        return {"success": False}

    # ═══════════════════════════════════
    # 🎵 AUDIO EXTRACTION
    # ═══════════════════════════════════

    @staticmethod
    def extract_audio(video_path, custom_name=None):
        try:
            if custom_name:
                safe_name = re.sub(r'[^\w\s-]', '', custom_name).strip()[:50]
                if not safe_name:
                    safe_name = "Instagram_Audio"
                file_name = f"{safe_name}.mp3"
            else:
                base = os.path.splitext(os.path.basename(video_path))[0]
                file_name = f"{base}.mp3"
            
            audio_path = os.path.join(DOWNLOAD_DIR, file_name)
            
            if not shutil.which('ffmpeg'):
                return {"success": False, "error": "FFmpeg not found"}
            
            probe = subprocess.run(
                ['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_entries', 'stream=codec_type', '-of', 'csv=p=0', video_path],
                capture_output=True, text=True, timeout=30
            )
            
            if not probe.stdout.strip():
                return {"success": False, "error": "❌ Is video main audio nahi hai!"}
            
            cmd = ['ffmpeg', '-i', video_path, '-vn', '-acodec', 'libmp3lame', '-ab', '192k', '-ar', '44100', '-y', audio_path]
            subprocess.run(cmd, capture_output=True, timeout=180)
            
            if os.path.exists(audio_path) and os.path.getsize(audio_path) > 1000:
                return {"success": True, "file_path": audio_path}
            
            return {"success": False, "error": "Audio extract failed"}
        except:
            return {"success": False, "error": "Audio error"}
    
    @staticmethod
    def cleanup(file_path):
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
        except:
            pass
    
    @staticmethod
    def cleanup_dir():
        try:
            for f in os.listdir(DOWNLOAD_DIR):
                try: os.remove(os.path.join(DOWNLOAD_DIR, f))
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
        "✅ **Post link** → Photo(s) 📸\n"
        "✅ **Multiple photos** → Sab ek-ek karke 🔄\n"
        "✅ **Audio button** → Naam do → MP3 ⚡\n\n"
        "**Bas link bhejo!** ⬇️",
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
        await update.message.reply_text("❌ Invalid URL")
        return
    
    context.user_data['current_url'] = url
    
    msg = await update.message.reply_text("⏳ **Processing...**", parse_mode="Markdown")
    
    try:
        is_reel = '/reel/' in url or '/tv/' in url
        await msg.edit_text("📥 **Downloading...**" if is_reel else "📥 **Downloading Photo...**")
        
        result = InstaDownloader.download_media(url)
        
        if not result.get("success"):
            await msg.edit_text(
                f"❌ **Failed!**\n\n{result.get('error', 'Unknown')}\n\n"
                f"💡 **Fix:**\n"
                f"1. Instagram se logout → login karein\n"
                f"2. Chrome extension se **naya cookies.txt** banao\n"
                f"3. GitHub par update karo\n"
                f"4. Railway redeploy karo",
                parse_mode="Markdown"
            )
            return
        
        # ⭐ MULTIPLE PHOTOS
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
        
        # ⭐ SINGLE FILE
        fp = result["file_path"]
        if not os.path.exists(fp) or os.path.getsize(fp) < 1000:
            await msg.edit_text("❌ Download incomplete")
            return
        
        if os.path.getsize(fp) > 50 * 1024 * 1024:
            await msg.edit_text("❌ File >50MB")
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
        
    except TimedOut:
        await msg.edit_text("⏰ Timeout! Dobara try karo.")
    except Exception as e:
        await msg.edit_text(f"❌ **Error:** {str(e)}")
        InstaDownloader.cleanup_dir()

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
                    audio=f,
                    title=audio_name,
                    performer="Instagram",
                    caption=f"🎵 **{audio_name}** ✅"
                )
            await status_msg.edit_text(f"✅ **{audio_name} sent!** 🎵")
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
    
    if query.data == "get_audio":
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            "🎵 **Audio Ka Naam Likhein** 🎵\n\n"
            "Jaise: `Meri Pyaari Song`\n"
            "Ya: `skip` dalo\n\n"
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
    
    # FFmpeg
    if shutil.which('ffmpeg'):
        print(f"✅ FFmpeg: {shutil.which('ffmpeg')}")
    else:
        print("⚠️ Installing ffmpeg...")
        os.system('apt-get update && apt-get install ffmpeg -y')
    
    # cookies.txt
    if os.path.exists('cookies.txt'):
        print(f"✅ cookies.txt ({os.path.getsize('cookies.txt')} bytes)")
        with open('cookies.txt') as f:
            c = f.read()
        if 'sessionid' in c:
            print("✅ sessionid found")
        else:
            print("⚠️ No sessionid")
    else:
        print("❌ cookies.txt missing")
    
    InstaDownloader.cleanup_dir()
    print("✅ Bot Started! 🚀")
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    app.run_polling()

if __name__ == "__main__":
    main()
