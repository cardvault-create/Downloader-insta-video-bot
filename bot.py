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
            print(f"📸 Downloading Post: {shortcode}")
            return InstaDownloader._download_post(shortcode, url)
    
    @staticmethod
    def _download_video(shortcode, url):
        """Reel/Video download"""
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
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                
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
                return {"success": False, "error": "cookies.txt expired!"}
            return {"success": False, "error": f"Error: {err[:80]}"}
    
    @staticmethod
    def _download_post(shortcode, url):
        """
        Post download - CAROUSEL FULL SUPPORT
        Step 1: Extract info to check if carousel
        Step 2: Download ALL photos
        Step 3: Return all file paths
        """
        
        # Clean existing files for this shortcode
        for f in list(os.listdir(DOWNLOAD_DIR)):
            if shortcode in f:
                try: os.remove(os.path.join(DOWNLOAD_DIR, f))
                except: pass
        
        try:
            # ============================================
            # STEP 1: Extract info to check media count
            # ============================================
            print(f"🔍 Checking post type for: {shortcode}")
            
            info_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
                'dumpjson': False,
            }
            if os.path.exists('cookies.txt'):
                info_opts['cookiefile'] = 'cookies.txt'
            
            media_count = 1  # Default: single photo
            is_carousel = False
            
            try:
                with yt_dlp.YoutubeDL(info_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    
                    if info:
                        # Check for playlist/carousel
                        entries = info.get('entries', [])
                        if entries:
                            media_count = len(entries)
                            is_carousel = True
                            print(f"📸 Carousel detected: {media_count} photos!")
                        else:
                            # Check other indicators
                            if 'playlist_count' in info and info['playlist_count'] > 1:
                                media_count = info['playlist_count']
                                is_carousel = True
                                print(f"📸 Carousel detected (playlist): {media_count} photos!")
                            else:
                                print(f"📸 Single photo post")
            except Exception as e:
                print(f"⚠️ Info extraction error (will try direct download): {e}")
            
            # ============================================
            # STEP 2: Download all media
            # ============================================
            print(f"📥 Downloading {media_count} photo(s)...")
            
            if is_carousel:
                # Carousel: Download with playlist index
                download_opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'outtmpl': os.path.join(DOWNLOAD_DIR, f'{shortcode}_%(playlist_index)s.%(ext)s'),
                    'format': 'best[ext=jpg]/best[ext=png]/best[ext=webp]/best',
                    'retries': 3,
                    'ignoreerrors': True,
                    'no_playlist': False,
                    'extract_flat': False,
                }
            else:
                # Single photo: Simple download
                download_opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'outtmpl': os.path.join(DOWNLOAD_DIR, f'{shortcode}.%(ext)s'),
                    'format': 'best[ext=jpg]/best[ext=png]/best[ext=webp]/best',
                    'retries': 3,
                }
            
            if os.path.exists('cookies.txt'):
                download_opts['cookiefile'] = 'cookies.txt'
            
            try:
                with yt_dlp.YoutubeDL(download_opts) as ydl:
                    ydl.download([url])
                print("✅ Download completed!")
            except Exception as e:
                print(f"⚠️ First download attempt failed: {e}")
                
                # Fallback: Try simple download
                fallback_opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'outtmpl': os.path.join(DOWNLOAD_DIR, f'{shortcode}.%(ext)s'),
                    'format': 'best',
                    'retries': 3,
                }
                if os.path.exists('cookies.txt'):
                    fallback_opts['cookiefile'] = 'cookies.txt'
                
                try:
                    with yt_dlp.YoutubeDL(fallback_opts) as ydl:
                        ydl.download([url])
                    print("✅ Fallback download completed!")
                except Exception as e2:
                    print(f"❌ All download attempts failed: {e2}")
            
            # ============================================
            # STEP 3: Collect downloaded files
            # ============================================
            time.sleep(1)  # Wait for files
            
            photo_files = []
            
            for f in sorted(os.listdir(DOWNLOAD_DIR)):
                if shortcode in f and not f.endswith(('.mp4', '.mov', '.webm', '.part', '.ytdl')):
                    fp = os.path.join(DOWNLOAD_DIR, f)
                    if os.path.exists(fp) and os.path.getsize(fp) > 1000:
                        photo_files.append(fp)
                        print(f"  📸 {f} ({os.path.getsize(fp)} bytes)")
            
            # Remove duplicates (same size = same photo)
            if len(photo_files) > 1:
                unique_photos = []
                seen_sizes = set()
                for fp in photo_files:
                    size = os.path.getsize(fp)
                    if size not in seen_sizes:
                        seen_sizes.add(size)
                        unique_photos.append(fp)
                    else:
                        try: os.remove(fp)
                        except: pass
                photo_files = unique_photos
            
            if not photo_files:
                print("❌ No photos downloaded!")
                return {"success": False, "error": "No photos found. Post may be private or deleted."}
            
            print(f"✅ Total photos collected: {len(photo_files)}")
            
            # ============================================
            # STEP 4: Return result
            # ============================================
            if len(photo_files) == 1:
                return {"success": True, "file_path": photo_files[0], "is_video": False}
            else:
                return {
                    "success": True,
                    "file_paths": sorted(photo_files),
                    "is_video": False,
                    "is_multiple": True,
                    "total_photos": len(photo_files)
                }
                
        except Exception as e:
            print(f"❌ Fatal error: {e}")
            return {"success": False, "error": f"Download error: {str(e)[:100]}"}
    
    @staticmethod
    def extract_audio(video_path, custom_name=None):
        """Extract audio from video"""
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
                return {"success": False, "error": "No audio track in this video"}
            
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
        "✅ **Reel** → HD Video + Audio 🎬\n"
        "✅ **Post** → ALL Photos (1-by-1) 📸\n"
        "✅ **Carousel/Album** → Ek ke baad ek saari photos! 🔄\n"
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
    
    # Audio name input handling
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
        
        if is_reel:
            await msg.edit_text("📥 **Downloading Reel...**")
        else:
            await msg.edit_text("📥 **Checking & Downloading Photos...**")
        
        result = InstaDownloader.download_media(url)
        
        if not result.get("success"):
            error = result.get('error', 'Unknown error')
            await msg.edit_text(f"❌ **Failed!**\n\n{error}", parse_mode="Markdown")
            return
        
        # ============================================
        # HANDLE MULTIPLE PHOTOS (CAROUSEL)
        # ============================================
        if result.get("is_multiple"):
            photo_paths = result.get("file_paths", [])
            total = result.get("total_photos", len(photo_paths))
            
            await msg.edit_text(f"📤 **{total} Photos mil gayi! Ek ek karke bhej raha hun...** ⏳")
            
            success_count = 0
            for i, fp in enumerate(photo_paths, 1):
                if os.path.exists(fp) and os.path.getsize(fp) > 1000:
                    try:
                        with open(fp, 'rb') as f:
                            if i == 1:
                                caption = f"✅ **Photo {i}/{total}**\n🔗 [View on Instagram]({url})"
                            else:
                                caption = f"✅ **Photo {i}/{total}**"
                            
                            await update.message.reply_photo(
                                photo=f,
                                caption=caption,
                                parse_mode="Markdown"
                            )
                            success_count += 1
                            print(f"  ✅ Sent photo {i}/{total}")
                        
                        # Small delay
                        if i < total:
                            await asyncio.sleep(0.5)
                            
                    except Exception as e:
                        print(f"  ❌ Photo {i} send error: {e}")
                        await update.message.reply_text(f"❌ Photo {i} bhejne mein error!")
                    
                    # Cleanup
                    InstaDownloader.cleanup(fp)
            
            # Final status
            try:
                await msg.edit_text(f"✅ **{success_count}/{total} Photos bhej diye!** 🔥")
                await asyncio.sleep(2)
                await msg.delete()
            except:
                pass
            
            return
        
        # ============================================
        # HANDLE SINGLE FILE
        # ============================================
        fp = result["file_path"]
        if not os.path.exists(fp) or os.path.getsize(fp) < 1000:
            await msg.edit_text("❌ File corrupted or too small")
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
                    caption=f"✅ **Video Downloaded** ✅\n🔗 [View on Instagram]({url})",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    supports_streaming=True
                )
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
        error_msg = str(e)[:100]
        print(f"❌ Handler error: {e}")
        await msg.edit_text(f"❌ **Error:** {error_msg}")
        
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
    
    print("=" * 50)
    print("  INSTAGRAM BOT - CAROUSEL SUPPORT")
    print("=" * 50)
    
    # FFmpeg
    if not shutil.which('ffmpeg'):
        print("⚠️ Installing FFmpeg...")
        os.system('apt-get update && apt-get install ffmpeg -y 2>/dev/null')
    print(f"✅ FFmpeg: {shutil.which('ffmpeg')}")
    
    # Cookies
    if os.path.exists('cookies.txt'):
        print(f"✅ cookies.txt: {os.path.getsize('cookies.txt')} bytes")
    else:
        print("ℹ️ cookies.txt not found")
    
    # Clean downloads folder
    for f in os.listdir(DOWNLOAD_DIR):
        try: os.remove(os.path.join(DOWNLOAD_DIR, f))
        except: pass
    
    print("=" * 50)
    print("✅ BOT STARTED!")
    print("📸 Posts: ALL photos (carousel supported)")
    print("🎬 Reels: HD video + audio")
    print("=" * 50)
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    app.run_polling()

if __name__ == "__main__":
    main()
