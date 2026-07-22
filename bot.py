import logging
import os
import re
import subprocess
import shutil
import time
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
# 📥 DOWNLOAD ENGINE
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
    def download_media(url):
        result = InstaDownloader._download_ytdlp(url)
        if result.get("success"):
            return result
        result = InstaDownloader._download_scrape(url)
        if result.get("success"):
            return result
        return {"success": False, "error": "Download failed. cookies.txt check karo."}
    
    @staticmethod
    def _download_ytdlp(url):
        try:
            ydl_opts_info = {
                'quiet': True,
                'no_warnings': True,
                'ignoreerrors': True,
            }
            
            if os.path.exists('cookies.txt'):
                ydl_opts_info['cookiefile'] = 'cookies.txt'
            
            with yt_dlp.YoutubeDL(ydl_opts_info) as ydl:
                info = ydl.extract_info(url, download=False)
                
                if not info:
                    return {"success": False, "error": "No info"}
                
                is_video = info.get('is_video', False)
                ext = info.get('ext', '')
                formats = info.get('formats', [])
                has_video_format = any(f.get('vcodec') != 'none' for f in formats)
                
                if is_video or has_video_format or ext in ['mp4', 'mov', 'webm']:
                    ydl_opts_dl = {
                        'quiet': True,
                        'no_warnings': True,
                        'ignoreerrors': True,
                        'outtmpl': os.path.join(DOWNLOAD_DIR, '%(id)s.%(ext)s'),
                        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                    }
                    if os.path.exists('cookies.txt'):
                        ydl_opts_dl['cookiefile'] = 'cookies.txt'
                    
                    with yt_dlp.YoutubeDL(ydl_opts_dl) as ydl2:
                        info2 = ydl2.extract_info(url, download=True)
                        if info2:
                            file_id = info2.get('id', 'unknown')
                            file_path = os.path.join(DOWNLOAD_DIR, f"{file_id}.mp4")
                            
                            if not os.path.exists(file_path):
                                for f in os.listdir(DOWNLOAD_DIR):
                                    if file_id in f and f.endswith('.mp4'):
                                        file_path = os.path.join(DOWNLOAD_DIR, f)
                                        break
                            
                            if os.path.exists(file_path) and os.path.getsize(file_path) > 1000:
                                return {"success": True, "file_path": file_path, "is_video": True}
                
                ydl_opts_photo = {
                    'quiet': True,
                    'no_warnings': True,
                    'ignoreerrors': True,
                    'outtmpl': os.path.join(DOWNLOAD_DIR, '%(id)s.%(ext)s'),
                    'format': 'best',
                }
                if os.path.exists('cookies.txt'):
                    ydl_opts_photo['cookiefile'] = 'cookies.txt'
                
                with yt_dlp.YoutubeDL(ydl_opts_photo) as ydl3:
                    info3 = ydl3.extract_info(url, download=True)
                    if info3:
                        file_id = info3.get('id', 'unknown')
                        file_path = None
                        for f in os.listdir(DOWNLOAD_DIR):
                            if file_id in f and f.endswith(('.jpg', '.jpeg', '.png', '.webp')):
                                file_path = os.path.join(DOWNLOAD_DIR, f)
                                break
                        
                        if file_path and os.path.getsize(file_path) > 1000:
                            return {"success": True, "file_path": file_path, "is_video": False}
            
        except Exception as e:
            return {"success": False, "error": str(e)}
        
        return {"success": False, "error": "yt-dlp failed"}
    
    @staticmethod
    def _download_scrape(url):
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml',
            }
            
            resp = requests.get(url, headers=headers, timeout=15)
            
            v = re.search(r'"video_url":"([^"]+)"', resp.text)
            if v:
                shortcode = re.search(r'/(p|reel)/([^/]+)', url).group(2)
                fp = os.path.join(DOWNLOAD_DIR, f"{shortcode}.mp4")
                vr = requests.get(v.group(1).replace('\\u0026', '&'), stream=True, timeout=30)
                with open(fp, 'wb') as f:
                    for chunk in vr.iter_content(chunk_size=8192):
                        if chunk: f.write(chunk)
                if os.path.getsize(fp) > 1000:
                    return {"success": True, "file_path": fp, "is_video": True}
            
            im = re.search(r'"display_url":"([^"]+)"', resp.text)
            if im:
                shortcode = re.search(r'/(p|reel)/([^/]+)', url).group(2)
                fp = os.path.join(DOWNLOAD_DIR, f"{shortcode}.jpg")
                ir = requests.get(im.group(1).replace('\\u0026', '&'), stream=True, timeout=30)
                with open(fp, 'wb') as f:
                    for chunk in ir.iter_content(chunk_size=8192):
                        if chunk: f.write(chunk)
                if os.path.getsize(fp) > 1000:
                    return {"success": True, "file_path": fp, "is_video": False}
        except:
            pass
        return {"success": False, "error": "Scrape failed"}
    
    @staticmethod
    def extract_audio(video_path, custom_name=None):
        try:
            if custom_name:
                audio_path = os.path.join(DOWNLOAD_DIR, f"{custom_name}.mp3")
            else:
                audio_path = video_path.rsplit('.', 1)[0] + '.mp3'
            
            probe_cmd = ['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_entries', 'stream=codec_type', '-of', 'csv=p=0', video_path]
            probe_result = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=30)
            
            if not probe_result.stdout.strip():
                return {"success": False, "error": "❌ Is video main audio nahi hai!"}
            
            cmd = ['ffmpeg', '-i', video_path, '-vn', '-acodec', 'libmp3lame', '-ab', '192k', '-y', audio_path]
            subprocess.run(cmd, capture_output=True, timeout=180)
            
            if os.path.exists(audio_path) and os.path.getsize(audio_path) > 1000:
                return {"success": True, "file_path": audio_path}
            
            cmd2 = ['ffmpeg', '-i', video_path, '-vn', '-acodec', 'mp3', '-y', audio_path]
            subprocess.run(cmd2, capture_output=True, timeout=180)
            
            if os.path.exists(audio_path) and os.path.getsize(audio_path) > 1000:
                return {"success": True, "file_path": audio_path}
            
            return {"success": False, "error": "Audio extract failed"}
            
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "⏰ Timeout!"}
        except Exception as e:
            return {"success": False, "error": f"FFmpeg error: {str(e)}"}
    
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
        "✅ Video link bhejo → Video + Audio\n"
        "✅ Photo link bhejo → High Quality Photo\n"
        "✅ Audio button → Audio extract karega\n\n"
        "**Example:**\n"
        "`https://www.instagram.com/reel/xyz/`\n"
        "`https://www.instagram.com/p/xyz/`",
        parse_mode="Markdown"
    )

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
    
    msg = await update.message.reply_text("⏳ Downloading...")
    
    try:
        result = InstaDownloader.download_media(url)
        
        if not result.get("success"):
            await msg.edit_text(f"❌ **Failed:** {result.get('error')}\n\n💡 cookies.txt file banao aur upload karo", parse_mode="Markdown")
            return
        
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
                context.user_data['audio_url'] = url
                keyboard = [[InlineKeyboardButton("🎵 Download Audio", callback_data="audio_request")]]
                with open(fp, 'rb') as f:
                    await update.message.reply_video(
                        video=f,
                        caption=f"✅ **Downloaded** ✅\n🔗 [Instagram Link]({url})\n\n📌 Audio ke liye button click karein",
                        parse_mode="Markdown",
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        supports_streaming=True
                    )
            else:
                with open(fp, 'rb') as f:
                    await update.message.reply_photo(
                        photo=f,
                        caption=f"✅ **Downloaded** ✅\n🔗 [Instagram Link]({url})",
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
            await query.message.reply_text("❌ URL not found.")
            return
        
        await query.edit_message_reply_markup(reply_markup=None)
        status_msg = await query.message.reply_text("🎵 Audio extract ho raha hai...")
        
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
    
    ffmpeg_path = shutil.which('ffmpeg')
    if ffmpeg_path:
        print(f"✅ FFmpeg found: {ffmpeg_path}")
    else:
        print("⚠️ FFmpeg not found!")
    
    if os.path.exists('cookies.txt'):
        print("✅ cookies.txt found")
    else:
        print("⚠️ cookies.txt not found")
    
    print("✅ Bot Started!")
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    app.run_polling()

if __name__ == "__main__":
    main()
