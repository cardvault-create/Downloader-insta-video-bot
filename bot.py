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

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ═══════════════════════════
# 📊 DATABASES
# ═══════════════════════════

EMOJI_DB = "emojis.json"
STICKER_DB = "stickers.json"
VIDEO_LIST_DB = "video_list.json"
BOT_STATE_DB = "bot_state.json"
ACTIVATED_GROUPS_DB = "activated_groups.json"
PHOTO_CACHE_DB = "photo_cache.json"
VIDEO_DIR = "welcome_videos"
os.makedirs(VIDEO_DIR, exist_ok=True)

last_emoji_index = -1
last_sticker_index = -1
last_video_index = -1

def jload(f, d=None):
    try:
        if os.path.exists(f):
            with open(f, encoding='utf-8') as fl: return json.load(fl)
    except: pass
    return d if d is not None else {}

def jsave(f, d):
    with open(f, 'w', encoding='utf-8') as fl: json.dump(d, fl, indent=2, ensure_ascii=False)

def is_bot_enabled(): return jload(BOT_STATE_DB, {"enabled": True})["enabled"]
def set_bot_state(enabled): jsave(BOT_STATE_DB, {"enabled": enabled})

def is_group_activated(chat_id):
    data = jload(ACTIVATED_GROUPS_DB, [])
    return str(chat_id) in data

def activate_group(chat_id):
    data = jload(ACTIVATED_GROUPS_DB, [])
    if str(chat_id) not in data:
        data.append(str(chat_id))
        jsave(ACTIVATED_GROUPS_DB, data)
        return True
    return False

def get_emojis(): return jload(EMOJI_DB, {"emojis": []})["emojis"]
def add_emoji_db(eid):
    data = jload(EMOJI_DB, {"emojis": []})
    if eid not in data["emojis"]: data["emojis"].append(eid); jsave(EMOJI_DB, data); return True, len(data["emojis"])
    return False, len(data["emojis"])
def remove_emoji_db(idx):
    data = jload(EMOJI_DB, {"emojis": []})
    if 0 <= idx < len(data["emojis"]): data["emojis"].pop(idx); jsave(EMOJI_DB, data); return True, len(data["emojis"])
    return False, len(data["emojis"])
def get_random_emoji():
    global last_emoji_index
    emojis = get_emojis()
    if emojis:
        if len(emojis) > 1:
            available = [i for i in range(len(emojis)) if i != last_emoji_index]
            if available: last_emoji_index = random.choice(available); return emojis[last_emoji_index]
        last_emoji_index = 0; return emojis[0]
    return None

def get_stickers(): return jload(STICKER_DB, {"stickers": []})["stickers"]
def add_sticker_db(sid):
    data = jload(STICKER_DB, {"stickers": []})
    if sid not in data["stickers"]: data["stickers"].append(sid); jsave(STICKER_DB, data); return True, len(data["stickers"])
    return False, len(data["stickers"])
def remove_sticker_db(idx):
    data = jload(STICKER_DB, {"stickers": []})
    if 0 <= idx < len(data["stickers"]): data["stickers"].pop(idx); jsave(STICKER_DB, data); return True, len(data["stickers"])
    return False, len(data["stickers"])
def get_random_sticker():
    global last_sticker_index
    stickers = get_stickers()
    if stickers:
        if len(stickers) > 1:
            available = [i for i in range(len(stickers)) if i != last_sticker_index]
            if available: last_sticker_index = random.choice(available); return stickers[last_sticker_index]
        last_sticker_index = 0; return stickers[0]
    return None

def get_video_list(): return jload(VIDEO_LIST_DB, [])
def add_video_db(fp):
    vids = get_video_list(); vid = len(vids) + 1
    vids.append({"id": vid, "path": fp, "name": os.path.basename(fp)})
    jsave(VIDEO_LIST_DB, vids); return vid, len(vids)
def get_random_video():
    global last_video_index
    vids = get_video_list()
    if not vids: return None
    if len(vids) > 1:
        available = [v for v in vids if v["id"] != last_video_index]
        if available: chosen = random.choice(available); last_video_index = chosen["id"]; return chosen
    chosen = random.choice(vids); last_video_index = chosen["id"]; return chosen
def delete_video_db(vid):
    vids = get_video_list()
    for i, v in enumerate(vids):
        if v["id"] == vid:
            if os.path.exists(v["path"]): os.remove(v["path"])
            vids.pop(i); jsave(VIDEO_LIST_DB, vids); return True, len(vids)
    return False, len(vids)
def clear_videos_db():
    vids = get_video_list()
    for v in vids:
        if os.path.exists(v["path"]): os.remove(v["path"])
    jsave(VIDEO_LIST_DB, []); return len(vids)

def save_photo_cache(key, paths):
    data = jload(PHOTO_CACHE_DB, {})
    data[key] = {"paths": paths, "time": time.time()}
    for k in list(data.keys()):
        if time.time() - data[k].get("time", 0) > 3600: del data[k]
    jsave(PHOTO_CACHE_DB, data)

def get_photo_cache(key):
    data = jload(PHOTO_CACHE_DB, {})
    entry = data.get(key)
    if entry and time.time() - entry.get("time", 0) < 3600: return entry["paths"]
    return None

# ═══════════════════════════
# 🍪 COOKIES
# ═══════════════════════════

def get_cookie_dict():
    cookies = {}
    if os.path.exists('cookies.txt'):
        with open('cookies.txt', 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'): continue
                parts = line.split('\t')
                if len(parts) >= 7: cookies[parts[5]] = parts[6]
    return cookies

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
        m = re.search(r'(https?://)?(www\.)?instagram\.com/(p|reel|tv)/([a-zA-Z0-9_\-]+)', text)
        if m: return f"https://www.instagram.com/{m.group(3)}/{m.group(4)}/"
        return None
    
    @staticmethod
    def get_shortcode(url):
        m = re.search(r'/(p|reel|tv)/([a-zA-Z0-9_\-]+)', url)
        return m.group(2) if m else None
    
    @staticmethod
    def download_media(url):
        shortcode = InstaDownloader.get_shortcode(url)
        if not shortcode: return {"success": False, "error": "𝗜𝗻𝘃𝗮𝗹𝗶𝗱"}
        is_reel = '/reel/' in url or '/tv/' in url
        if is_reel: return InstaDownloader._download_video(shortcode, url)
        else: return InstaDownloader._download_photo(shortcode, url)
    
    @staticmethod
    def _download_video(shortcode, url):
        """VIDEO WITH AUDIO - yt-dlp best format"""
        ydl_opts = {
            'quiet': True, 'no_warnings': True,
            'outtmpl': os.path.join(DOWNLOAD_DIR, f'{shortcode}.%(ext)s'),
            'format': 'bestvideo+bestaudio/best',
            'merge_output_format': 'mp4',
            'retries': 15, 'socket_timeout': 120,
        }
        if os.path.exists('cookies.txt'): ydl_opts['cookiefile'] = 'cookies.txt'
        if shutil.which('ffmpeg'): ydl_opts['ffmpeg_location'] = shutil.which('ffmpeg')
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
                time.sleep(0.5)
                for f in sorted(os.listdir(DOWNLOAD_DIR), key=lambda x: os.path.getmtime(os.path.join(DOWNLOAD_DIR, x)), reverse=True):
                    if f.endswith('.mp4'):
                        fp = os.path.join(DOWNLOAD_DIR, f)
                        if os.path.exists(fp) and os.path.getsize(fp) > 50000:
                            return {"success": True, "file_path": fp, "is_video": True}
        except Exception as e:
            return {"success": False, "error": f"𝗩𝗶𝗱𝗲𝗼 𝗳𝗮𝗶𝗹𝗲𝗱: {str(e)[:50]}"}
        return {"success": False, "error": "𝗩𝗶𝗱𝗲𝗼 𝗱𝗼𝘄𝗻𝗹𝗼𝗮𝗱 𝗳𝗮𝗶𝗹𝗲𝗱"}
    
    @staticmethod
    def _download_photo(shortcode, url):
        """PHOTO - yt-dlp for ALL photos"""
        ydl_opts = {
            'quiet': True, 'no_warnings': True,
            'outtmpl': os.path.join(DOWNLOAD_DIR, f'{shortcode}_%(index)s.%(ext)s'),
            'format': 'best',
            'retries': 15, 'socket_timeout': 120,
            'ignoreerrors': True,
        }
        if os.path.exists('cookies.txt'): ydl_opts['cookiefile'] = 'cookies.txt'
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
                time.sleep(1)
                
                photos = []
                for f in sorted(os.listdir(DOWNLOAD_DIR), key=lambda x: os.path.getmtime(os.path.join(DOWNLOAD_DIR, x)), reverse=True):
                    if shortcode in f and f.endswith(('.jpg', '.jpeg', '.png', '.webp')):
                        fp = os.path.join(DOWNLOAD_DIR, f)
                        if os.path.getsize(fp) > 5000:
                            photos.append(fp)
                
                if photos:
                    result = {"success": True, "file_path": photos[0], "is_video": False}
                    if len(photos) > 1:
                        result["is_multiple"] = True
                        result["total"] = len(photos)
                        result["file_paths"] = photos
                    print(f"✅ Downloaded {len(photos)} photos")
                    return result
        except Exception as e:
            print(f"yt-dlp photo error: {e}")
        
        # FALLBACK: Direct page scrape with cookies
        try:
            cookies = get_cookie_dict()
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15',
                'Accept': 'text/html,application/xhtml+xml',
                'Accept-Language': 'en-US,en;q=0.9',
                'Referer': 'https://www.instagram.com/',
            })
            for name, value in cookies.items():
                session.cookies.set(name, value, domain='.instagram.com')
            
            resp = session.get(url, timeout=20)
            if resp.status_code != 200:
                return {"success": False, "error": f"𝗛𝗧𝗧𝗣 {resp.status_code} - 𝗨𝗽𝗱𝗮𝘁𝗲 𝗰𝗼𝗼𝗸𝗶𝗲𝘀"}
            
            html = resp.text
            image_urls = set()
            
            # All patterns for finding image URLs
            for pattern in [
                r'"display_url"\s*:\s*"([^"]+)"',
                r'"display_src"\s*:\s*"([^"]+)"',
                r'<meta\s+property="og:image"\s+content="([^"]+)"',
                r'https?://[^"\'\s]+\.(?:jpg|jpeg|png|webp)[^"\'\s]*',
            ]:
                for u in re.findall(pattern, html):
                    u = u.replace('\\u0026', '&').strip()
                    if u.startswith('http') and '.mp4' not in u and '.mov' not in u:
                        image_urls.add(u)
            
            if not image_urls:
                return {"success": False, "error": "𝗡𝗼 𝗽𝗵𝗼𝘁𝗼𝘀 𝗳𝗼𝘂𝗻𝗱"}
            
            downloaded = []
            for i, img_url in enumerate(list(image_urls)[:10]):
                try:
                    fp = os.path.join(DOWNLOAD_DIR, f"photo_{shortcode}_{i+1}.jpg")
                    r = session.get(img_url, stream=True, timeout=30)
                    if r.status_code == 200 and 'image' in r.headers.get('content-type', ''):
                        with open(fp, 'wb') as f:
                            for chunk in r.iter_content(8192):
                                if chunk: f.write(chunk)
                        if os.path.getsize(fp) > 5000:
                            downloaded.append(fp)
                except: continue
            
            if downloaded:
                result = {"success": True, "file_path": downloaded[0], "is_video": False}
                if len(downloaded) > 1:
                    result["is_multiple"] = True
                    result["total"] = len(downloaded)
                    result["file_paths"] = downloaded
                return result
            
            return {"success": False, "error": "𝗗𝗼𝘄𝗻𝗹𝗼𝗮𝗱 𝗳𝗮𝗶𝗹𝗲𝗱"}
        except Exception as e:
            return {"success": False, "error": str(e)[:80]}
    
    @staticmethod
    def extract_audio(video_path, custom_name=None):
        try:
            if custom_name and custom_name.lower() != "skip":
                safe = re.sub(r'[^\w\s-]', '', custom_name).strip()[:50] or "Audio"
                ap = os.path.join(DOWNLOAD_DIR, f"{safe}.mp3")
            else:
                ap = os.path.join(DOWNLOAD_DIR, f"{os.path.splitext(os.path.basename(video_path))[0]}.mp3")
            if not shutil.which('ffmpeg'): return {"success": False, "error": "𝗙𝗙𝗺𝗽𝗲𝗴 𝗻𝗼𝘁 𝗳𝗼𝘂𝗻𝗱"}
            subprocess.run(['ffmpeg', '-i', video_path, '-vn', '-acodec', 'libmp3lame', '-ab', '192k', '-y', ap], capture_output=True, timeout=180)
            if os.path.exists(ap) and os.path.getsize(ap) > 1000: return {"success": True, "file_path": ap}
            return {"success": False, "error": "𝗔𝘂𝗱𝗶𝗼 𝗲𝘅𝘁𝗿𝗮𝗰𝘁𝗶𝗼𝗻 𝗳𝗮𝗶𝗹𝗲𝗱"}
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
    "𝗗𝗼𝘄𝗻𝗹𝗼𝗮𝗱𝗲𝗱 𝗕𝘆 ➪ [˹𝚰𝖓𝖘𝖙𝖆𝖌𝖗𝖆𝖒 ✘ 𝚫𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐞𝐫˼ ♪�҉](https://t.me/Instagram_LinkToVideo_Bot)\n"
    "\n"
    "༼◉𝐂𝛄𝛆𝛂𝛕𝛆𝛄◉༽ 🪽 ➪ [𝜝𝜣𝜯 𝑭𝜟𝜯𝜢𝜮𝜞](https://t.me/FathersOfCreater) �҉"
)

WELCOME_TEXT = """ʜᴇʏ, {mention} 👋🏻
ɪ'ᴍ [˹𝚰𝖓𝖘𝖙𝖆𝖌𝖗𝖆𝖒 ✘ 𝚫𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐞𝐫˼ ♪�҉](https://t.me/Instagram_LinkToVideo_Bot),

┏━━━━━━━━━━━━━━━━━⧫
┠ ◆ ˹ɪ ʜᴀᴠᴇ sᴘᴇᴄɪᴀʟ ғᴇᴀᴛᴜʀᴇs˼
┠ ◆ ˹ᴀʟʟ-ɪɴ-ᴏɴᴇ ʙᴏᴛ˼
┗━━━━━━━━━━━━━━━━━⧫
┏━━━━━━━━━━━━━━━━━⧫
┠ ◆ ˹ʏᴏᴜ ᴄᴀɴ ᴅᴏᴡɴʟᴏᴀᴅ ɪɴsᴛᴀɢʀᴀᴍ ʀᴇᴇʟs˼
┠ ◆ ˹ʏᴏᴜ ᴄᴀɴ ᴅᴏᴡɴʟᴏᴀᴅ ɪɴsᴛᴀɢʀᴀᴍ ᴘʜᴏ𝘁𝗼𝘀˼
┠ ◆ ˹ʏᴏᴜ ᴄᴀɴ ᴇxᴛʀᴀᴄᴛ ᴀᴜᴅɪᴏ ғʀᴏᴍ ᴠɪᴅᴇᴏs˼
┠ ◆ ˹ʜᴅ ᴠɪᴅᴇᴏ + ᴏʀɪɢɪɴᴀʟ ᴀᴜᴅɪᴏ sᴜᴘᴘᴏʀᴛ˼
┠ ◆ ˹ᴍᴜʟᴛɪᴘʟᴇ ᴘʜᴏ𝘁𝗼 ᴅᴏᴡɴʟᴏᴀᴅ sᴜᴘᴘᴏʀᴛ˼
┠ ◆ ˹ɢʀᴏᴜᴘ sᴜᴘᴘᴏʀᴛ ᴀᴠᴀɪʟᴀʙʟᴇ˼
┗━━━━━━━━━━━━━━━━━⧫

⚡ ˹ᴸⁱⁿᵏ ᴮʰᵉʲᵒ → ⱽⁱᵈᵉᵒ ᴾᵃᵒ → ᴬᵘᵈⁱᵒ ᴺᵃᵃᵐ ᴮᵃᵗᵃᵒ → ᴬᵘᵈⁱᵒ ᴾᵃᵒ˼

⧫━━━━━✦◆ ◇ ◆ ◇ ◆ ◇✦━━━━━⧫
๏ ˹ᴄʟɪᴄᴋ ᴏɴ ᴛʜᴇ ᴀᴅᴅ ᴛᴏ ɢʀᴏᴜᴘ ʙᴜᴛᴛᴏɴ ʙᴇʟᴏᴡ ᴛᴏ ᴀᴅᴅ ᴛʜɪs ʙᴏᴛ ɪɴ ʏᴏᴜʀ ɢʀᴏᴜᴘ ᴀɴᴅ ᴇɴᴊᴏʏ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ ᴛʜᴇʀᴇ ᴛᴏᴏ˼

🫧 ˹ᴅᴇᴠᴇʟᴏᴩᴇʀ˼ 🪽 ➪ [𝜝𝜣𝜯 𝑭𝜟𝜯𝜢𝜮𝜞](https://t.me/FathersOfCreater) ✔︎"""

GROUP_WELCOME = """👋🏻 **ʜᴇʟʟᴏ {chat_title}!**

ɪ'ᴍ [˹𝚰𝖓𝖘𝖙𝖆𝖌𝖗𝖆𝖒 ✘ 𝚫𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐞𝐫˼ ♪�҉](https://t.me/Instagram_LinkToVideo_Bot),

┏━━━━━━━━━━━━━━━━━⧫
┠ ◆ ˹ᴅᴏᴡɴʟᴏᴀᴅ ɪɴsᴛᴀɢʀᴀᴍ ʀᴇᴇʟs, ᴘʜᴏᴛᴏs & ᴀᴜᴅɪᴏ˼
┠ ◆ ˹ʜᴅ ᴠɪᴅᴇᴏ + ᴏʀɪɢɪɴᴀʟ ᴀᴜᴅɪᴏ ɢᴜᴀʀᴀɴᴛᴇᴇᴅ˼
┠ ◆ ˹ᴊᴜsᴛ sᴇɴᴅ ɪɴsᴛᴀɢʀᴀᴍ ʟɪɴᴋ ɪɴ ɢʀᴏᴜᴘ˼
┗━━━━━━━━━━━━━━━━━⧫

⚡ ˹sɪʀғ ʟɪɴᴋ ʙʜᴇᴊᴏ, ʙᴀᴋɪ ʙᴏᴛ ᴅᴇᴋʜ ʟᴇɢᴀ˼

🫧 ˹ᴅᴇᴠᴇʟᴏᴩᴇʀ˼ 🪽 ➪ [𝜝𝜣𝜯 𝑭𝜟𝜯𝜢𝜮𝜞](https://t.me/FathersOfCreater) ✔︎"""

AUDIO_BUTTON_TEXT = "➪ ˹𝐃𝐨𝐰𝐧𝐥𝐨𝐚𝐝 𝐕𝐢𝐝𝐞𝐨 𝐀𝐮𝐝𝐢𝐨˼  ♪�҉"
AUDIO_DEFAULT_NAME = "➪ ༼◉♡ 𝙈𝙮 𝙈𝙪𝙨𝙞𝙘 ♪�҉🛸◉༽"

AUDIO_NAME_PROMPT = (
    "➪ 𝙊𝙠𝙖𝙮, 𝙂𝙖𝙫𝙚 𝙈𝙚 𝘼𝙪𝙙𝙞𝙤 𝙉𝙖𝙢𝙚?\n\n"
    "𝐄𝐱𝐚𝐦𝐩𝐥𝐞 : 𝐌𝐲 𝐌𝐮𝐬𝐢𝐜 🎶\n"
    " ˹ησ ι∂єα вє¢αυѕє уσυ gαу˼ ♪�҉\n\n"
    "𝐘𝐨𝐮 𝐇𝐚𝐯𝐞 𝐍𝐨 𝐈𝐝𝐞𝐚 𝐓𝐡𝐚𝐧 𝐂𝐥𝐢𝐜𝐤 𝐓𝐡𝐢𝐬 𝐁𝐮𝐭𝐭𝐨𝐧 🔽"
)

# ═══════════════════════════
# 🎬 WELCOME ANIMATION
# ═══════════════════════════

async def welcome_animation(bot, chat_id, user_id, first_name):
    try:
        user_mention = f"[{first_name}](tg://user?id={user_id})"
        emoji_id = get_random_emoji()
        if emoji_id:
            try: await bot.send_sticker(chat_id, emoji_id)
            except: pass
        await asyncio.sleep(0.1)
        welcome_emojis = ["🩷", "🌸", "🏖️", "🍰", "🥂"]
        welcome_msg = await bot.send_message(chat_id, f"𝐖𝐞𝐥𝐜𝐨𝐦𝐞 𝐁ᴀʙʏ ꨄ {user_mention}...🩷", parse_mode="Markdown")
        for emoji in welcome_emojis:
            await asyncio.sleep(0.5)
            try: await welcome_msg.edit_text(f"𝐖𝐞𝐥𝐜𝐨𝐦𝐞 𝐁ᴀʙʏ ꨄ {user_mention}...{emoji}", parse_mode="Markdown")
            except: break
        await welcome_msg.delete()
        await asyncio.sleep(0.2)
        starting_emojis = ["🚀", "🌠", "🪶", "🍓", "🤖", "🥡", "🍷", "🍭", "🍨", "🧭", "🫧", "🍫", "🛸"]
        words = ["s", "t", "α", "я", "т", "ι", "и", "g", ".", ".", ".", ".", "."]
        starter_msg = await bot.send_message(chat_id, f"**{starting_emojis[0]}**", parse_mode="Markdown")
        for i in range(len(words)):
            await asyncio.sleep(0.08)
            try: await starter_msg.edit_text(f"**{starting_emojis[i%len(starting_emojis)]} " + "".join(words[:i+1]) + "**", parse_mode="Markdown")
            except: break
        await asyncio.sleep(0.2); await starter_msg.delete()
        sticker_id = get_random_sticker()
        if sticker_id:
            try: await bot.send_sticker(chat_id, sticker_id)
            except: pass
        await asyncio.sleep(4)
        video_data = get_random_video()
        final_text = WELCOME_TEXT.replace("{mention}", user_mention)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("◆ ➪ ˹𝜟𝙙𝙙 𝜯𝜣 𝑮𝜞𝜭𝑼𝝆˼ ♪☬", url=f"https://t.me/{(await bot.get_me()).username}?startgroup=true")]])
        if video_data and os.path.exists(video_data["path"]):
            await bot.send_video(chat_id, video_data["path"], caption=final_text, parse_mode="Markdown", reply_markup=kb)
        else:
            await bot.send_message(chat_id, final_text, parse_mode="Markdown", reply_markup=kb)
    except:
        pass

# ═══════════════════════════
# 🤖 HANDLERS
# ═══════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_bot_enabled(): return
    if update.effective_chat.type != 'private': return
    await welcome_animation(context.bot, update.effective_chat.id, update.effective_user.id, update.effective_user.first_name or "User")

async def activate_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in ['group', 'supergroup']: return
    if is_group_activated(chat.id):
        await update.message.reply_text("✅ **𝗔𝗹𝗿𝗲𝗮𝗱𝘆 𝗮𝗰𝘁𝗶𝘃𝗮𝘁𝗲𝗱!**", parse_mode="Markdown")
    else:
        activate_group(chat.id)
        await update.message.reply_text("✅ **𝗔𝗰𝘁𝗶𝘃𝗮𝘁𝗲𝗱!** 🚀\n𝗦𝗲𝗻𝗱 𝗜𝗻𝘀𝘁𝗮𝗴𝗿𝗮𝗺 𝗹𝗶𝗻𝗸 𝗻𝗼𝘄!", parse_mode="Markdown")

async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    await update.message.reply_text("⚙️ **𝗖𝗢𝗠𝗠𝗔𝗡𝗗𝗦**\n\n👑 **𝗢𝗪𝗡𝗘𝗥:** /start /disable /enable /settings\n👥 **𝗚𝗥𝗢𝗨𝗣:** /activate\n🎨 **𝗘𝗠𝗢𝗝𝗜:** /addemoji /removeemoji /listemojis\n❄ **𝗦𝗧𝗜𝗖𝗞𝗘𝗥:** /addsticker /removesticker /liststickers\n📹 **𝗩𝗜𝗗𝗘𝗢:** /addvideo /delvideo /videos /clearvideos", parse_mode="Markdown", disable_web_page_preview=True)

async def bot_added_to_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_bot_enabled(): return
    if update.my_chat_member.new_chat_member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR]:
        chat = update.effective_chat; bot_user = await context.bot.get_me()
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("◆ ➪ ˹𝜟𝙙𝙙 𝜯𝜣 𝑮𝜞𝜭𝑼𝝆˼ ♪☬", url=f"https://t.me/{bot_user.username}?startgroup=true")]])
        try: await context.bot.send_message(chat.id, GROUP_WELCOME.replace("{chat_title}", chat.title or "Group"), parse_mode="Markdown", reply_markup=kb)
        except: pass

async def disable_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    set_bot_state(False)
    await update.message.reply_text("🚫 **𝗗𝗜𝗦𝗔𝗕𝗟𝗘𝗗**", parse_mode="Markdown")

async def enable_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    set_bot_state(True)
    await update.message.reply_text("✅ **𝗘𝗡𝗔𝗕𝗟𝗘𝗗**", parse_mode="Markdown")

async def add_emoji_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not update.message.reply_to_message or not update.message.reply_to_message.sticker:
        await update.message.reply_text("Reply to emoji sticker"); return
    s, t = add_emoji_db(update.message.reply_to_message.sticker.file_id)
    await update.message.reply_text(f"✅ Added! ({t})" if s else "❌ Exists!")

async def remove_emoji_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    try:
        idx = int(update.message.text.split()[1]) - 1
        s, t = remove_emoji_db(idx)
        await update.message.reply_text(f"✅ Removed! ({t})" if s else f"❌ Invalid! Total: {t}")
    except: await update.message.reply_text("/removeemoji index")

async def list_emojis_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    await update.message.reply_text(f"Emojis: {len(get_emojis())}")

async def add_sticker_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not update.message.reply_to_message or not update.message.reply_to_message.sticker:
        await update.message.reply_text("Reply to sticker"); return
    s, t = add_sticker_db(update.message.reply_to_message.sticker.file_id)
    await update.message.reply_text(f"✅ Added! ({t})" if s else "❌ Exists!")

async def remove_sticker_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    try:
        idx = int(update.message.text.split()[1]) - 1
        s, t = remove_sticker_db(idx)
        await update.message.reply_text(f"✅ Removed! ({t})" if s else f"❌ Invalid! Total: {t}")
    except: await update.message.reply_text("/removesticker index")

async def list_stickers_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    await update.message.reply_text(f"Stickers: {len(get_stickers())}")

async def add_video_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not update.message.reply_to_message or not update.message.reply_to_message.video:
        await update.message.reply_text("Reply to video"); return
    m = await update.message.reply_text("📂 **𝗔𝗱𝗱𝗶𝗻𝗴...**", parse_mode="Markdown")
    try:
        file = await update.message.reply_to_message.video.get_file()
        fp = os.path.join(VIDEO_DIR, f"w_{int(time.time())}.mp4")
        await file.download_to_drive(fp)
        vid, total = add_video_db(fp)
        await m.edit_text(f"✅ **𝗩𝗶𝗱𝗲𝗼 𝗔𝗱𝗱𝗲𝗱!** ID: {vid} ({total})", parse_mode="Markdown")
    except Exception as e: await m.edit_text(f"❌ {e}")

async def del_video_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    try:
        s, t = delete_video_db(int(update.message.text.split()[1]))
        await update.message.reply_text(f"✅ Deleted! ({t})" if s else "❌ Not found!")
    except: await update.message.reply_text("/delvideo ID")

async def list_videos_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    await update.message.reply_text(f"Videos: {len(get_video_list())}")

async def clear_videos_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    await update.message.reply_text(f"🗑️ {clear_videos_db()} videos cleared!")

# ═══════════════ MESSAGE HANDLER ═══════════════

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_bot_enabled(): return
    chat_type = update.effective_chat.type
    if chat_type in ['group', 'supergroup'] and not is_group_activated(update.effective_chat.id): return
    
    text = update.message.text
    if not text: return
    
    if context.user_data.get('awaiting_audio'):
        context.user_data['awaiting_audio'] = False
        audio_name = text.strip()
        url = context.user_data.get('audio_video_url')
        if url: await extract_and_send_audio(update, context, url, audio_name)
        context.user_data['audio_video_url'] = None
        return
    
    if text == AUDIO_DEFAULT_NAME:
        context.user_data['awaiting_audio'] = False
        url = context.user_data.get('audio_video_url')
        if url: await extract_and_send_audio(update, context, url, AUDIO_DEFAULT_NAME)
        context.user_data['audio_video_url'] = None
        return
    
    if not InstaDownloader.is_instagram_url(text): return
    url = InstaDownloader.extract_url(text)
    if not url:
        await update.message.reply_text("❌ **𝗜𝗻𝘃𝗮𝗹𝗶𝗱 𝗨𝗥𝗟**", parse_mode="Markdown")
        return
    
    context.user_data['current_url'] = url
    chat_id = update.effective_chat.id; user_id = update.effective_user.id
    shortcode = InstaDownloader.get_shortcode(url)
    cache_key = f"{chat_id}_{user_id}_{shortcode}"
    
    sticker_id = get_random_sticker()
    if sticker_id:
        try: await context.bot.send_sticker(chat_id, sticker_id)
        except: pass
    
    msg = await update.message.reply_text("⏳ **𝗣𝗿𝗼𝗰𝗲𝘀𝘀𝗶𝗻𝗴...**", parse_mode="Markdown")
    
    try:
        is_reel = '/reel/' in url or '/tv/' in url
        await msg.edit_text("📥 **𝗗𝗼𝘄𝗻𝗹𝗼𝗮𝗱𝗶𝗻𝗴 𝗩𝗶𝗱𝗲𝗼...**" if is_reel else "📥 **𝗗𝗼𝘄𝗻𝗹𝗼𝗮𝗱𝗶𝗻𝗴 𝗣𝗵𝗼𝘁𝗼...**", parse_mode="Markdown")
        result = InstaDownloader.download_media(url)
        
        if not result.get("success"):
            await msg.edit_text(f"❌ **𝗙𝗮𝗶𝗹𝗲𝗱!** {result.get('error', '')}", parse_mode="Markdown")
            return
        
        if result.get("is_multiple"):
            photo_paths = result.get("file_paths", []); total = len(photo_paths)
            save_photo_cache(cache_key, photo_paths)
            await msg.edit_text(f"📤 **𝗨𝗽𝗹𝗼𝗮𝗱𝗶𝗻𝗴 {total} 𝗣𝗵𝗼𝘁𝗼𝘀...**", parse_mode="Markdown")
            if total > 0 and os.path.exists(photo_paths[0]):
                keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(f"➪ 𝗡𝗲𝘅𝘁 𝗣𝗵𝗼𝘁𝗼 ➤ (2/{total})", callback_data=f"nxp_{cache_key}_0")]]) if total > 1 else None
                with open(photo_paths[0], 'rb') as f:
                    await update.message.reply_photo(photo=f, caption=f"📸 **𝗣𝗵𝗼𝘁𝗼 1/{total}**\n\n{CAPTION}", parse_mode="Markdown", reply_markup=keyboard)
            await msg.delete()
            return
        
        fp = result["file_path"]
        if not os.path.exists(fp) or os.path.getsize(fp) < 1000:
            await msg.edit_text("❌ **𝗙𝗶𝗹𝗲 𝗡𝗼𝘁 𝗙𝗼𝘂𝗻𝗱**", parse_mode="Markdown"); return
        
        size_mb = os.path.getsize(fp) / (1024 * 1024)
        if size_mb > 50:
            await msg.edit_text(f"❌ **>𝟱𝟬𝗠𝗕** ({size_mb:.1f}MB)", parse_mode="Markdown")
            InstaDownloader.cleanup(fp); return
        
        is_video = result.get("is_video", False) or fp.endswith(('.mp4', '.mov', '.webm'))
        
        if is_video:
            await msg.edit_text("📤 **𝗨𝗽𝗹𝗼𝗮𝗱𝗶𝗻𝗴 𝗩𝗶𝗱𝗲𝗼...**", parse_mode="Markdown")
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(AUDIO_BUTTON_TEXT, callback_data=f"aud_{url}")]])
            with open(fp, 'rb') as f:
                await update.message.reply_video(video=f, caption=CAPTION, parse_mode="Markdown", reply_markup=keyboard, supports_streaming=True)
        else:
            await msg.edit_text("📤 **𝗨𝗽𝗹𝗼𝗮𝗱𝗶𝗻𝗴 𝗣𝗵𝗼𝘁𝗼...**", parse_mode="Markdown")
            with open(fp, 'rb') as f:
                await update.message.reply_photo(photo=f, caption=CAPTION, parse_mode="Markdown")
        
        await msg.delete(); InstaDownloader.cleanup(fp)
    except Exception as e:
        await msg.edit_text(f"❌ **𝗘𝗿𝗿𝗼𝗿:** {str(e)[:100]}", parse_mode="Markdown")
        for f in os.listdir(DOWNLOAD_DIR):
            try: os.remove(os.path.join(DOWNLOAD_DIR, f))
            except: pass

async def extract_and_send_audio(update, context, url, audio_name):
    status_msg = await update.message.reply_text("🎵 **𝗘𝘅𝘁𝗿𝗮𝗰𝘁𝗶𝗻𝗴 𝗔𝘂𝗱𝗶𝗼...**", parse_mode="Markdown")
    try:
        result = InstaDownloader.download_media(url)
        if not result.get("success"): await status_msg.edit_text("❌ **𝗙𝗮𝗶𝗹𝗲𝗱**", parse_mode="Markdown"); return
        vp = result["file_path"]
        ar = InstaDownloader.extract_audio(vp, audio_name)
        if ar.get("success"):
            await status_msg.edit_text("📤 **𝗦𝗲𝗻𝗱𝗶𝗻𝗴 𝗔𝘂𝗱𝗶𝗼...**", parse_mode="Markdown")
            with open(ar["file_path"], 'rb') as f:
                await update.message.reply_audio(audio=f, title=audio_name, performer="Instagram", caption=CAPTION, parse_mode="Markdown")
            await asyncio.sleep(2); await status_msg.delete()
            try: os.remove(ar["file_path"])
            except: pass
        else: await status_msg.edit_text(f"❌ **{ar.get('error')}**", parse_mode="Markdown")
        InstaDownloader.cleanup(vp)
    except Exception as e: await status_msg.edit_text(f"❌ **{str(e)[:80]}**", parse_mode="Markdown")

async def extract_and_send_audio_direct(query, context, url, audio_name):
    status_msg = await query.message.reply_text("🎵 **𝗘𝘅𝘁𝗿𝗮𝗰𝘁𝗶𝗻𝗴 𝗔𝘂𝗱𝗶𝗼...**", parse_mode="Markdown")
    try:
        result = InstaDownloader.download_media(url)
        if not result.get("success"): await status_msg.edit_text("❌ **𝗙𝗮𝗶𝗹𝗲𝗱**", parse_mode="Markdown"); return
        vp = result["file_path"]
        ar = InstaDownloader.extract_audio(vp, audio_name)
        if ar.get("success"):
            await status_msg.edit_text("📤 **𝗦𝗲𝗻𝗱𝗶𝗻𝗴 𝗔𝘂𝗱𝗶𝗼...**", parse_mode="Markdown")
            with open(ar["file_path"], 'rb') as f:
                await query.message.reply_audio(audio=f, title=audio_name, performer="Instagram", caption=CAPTION, parse_mode="Markdown")
            await asyncio.sleep(2); await status_msg.delete()
            try: os.remove(ar["file_path"])
            except: pass
        else: await status_msg.edit_text(f"❌ **{ar.get('error')}**", parse_mode="Markdown")
        InstaDownloader.cleanup(vp)
    except Exception as e: await status_msg.edit_text(f"❌ **{str(e)[:80]}**", parse_mode="Markdown")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    
    if query.data.startswith("aud_"):
        video_url = query.data[4:]
        context.user_data['audio_video_url'] = video_url
        await query.edit_message_reply_markup(reply_markup=None)
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(AUDIO_DEFAULT_NAME, callback_data="def_audio")]])
        await query.message.reply_text(AUDIO_NAME_PROMPT, parse_mode="Markdown", reply_markup=keyboard)
        context.user_data['awaiting_audio'] = True
    elif query.data == "def_audio":
        await query.message.delete()
        context.user_data['awaiting_audio'] = False
        url = context.user_data.get('audio_video_url') or context.user_data.get('current_url')
        if url: await extract_and_send_audio_direct(query, context, url, AUDIO_DEFAULT_NAME)
    elif query.data.startswith("nxp_"):
        parts = query.data[4:].rsplit("_", 1); cache_key = parts[0]; current_idx = int(parts[1]); next_idx = current_idx + 1
        photo_paths = get_photo_cache(cache_key)
        if photo_paths and next_idx < len(photo_paths) and os.path.exists(photo_paths[next_idx]):
            await query.edit_message_reply_markup(reply_markup=None)
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(f"➪ 𝗡𝗲𝘅𝘁 𝗣𝗵𝗼𝘁𝗼 ➤ ({next_idx + 2}/{len(photo_paths)})", callback_data=f"nxp_{cache_key}_{next_idx}")]]) if next_idx + 1 < len(photo_paths) else None
            with open(photo_paths[next_idx], 'rb') as f:
                await query.message.reply_photo(photo=f, caption=f"📸 **𝗣𝗵𝗼𝘁𝗼 {next_idx + 1}/{len(photo_paths)}**\n\n{CAPTION}", parse_mode="Markdown", reply_markup=keyboard)
        else:
            await query.answer("No more photos!", show_alert=True)

# ═══════════════════════════
# 🚀 MAIN
# ═══════════════════════════

def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
    print("╔══════════════════════════╗")
    print("║  🤖 INSTAGRAM BOT v36   ║")
    print("║  ✅ ALL BOLD + WORKING  ║")
    print("╚══════════════════════════╝")
    
    os.system('apt-get update -qq && apt-get install -y -qq ffmpeg 2>/dev/null')
    print(f"🍪 Cookies: {'✅ Found' if os.path.exists('cookies.txt') else '❌ Missing'}")
    
    for f in os.listdir(DOWNLOAD_DIR):
        try: os.remove(os.path.join(DOWNLOAD_DIR, f))
        except: pass
    
    app = Application.builder().token(BOT_TOKEN).read_timeout(120).write_timeout(120).connect_timeout(120).pool_timeout(120).build()
    
    # All command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("activate", activate_cmd))
    app.add_handler(CommandHandler("settings", settings_cmd))
    app.add_handler(CommandHandler("disable", disable_cmd))
    app.add_handler(CommandHandler("enable", enable_cmd))
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
    
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, bot_added_to_group))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    print("✅ Bot Started! 🚀")
    app.run_polling(drop_pending_updates=True)
