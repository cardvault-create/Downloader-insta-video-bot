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
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.constants import ChatMemberStatus
import yt_dlp
import requests

# ═══════════════════════════
# 🔐 CONFIG
# ═══════════════════════════

BOT_TOKEN = "8518787964:AAHMOM3IsD-vVM4qLkSTw1JnplRg0Xd6STI"
OWNER_ID = 1987818347

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Add this line
download_semaphore = asyncio.Semaphore(2)  # Max 2 parallel downloads

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
# 📥 INSTAGRAM DOWNLOADER - FINAL FIXED
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
        if m:
            return f"https://www.instagram.com/{m.group(3)}/{m.group(4)}/"
        return None
    
    @staticmethod
    def get_shortcode(url):
        m = re.search(r'/(p|reel|tv)/([a-zA-Z0-9_\-]+)', url)
        return m.group(2) if m else None
    
    @staticmethod
    def download_media(url):
        shortcode = InstaDownloader.get_shortcode(url)
        if not shortcode:
            return {"success": False, "error": "Invalid"}
        is_reel = '/reel/' in url or '/tv/' in url
        for f in os.listdir(DOWNLOAD_DIR):
            if shortcode in f:
                try: os.remove(os.path.join(DOWNLOAD_DIR, f))
                except: pass
        if is_reel:
            return InstaDownloader._download_video_fixed(shortcode)
        else:
            return InstaDownloader._download_photo_fixed(shortcode)
    
    @staticmethod
    def _download_video_fixed(shortcode):
        url = f'https://www.instagram.com/reel/{shortcode}/'
        output_path = os.path.join(DOWNLOAD_DIR, f'{shortcode}.mp4')
        cmd = [
            'yt-dlp', url, '-o', output_path,
            '-f', 'bv*+ba/b', '--merge-output-format', 'mp4',
            '--socket-timeout', '20', '--retries', '2',
            '--no-warnings', '--no-color', '--force-overwrites',
            '--user-agent', 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15'
        ]
        if os.path.exists('cookies.txt'):
            cmd.extend(['--cookies', 'cookies.txt'])
        try:
            subprocess.run(cmd, capture_output=True, timeout=40)
        except subprocess.TimeoutExpired:
            os.system('pkill -9 yt-dlp 2>/dev/null')
        except: pass
        if os.path.exists(output_path) and os.path.getsize(output_path) > 50000:
            return {"success": True, "file_path": output_path, "is_video": True}
        cmd[4] = 'best[ext=mp4]/best'
        try:
            subprocess.run(cmd, capture_output=True, timeout=30)
        except subprocess.TimeoutExpired:
            os.system('pkill -9 yt-dlp 2>/dev/null')
        except: pass
        if os.path.exists(output_path) and os.path.getsize(output_path) > 50000:
            return {"success": True, "file_path": output_path, "is_video": True}
        return {"success": False, "error": "🚫 𝐒𝐞𝐫𝐯𝐞𝐫 𝐁𝐮𝐬𝐲, 𝐓𝐫𝐲 𝐀𝐠𝐚𝐢𝐧 (˃̣̣̥᷄⌓˂̣̣̥᷅)"}
    
    @staticmethod
    def _download_photo_fixed(shortcode):
        cdn_urls = [
            f"https://www.instagram.com/p/{shortcode}/media/?size=l",
            f"https://www.instagram.com/p/{shortcode}/media/",
        ]
        headers = {
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15',
            'Accept': 'image/*', 'Referer': 'https://www.instagram.com/'
        }
        for cdn_url in cdn_urls:
            try:
                r = requests.get(cdn_url, headers=headers, timeout=10, stream=True)
                if r.status_code == 200:
                    fp = os.path.join(DOWNLOAD_DIR, f"{shortcode}.jpg")
                    with open(fp, 'wb') as f:
                        for chunk in r.iter_content(8192): f.write(chunk)
                    if os.path.getsize(fp) > 5000:
                        return {"success": True, "file_path": fp, "is_video": False}
            except: continue
        try:
            url = f'https://www.instagram.com/p/{shortcode}/'
            r = requests.get(url, headers=headers, timeout=10)
            if r.status_code == 200:
                og = re.search(r'<meta\s+property="og:image"\s+content="([^"]+)"', r.text)
                if og:
                    img_r = requests.get(og.group(1), headers=headers, timeout=10, stream=True)
                    if img_r.status_code == 200:
                        fp = os.path.join(DOWNLOAD_DIR, f"{shortcode}.jpg")
                        with open(fp, 'wb') as f:
                            for chunk in img_r.iter_content(8192): f.write(chunk)
                        if os.path.getsize(fp) > 5000:
                            return {"success": True, "file_path": fp, "is_video": False}
        except: pass
        return {"success": False, "error": "🚫 𝐒𝐞𝐫𝐯𝐞𝐫 𝐢𝐬𝐬𝐮𝐞, 𝐩𝐥𝐞𝐚𝐬𝐞 𝐭𝐫𝐲 𝐚𝐠𝐚𝐢𝐧 (˃̣̣̥᷄⌓˂̣̣̥᷅)"}
    
    @staticmethod
    def extract_audio(video_path, custom_name=None):
        try:
            if custom_name and custom_name.lower() != "skip":
                safe = re.sub(r'[^\w\s-]', '', custom_name).strip()[:50] or "Audio"
                ap = os.path.join(os.path.dirname(video_path), f"{safe}.mp3")
            else:
                ap = os.path.join(os.path.dirname(video_path), f"{os.path.splitext(os.path.basename(video_path))[0]}.mp3")
            if not shutil.which('ffmpeg'): return {"success": False, "error": "FFmpeg not found"}
            subprocess.run(['ffmpeg', '-i', video_path, '-vn', '-acodec', 'libmp3lame', '-ab', '192k', '-y', ap], capture_output=True, timeout=120)
            if os.path.exists(ap) and os.path.getsize(ap) > 1000: return {"success": True, "file_path": ap}
            return {"success": False, "error": "Audio extraction failed"}
        except subprocess.TimeoutExpired: return {"success": False, "error": "Audio timeout"}
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
    "𝗗𝗼𝘄𝗻𝗹𝗼𝗮𝗱𝗲𝗱 𝗕𝘆 ➪ [˹𝚰𝖓𝖘𝖙𝖆𝖌𝖗𝖆𝖒 ✘ 𝚫𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐞𝐫˼ ♪](https://t.me/Instagram_LinkToVideo_Bot)\n"
    "\n"
    "༼◉𝐂𝛄𝛆𝛂𝛕𝛆𝛄◉༽ 🪽 ➪ [𝜝𝜣𝜯 𝑭𝜟𝜯𝜢𝜮𝜞](https://t.me/FathersOfCreater)"
)

WELCOME_TEXT = """ʜᴇʏ, {mention} . ˚◞♡ ◟˚ .
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

⚡ ˹ᴸⁱⁿᵏ ᴮʰᵉʲᵒ → ⱽⁱᵈᵉᵒ ᴾᵃᵒ → ᴰᵒʷⁿˡᵒᵃᵈ ⱽⁱᵈᵉᵒ ᴬᵘᵈⁱᵒ → ♡ ᴮᵘᵗᵗᵒⁿ ᴰᵃᵇᵃᵒ ♡ → ᴬᵘᵈⁱᵒ ᴾᵃᵒ˼✧ ⋆˚ · . 　 🌙 　 . · ˚⋆

⧫━━━━━✦◆ ◇ ◆ ◇ ◆ ◇✦━━━━━⧫
๏ ˹ᴄʟɪᴄᴋ ᴏɴ ᴛʜᴇ ᴀᴅᴅ ᴛᴏ ɢʀᴏᴜᴘ ʙᴜᴛᴛᴏɴ ʙᴇʟᴏᴡ ᴛᴏ ᴀᴅᴅ ᴛʜɪs ʙᴏᴛ ɪɴ ʏᴏᴜʀ ɢʀᴏᴜᴘ ᴀɴᴅ ᴇɴᴊᴏʏ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ ᴛʜᴇʀᴇ ᴛᴏᴏ˼

🫧 ˹ᴅᴇᴠᴇʟᴏᴩᴇʀ˼ 🪽 ➪ [𝜝𝜣𝜯 𝑭𝜟𝜯𝜢𝜮𝜞](https://t.me/FathersOfCreater) ✔︎"""

GROUP_WELCOME = """👋🏻 ʜᴇʟʟᴏ {chat_title} ♡ ⋆｡°✩

ɪ'ᴍ [˹𝚰𝖓𝖘𝖙𝖆𝖌𝖗𝖆𝖒 ✘ 𝚫𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐞𝐫˼ ♪](https://t.me/Instagram_LinkToVideo_Bot),

┏━━━━━━━━━━━━━━━━━⧫
┠ ◆ ˹ᴅᴏᴡɴʟᴏᴀᴅ ɪɴsᴛᴀɢʀᴀᴍ ʀᴇᴇʟs, ᴘʜᴏᴛᴏs & ᴀᴜᴅɪᴏ˼
┠ ◆ ˹ʜᴅ ᴠɪᴅᴇᴏ + ᴏʀɪɢɪɴᴀʟ ᴀᴜᴅɪᴏ ɢᴜᴀʀᴀɴᴛᴇᴇᴅ˼
┠ ◆ ˹ᴊᴜsᴛ sᴇɴᴅ ɪɴsᴛᴀɢʀᴀᴍ ʟɪɴᴋ ɪɴ ɢʀᴏᴜᴘ˼
┗━━━━━━━━━━━━━━━━━⧫

⚡ ˹sɪʀғ ʟɪɴᴋ ʙʜᴇᴊᴏ, ʙᴀᴋɪ ʙᴏᴛ ᴅᴇᴋʜ ʟᴇɢᴀ˼✧ ⋆˚ · . 　 ☽ 　 . · ˚⋆

🫧 ˹ᴅᴇᴠᴇʟᴏᴩᴇʀ˼ 🪽 ➪ [𝜝𝜣𝜯 𝑭𝜟𝜯𝜢𝜮𝜞](https://t.me/FathersOfCreater) ✔︎"""

BOT_DISABLED_MSG = "🚫 𝗕𝗢𝗧 𝗦𝗧𝗢𝗣 𝗕𝗬 𝗢𝗪𝗡𝗘𝗥\n\n𝗕𝗼𝘁 𝗶𝘀 𝗰𝘂𝗿𝗿𝗲𝗻𝘁𝗹𝘆 𝗱𝗶𝘀𝗮𝗯𝗹𝗲𝗱. (˃̣̣̥᷄⌓˂̣̣̥᷅)"

AUDIO_BUTTON_TEXT = "➪ ˹𝐃𝐨𝐰𝐧𝐥𝐨𝐚𝐝 𝐕𝐢𝐝𝐞𝐨 𝐀𝐮𝐝𝐢𝐨˼  ♪"
AUDIO_DEFAULT_NAME = "➪ ༼◉♡ 𝙈𝙮 𝙈𝙪𝙨𝙞𝙘 ♪🛸◉༽"

AUDIO_NAME_PROMPT = (
    "➪ 𝙊𝙠𝙖𝙮, 𝙂𝙖𝙫𝙚 𝙈𝙚 𝘼𝙪𝙙𝙞𝙤 𝙉𝙖𝙢𝙚?\n\n"
    "𝐄𝐱𝐚𝐦𝐩𝐥𝐞 : 𝐌𝐲 𝐌𝐮𝐬𝐢𝐜 🎶\n"
    " ˹ησ ι∂єα вє¢αυѕє уσυ gαу˼ ♪\n\n"
    "𝐘𝐨𝐮 𝐇𝐚𝐯𝐞 𝐍𝐨 𝐈𝐝𝐞𝐚 𝐓𝐡𝐚𝐧 𝐂𝐥𝐢𝐜𝐤 𝐓𝐡𝐢𝐬 𝐁𝐮𝐭𝐭𝐨𝐧 ⤵️"
)

SETTINGS_TEXT = (
    "⚙️ 𝗖𝗢𝗠𝗠𝗔𝗡𝗗𝗦 ：\n\n"
    "👑 𝗢𝗪𝗡𝗘𝗥 ： \n"
    "┣ /start ➪ 𝗦𝘁𝗮𝗿𝘁 𝗕𝗼𝘁\n"
    "┣ /disable ➪ 𝗗𝗶𝘀𝗮𝗯𝗹𝗲 𝗕𝗼𝘁\n"
    "┣ /enable ➪ 𝗘𝗻𝗮𝗯𝗹𝗲 𝗕𝗼𝘁\n"
    "┗ /settings ➪ 𝗕𝗼𝘁 𝗦𝗲𝘁𝘁𝗶𝗻𝗴𝘀\n\n"
    "👥 𝗚𝗥𝗢𝗨𝗣 ：\n"
    "┗ /activate ➪ 𝗔𝗰𝘁𝗶𝘃𝗮𝘁𝗲 𝗚𝗿𝗼𝘂𝗽\n\n"
    "🎨 𝗘𝗠𝗢𝗝Ｉ ：\n"
    "┣ /addemoji ➪ 𝗔𝗱𝗱 𝗘𝗺𝗼𝗷𝗶\n"
    "┣ /removeemoji ➪ 𝗥𝗲𝗺𝗼𝘃𝗲 𝗘𝗺𝗼𝗷𝗶\n"
    "┗ /listemojis ➪ 𝗟𝗶𝘀𝘁 𝗘𝗺𝗼𝗷𝗶𝘀\n\n"
    "❄ 𝗦𝗧𝗜𝗖𝗞𝗘𝗥 ：\n"
    "┣ /addsticker ➪ 𝗔𝗱𝗱 𝗦𝘁𝗶𝗰𝗸𝗲𝗿\n"
    "┣ /removesticker ➪ 𝗥𝗲𝗺𝗼𝘃𝗲 𝗦𝘁𝗶𝗰𝗸𝗲𝗿\n"
    "┗ /liststickers ➪ 𝗟𝗶𝘀𝘁 𝗦𝘁𝗶𝗰𝗸𝗲𝗿𝘀\n\n"
    "📹 𝗩𝗜𝗗𝗘𝗢 ：\n"
    "┣ /addvideo ➪ 𝗔𝗱𝗱 𝗩𝗶𝗱𝗲𝗼\n"
    "┣ /delvideo ➪ 𝗗𝗲𝗹𝗲𝘁𝗲 𝗩𝗶𝗱𝗲𝗼\n"
    "┣ /videos ➪ 𝗟𝗶𝘀𝘁 𝗩𝗶𝗱𝗲𝗼𝘀\n"
    "┗ /clearvideos ➪ 𝗖𝗹𝗲𝗮𝗿 𝗔𝗹𝗹 𝗩𝗶𝗱𝗲𝗼𝘀\n\n"
    "⧫━━━━━✦◆ ◇ ◆ ◇ ◆ ◇✦━━━━━⧫\n"
    "🫧 ˹𝗗𝗲𝘃𝗲𝗹𝗼𝗽𝗲𝗿˼ 🪽 ➪ [𝜝𝜣𝜯 𝑭𝜟𝜯𝜢𝜮𝜞](https://t.me/FathersOfCreater)"
)

async def welcome_animation(bot, chat_id, user_id, first_name):
    try:
        user_mention = f"[{first_name}](tg://user?id={user_id})"
        
        emoji_id = get_random_emoji()
        emoji_msg = None
        if emoji_id:
            try: 
                emoji_msg = await bot.send_sticker(chat_id, emoji_id)
            except: 
                pass
        
        await asyncio.sleep(1)
        
        welcome_msg = await bot.send_message(
            chat_id, 
            f"𝐖𝐞𝐥𝐜𝐨𝐦𝐞 𝐁ᴀʙʏ ꨄ {user_mention}...🩷", 
            parse_mode="Markdown"
        )
        
        welcome_emojis = ["🌸", "🏖️", "🍰", "🥂", "🩷"]
        for emoji in welcome_emojis:
            await asyncio.sleep(0.6)
            try:
                await welcome_msg.edit_text(
                    f"𝐖𝐞𝐥𝐜𝐨𝐦𝐞 𝐁ᴀʙʏ ꨄ {user_mention}...{emoji}",
                    parse_mode="Markdown"
                )
            except Exception as e:
                print(f"Edit error: {e}")
                break
        
        if emoji_msg:
            try: 
                await emoji_msg.delete()
            except: 
                pass
        
        await asyncio.sleep(0.2)
        
        starting_emojis = ["🚀", "🌠", "🪶", "🍓", "🤖", "🥡", "🍷", "🍭", "🍨", "🧭", "🫧", "🍫", "🛸"]
        words = ["𝙨", "𝙩", "α", "я", "†", "ι", "и", "g", ".", ".", ".", ".", "."]

        sticker_id = get_random_sticker()
        sticker_msg = None

        for i in range(len(words)):
            await asyncio.sleep(0.08)

            try: 
                await welcome_msg.edit_text(
                    f"**{starting_emojis[i%len(starting_emojis)]} " + "".join(words[:i+1]) + "**", 
                    parse_mode="Markdown"
                )
            except: 
                break

        # Starting khatam - turant sticker bhejo
        await welcome_msg.delete()

        if sticker_id:
            try: 
                sticker_msg = await bot.send_sticker(chat_id, sticker_id)
            except: 
                pass
        
        await asyncio.sleep(3)
        
        video_data = get_random_video()
        final_text = WELCOME_TEXT.replace("{mention}", user_mention)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("◆ ➪ ˹𝜟𝙙𝙙 𝜯𝜣 𝑮𝜞𝜭𝑼𝝆˼ ♪☬", url=f"https://t.me/{(await bot.get_me()).username}?startgroup=true")]])
        
        video_sent = False
        try:
            if video_data and os.path.exists(video_data["path"]):
                await bot.send_video(chat_id, video_data["path"], caption=final_text, parse_mode="Markdown", reply_markup=kb)
                video_sent = True
        except:
            pass
        
        if not video_sent:
            await bot.send_message(chat_id, final_text, parse_mode="Markdown", reply_markup=kb)
        
        if sticker_msg:
            await asyncio.sleep(4)
            try: 
                await sticker_msg.delete()
            except: 
                pass
            
    except Exception as e:
        print(f"Welcome animation error: {e}")
        
# ═══════════════════════════
# 🤖 HANDLERS
# ═══════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    
    if not is_bot_enabled() and user_id != OWNER_ID: return
    if update.effective_chat.type != 'private': return
    
    first_name = user.first_name or "No Name"
    username = user.username or "No Username"
    
    # Check if new user (first time)
    user_started_db = "user_started.json"
    started_users = jload(user_started_db, [])
    
    if user_id not in started_users:
        started_users.append(user_id)
        jsave(user_started_db, started_users)
        
        # Name with username link
        if user.username:
            user_link = f"[{first_name}](https://t.me/{username})"
        else:
            user_link = f"[{first_name}](tg://user?id={user_id})"
        
        # Owner ka real name with username link
        try:
            owner_info = await context.bot.get_chat(OWNER_ID)
            owner_name = owner_info.first_name or "Owner"
            if owner_info.username:
                owner_link = f"[{owner_name}](https://t.me/{owner_info.username})"
            else:
                owner_link = f"[{owner_name}](tg://user?id={OWNER_ID})"
        except:
            owner_link = "[Owner](https://t.me/FathersOfCreater)"
        
        # Send notification to owner with video
        owner_msg = (
            f"👋🏻 ʜᴇʟʟᴏ {owner_link} ♡ ⋆｡°✩\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🗞️ 𝗡𝗲𝘄 𝗨𝘀𝗲𝗿 𝗝𝗼𝗶𝗻𝗲𝗱\n"
            f"🎻 𝗡𝗮𝗺𝗲 ➪ {user_link}\n"
            f"🈲 𝗨𝘀𝗲𝗿 𝗜𝗗 ➪ `{user_id}`\n"
            f"🔎 𝗨𝘀𝗲𝗿𝗻𝗮𝗺𝗲 ➪ {user_link}\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🔹 𝗧𝗼𝘁𝗮𝗹 𝗨𝘀𝗲𝗿𝘀 ➪ {len(started_users)}\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🫧 𝚰𝛈𝒇𝛉𝛄𝒎 𝚩𝛙 ➪ [𝜝𝜣𝜯 𝑭𝜟𝜯𝜢𝜮𝜞](https://t.me/FathersOfCreater)"
        )
        
        try:
            # Send welcome video if available
            video_data = get_random_video()
            if video_data and os.path.exists(video_data["path"]):
                await context.bot.send_video(OWNER_ID, video_data["path"], caption=owner_msg, parse_mode="Markdown")
            else:
                await context.bot.send_message(OWNER_ID, owner_msg, parse_mode="Markdown")
        except:
            pass
    
    if is_bot_enabled() or user_id == OWNER_ID:
        asyncio.create_task(welcome_animation(context.bot, update.effective_chat.id, user_id, first_name))
    else:
        await update.message.reply_text(BOT_DISABLED_MSG, parse_mode="Markdown")
    
async def activate_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in ['group', 'supergroup']: return
    if is_group_activated(chat.id):
        await update.message.reply_text("✅ 𝗔𝗹𝗿𝗲𝗮𝗱𝘆 𝗮𝗰𝘁𝗶𝘃𝗮𝘁𝗲𝗱", parse_mode="Markdown")
    else:
        activate_group(chat.id)
        await update.message.reply_text("✅ 𝗔𝗰𝘁𝗶𝘃𝗮𝘁𝗲𝗱 🚀\n𝗦𝗲𝗻𝗱 𝗜𝗻𝘀𝘁𝗮𝗴𝗿𝗮𝗺 𝗹𝗶𝗻𝗸 𝗻𝗼𝘄", parse_mode="Markdown")

async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    await update.message.reply_text(SETTINGS_TEXT, parse_mode="Markdown", disable_web_page_preview=True)

async def bot_added_to_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    bot_user = await context.bot.get_me()
    
    # Bot disabled hone pe alag message
    if not is_bot_enabled():
        if update.message and update.message.new_chat_members:
            for member in update.message.new_chat_members:
                if member.id == bot_user.id:
                    try: 
                        await update.message.reply_text(BOT_DISABLED_MSG, parse_mode="Markdown")
                    except: pass
                    break
        return
    
    # Check if bot was added via new_chat_members
    if update.message and update.message.new_chat_members:
        for member in update.message.new_chat_members:
            if member.id == bot_user.id:
                kb = InlineKeyboardMarkup([[InlineKeyboardButton("◆ ➪ ˹𝜟𝙙𝙙 𝜯𝜣 𝑮𝜞𝜭𝑼𝝆˼ ♪☬", url=f"https://t.me/{bot_user.username}?startgroup=true")]])
                try:
                    # Try to send welcome video if available
                    video_data = get_random_video()
                    if video_data and os.path.exists(video_data["path"]):
                        await update.message.reply_video(
                            video=open(video_data["path"], 'rb'),
                            caption=GROUP_WELCOME.replace("{chat_title}", chat.title or "Group"),
                            parse_mode="Markdown",
                            reply_markup=kb
                        )
                    else:
                        await update.message.reply_text(
                            GROUP_WELCOME.replace("{chat_title}", chat.title or "Group"),
                            parse_mode="Markdown",
                            reply_markup=kb
                        )
                except: pass
                break

async def disable_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    set_bot_state(False)
    await update.message.reply_text("🚫 𝗗𝗜𝗦𝗔𝗕𝗟𝗘𝗗", parse_mode="Markdown")

async def enable_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    set_bot_state(True)
    await update.message.reply_text("✅ 𝗘𝗡𝗔𝗕𝗟𝗘𝗗", parse_mode="Markdown")

async def add_emoji_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not update.message.reply_to_message or not update.message.reply_to_message.sticker:
        await update.message.reply_text("⎘ 𝗥𝗲𝗽𝗹𝘆 𝘁𝗼 𝗲𝗺𝗼𝗷𝗶"); return
    s, t = add_emoji_db(update.message.reply_to_message.sticker.file_id)
    await update.message.reply_text(f"✅ 𝗔𝗗𝗗𝗘𝗗 ༼{t}༽" if s else "❌ 𝗘𝘅𝗶𝘀𝘁𝘀")

async def remove_emoji_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    try:
        idx = int(update.message.text.split()[1]) - 1
        s, t = remove_emoji_db(idx)
        await update.message.reply_text(f"✅ 𝗥𝗲𝗺𝗼𝘃𝗲𝗱 ༼{t}༽" if s else f"❌ 𝗜𝗻𝘃𝗮𝗹𝗶𝗱 Ｔｏｔａｌ： ༼t༽")
    except: await update.message.reply_text("/removeemoji 🅸🅽🅳🅴🆇")

async def list_emojis_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    emojis = get_emojis()
    if not emojis: await update.message.reply_text("📭 𝗡𝗼 𝗲𝗺𝗼𝗷𝗶𝘀"); return
    text = "🎨 𝗘𝗠𝗢𝗝𝗜𝗦\n" + "\n".join([f"**{i+1}.** `{e[:30]}`" for i, e in enumerate(emojis)])
    await update.message.reply_text(text + f"\n\n🔹 𝗧𝗼𝘁𝗮𝗹 {len(emojis)}", parse_mode="Markdown")

async def add_sticker_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not update.message.reply_to_message or not update.message.reply_to_message.sticker:
        await update.message.reply_text("⎘ 𝗥𝗲𝗽𝗹𝘆 𝘁𝗼 𝘀𝘁𝗶𝗰𝗸𝗲𝗿"); return
    s, t = add_sticker_db(update.message.reply_to_message.sticker.file_id)
    await update.message.reply_text(f"✅ 𝗔𝗗𝗗𝗘𝗗 ༼{t}༽" if s else "❌ 𝗘𝘅𝗶𝘀𝘁𝘀")

async def remove_sticker_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    try:
        idx = int(update.message.text.split()[1]) - 1
        s, t = remove_sticker_db(idx)
        await update.message.reply_text(f"✅ 𝗥𝗲𝗺𝗼𝘃𝗲𝗱 ༼{t}༽" if s else f"❌ 𝗜𝗻𝘃𝗮𝗹𝗶𝗱 Ｔｏｔａｌ： ༼t༽")
    except: await update.message.reply_text("/removesticker 🅘🅝🅓🅔🅧")

async def list_stickers_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    stickers = get_stickers()
    if not stickers: await update.message.reply_text("📭 𝗡𝗼 𝘀𝘁𝗶𝗰𝗸𝗲𝗿𝘀"); return
    text = "❄ 𝗦𝗧𝗜𝗖𝗞𝗘𝗥𝗦\n" + "\n".join([f"**{i+1}.** `{s[:25]}`" for i, s in enumerate(stickers)])
    await update.message.reply_text(text + f"\n\n🔹 𝗧𝗼𝘁𝗮𝗹 {len(stickers)}", parse_mode="Markdown")

async def add_video_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not update.message.reply_to_message or not update.message.reply_to_message.video:
        await update.message.reply_text("⎘ 𝗥𝗲𝗽𝗹𝘆 𝘁𝗼 𝘃𝗶𝗱𝗲𝗼")
        return
    m = await update.message.reply_text("📂𝗔𝗱𝗱𝗶𝗻𝗴 𝗩𝗶𝗱𝗲𝗼...")
    try:
        video_file = update.message.reply_to_message.video
        file = await context.bot.get_file(video_file.file_id)
        fp = os.path.join(VIDEO_DIR, f"w_{int(time.time())}.mp4")
        await file.download_to_drive(fp)
        
        vid, total = add_video_db(fp)
        duration = "Unknown"
        if video_file.duration:
            mins, secs = divmod(video_file.duration, 60)
            duration = f"{mins}m {secs}s"
        
        text = (
            f"✅ 𝐕𝐈𝐃𝐄𝐎 𝐀𝐃𝐃𝐄𝐃 𝐒𝐔𝐂𝐂𝐄𝐒𝐒𝐅𝐔𝐋𝐋𝐘 ✅\n\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"🆔 Ｖｉｄｅｏ ＩＤ ： {vid}\n"
            f"📁 Ｎａｍｅ ： {os.path.basename(fp)[:30]}\n"
            f"📹 Ｔｏｔａｌ Ｖｉｄｅｏｓ ： {total}\n"
            f"⏱️ Ｄｕｒａｔｉｏｎ ： {duration}\n"
            f"━━━━━━━━━━━━━━━━━━━\n\n"
            f"🎲 𝘝𝘪𝘥𝘦𝘰 𝘸𝘪𝘭𝘭 𝘱𝘭𝘢𝘺 𝘳𝘢𝘯𝘥𝘰𝘮𝘭𝘺 𝘰𝘯 𝘸𝘦𝘭𝘤𝘰𝘮𝘦!\n"
            f"📋 /videos ｔｏ ｓｅｅ ａｌｌ ｖｉｄｅｏ"
        )
        await m.edit_text(text)
    except Exception as e:
        await m.edit_text(f"❌ Ｅｒｒｏｒ ： ༼e༽")

async def del_video_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    try:
        vid = int(update.message.text.split()[1])
        s, t = delete_video_db(vid)
        await update.message.reply_text(f"✅ Ｄｅｌｅｔｅｄ！ ༼{t}༽" if s else "❌ Ｎｏｔ ｆｏｕｎｄ！")
    except:
        await update.message.reply_text("Ｕｓｅ ： /delvideo ＩＤ")

async def list_videos_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    vids = get_video_list()
    if not vids:
        await update.message.reply_text("📹 Ｎｏ ｖｉｄｅｏｓ！")
        return
    text = "📹 🇻 🇮 🇩 🇪 🇴 🇸 ：\n" + "\n".join([f"🛸{v['id']} {v['name'][:30]}" for v in vids])
    await update.message.reply_text(text + f"\n\n⎘ 丅ᗝ丅ᗩᒪ ： {len(vids)}")

async def clear_videos_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    n = clear_videos_db()
    await update.message.reply_text(f"🗑️ {n} 𝙫𝙞𝙙𝙚𝙤𝙨 𝙘𝙡𝙚𝙖𝙧𝙚𝙙！")

# ═══════════════ MESSAGE HANDLER ═══════════════

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_type = update.effective_chat.type
    if chat_type in ['group', 'supergroup'] and not is_group_activated(update.effective_chat.id): return
    
    text = update.message.text
    if not text: return
    
    user_id = update.effective_user.id
    
    # Bot disabled check - only owner can use
    if not is_bot_enabled():
        if user_id == OWNER_ID:
            pass  # Owner can use
        else:
            if InstaDownloader.is_instagram_url(text):
                await update.message.reply_text(BOT_DISABLED_MSG, parse_mode="Markdown")
            return
    
    # User-specific audio awaiting check
    user_id = update.effective_user.id
    user_data = context.user_data
    
    if not InstaDownloader.is_instagram_url(text): return
    url = InstaDownloader.extract_url(text)
    if not url:
        await update.message.reply_text("❌ 𝗜𝗻𝘃𝗮𝗹𝗶𝗱 𝗨𝗥𝗟", parse_mode="Markdown")
        return

    # Don't sleep here - process immediately
    asyncio.create_task(process_download(update, context, url))
    return

async def process_download(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
    chat_id = update.effective_chat.id; user_id = update.effective_user.id
    shortcode = InstaDownloader.get_shortcode(url)
    import uuid
    unique_id = str(uuid.uuid4())[:8]
    cache_key = f"{chat_id}_{user_id}_{shortcode}"
    
    sticker_id = get_random_sticker(); sticker_msg = None
    if sticker_id:
        try: sticker_msg = await context.bot.send_sticker(chat_id, sticker_id)
        except: pass
    
    msg = await update.message.reply_text("⏳ 𝗣𝗿𝗼𝗰𝗲𝘀𝘀𝗶𝗻𝗴...", parse_mode="Markdown")
    
    async def delete_sticker():
        if sticker_msg:
            try: await sticker_msg.delete()
            except: pass
    
    # Wait for semaphore (max 2 parallel)
    async with download_semaphore:
        try:
            is_reel = '/reel/' in url or '/tv/' in url
            await msg.edit_text("📥 𝗗𝗼𝘄𝗻𝗹𝗼𝗮𝗱𝗶𝗻𝗴 𝗩𝗶𝗱𝗲𝗼..." if is_reel else "📥 𝗗𝗼𝘄𝗻𝗹𝗼𝗮𝗱𝗶𝗻𝗴 𝗣𝗵𝗼𝘁𝗼...", parse_mode="Markdown")
            task_dir = os.path.join("downloads", f"task_{unique_id}")
            os.makedirs(task_dir, exist_ok=True)
    
            # Temp change DOWNLOAD_DIR for isolated download
            global DOWNLOAD_DIR
            original_dir = DOWNLOAD_DIR
            DOWNLOAD_DIR = task_dir

            import concurrent.futures
            result = None
            for attempt in range(3):
                try:
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(InstaDownloader.download_media, url)
                        result = future.result(timeout=120)
                    if result.get("success"):
                        break
                except concurrent.futures.TimeoutError:
                    time.sleep(3)
                    continue
                except Exception:
                    time.sleep(3)
                    continue

            if result is None:
                result = {"success": False, "error": "🚫 𝐒𝐞𝐫𝐯𝐞𝐫 𝐢𝐬𝐬𝐮𝐞, 𝐩𝐥𝐞𝐚𝐬𝐞 𝐭𝐫𝐲 𝐚𝐠𝐚𝐢𝐧 (˃̣̣̥᷄⌓˂̣̣̥᷅)"}

            DOWNLOAD_DIR = original_dir
            
            if not result.get("success"):
                await msg.edit_text(f"❌ 𝗙𝗮𝗶𝗹𝗲𝗱！ {result.get('error', '')}", parse_mode="Markdown")
                await delete_sticker()
                return
            
            if result.get("is_multiple"):
                photo_paths = result.get("file_paths", [])
                total = len(photo_paths)
                save_photo_cache(cache_key, photo_paths)
                await msg.edit_text(f"🪂 𝗨𝗽𝗹𝗼𝗮𝗱𝗶𝗻𝗴 {total} 𝗣𝗵𝗼𝘁𝗼𝘀...", parse_mode="Markdown")
    
                # Saare photos ek ek karke bhejo - No buttons
                for i, path in enumerate(photo_paths):
                    if os.path.exists(path):
                        with open(path, 'rb') as f:
                            if i == 0:
                                await update.message.reply_photo(photo=f, caption=f"📸 {i+1}/{total}\n\n{CAPTION}", parse_mode="Markdown", reply_to_message_id=update.message.message_id)
                            else:
                                await update.message.reply_photo(photo=f, caption=f"📸 {i+1}/{total}", reply_to_message_id=update.message.message_id)
                        await asyncio.sleep(0.5)  # Thoda gap
    
                await msg.delete()
                if sticker_msg:
                    try:
                        await asyncio.sleep(2)
                        await context.bot.delete_message(chat_id=chat_id, message_id=sticker_msg.message_id)
                    except:
                        pass
                return
            
            fp = result["file_path"]
            if not os.path.exists(fp) or os.path.getsize(fp) < 1000:
                await msg.edit_text("❌ 𝗙𝗶𝗹𝗲 𝗡𝗼𝘁 𝗙𝗼𝘂𝗻𝗱", parse_mode="Markdown")
                await delete_sticker()
                return
            
            size_mb = os.path.getsize(fp) / (1024 * 1024)
            if size_mb > 45:
                await msg.edit_text(f"❌ >𝟱𝟬𝗠𝗕 ({size_mb:.1f}MB)", parse_mode="Markdown")
                InstaDownloader.cleanup(fp)
                await delete_sticker()
                return
            
            is_video = result.get("is_video", False) or fp.endswith(('.mp4', '.mov', '.webm'))
            
            if is_video:
                await msg.edit_text("🪂 𝗨𝗽𝗹𝗼𝗮𝗱𝗶𝗻𝗴 𝗩𝗶𝗱𝗲𝗼 . ˚◞♡ ◟˚ .", parse_mode="Markdown")
                keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(AUDIO_BUTTON_TEXT, callback_data=f"aud_{shortcode}")]])
                try:
                    await context.bot.send_chat_action(chat_id=chat_id, action='upload_video')
                    with open(fp, 'rb') as f:
                        await update.message.reply_video(video=f, caption=CAPTION, parse_mode="Markdown", reply_markup=keyboard, supports_streaming=True, reply_to_message_id=update.message.message_id)
                except Exception as e:
                    await msg.edit_text(f"❌ Upload: {str(e)[:50]}", parse_mode="Markdown")
                    await delete_sticker()
                    InstaDownloader.cleanup(fp)
                    return
            else:
                await msg.edit_text("🪂 𝗨𝗽𝗹𝗼𝗮𝗱𝗶𝗻𝗴 𝗣𝗵𝗼𝘁𝗼♡ ⋆｡°✩", parse_mode="Markdown")
                try:
                    with open(fp, 'rb') as f:
                        await update.message.reply_photo(photo=f, caption=CAPTION, parse_mode="Markdown", reply_to_message_id=update.message.message_id)
                except Exception as e:
                    await msg.edit_text(f"❌ Upload: {str(e)[:50]}", parse_mode="Markdown")
                    await delete_sticker()
                    InstaDownloader.cleanup(fp)
                    return
            
            await msg.delete(); InstaDownloader.cleanup(fp)
            if sticker_msg:
                try:
                    await asyncio.sleep(4)
                    await context.bot.delete_message(chat_id=chat_id, message_id=sticker_msg.message_id)
                except:
                    pass
        except Exception as e:
            try: await msg.edit_text(f"❌ 𝗘𝗿𝗿𝗼𝗿 ： {str(e)[:100]}", parse_mode="Markdown")
            except: pass
            await delete_sticker()
            
async def extract_and_send_audio_direct(query, context, url, audio_name):
    msg = await query.message.reply_text("💽 𝗘𝘅𝘁𝗿𝗮𝗰𝘁𝗶𝗻𝗴 𝗔𝘂𝗱𝗶𝗼...", parse_mode="Markdown")
    try:
        loop = asyncio.get_event_loop()
        try:
            result = await asyncio.wait_for(loop.run_in_executor(None, InstaDownloader.download_media, url), timeout=70)
        except asyncio.TimeoutError:
            os.system('pkill -9 yt-dlp 2>/dev/null')
            await msg.edit_text("❌ 𝐓𝐢𝐦𝐞𝐨𝐮𝐭", parse_mode="Markdown")
            return
        if not result or not result.get("success"):
            await msg.edit_text("❌ 𝗗𝗼𝘄𝗻𝗹𝗼𝗮𝗱 𝗙𝗮𝗶𝗹𝗲𝗱", parse_mode="Markdown")
            return
        vp = result.get("file_path")
        if not vp or not os.path.exists(vp):
            await msg.edit_text("❌ 𝗩𝗶𝗱𝗲𝗼 𝗡𝗼𝘁 𝗙𝗼𝘂𝗻𝗱", parse_mode="Markdown")
            return
        await msg.edit_text("🎻 𝗘𝘅𝘁𝗿𝗮𝗰𝘁𝗶𝗻𝗴 𝗔𝘂𝗱𝗶𝗼...", parse_mode="Markdown")
        ar = InstaDownloader.extract_audio(vp, audio_name)
        if ar.get("success"):
            await msg.edit_text("🎻 𝗦𝗲𝗻𝗱𝗶𝗻𝗴 𝗔𝘂𝗱𝗶𝗼...", parse_mode="Markdown")
            try:
                await context.bot.send_chat_action(chat_id=query.message.chat_id, action='upload_audio')
                with open(ar["file_path"], 'rb') as f:
                    await query.message.reply_audio(audio=f, title=audio_name, performer="✩⋆｡°𝗕𝘆 ➪ 𓆩#ＫＡＲＴＩＫ𓆪 ♡", caption=CAPTION, parse_mode="Markdown", reply_to_message_id=query.message.message_id)
                await msg.delete()
            except Exception as e:
                await msg.edit_text(f"❌ Send: {str(e)[:50]}", parse_mode="Markdown")
            try: os.remove(ar["file_path"])
            except: pass
        else:
            await msg.edit_text(f"❌ {ar.get('error', 'Failed')}", parse_mode="Markdown")
        InstaDownloader.cleanup(vp)
    except Exception as e:
        try: await msg.edit_text(f"❌ Error: {str(e)[:80]}", parse_mode="Markdown")
        except: pass

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data.startswith("aud_"):
        shortcode = query.data[4:]
        video_url = f"https://www.instagram.com/reel/{shortcode}/"
        await query.edit_message_reply_markup(reply_markup=None)
        asyncio.create_task(extract_and_send_audio_direct(query, context, video_url, AUDIO_DEFAULT_NAME))
        return
    elif query.data == "def_audio":
        await query.message.delete()
        url = context.user_data.get('audio_video_url') or context.user_data.get('current_url')
        if url: 
            asyncio.create_task(extract_and_send_audio_direct(query, context, url, AUDIO_DEFAULT_NAME))
        return
    elif query.data.startswith("nxp_"):
        parts = query.data[4:].rsplit("_", 1); cache_key = parts[0]; current_idx = int(parts[1]); next_idx = current_idx + 1
        photo_paths = get_photo_cache(cache_key)
        if photo_paths and next_idx < len(photo_paths) and os.path.exists(photo_paths[next_idx]):
            await query.edit_message_reply_markup(reply_markup=None)
            keyboard = None
            if next_idx + 1 < len(photo_paths):
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"➪ 𝗡𝗲𝘅𝘁 𝗣𝗵𝗼𝘁𝗼 ➤ ({next_idx + 2}/{len(photo_paths)})", callback_data=f"nxp_{cache_key}_{next_idx}")]
                ])
            with open(photo_paths[next_idx], 'rb') as f:
                await query.message.reply_photo(photo=f, caption=f"📸 𝗣𝗵𝗼𝘁𝗼 {next_idx + 1}/{len(photo_paths)}**\n\n{CAPTION}", parse_mode="Markdown", reply_markup=keyboard)
        else:
            await query.answer("No more photos!", show_alert=True)
            
# ═══════════════════════════
# 🚀 MAIN
# ═══════════════════════════

def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
    print("╔══════════════════════════╗")
    print("║  🤖 INSTAGRAM BOT vFINAL║")
    print("║  ✅ FAST & WITH AUDIO   ║")
    print("╚══════════════════════════╝")
    
    os.system('apt-get update -qq && apt-get install -y -qq ffmpeg 2>/dev/null')
    os.system('pip install -U yt-dlp 2>/dev/null')
    
    print(f"🔹 Bot: {'ENABLED' if is_bot_enabled() else 'DISABLED'}")
    print(f"🎨 E:{len(get_emojis())} S:{len(get_stickers())} V:{len(get_video_list())}")
    
    for f in os.listdir(DOWNLOAD_DIR):
        try: os.remove(os.path.join(DOWNLOAD_DIR, f))
        except: pass
    
    app = Application.builder().token(BOT_TOKEN).read_timeout(80000).write_timeout(80000).connect_timeout(80000).pool_timeout(80000).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("activate", activate_cmd))
    app.add_handler(CommandHandler("settings", settings_cmd))
    app.add_handler(CommandHandler("disable", disable_cmd))
    app.add_handler(CommandHandler("enable", enable_cmd))
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
    
    print("✅ Bot Started! FAST & RELIABLE! 🚀")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
