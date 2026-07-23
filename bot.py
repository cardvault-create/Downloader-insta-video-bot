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
    
    # Instagram ke different User-Agents (mobile + desktop)
    USER_AGENTS = [
        'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
        'Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    ]
    
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
    
    @staticmethod
    def create_session():
        """Create a requests session with proper headers"""
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        return session
    
    @staticmethod
    def download_media(url):
        shortcode = InstaDownloader.get_shortcode(url)
        if not shortcode:
            return {"success": False, "error": "Invalid shortcode"}
        
        media_type = InstaDownloader.get_type(url)
        is_reel = media_type in ('reel', 'tv')
        
        if is_reel:
            print(f"🎬 Reel: {shortcode}")
            return InstaDownloader._download_reel(shortcode)
        else:
            print(f"📸 Post: {shortcode}")
            return InstaDownloader._download_post_photos(shortcode, url)
    
    @staticmethod
    def _download_reel(shortcode):
        """Download reel using rapidapi or direct method"""
        # Reel ke liye yt-dlp best hai
        try:
            import yt_dlp
            url = f"https://www.instagram.com/reel/{shortcode}/"
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
                ydl.download([url])
            
            time.sleep(1)
            for f in os.listdir(DOWNLOAD_DIR):
                if shortcode in f and f.endswith('.mp4'):
                    fp = os.path.join(DOWNLOAD_DIR, f)
                    if os.path.getsize(fp) > 5000:
                        return {"success": True, "file_path": fp, "is_video": True}
        except Exception as e:
            print(f"Reel error: {e}")
        
        return {"success": False, "error": "Reel download failed"}
    
    @staticmethod
    def _download_post_photos(shortcode, url):
        """
        Post photos download - DIRECT METHOD
        Uses Instagram's oEmbed API + page scraping
        No yt-dlp needed for photos!
        """
        
        all_photo_urls = []
        session = InstaDownloader.create_session()
        
        # ============================================
        # METHOD 1: oEmbed API (PUBLIC - NO AUTH)
        # ============================================
        print("📥 Method 1: oEmbed API...")
        try:
            post_url = f"https://www.instagram.com/p/{shortcode}/"
            api_url = f"https://api.instagram.com/oembed?url={urllib.parse.quote(post_url)}"
            
            resp = session.get(api_url, timeout=15)
            
            if resp.status_code == 200:
                data = resp.json()
                thumbnail = data.get('thumbnail_url', '')
                
                if thumbnail:
                    # High quality version
                    hd_url = re.sub(r'/s\d+x\d+/', '/s1080x1080/', thumbnail)
                    hd_url = hd_url.split('?')[0]
                    
                    if hd_url not in all_photo_urls:
                        all_photo_urls.append(hd_url)
                        print(f"  ✅ oEmbed URL: {hd_url[:80]}...")
        except Exception as e:
            print(f"  ⚠️ oEmbed error: {e}")
        
        # ============================================
        # METHOD 2: Instagram GraphQL (Embed Page)
        # ============================================
        print("📥 Method 2: Embed page scraping...")
        try:
            embed_url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
            
            for ua in InstaDownloader.USER_AGENTS:
                session.headers['User-Agent'] = ua
                resp = session.get(embed_url, timeout=15)
                
                if resp.status_code == 200:
                    html = resp.text
                    
                    # Find all JSON blocks in script tags
                    json_blocks = re.findall(r'<script[^>]*>({.*?})</script>', html, re.DOTALL)
                    
                    for block in json_blocks:
                        try:
                            # Clean the JSON
                            block = block.replace('\\"', '"').replace('\\\\', '\\')
                            data = json.loads(block)
                            
                            # Extract all image URLs recursively
                            def extract_urls(obj, depth=0):
                                if depth > 15:
                                    return []
                                urls = []
                                
                                if isinstance(obj, dict):
                                    # Check for carousel media
                                    if 'carousel_media' in obj:
                                        for item in obj['carousel_media']:
                                            if 'image_versions2' in item:
                                                candidates = item['image_versions2'].get('candidates', [])
                                                if candidates:
                                                    urls.append(candidates[0]['url'])
                                            elif 'images' in item:
                                                for img_type in ['standard_resolution', 'thumbnail']:
                                                    if img_type in item['images']:
                                                        urls.append(item['images'][img_type]['url'])
                                                        break
                                    
                                    # Check for single image
                                    if 'image_versions2' in obj:
                                        candidates = obj['image_versions2'].get('candidates', [])
                                        if candidates:
                                            urls.append(candidates[0]['url'])
                                    
                                    # Check for display_url
                                    if 'display_url' in obj:
                                        url_val = obj['display_url']
                                        if url_val not in urls:
                                            urls.append(url_val)
                                    
                                    # Check for edge_sidecar
                                    if 'edge_sidecar_to_children' in obj:
                                        for edge in obj['edge_sidecar_to_children'].get('edges', []):
                                            node = edge.get('node', {})
                                            if 'display_url' in node:
                                                urls.append(node['display_url'])
                                            elif 'image_versions2' in node:
                                                candidates = node['image_versions2'].get('candidates', [])
                                                if candidates:
                                                    urls.append(candidates[0]['url'])
                                    
                                    # Recursively search
                                    for v in obj.values():
                                        urls.extend(extract_urls(v, depth + 1))
                                
                                elif isinstance(obj, list):
                                    for item in obj:
                                        urls.extend(extract_urls(item, depth + 1))
                                
                                return urls
                            
                            found_urls = extract_urls(data)
                            for u in found_urls:
                                u = u.split('?')[0]
                                if u not in all_photo_urls and '.mp4' not in u and '.mov' not in u:
                                    all_photo_urls.append(u)
                            
                            if len(all_photo_urls) > 0:
                                break
                                
                        except:
                            continue
                    
                    if len(all_photo_urls) > 0:
                        break
                        
        except Exception as e:
            print(f"  ⚠️ Embed error: {e}")
        
        # ============================================
        # METHOD 3: Direct Instagram Page Scrape
        # ============================================
        if not all_photo_urls:
            print("📥 Method 3: Direct page scrape...")
            try:
                for ua in InstaDownloader.USER_AGENTS:
                    session.headers['User-Agent'] = ua
                    resp = session.get(url, timeout=15)
                    
                    if resp.status_code == 200:
                        html = resp.text
                        
                        # Extract JSON from script tags
                        json_patterns = [
                            r'<script type="application/json"[^>]*>({.*?})</script>',
                            r'<script type="text/javascript">window\.__INITIAL_STATE__\s*=\s*({.*?});</script>',
                            r'<script>window\.__INITIAL_STATE__\s*=\s*({.*?});</script>',
                        ]
                        
                        for pattern in json_patterns:
                            matches = re.findall(pattern, html, re.DOTALL)
                            for match in matches:
                                try:
                                    data = json.loads(match)
                                    
                                    # Search for image URLs
                                    def find_display_urls(obj, depth=0):
                                        if depth > 15:
                                            return []
                                        urls = []
                                        if isinstance(obj, dict):
                                            if 'display_url' in obj:
                                                urls.append(obj['display_url'])
                                            if 'image_versions2' in obj:
                                                candidates = obj['image_versions2'].get('candidates', [])
                                                if candidates:
                                                    urls.append(candidates[0]['url'])
                                            if 'carousel_media' in obj:
                                                for item in obj['carousel_media']:
                                                    if 'image_versions2' in item:
                                                        candidates = item['image_versions2'].get('candidates', [])
                                                        if candidates:
                                                            urls.append(candidates[0]['url'])
                                            for v in obj.values():
                                                urls.extend(find_display_urls(v, depth + 1))
                                        elif isinstance(obj, list):
                                            for item in obj:
                                                urls.extend(find_display_urls(item, depth + 1))
                                        return urls
                                    
                                    found = find_display_urls(data)
                                    for u in found:
                                        u = u.split('?')[0]
                                        if u not in all_photo_urls and '.mp4' not in u:
                                            all_photo_urls.append(u)
                                    
                                    if all_photo_urls:
                                        break
                                except:
                                    continue
                        
                        if all_photo_urls:
                            break
                            
            except Exception as e:
                print(f"  ⚠️ Page scrape error: {e}")
        
        # ============================================
        # DOWNLOAD ALL FOUND PHOTOS
        # ============================================
        if not all_photo_urls:
            print("❌ No photo URLs found!")
            return {"success": False, "error": "No photos found. Instagram changed their API."}
        
        print(f"✅ Found {len(all_photo_urls)} unique photo URLs!")
        
        downloaded = []
        for i, photo_url in enumerate(all_photo_urls, 1):
            try:
                # Fix URL
                if photo_url.startswith('//'):
                    photo_url = 'https:' + photo_url
                
                # Clean URL
                photo_url = photo_url.replace('http://', 'https://')
                
                # File extension
                ext = 'jpg'
                if '.png' in photo_url.lower():
                    ext = 'png'
                elif '.webp' in photo_url.lower():
                    ext = 'webp'
                
                # Filename
                if len(all_photo_urls) > 1:
                    filename = f"{shortcode}_{i}.{ext}"
                else:
                    filename = f"{shortcode}.{ext}"
                
                filepath = os.path.join(DOWNLOAD_DIR, filename)
                
                # Download with retries
                for attempt in range(3):
                    try:
                        img_resp = session.get(photo_url, timeout=30, stream=True)
                        
                        if img_resp.status_code == 200:
                            with open(filepath, 'wb') as f:
                                for chunk in img_resp.iter_content(chunk_size=8192):
                                    if chunk:
                                        f.write(chunk)
                            
                            if os.path.exists(filepath) and os.path.getsize(filepath) > 1000:
                                downloaded.append(filepath)
                                print(f"  ✅ Photo {i}/{len(all_photo_urls)}: {filename} ({os.path.getsize(filepath)} bytes)")
                                break
                            else:
                                os.remove(filepath)
                    except:
                        time.sleep(1)
                        continue
                    
            except Exception as e:
                print(f"  ⚠️ Photo {i} download error: {e}")
                continue
        
        if not downloaded:
            return {"success": False, "error": "Could not download any photos"}
        
        print(f"✅ Total downloaded: {len(downloaded)} photos")
        
        if len(downloaded) == 1:
            return {"success": True, "file_path": downloaded[0], "is_video": False}
        else:
            return {
                "success": True,
                "file_paths": sorted(downloaded),
                "is_video": False,
                "is_multiple": True,
                "total_photos": len(downloaded)
            }
    
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
        "✅ **Reel link** → HD Video 🎬\n"
        "✅ **Post link** → ALL Photos (1-by-1) 📸\n"
        "✅ **Carousel** → Saari photos ek ke baad ek! 🔄\n"
        "✅ **Audio Button** → MP3 ⚡\n\n"
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
        await update.message.reply_text("❌ Invalid Instagram URL")
        return
    
    context.user_data['current_url'] = url
    
    msg = await update.message.reply_text("⏳ **Processing...**", parse_mode="Markdown")
    
    try:
        is_reel = '/reel/' in url or '/tv/' in url
        
        await msg.edit_text("📥 **Downloading...**")
        
        result = InstaDownloader.download_media(url)
        
        if not result.get("success"):
            error = result.get('error', 'Unknown error')
            await msg.edit_text(f"❌ **Failed!**\n\n{error}", parse_mode="Markdown")
            return
        
        # MULTIPLE PHOTOS
        if result.get("is_multiple"):
            photo_paths = result.get("file_paths", [])
            total = result.get("total_photos", len(photo_paths))
            
            await msg.edit_text(f"📤 **{total} Photos mil gayi! Bhej raha hun...**")
            
            for i, fp in enumerate(photo_paths, 1):
                if os.path.exists(fp) and os.path.getsize(fp) > 1000:
                    try:
                        with open(fp, 'rb') as f:
                            caption = f"✅ **Photo {i}/{total}**"
                            if i == 1:
                                caption += f"\n🔗 [Instagram Post]({url})"
                            
                            await update.message.reply_photo(
                                photo=f,
                                caption=caption,
                                parse_mode="Markdown"
                            )
                        
                        if i < total:
                            await asyncio.sleep(0.3)
                    except Exception as e:
                        await update.message.reply_text(f"❌ Photo {i}: {str(e)[:50]}")
                    
                    InstaDownloader.cleanup(fp)
            
            try:
                await msg.edit_text(f"✅ **{total} Photos sent!** 🔥")
                await asyncio.sleep(2)
                await msg.delete()
            except:
                pass
            return
        
        # SINGLE FILE
        fp = result["file_path"]
        if not os.path.exists(fp) or os.path.getsize(fp) < 1000:
            await msg.edit_text("❌ File error")
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
                    caption=f"✅ **Video Downloaded** ✅\n🔗 [Link]({url})",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    supports_streaming=True
                )
        else:
            await msg.edit_text("📤 **Uploading Photo...**")
            with open(fp, 'rb') as f:
                await update.message.reply_photo(
                    photo=f,
                    caption=f"✅ **Photo Downloaded** ✅\n🔗 [Link]({url})",
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
            await status_msg.edit_text("❌ Download failed")
            return
        
        if result.get("is_multiple"):
            vp = result["file_paths"][0]
        else:
            vp = result["file_path"]
        
        if not vp or not os.path.exists(vp):
            await status_msg.edit_text("❌ File not found")
            return
        
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
            await status_msg.edit_text(f"❌ {audio_result.get('error', 'Failed')}")
        
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
            "Jaise: `Meri Song`\nYa: `skip`\n\n⬇️ Type karo:",
            parse_mode="Markdown"
        )
        context.user_data['awaiting_audio'] = True

# ═══════════════════════════
# 🚀 MAIN
# ═══════════════════════════

def main():
    logging.basicConfig(level=logging.INFO)
    
    print("=" * 50)
    print("  INSTAGRAM BOT - NO yt-dlp FOR PHOTOS")
    print("=" * 50)
    
    if not shutil.which('ffmpeg'):
        os.system('apt-get update && apt-get install ffmpeg -y 2>/dev/null')
    print(f"✅ FFmpeg: {shutil.which('ffmpeg')}")
    
    for f in os.listdir(DOWNLOAD_DIR):
        try: os.remove(os.path.join(DOWNLOAD_DIR, f))
        except: pass
    
    print("✅ Bot Started!")
    print("📸 Photos: Direct download (oEmbed + scraping)")
    print("🔄 Carousel: ALL photos supported!")
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    app.run_polling()

if __name__ == "__main__":
    main()
