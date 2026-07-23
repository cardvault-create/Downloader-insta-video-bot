import logging
import os
import re
import subprocess
import shutil
import time
import json
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import yt_dlp
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
        return bool(re.search(r'(instagram\.com|instagr\.am)/(p|reel|tv)/[a-zA-Z0-9_\-]+', text or ''))
    
    @staticmethod
    def extract_url(text):
        m = re.search(r'(instagram\.com|instagr\.am)/(p|reel|tv)/([a-zA-Z0-9_\-]+)', text or '')
        return f"https://www.instagram.com/{m.group(2)}/{m.group(3)}/" if m else None
    
    @staticmethod
    def get_shortcode(url):
        m = re.search(r'/(p|reel|tv)/([a-zA-Z0-9_\-]+)', url)
        return m.group(2) if m else None
    
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
        
        # Check cookies
        if not os.path.exists('cookies.txt'):
            return {
                "success": False, 
                "error": "❌ cookies.txt nahi hai!\n\n📌 cookies.txt banane ka tarika:\n1. Chrome mein EditThisCookie extension install karo\n2. Instagram.com pe login karo\n3. Extension se cookies export karo\n4. File 'cookies.txt' naam se bot folder mein rakho"
            }
        
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'cookiefile': 'cookies.txt',
                'retries': 5,
                'ignoreerrors': True,
                'extract_flat': False,
            }
            
            if is_reel:
                # REEL DOWNLOAD
                ydl_opts.update({
                    'outtmpl': os.path.join(DOWNLOAD_DIR, f'{shortcode}.%(ext)s'),
                    'format': 'best[ext=mp4]/best',
                })
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                
                time.sleep(1)
                for f in os.listdir(DOWNLOAD_DIR):
                    if shortcode in f and f.endswith('.mp4'):
                        fp = os.path.join(DOWNLOAD_DIR, f)
                        if os.path.getsize(fp) > 5000:
                            return {"success": True, "file_path": fp, "is_video": True}
                
                return {"success": False, "error": "Reel download failed"}
            
            else:
                # POST DOWNLOAD - CAROUSEL SUPPORT
                ydl_opts.update({
                    'outtmpl': os.path.join(DOWNLOAD_DIR, f'{shortcode}_%(playlist_index)s.%(ext)s'),
                    'format': 'best[ext=jpg]/best[ext=png]/best',
                    'no_playlist': False,  # IMPORTANT: Carousel ke liye
                })
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                
                time.sleep(2)
                
                # Collect photos
                photos = []
                for f in sorted(os.listdir(DOWNLOAD_DIR)):
                    if shortcode in f and not f.endswith(('.mp4', '.mov', '.webm')):
                        fp = os.path.join(DOWNLOAD_DIR, f)
                        if os.path.exists(fp) and os.path.getsize(fp) > 1000:
                            photos.append(fp)
                
                # Remove duplicates
                if photos:
                    unique = []
                    sizes = set()
                    for fp in photos:
                        s = os.path.getsize(fp)
                        if s not in sizes:
                            sizes.add(s)
                            unique.append(fp)
                        else:
                            os.remove(fp)
                    photos = unique
                
                if not photos:
                    # Fallback: try without playlist index
                    ydl_opts['outtmpl'] = os.path.join(DOWNLOAD_DIR, f'{shortcode}.%(ext)s')
                    ydl_opts['no_playlist'] = True
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([url])
                    
                    time.sleep(1)
                    for f in os.listdir(DOWNLOAD_DIR):
                        if shortcode in f and not f.endswith(('.mp4', '.mov', '.webm')):
                            fp = os.path.join(DOWNLOAD_DIR, f)
                            if os.path.exists(fp) and os.path.getsize(fp) > 1000:
                                photos.append(fp)
                
                if photos:
                    if len(photos) == 1:
                        return {"success": True, "file_path": photos[0], "is_video": False}
                    else:
                        return {"success": True, "file_paths": sorted(photos), "is_video": False, "is_multiple": True, "total": len(photos)}
                
                return {"success": False, "error": "No photos downloaded. Cookies expired?"}
                
        except Exception as e:
            err = str(e)
            if '403' in err or '401' in err or 'login' in err.lower():
                return {"success": False, "error": "❌ cookies.txt EXPIRED! Naya banao."}
            return {"success": False, "error": f"Error: {err[:100]}"}
    
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
# 🤖 TELEGRAM HANDLERS
# ═══════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in AUTHORIZED_USERS:
        return
    
    has_cookies = "✅ Working" if os.path.exists('cookies.txt') else "❌ Nahi hai!"
    
    await update.message.reply_text(
        f"📥 **Instagram Downloader Bot**\n\n"
        f"🔐 **cookies.txt:** {has_cookies}\n\n"
        f"✅ **Reel** → HD Video 🎬\n"
        f"✅ **Post** → ALL Photos (Carousel) 📸\n"
        f"✅ **Audio Button** → MP3 ⚡\n\n"
        f"⚠️ **cookies.txt ke bina sirf 1 photo aayegi!**",
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
        url = context.user_data.get('current_url')
        if url:
            await extract_audio_handler(update, context, url, text.strip())
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
        
        # Multiple photos
        if result.get("is_multiple"):
            photos = result["file_paths"]
            total = result.get("total", len(photos))
            
            await msg.edit_text(f"📤 **{total} Photos bhej raha hun...**")
            
            for i, fp in enumerate(photos, 1):
                if os.path.exists(fp):
                    try:
                        with open(fp, 'rb') as f:
                            caption = f"✅ **Photo {i}/{total}**"
                            if i == 1:
                                caption += f"\n🔗 [Post Link]({url})"
                            await update.message.reply_photo(photo=f, caption=caption, parse_mode="Markdown")
                        
                        if i < total:
                            await asyncio.sleep(0.3)
                    except Exception as e:
                        await update.message.reply_text(f"❌ Photo {i}: {str(e)[:50]}")
                    InstaDownloader.cleanup(fp)
            
            await msg.edit_text(f"✅ **{total} Photos sent!** 🔥")
            return
        
        # Single file
        fp = result["file_path"]
        if not os.path.exists(fp):
            await msg.edit_text("❌ File not found")
            return
        
        size_mb = os.path.getsize(fp) / (1024*1024)
        if size_mb > 50:
            await msg.edit_text(f"❌ {size_mb:.1f}MB > 50MB limit")
            InstaDownloader.cleanup(fp)
            return
        
        is_video = result.get("is_video", False) or fp.endswith(('.mp4', '.mov', '.webm'))
        
        if is_video:
            await msg.edit_text("📤 **Uploading Video...**")
            kb = [[InlineKeyboardButton("🎵 Download Audio", callback_data="get_audio")]]
            with open(fp, 'rb') as f:
                await update.message.reply_video(video=f, caption=f"✅ Done\n🔗 [Link]({url})",
                    parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb), supports_streaming=True)
        else:
            await msg.edit_text("📤 **Uploading Photo...**")
            with open(fp, 'rb') as f:
                await update.message.reply_photo(photo=f, caption=f"✅ Done\n🔗 [Link]({url})", parse_mode="Markdown")
        
        await msg.delete()
        InstaDownloader.cleanup(fp)
        
    except Exception as e:
        await msg.edit_text(f"❌ Error: {str(e)[:100]}")

async def extract_audio_handler(update, context, url, name):
    msg = await update.message.reply_text(f"🎵 **{name}...**", parse_mode="Markdown")
    try:
        result = InstaDownloader.download_media(url)
        if not result.get("success"):
            await msg.edit_text("❌ Failed")
            return
        
        vp = result["file_paths"][0] if result.get("is_multiple") else result["file_path"]
        ar = InstaDownloader.extract_audio(vp, name)
        
        if ar.get("success"):
            await msg.edit_text("📤 **Uploading...**")
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
    logging.basicConfig(level=logging.INFO)
    
    print("="*40)
    print("  INSTAGRAM BOT - COOKIES REQUIRED")
    print("="*40)
    
    if not shutil.which('ffmpeg'):
        os.system('apt-get update && apt-get install ffmpeg -y 2>/dev/null')
    
    print(f"✅ FFmpeg: {shutil.which('ffmpeg')}")
    print(f"{'✅' if os.path.exists('cookies.txt') else '❌'} cookies.txt")
    
    if not os.path.exists('cookies.txt'):
        print("\n⚠️  cookies.txt BANAO:")
        print("1. Chrome → EditThisCookie extension")
        print("2. Instagram.com login karo")
        print("3. Cookies export karo → cookies.txt")
        print("4. Bot folder mein daalo\n")
    
    for f in os.listdir(DOWNLOAD_DIR):
        try: os.remove(os.path.join(DOWNLOAD_DIR, f))
        except: pass
    
    print("✅ Bot Ready!")
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.run_polling()

if __name__ == "__main__":
    main()
