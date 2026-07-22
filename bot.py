import logging
import os
import re
import subprocess
import shutil
import time
import json
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
# 📥 DOWNLOAD ENGINE - GRAPHQL API BASED
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
    def _get_shortcode(url):
        """Extract shortcode from URL"""
        match = re.search(r'/(p|reel|tv|stories|s)/([a-zA-Z0-9_\-]+)', url)
        if match:
            return match.group(2)
        return None

    @staticmethod
    def _get_cookies():
        """Parse cookies from cookies.txt file"""
        cookies = {}
        if os.path.exists('cookies.txt'):
            with open('cookies.txt', 'r') as f:
                for line in f:
                    if line.startswith('#') or not line.strip():
                        continue
                    parts = line.strip().split('\t')
                    if len(parts) >= 7:
                        cookies[parts[5]] = parts[6]
            return cookies
        return None

    @staticmethod
    def download_media(url):
        """Main download function using GraphQL API"""
        
        shortcode = InstaDownloader._get_shortcode(url)
        if not shortcode:
            return {"success": False, "error": "Invalid URL"}
        
        print(f"🔍 Fetching media for shortcode: {shortcode}")
        
        # Get media info using GraphQL
        media_info = InstaDownloader._get_media_info(shortcode)
        if not media_info:
            return {"success": False, "error": "Failed to fetch media info"}
        
        # Check if it's video or photo
        if media_info.get('is_video'):
            print("🎬 Downloading video...")
            return InstaDownloader._download_video(media_info, url)
        else:
            print("📸 Downloading photo(s)...")
            return InstaDownloader._download_photos(media_info, shortcode)

    @staticmethod
    def _get_media_info(shortcode):
        """Fetch media info using Instagram's GraphQL API"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Cache-Control': 'max-age=0',
            }
            
            # Get cookies
            cookies = InstaDownloader._get_cookies()
            if not cookies:
                print("❌ No cookies found")
                return None
            
            # First, get the page to extract CSRF token
            page_url = f"https://www.instagram.com/p/{shortcode}/"
            response = requests.get(page_url, headers=headers, cookies=cookies, timeout=15)
            
            if response.status_code != 200:
                print(f"❌ Failed to fetch page: {response.status_code}")
                return None
            
            html = response.text
            
            # Extract JSON data from page
            json_pattern = r'<script type="text/javascript">window\._sharedData = (.*?);</script>'
            json_match = re.search(json_pattern, html, re.DOTALL)
            
            if not json_match:
                print("❌ No JSON data found in page")
                return None
            
            try:
                data = json.loads(json_match.group(1))
                
                # Navigate to media data
                if 'entry_data' in data:
                    for entry in data['entry_data'].get('PostPage', []):
                        if 'graphql' in entry:
                            media = entry['graphql'].get('shortcode_media', {})
                            if media:
                                print("✅ Media info fetched successfully")
                                return media
                
                return None
                
            except json.JSONDecodeError as e:
                print(f"❌ JSON decode error: {e}")
                return None
                
        except Exception as e:
            print(f"❌ Error fetching media info: {e}")
            return None

    @staticmethod
    def _download_photos(media_info, shortcode):
        """Download photo(s) from media info"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            }
            
            downloaded_paths = []
            
            # Check if it's a carousel (multiple photos)
            if media_info.get('__typename') == 'GraphSidecar':
                edges = media_info.get('edge_sidecar_to_children', {}).get('edges', [])
                print(f"📸 Found {len(edges)} photos in carousel")
                
                for i, edge in enumerate(edges):
                    node = edge.get('node', {})
                    if node.get('display_url'):
                        img_url = node['display_url']
                        ext = img_url.split('.')[-1].split('?')[0]
                        if ext not in ['jpg', 'jpeg', 'png', 'webp']:
                            ext = 'jpg'
                        
                        file_name = f"{shortcode}_{i+1}.{ext}"
                        file_path = os.path.join(DOWNLOAD_DIR, file_name)
                        
                        # Download image
                        img_response = requests.get(img_url, headers=headers, stream=True, timeout=30)
                        if img_response.status_code == 200:
                            with open(file_path, 'wb') as f:
                                for chunk in img_response.iter_content(chunk_size=8192):
                                    if chunk:
                                        f.write(chunk)
                            
                            if os.path.getsize(file_path) > 1000:
                                downloaded_paths.append(file_path)
                                print(f"✅ Downloaded photo {i+1}")
            
            # Single photo
            elif media_info.get('display_url'):
                img_url = media_info['display_url']
                ext = img_url.split('.')[-1].split('?')[0]
                if ext not in ['jpg', 'jpeg', 'png', 'webp']:
                    ext = 'jpg'
                
                file_name = f"{shortcode}.{ext}"
                file_path = os.path.join(DOWNLOAD_DIR, file_name)
                
                img_response = requests.get(img_url, headers=headers, stream=True, timeout=30)
                if img_response.status_code == 200:
                    with open(file_path, 'wb') as f:
                        for chunk in img_response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                    
                    if os.path.getsize(file_path) > 1000:
                        downloaded_paths.append(file_path)
                        print(f"✅ Downloaded photo")
            
            if downloaded_paths:
                if len(downloaded_paths) == 1:
                    return {"success": True, "file_path": downloaded_paths[0], "is_video": False}
                else:
                    return {"success": True, "file_paths": downloaded_paths, "is_video": False, "is_multiple": True}
            else:
                return {"success": False, "error": "No photos downloaded"}
                
        except Exception as e:
            print(f"❌ Photo download error: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def _download_video(media_info, url):
        """Download video with audio using yt-dlp"""
        try:
            if not os.path.exists('cookies.txt'):
                return {"success": False, "error": "cookies.txt not found"}
            
            # Get video URL from media info if available
            if media_info.get('video_url'):
                print("🎬 Downloading video from direct URL...")
                video_url = media_info['video_url']
                shortcode = InstaDownloader._get_shortcode(url)
                file_path = os.path.join(DOWNLOAD_DIR, f"{shortcode}.mp4")
                
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                }
                
                video_response = requests.get(video_url, headers=headers, stream=True, timeout=60)
                if video_response.status_code == 200:
                    with open(file_path, 'wb') as f:
                        for chunk in video_response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                    
                    if os.path.getsize(file_path) > 1000:
                        print(f"✅ Video downloaded: {file_path}")
                        return {"success": True, "file_path": file_path, "is_video": True}
            
            # Fallback to yt-dlp
            print("🎬 Downloading video using yt-dlp...")
            video_opts = {
                'quiet': True,
                'no_warnings': True,
                'ignoreerrors': True,
                'outtmpl': os.path.join(DOWNLOAD_DIR, '%(id)s.%(ext)s'),
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                'merge_output_format': 'mp4',
                'cookiefile': 'cookies.txt',
                'postprocessors': [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4',
                }],
            }
            
            with yt_dlp.YoutubeDL(video_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if info:
                    file_id = info.get('id', 'unknown')
                    file_path = None
                    for f in os.listdir(DOWNLOAD_DIR):
                        if file_id in f and f.endswith('.mp4'):
                            file_path = os.path.join(DOWNLOAD_DIR, f)
                            break
                    
                    if file_path and os.path.getsize(file_path) > 1000:
                        print(f"✅ Video downloaded: {file_path}")
                        return {"success": True, "file_path": file_path, "is_video": True}
            
            return {"success": False, "error": "Video download failed"}
            
        except Exception as e:
            print(f"❌ Video download error: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def extract_audio(video_path, custom_name=None):
        """Extract audio from video"""
        try:
            if custom_name and custom_name != "skip":
                safe_name = re.sub(r'[^\w\s-]', '', custom_name).strip()
                if not safe_name:
                    safe_name = "Instagram_Audio"
                audio_path = os.path.join(DOWNLOAD_DIR, f"{safe_name}.mp3")
            else:
                audio_path = video_path.rsplit('.', 1)[0] + '.mp3'
            
            # Check if video has audio
            probe_cmd = ['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_entries', 'stream=codec_type', '-of', 'csv=p=0', video_path]
            probe_result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=30)
            
            if not probe_result.stdout.strip():
                return {"success": False, "error": "❌ Is video main audio nahi hai!"}
            
            # Extract audio
            cmd = ['ffmpeg', '-i', video_path, '-vn', '-acodec', 'libmp3lame', '-ab', '192k', '-y', audio_path]
            subprocess.run(cmd, capture_output=True, timeout=180)
            
            if os.path.exists(audio_path) and os.path.getsize(audio_path) > 1000:
                return {"success": True, "file_path": audio_path}
            
            return {"success": False, "error": "Audio extract failed"}
            
        except Exception as e:
            return {"success": False, "error": f"Error: {str(e)}"}
    
    @staticmethod
    def cleanup(file_path):
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
            if file_path:
                ap = file_path.rsplit('.', 1)[0] + '.mp3'
                if os.path.exists(ap):
                    os.remove(ap)
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
        "✅ Video link bhejo → **Video with Audio**\n"
        "✅ Photo link bhejo → **High Quality Photo(s)**\n"
        "✅ Multiple photos → **1-1 karke**\n"
        "✅ Audio button → **Custom name**\n\n"
        "**Example:**\n"
        "`https://www.instagram.com/reel/xyz/`\n"
        "`https://www.instagram.com/p/xyz/`\n\n"
        "**Note:** cookies.txt must be valid!",
        parse_mode="Markdown"
    )

async def update_status(msg, text):
    try:
        await msg.edit_text(text, parse_mode="Markdown")
    except:
        pass

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.id
    if user not in AUTHORIZED_USERS:
        return
    
    text = update.message.text
    
    # Check if it's audio name input
    if context.user_data.get('awaiting_audio_name'):
        context.user_data['awaiting_audio_name'] = False
        audio_name = text.strip()
        keyboard = [[InlineKeyboardButton("✅ Confirm", callback_data=f"audio_confirm_{audio_name}")]]
        await update.message.reply_text(
            f"🎵 Audio Name: **{audio_name}**\n\nClick confirm to extract.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return
    
    # Check if it's Instagram URL
    if not InstaDownloader.is_instagram_url(text):
        return
    
    url = InstaDownloader.extract_url(text)
    if not url:
        await update.message.reply_text("❌ Invalid URL")
        return
    
    msg = await update.message.reply_text("⏳ **Checking...**", parse_mode="Markdown")
    
    try:
        # Get media info first
        shortcode = InstaDownloader._get_shortcode(url)
        if not shortcode:
            await msg.edit_text("❌ Invalid URL")
            return
        
        await update_status(msg, "📥 **Fetching Media Info...**")
        
        media_info = InstaDownloader._get_media_info(shortcode)
        if not media_info:
            await msg.edit_text(
                f"❌ **Failed:** Could not fetch media info\n\n"
                f"💡 **Solution:**\n"
                f"1. cookies.txt expire ho gayi hai\n"
                f"2. Instagram se logout → login karein\n"
                f"3. Fresh cookies.txt export karein\n"
                f"4. GitHub par update karein\n"
                f"5. Railway redeploy karein",
                parse_mode="Markdown"
            )
            return
        
        is_video = media_info.get('is_video', False)
        
        if is_video:
            await update_status(msg, "📥 **Downloading Video From Instagram...**")
        else:
            await update_status(msg, "📸 **Downloading Photo From Instagram...**")
        
        result = InstaDownloader.download_media(url)
        
        if not result.get("success"):
            await msg.edit_text(
                f"❌ **Failed:** {result.get('error')}\n\n"
                f"💡 **Solution:**\n"
                f"1. cookies.txt expire ho gayi hai\n"
                f"2. Instagram se logout → login karein\n"
                f"3. Fresh cookies.txt export karein\n"
                f"4. GitHub par update karein\n"
                f"5. Railway redeploy karein",
                parse_mode="Markdown"
            )
            return
        
        # Multiple photos
        if result.get("is_multiple"):
            photo_paths = result.get("file_paths", [])
            if photo_paths:
                await update_status(msg, f"📸 **Uploading {len(photo_paths)} Photos...**")
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
                            await update.message.reply_text(f"❌ Error sending photo {i+1}: {str(e)}")
                        InstaDownloader.cleanup(fp)
                await msg.delete()
                return
        
        # Single file
        fp = result["file_path"]
        if not os.path.exists(fp) or os.path.getsize(fp) < 1000:
            await msg.edit_text("❌ Download incomplete")
            return
        
        if os.path.getsize(fp) > 50 * 1024 * 1024:
            await msg.edit_text("❌ File >50MB (Telegram limit)")
            InstaDownloader.cleanup(fp)
            return
        
        is_video = result.get("is_video", False) or fp.endswith(('.mp4', '.mov', '.webm'))
        
        try:
            if is_video:
                await update_status(msg, "📤 **Uploading Video...**")
                context.user_data['audio_url'] = url
                keyboard = [[InlineKeyboardButton("🎵 Download Audio", callback_data="audio_request")]]
                with open(fp, 'rb') as f:
                    await update.message.reply_video(
                        video=f,
                        caption=f"✅ **Video with Audio** ✅\n🔗 [Instagram Link]({url})\n\n📌 Audio ke liye button click karein",
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        supports_streaming=True
                    )
            else:
                await update_status(msg, "📤 **Uploading Photo...**")
                with open(fp, 'rb') as f:
                    await update.message.reply_photo(
                        photo=f,
                        caption=f"✅ **Photo Downloaded** ✅\n🔗 [Instagram Link]({url})",
                        parse_mode="Markdown"
                    )
            await msg.delete()
        except TimedOut:
            await msg.edit_text("⏰ **Timeout!** Try again.")
        except Exception as e:
            await msg.edit_text(f"❌ Send error: {str(e)}")
        
        InstaDownloader.cleanup(fp)
        
    except Exception as e:
        await msg.edit_text(f"❌ Error: {str(e)}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "audio_request":
        await query.edit_message_reply_markup(reply_markup=None)
        await query.message.reply_text(
            "🎵 **Audio Name?**\n\n"
            "Audio ka naam likhein (jaise: `My Song`)\n"
            "Ya `skip` likhein default naam ke liye.",
            parse_mode="Markdown"
        )
        context.user_data['awaiting_audio_name'] = True
        return
    
    elif data.startswith("audio_confirm_"):
        custom_name = data.replace("audio_confirm_", "")
        if custom_name == "skip":
            custom_name = None
        
        url = context.user_data.get('audio_url')
        if not url:
            await query.message.reply_text("❌ URL not found. Please send video again.")
            return
        
        await query.edit_message_reply_markup(reply_markup=None)
        status_msg = await query.message.reply_text("🎵 **Extracting Audio...**", parse_mode="Markdown")
        
        try:
            result = InstaDownloader.download_media(url)
            if not result.get("success"):
                await status_msg.edit_text("❌ Video download failed.")
                return
            
            vp = result["file_path"]
            audio_result = InstaDownloader.extract_audio(vp, custom_name)
            
            if audio_result.get("success"):
                ap = audio_result["file_path"]
                try:
                    audio_name = custom_name if custom_name else "Instagram Audio"
                    await update_status(status_msg, "📤 **Uploading Audio...**")
                    with open(ap, 'rb') as f:
                        await query.message.reply_audio(
                            audio=f,
                            title=audio_name,
                            performer="Instagram",
                            caption=f"🎵 **{audio_name}** ✅"
                        )
                    await status_msg.edit_text("✅ Audio sent! 🎵")
                except TimedOut:
                    await status_msg.edit_text("⏰ Timeout! Try again.")
                except Exception as e:
                    await status_msg.edit_text(f"❌ Error: {str(e)}")
                try: 
                    os.remove(ap)
                except: 
                    pass
            else:
                await status_msg.edit_text(f"❌ {audio_result.get('error')}")
            
            InstaDownloader.cleanup(vp)
            
        except Exception as e:
            await status_msg.edit_text(f"❌ Error: {str(e)}")
        
        context.user_data['awaiting_audio_name'] = False

# ══════════════════════════════════════
# 🚀 MAIN
# ══════════════════════════════════════

def main():
    logging.basicConfig(level=logging.INFO)
    
    # Check FFmpeg
    ffmpeg_path = shutil.which('ffmpeg')
    if ffmpeg_path:
        print(f"✅ FFmpeg found: {ffmpeg_path}")
    else:
        print("⚠️ FFmpeg not found! Installing...")
        os.system('apt-get update && apt-get install ffmpeg -y')
    
    # Check cookies.txt
    if os.path.exists('cookies.txt'):
        print("✅ cookies.txt found")
        try:
            with open('cookies.txt', 'r') as f:
                lines = f.readlines()
                print(f"📄 cookies.txt has {len(lines)} lines")
                has_session = any('sessionid' in line for line in lines)
                if has_session:
                    print("✅ cookies.txt has sessionid (valid)")
                else:
                    print("⚠️ cookies.txt missing sessionid - might be expired!")
        except:
            print("⚠️ Error reading cookies.txt")
    else:
        print("⚠️ cookies.txt not found!")
    
    print("✅ Bot Started!")
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    app.run_polling()

if __name__ == "__main__":
    main()
