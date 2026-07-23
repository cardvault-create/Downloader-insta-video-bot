import os
import re
import subprocess
import shutil
import time
import sys
import requests
import json
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
    def load_cookies():
        """Load cookies from cookies.txt file"""
        cookies = {}
        if not os.path.exists('cookies.txt'):
            return cookies
        
        with open('cookies.txt', 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                parts = line.split('\t')
                if len(parts) >= 7:
                    cookies[parts[5]] = parts[6]
        
        return cookies
    
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
                return InstaDownloader._download_post_direct(shortcode)
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
    def _download_post_direct(shortcode):
        """
        DIRECT PHOTO DOWNLOAD - NO yt-dlp!
        Uses Instagram's embed API + direct scraping
        """
        print("📸 Downloading photos DIRECT METHOD...")
        
        cookies = InstaDownloader.load_cookies()
        session = requests.Session()
        
        # Set cookies
        for name, value in cookies.items():
            session.cookies.set(name, value, domain='.instagram.com')
        
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
        })
        
        all_image_urls = []
        
        # ============================================
        # METHOD 1: oEmbed API (PUBLIC - always works)
        # ============================================
        print("  Method 1: oEmbed API...")
        try:
            post_url = f"https://www.instagram.com/p/{shortcode}/"
            api_url = f"https://api.instagram.com/oembed?url={post_url}"
            
            resp = session.get(api_url, timeout=15)
            
            if resp.status_code == 200:
                data = resp.json()
                thumbnail = data.get('thumbnail_url', '')
                
                if thumbnail:
                    # Get HD version
                    hd_url = re.sub(r'/s\d+x\d+/', '/s1080x1080/', thumbnail)
                    hd_url = hd_url.split('?')[0]
                    if hd_url not in all_image_urls:
                        all_image_urls.append(hd_url)
                        print(f"    ✅ oEmbed: {hd_url[:80]}...")
        except Exception as e:
            print(f"    ⚠️ oEmbed: {e}")
        
        # ============================================
        # METHOD 2: Embed page scrape (carousel support)
        # ============================================
        print("  Method 2: Embed page scrape...")
        try:
            embed_url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
            resp = session.get(embed_url, timeout=15)
            
            if resp.status_code == 200:
                html = resp.text
                
                # Find JSON data in script tags
                json_patterns = [
                    r'<script[^>]*>\s*window\.__INITIAL_STATE__\s*=\s*({.*?});\s*</script>',
                    r'<script[^>]*>({.*?"shortcode_media".*?})</script>',
                ]
                
                for pattern in json_patterns:
                    matches = re.findall(pattern, html, re.DOTALL)
                    for match in matches:
                        try:
                            data = json.loads(match)
                            
                            # Extract all image URLs
                            def extract_urls(obj, depth=0):
                                if depth > 15:
                                    return []
                                urls = []
                                
                                if isinstance(obj, dict):
                                    # Carousel media
                                    if 'carousel_media' in obj:
                                        for item in obj['carousel_media']:
                                            if 'image_versions2' in item:
                                                candidates = item['image_versions2'].get('candidates', [])
                                                if candidates:
                                                    urls.append(candidates[0]['url'])
                                            elif 'display_url' in item:
                                                urls.append(item['display_url'])
                                    
                                    # Single image
                                    if 'display_url' in obj:
                                        u = obj['display_url']
                                        if u not in urls:
                                            urls.append(u)
                                    
                                    if 'image_versions2' in obj:
                                        candidates = obj['image_versions2'].get('candidates', [])
                                        if candidates:
                                            u = candidates[0]['url']
                                            if u not in urls:
                                                urls.append(u)
                                    
                                    # edge_sidecar
                                    if 'edge_sidecar_to_children' in obj:
                                        for edge in obj['edge_sidecar_to_children'].get('edges', []):
                                            node = edge.get('node', {})
                                            if 'display_url' in node:
                                                urls.append(node['display_url'])
                                            elif 'image_versions2' in node:
                                                candidates = node['image_versions2'].get('candidates', [])
                                                if candidates:
                                                    urls.append(candidates[0]['url'])
                                    
                                    for v in obj.values():
                                        urls.extend(extract_urls(v, depth + 1))
                                
                                elif isinstance(obj, list):
                                    for item in obj:
                                        urls.extend(extract_urls(item, depth + 1))
                                
                                return urls
                            
                            found = extract_urls(data)
                            for u in found:
                                u = u.split('?')[0]
                                if u not in all_image_urls and '.mp4' not in u:
                                    all_image_urls.append(u)
                            
                            if len(all_image_urls) > 1:
                                break
                        except:
                            continue
                    
                    if len(all_image_urls) > 1:
                        break
        except Exception as e:
            print(f"    ⚠️ Embed scrape: {e}")
        
        # ============================================
        # METHOD 3: Direct page scrape
        # ============================================
        if not all_image_urls:
            print("  Method 3: Direct page scrape...")
            try:
                page_url = f"https://www.instagram.com/p/{shortcode}/"
                resp = session.get(page_url, timeout=15)
                
                if resp.status_code == 200:
                    html = resp.text
                    
                    # Find all display_url in JSON
                    json_blocks = re.findall(r'\{[^}]*"display_url"[^}]*\}', html)
                    for block in json_blocks:
                        url_match = re.search(r'"display_url"\s*:\s*"([^"]+)"', block)
                        if url_match:
                            u = url_match.group(1).replace('\\u0026', '&').split('?')[0]
                            if u not in all_image_urls and '.mp4' not in u:
                                all_image_urls.append(u)
            except Exception as e:
                print(f"    ⚠️ Direct scrape: {e}")
        
        # ============================================
        # DOWNLOAD ALL FOUND PHOTOS
        # ============================================
        if not all_image_urls:
            print("❌ No image URLs found!")
            return {"success": False, "error": "No photos found. Post may be private."}
        
        print(f"\n✅ Found {len(all_image_urls)} photo URL(s)")
        
        downloaded = []
        img_headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15',
            'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
            'Referer': 'https://www.instagram.com/',
        }
        
        for i, img_url in enumerate(all_image_urls, 1):
            try:
                # Fix URL
                if img_url.startswith('//'):
                    img_url = 'https:' + img_url
                
                # Extension
                ext = 'jpg'
                if '.png' in img_url.lower():
                    ext = 'png'
                elif '.webp' in img_url.lower():
                    ext = 'webp'
                
                # Filename
                if len(all_image_urls) > 1:
                    filename = f"{shortcode}_{i}.{ext}"
                else:
                    filename = f"{shortcode}.{ext}"
                
                filepath = os.path.join(DOWNLOAD_DIR, filename)
                
                # Download with retries
                for attempt in range(3):
                    try:
                        img_resp = session.get(img_url, headers=img_headers, timeout=30)
                        
                        if img_resp.status_code == 200 and len(img_resp.content) > 1000:
                            with open(filepath, 'wb') as f:
                                f.write(img_resp.content)
                            
                            if os.path.exists(filepath) and os.path.getsize(filepath) > 1000:
                                downloaded.append(filepath)
                                print(f"  ✅ Photo {i}/{len(all_image_urls)}: {filename} ({os.path.getsize(filepath)} bytes)")
                                break
                        else:
                            time.sleep(0.5)
                    except:
                        time.sleep(0.5)
                        continue
                        
            except Exception as e:
                print(f"  ❌ Photo {i}: {e}")
                continue
        
        if downloaded:
            print(f"\n✅ Total downloaded: {len(downloaded)} photo(s)")
            
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
        
        return {"success": False, "error": "Could not download any photos"}
    
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
    print("  INSTAGRAM BOT - DIRECT METHOD")
    print("=" * 50)
    
    if not shutil.which('ffmpeg'):
        os.system('apt-get update -qq && apt-get install ffmpeg -y -qq 2>/dev/null')
    
    for f in os.listdir(DOWNLOAD_DIR):
        try: os.remove(os.path.join(DOWNLOAD_DIR, f))
        except: pass
    
    print("✅ Bot Started!")
    print("📸 Photos: Direct download (NO yt-dlp)")
    print("🎬 Reels: yt-dlp")
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.run_polling()

if __name__ == "__main__":
    main()
