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
            return InstaDownloader._download_video(shortcode, url)
        else:
            return InstaDownloader._download_photo(shortcode, url)
    
    # ═══════════════════════════
    # 🎬 VIDEO
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
                if not info:
                    return {"success": False, "error": "No response"}
                
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
    # 📸 PHOTO - ALL IMAGES FIX
    # ═══════════════════════════
    
    @staticmethod
    def _download_photo(shortcode, url):
        """Photo download - sabhi photos 1-1 karke"""
        
        # METHOD 1: Page scrape - sabse saare photos deta hai
        print("📥 Method 1: Page scrape (all photos)")
        result = InstaDownloader._scrape_all_photos(shortcode)
        if result.get("success"):
            return result
        
        # METHOD 2: oEmbed API
        print("📥 Method 2: oEmbed API")
        result = InstaDownloader._oembed_all_photos(shortcode)
        if result.get("success"):
            return result
        
        # METHOD 3: yt-dlp
        print("📥 Method 3: yt-dlp")
        result = InstaDownloader._ytdlp_photo(shortcode)
        if result.get("success"):
            return result
        
        return {"success": False, "error": "Photo download failed"}
    
    @staticmethod
    def _scrape_all_photos(shortcode):
        """Sabse reliable - Instagram page se saare photos nikalta hai"""
        try:
            session = requests.Session()
            
            # Cookies
            if os.path.exists('cookies.txt'):
                with open('cookies.txt', 'r') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'): continue
                        parts = line.split('\t')
                        if len(parts) >= 7: session.cookies.set(parts[5], parts[6], domain='.instagram.com')
            
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Linux; Android 13; SM-S908B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            })
            
            page_url = f"https://www.instagram.com/p/{shortcode}/"
            resp = session.get(page_url, timeout=15)
            
            if resp.status_code != 200:
                return {"success": False}
            
            html = resp.text
            
            # ⭐ SABHI IMAGE URLS NIKALO - Multiple methods
            all_image_urls = []
            
            # METHOD A: __NEXT_DATA__ (Instagram ka internal data)
            nd = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.DOTALL)
            if nd:
                try:
                    data = json.loads(nd.group(1))
                    def find_images(obj, depth=0):
                        urls = []
                        if depth > 8: return urls
                        if isinstance(obj, dict):
                            # Carousel children
                            edges = obj.get('edge_sidecar_to_children', {}).get('edges', [])
                            for edge in edges:
                                node = edge.get('node', {})
                                du = node.get('display_url') or node.get('display_src') or ''
                                if du and du.startswith('http'): urls.append(du)
                            
                            # Single post
                            du = obj.get('display_url') or obj.get('display_src') or ''
                            if du and du.startswith('http'): urls.append(du)
                            
                            # Recurse
                            for v in obj.values():
                                urls.extend(find_images(v, depth + 1))
                        elif isinstance(obj, list):
                            for item in obj:
                                urls.extend(find_images(item, depth + 1))
                        return urls
                    
                    all_image_urls = find_images(data)
                    # Remove duplicates
                    all_image_urls = list(dict.fromkeys(all_image_urls))
                except: pass
            
            # METHOD B: Regex display_url
            if not all_image_urls:
                urls = re.findall(r'"display_url":"([^"]+)"', html)
                seen = set()
                for u in urls:
                    u = u.replace('\\u0026', '&')
                    if u not in seen:
                        seen.add(u)
                        all_image_urls.append(u)
            
            # METHOD C: Regex display_src
            if not all_image_urls:
                urls = re.findall(r'"display_src":"([^"]+)"', html)
                seen = set()
                for u in urls:
                    u = u.replace('\\u0026', '&')
                    if u not in seen:
                        seen.add(u)
                        all_image_urls.append(u)
            
            # METHOD D: og:image
            if not all_image_urls:
                og = re.findall(r'<meta\s+property="og:image"\s+content="([^"]+)"', html)
                all_image_urls = list(set(og))
            
            # METHOD E: Any img tag with instagram CDN
            if not all_image_urls:
                imgs = re.findall(r'<img[^>]+src="([^"]+)"', html)
                for img in imgs:
                    if 'cdninstagram' in img or 'instagram' in img:
                        all_image_urls.append(img)
            
            if not all_image_urls:
                print("⚠️ No images found in page")
                return {"success": False}
            
            # Filter out video URLs
            image_urls = [u for u in all_image_urls if '.mp4' not in u]
            
            if not image_urls:
                return {"success": False}
            
            print(f"🔍 Found {len(image_urls)} images")
            
            # ⭐ DOWNLOAD SABHI PHOTOS
            downloaded_paths = []
            
            for i, img_url in enumerate(image_urls):
                try:
                    if img_url.startswith('//'): img_url = 'https:' + img_url
                    if img_url.startswith('http://'): img_url = img_url.replace('http://', 'https://')
                    
                    # Clean URL
                    img_url = img_url.split('?')[0]
                    
                    # HD quality - remove size constraints
                    img_url = re.sub(r'/s\d+x\d+/', '/', img_url)
                    
                    ext = 'jpg'
                    if '.png' in img_url: ext = 'png'
                    elif '.webp' in img_url: ext = 'webp'
                    
                    # Unique filename for each photo
                    file_name = f"{shortcode}_{i+1}.{ext}"
                    file_path = os.path.join(DOWNLOAD_DIR, file_name)
                    
                    img_headers = {
                        'User-Agent': 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36',
                        'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
                        'Referer': 'https://www.instagram.com/',
                    }
                    
                    ir = session.get(img_url, headers=img_headers, stream=True, timeout=30)
                    if ir.status_code == 200:
                        with open(file_path, 'wb') as f:
                            for chunk in ir.iter_content(chunk_size=8192):
                                if chunk: f.write(chunk)
                        
                        if os.path.exists(file_path) and os.path.getsize(file_path) > 1000:
                            downloaded_paths.append(file_path)
                            print(f"✅ Photo {i+1}: {os.path.basename(file_path)} ({os.path.getsize(file_path)} bytes)")
                except Exception as e:
                    print(f"⚠️ Error downloading image {i+1}: {e}")
                    continue
            
            if downloaded_paths:
                if len(downloaded_paths) == 1:
                    return {"success": True, "file_path": downloaded_paths[0], "is_video": False}
                else:
                    print(f"📸 Total {len(downloaded_paths)} photos downloaded!")
                    return {"success": True, "file_paths": downloaded_paths, "is_video": False, "is_multiple": True}
            
            return {"success": False}
            
        except Exception as e:
            print(f"⚠️ Scrape error: {e}")
            return {"success": False}
    
    @staticmethod
    def _oembed_all_photos(shortcode):
        """oEmbed API - 1 photo deta hai mostly, but try karte hain"""
        try:
            post_url = f"https://www.instagram.com/p/{shortcode}/"
            api_url = f"https://api.instagram.com/oembed?url={urllib.parse.quote(post_url)}"
            
            resp = requests.get(api_url, timeout=15)
            if resp.status_code != 200: return {"success": False}
            
            data = resp.json()
            thumbnail = data.get('thumbnail_url', '')
            embed_html = data.get('html', '')
            
            image_urls = []
            if thumbnail:
                hd_url = re.sub(r'/s\d+x\d+/', '/', thumbnail)
                hd_url = hd_url.split('?')[0]
                image_urls.append(hd_url)
                image_urls.append(thumbnail)
            
            if embed_html:
                imgs = re.findall(r'<img[^>]+src="([^"]+)"', embed_html)
                for u in imgs:
                    if u not in image_urls: image_urls.append(u)
            
            if not image_urls: return {"success": False}
            
            downloaded = []
            for img_url in image_urls[:3]:
                try:
                    if img_url.startswith('//'): img_url = 'https:' + img_url
                    img_url = re.sub(r'/s\d+x\d+/', '/', img_url)
                    img_url = img_url.split('?')[0]
                    
                    ext = 'jpg'
                    if '.png' in img_url: ext = 'png'
                    elif '.webp' in img_url: ext = 'webp'
                    
                    file_name = f"{shortcode}.{ext}"
                    file_path = os.path.join(DOWNLOAD_DIR, file_name)
                    
                    headers = {'User-Agent': 'Mozilla/5.0', 'Accept': 'image/*', 'Referer': 'https://www.instagram.com/'}
                    r = requests.get(img_url, headers=headers, stream=True, timeout=30)
                    if r.status_code == 200:
                        with open(file_path, 'wb') as f:
                            for chunk in r.iter_content(chunk_size=8192):
                                if chunk: f.write(chunk)
                        if os.path.exists(file_path) and os.path.getsize(file_path) > 1000:
                            downloaded.append(file_path); break
                except: continue
            
            if downloaded:
                return {"success": True, "file_path": downloaded[0], "is_video": False}
        except: pass
        return {"success": False}
    
    @staticmethod
    def _ytdlp_photo(shortcode):
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
                    time.sleep(1)
                    for f in os.listdir(DOWNLOAD_DIR):
                        if shortcode in f and not f.endswith(('.mp4', '.mov', '.webm')):
                            fp = os.path.join(DOWNLOAD_DIR, f)
                            if os.path.exists(fp) and os.path.getsize(fp) > 1000:
                                return {"success": True, "file_path": fp, "is_video": False}
        except: pass
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
        except Exception as e: return {"success": False, "error": f"Error: {str(e)[:50]}"}
    
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
        "✅ **Reel link** → HD Video + Audio 🎬\n"
        "✅ **Post link** → **SABHI Photos** 1-1 karke 📸\n"
        "✅ **Carousel (multiple photos)** → **Sab aayenge!** 🔄\n"
        "✅ **Audio button** → Naam do → MP3 ⚡\n\n"
        "**Sirf link bhejo!** 🔗",
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
        await update.message.reply_text("❌ Could not extract URL")
        return
    
    context.user_data['current_url'] = url
    
    msg = await update.message.reply_text("⏳ **Processing...**", parse_mode="Markdown")
    
    try:
        is_reel = '/reel/' in url or '/tv/' in url
        await msg.edit_text("📥 **Downloading Video...**" if is_reel else "📥 **Downloading Photo(s)...**")
        
        result = InstaDownloader.download_media(url)
        
        if not result.get("success"):
            await msg.edit_text(f"❌ **Failed!**\n\n{result.get('error', 'Unknown')}\n\n💡 Fresh cookies.txt banao aur GitHub pe upload karo.", parse_mode="Markdown")
            return
        
        # ⭐ MULTIPLE PHOTOS - Sab 1-1 karke
        if result.get("is_multiple"):
            photo_paths = result.get("file_paths", [])
            total = len(photo_paths)
            await msg.edit_text(f"📤 **Uploading {total} photos...**")
            
            for i, fp in enumerate(photo_paths):
                if os.path.exists(fp) and os.path.getsize(fp) > 1000:
                    try:
                        with open(fp, 'rb') as f:
                            caption = f"✅ **Photo {i+1}/{total}** ✅\n🔗 [Instagram Link]({url})"
                            if i == 0:
                                caption = f"✅ **Photo {i+1}/{total}** ✅\n🔗 [Instagram Link]({url})"
                            await update.message.reply_photo(photo=f, caption=caption, parse_mode="Markdown")
                            print(f"📤 Sent photo {i+1}/{total}")
                    except Exception as e:
                        await update.message.reply_text(f"❌ Photo {i+1} error: {str(e)[:50]}")
                    try: os.remove(fp)
                    except: pass
            
            await msg.delete()
            return
        
        # ⭐ SINGLE FILE
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
                await update.message.reply_video(video=f, caption=f"✅ **Video + Audio** ✅\n🔗 [Instagram Link]({url})", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard), supports_streaming=True)
            await msg.delete()
        else:
            await msg.edit_text("📤 **Uploading Photo...**")
            with open(fp, 'rb') as f:
                await update.message.reply_photo(photo=f, caption=f"✅ **Photo Downloaded** ✅\n🔗 [Instagram Link]({url})", parse_mode="Markdown")
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
            await status_msg.edit_text("❌ Video download failed"); return
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
        else: await status_msg.edit_text(f"❌ {audio_result.get('error')}")
        InstaDownloader.cleanup(vp)
    except Exception as e: await status_msg.edit_text(f"❌ Error: {str(e)[:80]}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "get_audio":
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text("🎵 **Audio ka naam likhein:**\n\nJaise: `Meri Song`\nYa: `skip`\n\n⬇️ Type karo:", parse_mode="Markdown")
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
    print("📸 Multiple photos: SABHI 1-1 karke aayenge!")
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.run_polling()

if __name__ == "__main__":
    main()
