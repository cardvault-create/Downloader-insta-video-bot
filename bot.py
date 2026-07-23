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
            print(f"📸 Downloading Photo(s): {shortcode}")
            return InstaDownloader._download_photo(shortcode)
    
    # ═══════════════════════════
    # 🎬 VIDEO
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
                return {"success": False, "error": "❌ cookies.txt expired! Naya banao."}
            return {"success": False, "error": f"❌ {err[:80]}"}
    
    # ═══════════════════════════
    # 📸 PHOTO - COMBO METHOD (oEmbed + yt-dlp)
    # ═══════════════════════════
    
    @staticmethod
    def _download_photo(shortcode):
        """
        COMBO METHOD:
        1. Pehle oEmbed API se check karo (fast, no login needed)
        2. Phir yt-dlp se saari photos download karo (including carousel)
        3. Agar yt-dlp fail, to oEmbed se kam se kam pehli photo to do
        """
        
        all_photos = []
        
        # ═══════════════════════
        # STEP 1: yt-dlp se saari photos download karo
        # ═══════════════════════
        print("📥 Step 1: Downloading ALL photos via yt-dlp...")
        yt_result = InstaDownloader._download_via_ytdlp(shortcode)
        
        if yt_result.get("success"):
            if yt_result.get("is_multiple"):
                print(f"✅ yt-dlp se {len(yt_result['file_paths'])} photos mili!")
                return yt_result
            else:
                print("✅ yt-dlp se single photo mili!")
                all_photos.append(yt_result["file_path"])
        
        # ═══════════════════════
        # STEP 2: Agar yt-dlp fail, to oEmbed se try karo
        # ═══════════════════════
        if not all_photos:
            print("📥 Step 2: Trying oEmbed API...")
            oembed_result = InstaDownloader._download_via_oembed(shortcode)
            
            if oembed_result.get("success"):
                if oembed_result.get("is_multiple"):
                    return oembed_result
                else:
                    all_photos.append(oembed_result["file_path"])
                    print("✅ oEmbed se photo mili!")
        
        # ═══════════════════════
        # STEP 3: Agar kuch bhi nahi mila, to error
        # ═══════════════════════
        if all_photos:
            return {"success": True, "file_path": all_photos[0], "is_video": False}
        
        return {"success": False, "error": "Photo download failed. Try again later."}
    
    # ═══════════════════════
    # METHOD: yt-dlp (CAROUSEL SUPPORT)
    # ═══════════════════════
    
    @staticmethod
    def _download_via_ytdlp(shortcode):
        """yt-dlp se saari photos download karo"""
        try:
            url = f"https://www.instagram.com/p/{shortcode}/"
            
            # Pehle info extract karo bina download kiye
            info_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
            }
            if os.path.exists('cookies.txt'):
                info_opts['cookiefile'] = 'cookies.txt'
            
            with yt_dlp.YoutubeDL(info_opts) as ydl:
                try:
                    info = ydl.extract_info(url, download=False)
                except:
                    info = None
            
            # Ab download karo
            download_opts = {
                'quiet': True,
                'no_warnings': True,
                'outtmpl': os.path.join(DOWNLOAD_DIR, f'{shortcode}_%(playlist_index)s.%(ext)s'),
                'format': 'best[ext=jpg]/best[ext=png]/best[ext=webp]/best',
                'retries': 3,
                'ignoreerrors': True,
                'no_playlist': False,  # Carousel ke liye playlist mode ON
            }
            if os.path.exists('cookies.txt'):
                download_opts['cookiefile'] = 'cookies.txt'
            
            with yt_dlp.YoutubeDL(download_opts) as ydl:
                try:
                    ydl.download([url])
                except:
                    # Agar playlist mode fail, to single try karo
                    download_opts['no_playlist'] = True
                    download_opts['outtmpl'] = os.path.join(DOWNLOAD_DIR, f'{shortcode}.%(ext)s')
                    with yt_dlp.YoutubeDL(download_opts) as ydl2:
                        ydl2.download([url])
            
            # Wait for files to be written
            time.sleep(1.5)
            
            # Saari downloaded photos collect karo
            photo_files = []
            for f in sorted(os.listdir(DOWNLOAD_DIR)):
                if shortcode in f and not f.endswith(('.mp4', '.mov', '.webm')):
                    fp = os.path.join(DOWNLOAD_DIR, f)
                    if os.path.exists(fp) and os.path.getsize(fp) > 1000:
                        photo_files.append(fp)
                        print(f"  📸 Found: {f} ({os.path.getsize(fp)} bytes)")
            
            # Agar playlist index wali files nahi mili, to direct shortcode wali dhundho
            if not photo_files:
                for f in os.listdir(DOWNLOAD_DIR):
                    if shortcode in f and not f.endswith(('.mp4', '.mov', '.webm')):
                        fp = os.path.join(DOWNLOAD_DIR, f)
                        if os.path.exists(fp) and os.path.getsize(fp) > 1000:
                            photo_files.append(fp)
            
            if photo_files:
                # Remove duplicates
                unique_photos = []
                seen_sizes = set()
                for fp in photo_files:
                    size = os.path.getsize(fp)
                    if size not in seen_sizes:
                        seen_sizes.add(size)
                        unique_photos.append(fp)
                
                print(f"✅ yt-dlp total photos: {len(unique_photos)}")
                
                if len(unique_photos) == 1:
                    return {"success": True, "file_path": unique_photos[0], "is_video": False}
                else:
                    return {
                        "success": True,
                        "file_paths": sorted(unique_photos),
                        "is_video": False,
                        "is_multiple": True,
                        "total_photos": len(unique_photos)
                    }
            
            return {"success": False}
            
        except Exception as e:
            print(f"⚠️ yt-dlp error: {e}")
            return {"success": False}
    
    # ═══════════════════════
    # METHOD: oEmbed (PUBLIC API - NO LOGIN NEEDED)
    # ═══════════════════════
    
    @staticmethod
    def _download_via_oembed(shortcode):
        """Instagram ka official public oEmbed API - hamesha kaam karega"""
        try:
            post_url = f"https://www.instagram.com/p/{shortcode}/"
            api_url = f"https://api.instagram.com/oembed?url={urllib.parse.quote(post_url)}&maxwidth=1080"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json',
            }
            
            resp = requests.get(api_url, headers=headers, timeout=15)
            
            if resp.status_code != 200:
                print(f"⚠️ oEmbed returned {resp.status_code}")
                return {"success": False}
            
            data = resp.json()
            
            # Thumbnail URL se high quality URL banao
            thumbnail_url = data.get('thumbnail_url', '')
            
            if not thumbnail_url:
                print("⚠️ No thumbnail URL in oEmbed response")
                return {"success": False}
            
            # High quality ke liye URL modify karo
            # /s640x640/ ya /s150x150/ ko /s1080x1080/ se replace karo
            hd_url = re.sub(r'/s\d+x\d+/', '/s1080x1080/', thumbnail_url)
            
            # Agar s1080 wala fail ho to original try karo
            image_urls = [hd_url, thumbnail_url]
            
            print(f"🔗 oEmbed se {len(image_urls)} image URLs try kar rahe hain")
            
            # Download karo
            for img_url in image_urls:
                try:
                    if img_url.startswith('//'):
                        img_url = 'https:' + img_url
                    
                    # Query parameters hatao
                    img_url = img_url.split('?')[0]
                    
                    file_name = f"{shortcode}_oembed.jpg"
                    file_path = os.path.join(DOWNLOAD_DIR, file_name)
                    
                    img_headers = {
                        'User-Agent': 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
                        'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
                        'Referer': 'https://www.instagram.com/',
                    }
                    
                    r = requests.get(img_url, headers=img_headers, stream=True, timeout=30)
                    
                    if r.status_code == 200 and len(r.content) > 1000:
                        with open(file_path, 'wb') as f:
                            for chunk in r.iter_content(chunk_size=8192):
                                if chunk: f.write(chunk)
                        
                        if os.path.exists(file_path) and os.path.getsize(file_path) > 1000:
                            print(f"✅ oEmbed photo downloaded: {os.path.getsize(file_path)} bytes")
                            return {"success": True, "file_path": file_path, "is_video": False}
                    
                except Exception as e:
                    print(f"⚠️ oEmbed download error: {e}")
                    continue
            
            return {"success": False}
            
        except Exception as e:
            print(f"⚠️ oEmbed method error: {e}")
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
        "📥 **Instagram Downloader Bot**\n\n"
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
        
        await msg.edit_text("📥 **Downloading...**")
        
        result = InstaDownloader.download_media(url)
        
        if not result.get("success"):
            error = result.get('error', 'Unknown error')
            await msg.edit_text(
                f"❌ **Failed!**\n\n{error}\n\n"
                f"💡 **Tip:** Kuch der baad try karo ya cookies.txt add karo.",
                parse_mode="Markdown"
            )
            return
        
        # ═══════════════════════
        # MULTIPLE PHOTOS (CAROUSEL)
        # ═══════════════════════
        if result.get("is_multiple"):
            photo_paths = result.get("file_paths", [])
            total = result.get("total_photos", len(photo_paths))
            
            await msg.edit_text(f"📤 **{total} Photos mil gaye! Ek ek karke bhej raha hun...**")
            
            for i, fp in enumerate(photo_paths, 1):
                if os.path.exists(fp) and os.path.getsize(fp) > 1000:
                    try:
                        with open(fp, 'rb') as f:
                            if i == 1:
                                caption = f"✅ **Photo {i}/{total}**\n🔗 [Instagram Post]({url})"
                            else:
                                caption = f"✅ **Photo {i}/{total}**"
                            
                            await update.message.reply_photo(
                                photo=f,
                                caption=caption,
                                parse_mode="Markdown"
                            )
                        
                        # Small delay between photos
                        if i < total:
                            await asyncio.sleep(0.3)
                            
                    except Exception as e:
                        await update.message.reply_text(f"❌ Photo {i} error: {str(e)[:50]}")
                    
                    # Cleanup after sending
                    InstaDownloader.cleanup(fp)
            
            # Final status
            try:
                await msg.edit_text(f"✅ **Sab {total} Photos bhej diye!** 🔥")
                await asyncio.sleep(2)
                await msg.delete()
            except:
                pass
            
            return
        
        # ═══════════════════════
        # SINGLE FILE (Photo or Video)
        # ═══════════════════════
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
        # Cleanup downloads folder
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
        
        # Get video path
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
    print("║  🤖 INSTAGRAM BOT v4.0      ║")
    print("║  Combo: yt-dlp + oEmbed     ║")
    print("╚══════════════════════════════╝")
    
    # FFmpeg
    ffmpeg = shutil.which('ffmpeg')
    if ffmpeg:
        print(f"✅ FFmpeg: {ffmpeg}")
    else:
        print("⚠️ Installing FFmpeg...")
        os.system('apt-get update && apt-get install ffmpeg -y 2>/dev/null')
    
    # cookies.txt
    if os.path.exists('cookies.txt'):
        size = os.path.getsize('cookies.txt')
        print(f"✅ cookies.txt ({size} bytes)")
    else:
        print("ℹ️ cookies.txt not found (works without it too!)")
    
    # Clean downloads
    for f in os.listdir(DOWNLOAD_DIR):
        try: os.remove(os.path.join(DOWNLOAD_DIR, f))
        except: pass
    
    print("✅ Bot Started! 🚀")
    print("📸 Photos: yt-dlp (all photos) + oEmbed (backup)")
    print("🎬 Videos: yt-dlp best format")
    print("🔄 Carousel: ALL photos will be sent one by one!")
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    app.run_polling()

if __name__ == "__main__":
    main()
