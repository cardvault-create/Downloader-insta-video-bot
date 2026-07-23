import logging
import os
import re
import subprocess
import shutil
import time
import json
import urllib.parse
import random
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.constants import ChatMemberStatus
import yt_dlp
import requests

# ═══════════════════════════
# 🔐 CONFIG
# ═══════════════════════════

BOT_TOKEN = "8518787964:AAHGimBKXfdtrI6UaASGsoI8Aj5Rj_WxF5I"
OWNER_ID = 1987818347
ALLOW_ALL_USERS = True

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ═══════════════════════════
# 📊 ANIMATION DATABASES
# ═══════════════════════════

EMOJI_DB = "emojis.json"
STICKER_DB = "stickers.json"
VIDEO_LIST_DB = "video_list.json"
VIDEO_DIR = "welcome_videos"
os.makedirs(VIDEO_DIR, exist_ok=True)

last_emoji_index = -1
last_sticker_index = -1
last_video_index = -1

STICKER_DELETE_AFTER = 3  # Sticker delete after final msg

def jload(f, d=None):
    try:
        if os.path.exists(f):
            with open(f) as fl: return json.load(fl)
    except: pass
    return d if d is not None else {}

def jsave(f, d):
    with open(f, 'w') as fl: json.dump(d, fl, indent=2)

# ═══════════════ EMOJI ═══════════════
def get_emojis():
    return jload(EMOJI_DB, {"emojis": []})["emojis"]

def add_emoji_db(emoji_id):
    data = jload(EMOJI_DB, {"emojis": []})
    if emoji_id not in data["emojis"]:
        data["emojis"].append(emoji_id)
        jsave(EMOJI_DB, data)
        return True, len(data["emojis"])
    return False, len(data["emojis"])

def remove_emoji_db(index):
    data = jload(EMOJI_DB, {"emojis": []})
    if 0 <= index < len(data["emojis"]):
        data["emojis"].pop(index)
        jsave(EMOJI_DB, data)
        return True, len(data["emojis"])
    return False, len(data["emojis"])

def get_random_emoji():
    global last_emoji_index
    emojis = get_emojis()
    if emojis:
        if len(emojis) > 1:
            available = [i for i in range(len(emojis)) if i != last_emoji_index]
            if available:
                last_emoji_index = random.choice(available)
                return emojis[last_emoji_index]
        last_emoji_index = 0
        return emojis[0]
    return None

# ═══════════════ STICKER ═══════════════
def get_stickers():
    return jload(STICKER_DB, {"stickers": []})["stickers"]

def add_sticker_db(sticker_id):
    data = jload(STICKER_DB, {"stickers": []})
    if sticker_id not in data["stickers"]:
        data["stickers"].append(sticker_id)
        jsave(STICKER_DB, data)
        return True, len(data["stickers"])
    return False, len(data["stickers"])

def remove_sticker_db(index):
    data = jload(STICKER_DB, {"stickers": []})
    if 0 <= index < len(data["stickers"]):
        data["stickers"].pop(index)
        jsave(STICKER_DB, data)
        return True, len(data["stickers"])
    return False, len(data["stickers"])

def get_random_sticker():
    global last_sticker_index
    stickers = get_stickers()
    if stickers:
        if len(stickers) > 1:
            available = [i for i in range(len(stickers)) if i != last_sticker_index]
            if available:
                last_sticker_index = random.choice(available)
                return stickers[last_sticker_index]
        last_sticker_index = 0
        return stickers[0]
    return None

# ═══════════════ VIDEO ═══════════════
def get_video_list():
    return jload(VIDEO_LIST_DB, [])

def add_video_db(file_path):
    vids = get_video_list()
    vid = len(vids) + 1
    vids.append({"id": vid, "path": file_path, "name": os.path.basename(file_path)})
    jsave(VIDEO_LIST_DB, vids)
    return vid, len(vids)

def get_random_video():
    global last_video_index
    vids = get_video_list()
    if not vids: return None
    if len(vids) > 1:
        available = [v for v in vids if v["id"] != last_video_index]
        if available:
            chosen = random.choice(available)
            last_video_index = chosen["id"]
            return chosen
    chosen = random.choice(vids)
    last_video_index = chosen["id"]
    return chosen

def delete_video_db(vid):
    vids = get_video_list()
    for i, v in enumerate(vids):
        if v["id"] == vid:
            if os.path.exists(v["path"]): os.remove(v["path"])
            vids.pop(i)
            jsave(VIDEO_LIST_DB, vids)
            return True, len(vids)
    return False, len(vids)

def clear_videos_db():
    vids = get_video_list()
    for v in vids:
        if os.path.exists(v["path"]): os.remove(v["path"])
    jsave(VIDEO_LIST_DB, [])
    return len(vids)

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
    def download_media(url):
        shortcode = re.search(r'/(p|reel|tv)/([a-zA-Z0-9_\-]+)', url)
        if not shortcode: return {"success": False, "error": "Invalid shortcode"}
        shortcode = shortcode.group(2)
        is_reel = '/reel/' in url or '/tv/' in url
        if is_reel:
            return InstaDownloader._download_video(shortcode, url)
        else:
            return InstaDownloader._download_photo(shortcode)
    
    # ═══════════════ VIDEO - GUARANTEED AUDIO ═══════════════
    @staticmethod
    def _download_video(shortcode, url):
        try:
            # Use yt-dlp with bestvideo+bestaudio to guarantee audio
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'outtmpl': os.path.join(DOWNLOAD_DIR, f'{shortcode}.%(ext)s'),
                'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                'merge_output_format': 'mp4',
                'retries': 10,
                'fragment_retries': 10,
                'extractor_retries': 5,
                'socket_timeout': 30,
            }
            
            if os.path.exists('cookies.txt'):
                ydl_opts['cookiefile'] = 'cookies.txt'
            
            ffmpeg = shutil.which('ffmpeg')
            if ffmpeg:
                ydl_opts['ffmpeg_location'] = ffmpeg
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if info:
                    time.sleep(0.5)
                    # Find downloaded file
                    for f in sorted(os.listdir(DOWNLOAD_DIR), key=lambda x: os.path.getmtime(os.path.join(DOWNLOAD_DIR, x)), reverse=True):
                        if f.endswith('.mp4'):
                            fp = os.path.join(DOWNLOAD_DIR, f)
                            if os.path.exists(fp) and os.path.getsize(fp) > 5000:
                                # Verify audio
                                try:
                                    probe = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_entries', 'stream=codec_type', '-of', 'csv=p=0', fp], capture_output=True, text=True, timeout=10)
                                    if probe.stdout.strip():
                                        print(f"✅ Video with AUDIO: {f} ({os.path.getsize(fp)} bytes)")
                                        return {"success": True, "file_path": fp, "is_video": True}
                                    else:
                                        print(f"⚠️ No audio track, retrying...")
                                        os.remove(fp)
                                except:
                                    pass
            
            # Retry with different format
            ydl_opts['format'] = 'best'
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if info:
                    time.sleep(0.5)
                    for f in sorted(os.listdir(DOWNLOAD_DIR), key=lambda x: os.path.getmtime(os.path.join(DOWNLOAD_DIR, x)), reverse=True):
                        if f.endswith('.mp4'):
                            fp = os.path.join(DOWNLOAD_DIR, f)
                            if os.path.exists(fp) and os.path.getsize(fp) > 5000:
                                print(f"✅ Video fallback: {f}")
                                return {"success": True, "file_path": fp, "is_video": True}
            
            return {"success": False, "error": "Video download failed"}
            
        except Exception as e:
            err = str(e)
            if '403' in err or '401' in err:
                return {"success": False, "error": "cookies.txt expired!"}
            return {"success": False, "error": f"{err[:80]}"}
    
    # ═══════════════ PHOTO ═══════════════
    @staticmethod
    def _download_photo(shortcode):
        methods = [
            InstaDownloader._method_oembed,
            InstaDownloader._method_ytdlp,
            InstaDownloader._method_scrape,
            InstaDownloader._method_bibliogram,
            InstaDownloader._method_cdn,
        ]
        for i, method in enumerate(methods):
            print(f"📥 Photo Method {i+1}")
            result = method(shortcode)
            if result.get("success"): return result
        return {"success": False, "error": "Photo download failed"}
    
    @staticmethod
    def _method_oembed(shortcode):
        try:
            post_url = f"https://www.instagram.com/p/{shortcode}/"
            api_url = f"https://api.instagram.com/oembed?url={urllib.parse.quote(post_url)}&maxwidth=1080"
            resp = requests.get(api_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
            if resp.status_code != 200: return {"success": False}
            data = resp.json()
            image_urls = []
            thumb = data.get('thumbnail_url', '')
            if thumb:
                hd = re.sub(r'/s\d+x\d+/', '/', thumb).split('?')[0]
                image_urls.append(hd)
            for img_url in image_urls:
                ext = 'jpg'
                fp = os.path.join(DOWNLOAD_DIR, f"{shortcode}.{ext}")
                r = requests.get(img_url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.instagram.com/'}, stream=True, timeout=30)
                if r.status_code == 200:
                    with open(fp, 'wb') as f:
                        for chunk in r.iter_content(8192):
                            if chunk: f.write(chunk)
                    if os.path.exists(fp) and os.path.getsize(fp) > 1000:
                        return {"success": True, "file_path": fp, "is_video": False}
            return {"success": False}
        except: return {"success": False}
    
    @staticmethod
    def _method_ytdlp(shortcode):
        try:
            ydl_opts = {'quiet': True, 'outtmpl': os.path.join(DOWNLOAD_DIR, f'{shortcode}.%(ext)s'), 'format': 'best', 'retries': 3}
            if os.path.exists('cookies.txt'): ydl_opts['cookiefile'] = 'cookies.txt'
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.extract_info(f"https://www.instagram.com/p/{shortcode}/", download=True)
                time.sleep(0.5)
                for f in os.listdir(DOWNLOAD_DIR):
                    if shortcode in f and not f.endswith(('.mp4','.mov','.webm')):
                        fp = os.path.join(DOWNLOAD_DIR, f)
                        if os.path.getsize(fp) > 1000: return {"success": True, "file_path": fp, "is_video": False}
        except: pass
        return {"success": False}
    
    @staticmethod
    def _method_scrape(shortcode):
        try:
            session = requests.Session()
            session.headers.update({'User-Agent': 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36'})
            if os.path.exists('cookies.txt'):
                cookies = {}
                with open('cookies.txt') as f:
                    for line in f:
                        if line.strip() and not line.startswith('#'):
                            parts = line.split('\t')
                            if len(parts) >= 7: cookies[parts[5]] = parts[6]
                for k, v in cookies.items(): session.cookies.set(k, v, domain='.instagram.com')
            resp = session.get(f"https://www.instagram.com/p/{shortcode}/", timeout=15)
            if resp.status_code != 200: return {"success": False}
            html = resp.text
            image_urls = re.findall(r'"display_url":"([^"]+)"', html)
            if not image_urls:
                og = re.findall(r'<meta\s+property="og:image"\s+content="([^"]+)"', html)
                image_urls = list(set(og))
            for img_url in image_urls[:5]:
                try:
                    if '.mp4' in img_url: continue
                    fp = os.path.join(DOWNLOAD_DIR, f"{shortcode}.jpg")
                    r = session.get(img_url, headers={'User-Agent': 'Mozilla/5.0'}, stream=True, timeout=30)
                    if r.status_code == 200:
                        with open(fp, 'wb') as f:
                            for chunk in r.iter_content(8192):
                                if chunk: f.write(chunk)
                        if os.path.getsize(fp) > 1000: return {"success": True, "file_path": fp, "is_video": False}
                except: continue
            return {"success": False}
        except: return {"success": False}
    
    @staticmethod
    def _method_bibliogram(shortcode):
        for url in [f"https://bibliogram.art/u/p/{shortcode}/", f"https://bibliogram.pussthecat.org/u/p/{shortcode}/"]:
            try:
                resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
                if resp.status_code == 200:
                    imgs = re.findall(r'<img[^>]+src="([^"]+)"', resp.text)
                    for img in imgs:
                        if shortcode in img or 'jpg' in img:
                            fp = os.path.join(DOWNLOAD_DIR, f"{shortcode}.jpg")
                            r = requests.get(img, headers={'User-Agent': 'Mozilla/5.0'}, stream=True, timeout=30)
                            if r.status_code == 200:
                                with open(fp, 'wb') as f:
                                    for chunk in r.iter_content(8192):
                                        if chunk: f.write(chunk)
                                if os.path.getsize(fp) > 1000: return {"success": True, "file_path": fp, "is_video": False}
            except: continue
        return {"success": False}
    
    @staticmethod
    def _method_cdn(shortcode):
        try:
            url = f"https://www.instagram.com/p/{shortcode}/media/?size=l"
            r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, stream=True, timeout=30)
            if r.status_code == 200 and 'image' in r.headers.get('content-type', ''):
                fp = os.path.join(DOWNLOAD_DIR, f"{shortcode}.jpg")
                with open(fp, 'wb') as f:
                    for chunk in r.iter_content(8192):
                        if chunk: f.write(chunk)
                if os.path.getsize(fp) > 1000: return {"success": True, "file_path": fp, "is_video": False}
        except: pass
        return {"success": False}
    
    @staticmethod
    def extract_audio(video_path, custom_name=None):
        try:
            if custom_name and custom_name != "skip":
                safe = re.sub(r'[^\w\s-]', '', custom_name).strip()[:50] or "Audio"
                ap = os.path.join(DOWNLOAD_DIR, f"{safe}.mp3")
            else:
                ap = os.path.join(DOWNLOAD_DIR, f"{os.path.splitext(os.path.basename(video_path))[0]}.mp3")
            if not shutil.which('ffmpeg'): return {"success": False, "error": "No FFmpeg"}
            probe = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_entries', 'stream=codec_type', '-of', 'csv=p=0', video_path], capture_output=True, text=True, timeout=30)
            if not probe.stdout.strip(): return {"success": False, "error": "No audio track"}
            subprocess.run(['ffmpeg', '-i', video_path, '-vn', '-acodec', 'libmp3lame', '-ab', '192k', '-y', ap], capture_output=True, timeout=180)
            if os.path.exists(ap) and os.path.getsize(ap) > 1000: return {"success": True, "file_path": ap}
            return {"success": False, "error": "Extraction failed"}
        except Exception as e: return {"success": False, "error": str(e)[:50]}
    
    @staticmethod
    def cleanup(fp):
        try:
            if fp and os.path.exists(fp): os.remove(fp)
        except: pass

# ═══════════════════════════
# 📝 TEXT TEMPLATES
# ═══════════════════════════

CAPTION = (
    "𝘋/𝘓 𝘉𝘺 ➪ [˹𝚰𝖓𝖘𝖙𝖆𝖌𝖗𝖆𝖒 ✘ 𝚫𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐞𝐫˼ ♪�҉](https://t.me/Instagram_LinkToVideo_Bot)\n"
    "\n"
    "༼◉𝐂𝛄𝛆𝛂𝛕𝛆𝛄◉༽ 🪽 ➪ [𝜝𝜣𝜯 𝑭𝜟𝜯𝜢𝜮𝜞](https://t.me/FathersOfCreater) �҉"
)

WELCOME_TEXT = """ʜᴇʏ, {mention} 👋🏻
ɪ'ᴍ [˹𝚰𝖓𝖘𝖙𝖆𝖌𝖗𝖆𝖒 ✘ 𝚫𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐞𝐫˼ ♪](https://t.me/Instagram_LinkToVideo_Bot),

┏━━━━━━━━━━━━━━━━━⧫
┠ ◆ ˹ɪ ʜᴀᴠᴇ sᴘᴇᴄɪᴀʟ ғᴇᴀᴛᴜʀᴇs˼
┠ ◆ ˹ᴀʟʟ-ɪɴ-ᴏɴᴇ ʙᴏᴛ˼
┗━━━━━━━━━━━━━━━━━⧫
┏━━━━━━━━━━━━━━━━━⧫
┠ ◆ ˹ʏᴏᴜ ᴄᴀɴ ᴅᴏᴡɴʟᴏᴀᴅ ɪɴsᴛᴀɢʀᴀᴍ ʀᴇᴇʟs˼
┠ ◆ ˹ʏᴏᴜ ᴄᴀɴ ᴅᴏᴡɴʟᴏᴀᴅ ɪɴsᴛᴀɢʀᴀᴍ ᴘʜᴏᴛᴏs˼
┠ ◆ ˹ʏᴏᴜ ᴄᴀɴ ᴇxᴛʀᴀᴄᴛ ᴀᴜᴅɪᴏ ғʀᴏᴍ ᴠɪᴅᴇᴏs˼
┠ ◆ ˹ʜᴅ ᴠɪᴅᴇᴏ + ᴏʀɪɢɪɴᴀʟ ᴀᴜᴅɪᴏ sᴜᴘᴘᴏʀᴛ˼
┠ ◆ ˹ᴍᴜʟᴛɪᴘʟᴇ ᴘʜᴏᴛᴏ ᴅᴏᴡɴʟᴏᴀᴅ sᴜᴘᴘᴏʀᴛ˼
┠ ◆ ˹ɢʀᴏᴜᴘ sᴜᴘᴘᴏʀᴛ ᴀᴠᴀɪʟᴀʙʟᴇ˼
┗━━━━━━━━━━━━━━━━━⧫

⚡ ˹ᴸⁱⁿᵏ ᴮʰᵉʲᵒ → ⱽⁱᵈᵉᵒ ᴾᵃᵒ → ᴬᵘᵈⁱᵒ ᴺᵃᵃᵐ ᴮᵃᵗᵃᵒ → ᴬᵘᵈⁱᵒ ᴾᵃᵒ˼

⧫━━━━━✦◆ ◇ ◆ ◇ ◆ ◇✦━━━━━⧫
๏ ˹ᴄʟɪᴄᴋ ᴏɴ ᴛʜᴇ ᴀᴅᴅ ᴛᴏ ɢʀᴏᴜᴘ ʙᴜᴛᴛᴏɴ ʙᴇʟᴏᴡ ᴛᴏ ᴀᴅᴅ ᴛʜɪs ʙᴏᴛ ɪɴ ʏᴏᴜʀ ɢʀᴏᴜᴘ ᴀɴᴅ ᴇɴᴊᴏʏ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ ᴛʜᴇʀᴇ ᴛᴏᴏ˼

🫧 ˹ᴅᴇᴠᴇʟᴏᴩᴇʀ˼ 🪽 ➪ [𝜝𝜣𝜯 𝑭𝜟𝜯𝜢𝜮𝜞](https://t.me/FathersOfCreater) ✔︎"""

GROUP_WELCOME = """👋🏻 **ʜᴇʟʟᴏ {chat_title}!**

ɪ'ᴍ [˹𝚰𝖓𝖘𝖙𝖆𝖌𝖗𝖆𝖒 ✘ 𝚫𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐞𝐫˼ ♪](https://t.me/Instagram_LinkToVideo_Bot),

┏━━━━━━━━━━━━━━━━━⧫
┠ ◆ ˹ᴅᴏᴡɴʟᴏᴀᴅ ɪɴsᴛᴀɢʀᴀᴍ ʀᴇᴇʟs, ᴘʜᴏᴛᴏs & ᴀᴜᴅɪᴏ˼
┠ ◆ ˹ʜᴅ ᴠɪᴅᴇᴏ + ᴏʀɪɢɪɴᴀʟ ᴀᴜᴅɪᴏ ɢᴜᴀʀᴀɴᴛᴇᴇᴅ˼
┠ ◆ ˹ᴊᴜsᴛ sᴇɴᴅ ɪɴsᴛᴀɢʀᴀᴍ ʟɪɴᴋ ɪɴ ɢʀᴏᴜᴘ˼
┗━━━━━━━━━━━━━━━━━⧫

⚡ ˹sɪʀғ ʟɪɴᴋ ʙʜᴇᴊᴏ, ʙᴀᴋɪ ʙᴏᴛ ᴅᴇᴋʜ ʟᴇɢᴀ˼

🫧 ˹ᴅᴇᴠᴇʟᴏᴩᴇʀ˼ 🪽 ➪ [𝜝𝜣𝜯 𝑭𝜟𝜯𝜢𝜮𝜞](https://t.me/FathersOfCreater) ✔︎"""

AUDIO_BUTTON_TEXT = "➪ ˹𝐃𝐨𝐰𝐧𝐥𝐨𝐚𝐝 𝐕𝐢𝐝𝐞𝐨 𝐀𝐮𝐝𝐢𝐨˼  ♪�҉"

# ═══════════════════════════
# 🎬 WELCOME ANIMATION (FAST)
# ═══════════════════════════

async def send_welcome_animation(bot, chat_id, user_id, first_name):
    user_mention = f"[{first_name}](tg://user?id={user_id})"
    
    # Step 1: Emoji sticker + instant welcome baby msg
    emoji_id = get_random_emoji()
    emoji_msg = None
    if emoji_id:
        try:
            emoji_msg = await bot.send_sticker(chat_id, emoji_id)
        except: pass
    
    await asyncio.sleep(0.1)  # 0.10 sec delay
    
    # Welcome baby msg
    welcome_emojis = ["🩷", "🌸", "🏖️", "🍰", "🥂"]
    welcome_msg = await bot.send_message(
        chat_id,
        f"𝐖𝐞𝐥𝐜𝐨𝐦𝐞 𝐁ᴀʙʏ ꨄ {user_mention}...🩷",
        parse_mode="Markdown"
    )
    
    # Emoji change animation (3 seconds)
    for emoji in welcome_emojis:
        await asyncio.sleep(0.5)
        try:
            await welcome_msg.edit_text(f"𝐖𝐞𝐥𝐜𝐨𝐦𝐞 𝐁ᴀʙʏ ꨄ {user_mention}...{emoji}", parse_mode="Markdown")
        except: pass
    
    # Delete emoji sticker at 3 sec
    if emoji_msg:
        try: await emoji_msg.delete()
        except: pass
    
    await asyncio.sleep(0.1)
    
    # Step 2: Starting animation
    starting_emojis = ["🚀", "🌠", "🪶", "🍓", "🤖", "🥡", "🍷", "🍭", "🍨", "🧭", "🫧", "🍫", "🛸"]
    words = ["s", "t", "α", "я", "т", "ι", "и", "g", ".", ".", ".", ".", "."]
    
    await welcome_msg.edit_text(f"**{starting_emojis[0]}**", parse_mode="Markdown")
    await asyncio.sleep(0.1)
    
    for i in range(len(words)):
        current_text = "".join(words[:i + 1])
        emoji = starting_emojis[i % len(starting_emojis)]
        try: await welcome_msg.edit_text(f"**{emoji} " + current_text + "**", parse_mode="Markdown")
        except: pass
        await asyncio.sleep(0.08)
    
    await asyncio.sleep(0.1)
    try: await welcome_msg.delete()
    except: pass
    
    # Step 3: Sticker immediately
    sticker_id = get_random_sticker()
    sticker_msg = None
    if sticker_id:
        try:
            sticker_msg = await bot.send_sticker(chat_id, sticker_id)
        except: pass
    
    await asyncio.sleep(3)  # 3 second display
    
    # Step 4: Final message
    video_data = get_random_video()
    final_text = WELCOME_TEXT.replace("{mention}", user_mention)
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("◆ ➪ ˹𝜟𝙙𝙙 𝜯𝜣 𝑮𝜞𝜭𝑼𝝆˼ ♪☬", url=f"https://t.me/{(await bot.get_me()).username}?startgroup=true")]
    ])
    
    if video_data and os.path.exists(video_data["path"]):
        await bot.send_video(chat_id, video_data["path"], caption=final_text, parse_mode="Markdown", reply_markup=kb)
    else:
        await bot.send_message(chat_id, final_text, parse_mode="Markdown", reply_markup=kb)
    
    # Step 5: Delete sticker
    if sticker_msg:
        await asyncio.sleep(STICKER_DELETE_AFTER)
        try: await sticker_msg.delete()
        except: pass

# ═══════════════════════════
# 🤖 HANDLERS
# ═══════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not ALLOW_ALL_USERS and user.id != OWNER_ID: return
    await send_welcome_animation(context.bot, update.effective_chat.id, user.id, user.first_name or "User")

async def bot_added_to_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.my_chat_member.new_chat_member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR]:
        chat = update.effective_chat
        bot_user = await context.bot.get_me()
        welcome_msg = GROUP_WELCOME.replace("{chat_title}", chat.title or "Group")
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("◆ ➪ ˹𝜟𝙙𝙙 𝜯𝜣 𝑮𝜞𝜭𝑼𝝆˼ ♪☬", url=f"https://t.me/{bot_user.username}?startgroup=true")]
        ])
        await context.bot.send_message(chat.id, welcome_msg, parse_mode="Markdown", reply_markup=kb)

# ═══════════════ ADMIN COMMANDS ═══════════════

async def add_emoji_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not update.message.reply_to_message or not update.message.reply_to_message.sticker:
        await update.message.reply_text("Reply to emoji sticker with /addemoji"); return
    eid = update.message.reply_to_message.sticker.file_id
    s, t = add_emoji_db(eid)
    await update.message.reply_text(f"✅ Added! ({t})" if s else "❌ Already exists!")

async def remove_emoji_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    try:
        idx = int(update.message.text.split()[1]) - 1
        s, t = remove_emoji_db(idx)
        await update.message.reply_text(f"✅ Removed! ({t})" if s else f"❌ Invalid! Total: {t}")
    except: await update.message.reply_text("/removeemoji index")

async def list_emojis_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    emojis = get_emojis()
    if not emojis: await update.message.reply_text("No emojis!"); return
    await update.message.reply_text("EMOJIS:\n" + "\n".join([f"{i+1}. `{e[:30]}`" for i, e in enumerate(emojis)]), parse_mode="Markdown")

async def add_sticker_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not update.message.reply_to_message or not update.message.reply_to_message.sticker:
        await update.message.reply_text("Reply to sticker with /addsticker"); return
    sid = update.message.reply_to_message.sticker.file_id
    s, t = add_sticker_db(sid)
    await update.message.reply_text(f"✅ Added! ({t})" if s else "❌ Already exists!")

async def remove_sticker_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    try:
        idx = int(update.message.text.split()[1]) - 1
        s, t = remove_sticker_db(idx)
        await update.message.reply_text(f"✅ Removed! ({t})" if s else f"❌ Invalid! Total: {t}")
    except: await update.message.reply_text("/removesticker index")

async def list_stickers_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    stickers = get_stickers()
    if not stickers: await update.message.reply_text("No stickers!"); return
    await update.message.reply_text("STICKERS:\n" + "\n".join([f"{i+1}. `{s[:25]}`" for i, s in enumerate(stickers)]), parse_mode="Markdown")

async def add_video_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not update.message.reply_to_message or not update.message.reply_to_message.video:
        await update.message.reply_text("Reply to video with /addvideo"); return
    m = await update.message.reply_text("Adding...")
    try:
        file = await update.message.reply_to_message.video.get_file()
        fp = os.path.join(VIDEO_DIR, f"w_{int(time.time())}.mp4")
        await file.download_to_drive(fp)
        vid, total = add_video_db(fp)
        await m.edit_text(f"✅ Added! ID:{vid} ({total})")
    except Exception as e: await m.edit_text(f"❌ {e}")

async def del_video_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    try:
        s, t = delete_video_db(int(update.message.text.split()[1]))
        await update.message.reply_text(f"✅ Deleted! ({t})" if s else "❌ Not found")
    except: await update.message.reply_text("/delvideo ID")

async def list_videos_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    vids = get_video_list()
    if not vids: await update.message.reply_text("No videos!"); return
    await update.message.reply_text("VIDEOS:\n" + "\n".join([f"#{v['id']} {v['name'][:30]}" for v in vids]))

async def clear_videos_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    await update.message.reply_text(f"🗑️ {clear_videos_db()} videos cleared!")

# ═══════════════ MESSAGE HANDLER ═══════════════

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not ALLOW_ALL_USERS and user.id != OWNER_ID: return
    
    text = update.message.text
    if not text: return
    
    if context.user_data.get('awaiting_audio'):
        context.user_data['awaiting_audio'] = False
        url = context.user_data.get('current_url')
        if url:
            await extract_and_send_audio(update, context, url, text.strip())
        return
    
    if not InstaDownloader.is_instagram_url(text): return
    
    url = InstaDownloader.extract_url(text)
    if not url:
        await update.message.reply_text("❌ Could not extract URL"); return
    
    context.user_data['current_url'] = url
    
    # Send random sticker
    sticker_id = get_random_sticker()
    sticker_msg = None
    if sticker_id:
        try: sticker_msg = await context.bot.send_sticker(update.effective_chat.id, sticker_id)
        except: pass
    
    msg = await update.message.reply_text("⏳ **Processing...**", parse_mode="Markdown")
    
    try:
        await msg.edit_text("📥 **Downloading...**", parse_mode="Markdown")
        result = InstaDownloader.download_media(url)
        
        if not result.get("success"):
            await msg.edit_text(f"❌ {result.get('error', 'Failed')}", parse_mode="Markdown")
            if sticker_msg:
                try: await sticker_msg.delete()
                except: pass
            return
        
        fp = result["file_path"]
        if not os.path.exists(fp) or os.path.getsize(fp) < 1000:
            await msg.edit_text("❌ File not found")
            if sticker_msg:
                try: await sticker_msg.delete()
                except: pass
            return
        
        size_mb = os.path.getsize(fp) / (1024 * 1024)
        if size_mb > 50:
            await msg.edit_text(f"❌ >50MB ({size_mb:.1f}MB)")
            InstaDownloader.cleanup(fp)
            if sticker_msg:
                try: await sticker_msg.delete()
                except: pass
            return
        
        is_video = result.get("is_video", False) or fp.endswith(('.mp4', '.mov', '.webm'))
        
        if is_video:
            await msg.edit_text("📤 **Uploading Video...**", parse_mode="Markdown")
            keyboard = [[InlineKeyboardButton(AUDIO_BUTTON_TEXT, callback_data="get_audio")]]
            with open(fp, 'rb') as f:
                await update.message.reply_video(
                    video=f, caption=CAPTION, parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(keyboard), supports_streaming=True
                )
        else:
            await msg.edit_text("📤 **Uploading Photo...**", parse_mode="Markdown")
            with open(fp, 'rb') as f:
                await update.message.reply_photo(photo=f, caption=CAPTION, parse_mode="Markdown")
        
        await msg.delete()
        InstaDownloader.cleanup(fp)
        
        # Delete sticker after 3 sec
        if sticker_msg:
            await asyncio.sleep(STICKER_DELETE_AFTER)
            try: await sticker_msg.delete()
            except: pass
        
    except Exception as e:
        await msg.edit_text(f"❌ {str(e)[:100]}", parse_mode="Markdown")
        for f in os.listdir(DOWNLOAD_DIR):
            try: os.remove(os.path.join(DOWNLOAD_DIR, f))
            except: pass
        if sticker_msg:
            try: await sticker_msg.delete()
            except: pass

async def extract_and_send_audio(update, context, url, audio_name):
    msg = await update.message.reply_text(f"🎵 **Extracting...**", parse_mode="Markdown")
    try:
        result = InstaDownloader.download_media(url)
        if not result.get("success"): await msg.edit_text("❌ Failed"); return
        vp = result["file_path"]
        ar = InstaDownloader.extract_audio(vp, audio_name)
        if ar.get("success"):
            await msg.edit_text("📤 **Uploading Audio...**", parse_mode="Markdown")
            with open(ar["file_path"], 'rb') as f:
                await update.message.reply_audio(audio=f, title=audio_name, performer="Instagram", caption=CAPTION, parse_mode="Markdown")
            await msg.edit_text(f"✅ **{audio_name}** 🎵")
            try: os.remove(ar["file_path"])
            except: pass
        else: await msg.edit_text(f"❌ {ar.get('error')}")
        InstaDownloader.cleanup(vp)
    except Exception as e: await msg.edit_text(f"❌ {str(e)[:80]}")

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
    print("║  🤖 INSTAGRAM BOT v3    ║")
    print("║  🎬 Fast Animation      ║")
    print("║  🎵 Guaranteed Audio    ║")
    print("╚══════════════════════════╝")
    
    if not shutil.which('ffmpeg'):
        os.system('apt-get update && apt-get install ffmpeg -y 2>/dev/null')
    
    print(f"🎨 E:{len(get_emojis())} S:{len(get_stickers())} V:{len(get_video_list())}")
    
    for f in os.listdir(DOWNLOAD_DIR):
        try: os.remove(os.path.join(DOWNLOAD_DIR, f))
        except: pass
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, bot_added_to_group))
    app.add_handler(CommandHandler("addemoji", add_emoji_cmd))
    app.add_handler(CommandHandler("removeemoji", remove_emoji_cmd))
    app.add_handler(CommandHandler("listemojis", list_emojis_cmd))
    app.add_handler(CommandHandler("addsticker", add_sticker_cmd))
    app.add_handler(CommandHandler("removesticker", remove_sticker_cmd))
    app.add_handler(CommandHandler("liststickers", list_stickers_cmd))
    app.add_handler(CommandHandler("addvideo", add_video_cmd))
    app.add_handler(CommandHandler("delvideo", del_video_cmd))
    app.add_handler(CommandHandler("videos", list_videos_cmd))
    app.add_handler(CommandHandler("clearvideos", clear_videos_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    print("✅ Bot Started! 🚀")
    app.run_polling()

if __name__ == "__main__":
    main()
