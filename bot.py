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
import yt_dlp
import requests

# ═══════════════════════════
# 🔐 CONFIG
# ═══════════════════════════

BOT_TOKEN = "8518787964:AAHGimBKXfdtrI6UaASGsoI8Aj5Rj_WxF5I"
AUTHORIZED_USERS = [1987818347]
OWNER_ID = 1987818347

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

def jload(f, d=None):
    try:
        if os.path.exists(f):
            with open(f) as fl:
                return json.load(fl)
    except:
        pass
    return d if d is not None else {}

def jsave(f, d):
    with open(f, 'w') as fl:
        json.dump(d, fl, indent=2)

# ═══════════════ EMOJI FUNCTIONS ═══════════════
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
        removed = data["emojis"].pop(index)
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

# ═══════════════ STICKER FUNCTIONS ═══════════════
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
        removed = data["stickers"].pop(index)
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

# ═══════════════ VIDEO FUNCTIONS ═══════════════
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
    if not vids:
        return None
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
            if os.path.exists(v["path"]):
                os.remove(v["path"])
            vids.pop(i)
            jsave(VIDEO_LIST_DB, vids)
            return True, len(vids)
    return False, len(vids)

def clear_videos_db():
    vids = get_video_list()
    for v in vids:
        if os.path.exists(v["path"]):
            os.remove(v["path"])
    jsave(VIDEO_LIST_DB, [])
    return len(vids)

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
            print(f"📸 Downloading Photo: {shortcode}")
            return InstaDownloader._download_photo(shortcode)
    
    @staticmethod
    def _download_video(shortcode, url):
        try:
            instagram_api_url = f"https://www.instagram.com/p/{shortcode}/?__a=1&__d=1"
            
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Referer': 'https://www.instagram.com/',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
            })
            
            if os.path.exists('cookies.txt'):
                cookies = {}
                with open('cookies.txt', 'r') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        parts = line.split('\t')
                        if len(parts) >= 7:
                            cookies[parts[5]] = parts[6]
                for name, value in cookies.items():
                    session.cookies.set(name, value, domain='.instagram.com')
            
            video_url = None
            try:
                resp = session.get(instagram_api_url, timeout=15)
                if resp.status_code == 200:
                    data = resp.json()
                    def extract_video_url(data_dict, depth=0):
                        if depth > 5:
                            return None
                        if isinstance(data_dict, dict):
                            if 'video_url' in data_dict:
                                return data_dict['video_url']
                            if 'video_versions' in data_dict:
                                versions = data_dict['video_versions']
                                if versions:
                                    return versions[0].get('url')
                            for k, v in data_dict.items():
                                result = extract_video_url(v, depth + 1)
                                if result:
                                    return result
                        elif isinstance(data_dict, list):
                            for item in data_dict:
                                result = extract_video_url(item, depth + 1)
                                if result:
                                    return result
                        return None
                    video_url = extract_video_url(data)
            except:
                pass
            
            if not video_url:
                ydl_opts = {
                    'quiet': True,
                    'no_warnings': True,
                    'outtmpl': os.path.join(DOWNLOAD_DIR, f'{shortcode}.%(ext)s'),
                    'format': 'mp4',
                    'retries': 3,
                    'merge_output_format': 'mp4',
                }
                if os.path.exists('cookies.txt'):
                    ydl_opts['cookiefile'] = 'cookies.txt'
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    if info:
                        for f in os.listdir(DOWNLOAD_DIR):
                            if shortcode in f and f.endswith('.mp4'):
                                fp = os.path.join(DOWNLOAD_DIR, f)
                                if os.path.exists(fp) and os.path.getsize(fp) > 5000:
                                    return {"success": True, "file_path": fp, "is_video": True}
                return {"success": False, "error": "File not found"}
            
            if video_url:
                video_url = video_url.replace('\\u0026', '&')
                file_path = os.path.join(DOWNLOAD_DIR, f"{shortcode}.mp4")
                dl_headers = {
                    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15',
                    'Referer': 'https://www.instagram.com/',
                }
                vr = session.get(video_url, headers=dl_headers, stream=True, timeout=60)
                if vr.status_code == 200:
                    with open(file_path, 'wb') as f:
                        for chunk in vr.iter_content(chunk_size=8192):
                            if chunk: f.write(chunk)
                    if os.path.exists(file_path) and os.path.getsize(file_path) > 5000:
                        return {"success": True, "file_path": file_path, "is_video": True}
            
            return {"success": False, "error": "Download failed"}
            
        except Exception as e:
            err = str(e)
            if 'HTTP Error 403' in err or 'HTTP Error 401' in err:
                return {"success": False, "error": "cookies.txt expired!"}
            return {"success": False, "error": f"{err[:80]}"}
    
    @staticmethod
    def _download_photo(shortcode):
        result = InstaDownloader._method_oembed(shortcode)
        if result.get("success"): return result
        result = InstaDownloader._method_ytdlp(shortcode)
        if result.get("success"): return result
        result = InstaDownloader._method_scrape(shortcode)
        if result.get("success"): return result
        return {"success": False, "error": "Photo download failed"}
    
    @staticmethod
    def _method_oembed(shortcode):
        try:
            post_url = f"https://www.instagram.com/p/{shortcode}/"
            api_url = f"https://api.instagram.com/oembed?url={urllib.parse.quote(post_url)}&maxwidth=1080"
            resp = requests.get(api_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
            if resp.status_code != 200:
                return {"success": False}
            data = resp.json()
            image_urls = []
            thumbnail_url = data.get('thumbnail_url', '')
            if thumbnail_url:
                hd_url = re.sub(r'/s\d+x\d+/', '/', thumbnail_url).split('?')[0]
                image_urls.append(hd_url)
            for img_url in image_urls:
                if img_url.startswith('//'): img_url = 'https:' + img_url
                ext = 'jpg'
                file_path = os.path.join(DOWNLOAD_DIR, f"{shortcode}.{ext}")
                r = requests.get(img_url, headers={'User-Agent': 'Mozilla/5.0'}, stream=True, timeout=30)
                if r.status_code == 200:
                    with open(file_path, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=8192):
                            if chunk: f.write(chunk)
                    if os.path.exists(file_path) and os.path.getsize(file_path) > 1000:
                        return {"success": True, "file_path": file_path, "is_video": False}
            return {"success": False}
        except:
            return {"success": False}
    
    @staticmethod
    def _method_ytdlp(shortcode):
        try:
            url = f"https://www.instagram.com/p/{shortcode}/"
            ydl_opts = {'quiet': True, 'no_warnings': True, 'outtmpl': os.path.join(DOWNLOAD_DIR, f'{shortcode}.%(ext)s'), 'format': 'best', 'retries': 3}
            if os.path.exists('cookies.txt'): ydl_opts['cookiefile'] = 'cookies.txt'
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if info:
                    time.sleep(1)
                    for f in os.listdir(DOWNLOAD_DIR):
                        if shortcode in f:
                            fp = os.path.join(DOWNLOAD_DIR, f)
                            if os.path.exists(fp) and os.path.getsize(fp) > 1000 and not f.endswith(('.mp4', '.mov', '.webm')):
                                return {"success": True, "file_path": fp, "is_video": False}
        except:
            pass
        return {"success": False}
    
    @staticmethod
    def _method_scrape(shortcode):
        try:
            session = requests.Session()
            session.headers.update({'User-Agent': 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36'})
            page_url = f"https://www.instagram.com/p/{shortcode}/"
            resp = session.get(page_url, timeout=15)
            if resp.status_code != 200:
                return {"success": False}
            html = resp.text
            image_urls = []
            urls = re.findall(r'"display_url":"([^"]+)"', html)
            for u in urls:
                image_urls.append(u.replace('\\u0026', '&'))
            if not image_urls:
                og = re.findall(r'<meta\s+property="og:image"\s+content="([^"]+)"', html)
                image_urls = list(set(og))
            for img_url in image_urls[:5]:
                try:
                    if '.mp4' in img_url: continue
                    ext = 'jpg'
                    file_path = os.path.join(DOWNLOAD_DIR, f"{shortcode}.{ext}")
                    r = session.get(img_url, headers={'User-Agent': 'Mozilla/5.0'}, stream=True, timeout=30)
                    if r.status_code == 200:
                        with open(file_path, 'wb') as f:
                            for chunk in r.iter_content(chunk_size=8192):
                                if chunk: f.write(chunk)
                        if os.path.exists(file_path) and os.path.getsize(file_path) > 1000:
                            return {"success": True, "file_path": file_path, "is_video": False}
                except:
                    continue
            return {"success": False}
        except:
            return {"success": False}
    
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
            
            probe = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_entries', 'stream=codec_type', '-of', 'csv=p=0', video_path], capture_output=True, text=True, timeout=30)
            if not probe.stdout.strip():
                return {"success": False, "error": "No audio track"}
            
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
# 📝 CAPTION TEMPLATE
# ═══════════════════════════

CAPTION = (
    "𝘋/𝘓 𝘉𝘺 ➪ [˹𝚰𝖓𝖘𝖙𝖆𝖌𝖗𝖆𝖒 ✘ 𝚫𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐞𝐫˼ ♪�҉](https://t.me/Instagram_LinkToVideo_Bot)\n"
    "\n"
    "༼◉𝐂𝛄𝛆𝛂𝛕𝛆𝛄◉༽ 🪽 ➪ [𝜝𝜣𝜯 𝑭𝜟𝜯𝜢𝜮𝜞](https://t.me/FathersOfCreater) �҉"
)

# ═══════════════════════════
# 🎬 WELCOME ANIMATION
# ═══════════════════════════

async def welcome_animation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    first_name = user.first_name or "User"
    user_id = user.id
    user_mention = f"[{first_name}](tg://user?id={user_id})"

    # Step 1: Send random emoji sticker
    emoji_id = get_random_emoji()
    emoji_msg = None
    if emoji_id:
        try:
            emoji_msg = await context.bot.send_sticker(chat_id, emoji_id)
        except:
            pass

    await asyncio.sleep(0.3)

    # Step 2: Welcome animation text
    welcome_emojis = ["🩷", "🌸", "🏖️", "🍰", "🥂"]
    welcome_msg = await context.bot.send_message(
        chat_id,
        f"𝐖𝐞𝐥𝐜𝐨𝐦𝐞 𝐁ᴀʙʏ ꨄ {user_mention}...🩷",
        parse_mode="Markdown"
    )

    for emoji in welcome_emojis:
        await asyncio.sleep(0.3)
        try:
            await welcome_msg.edit_text(f"𝐖𝐞𝐥𝐜𝐨𝐦𝐞 𝐁ᴀʙʏ ꨄ {user_mention}...{emoji}", parse_mode="Markdown")
        except:
            pass

    if emoji_msg:
        try:
            await emoji_msg.delete()
        except:
            pass

    await asyncio.sleep(0.2)

    # Step 3: Starting animation
    starting_emojis = ["🚀", "🌠", "🪶", "🍓", "🤖", "🥡", "🍷", "🍭", "🍨", "🧭", "🫧", "🍫", "🛸"]
    words = ["s", "t", "α", "я", "т", "ι", "и", "g", ".", ".", ".", ".", "."]

    await welcome_msg.edit_text(f"**{starting_emojis[0]}**", parse_mode="Markdown")
    await asyncio.sleep(0.15)

    for i in range(len(words)):
        current_text = "".join(words[:i + 1])
        emoji = starting_emojis[i % len(starting_emojis)]
        try:
            await welcome_msg.edit_text(f"**{emoji} " + current_text + "**", parse_mode="Markdown")
        except:
            pass
        await asyncio.sleep(0.12)

    await asyncio.sleep(0.2)

    try:
        await welcome_msg.delete()
    except:
        pass

    await asyncio.sleep(0.2)

    # Step 4: Send random welcome sticker
    sticker_id = get_random_sticker()
    if sticker_id:
        try:
            await context.bot.send_sticker(chat_id, sticker_id)
        except:
            pass

    await asyncio.sleep(1.5)

    # Step 5: Send random welcome video or final message
    video_data = get_random_video()
    final_text = (
        f"ʜᴇʏ, {user_mention} 👋🏻\n"
        f"ɪ'ᴍ [˹𝚰𝖓𝖘𝖙𝖆𝖌𝖗𝖆𝖒 ✘ 𝚫𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐞𝐫˼ ♪](https://t.me/Instagram_LinkToVideo_Bot),\n\n"
        f"┏━━━━━━━━━━━━━━━━━⧫\n"
        f"┠ ◆ ˹ɪ ʜᴀᴠᴇ sᴘᴇᴄɪᴀʟ ғᴇᴀᴛᴜʀᴇs˼\n"
        f"┠ ◆ ˹ᴀʟʟ-ɪɴ-ᴏɴᴇ ʙᴏᴛ˼\n"
        f"┗━━━━━━━━━━━━━━━━━⧫\n"
        f"┏━━━━━━━━━━━━━━━━━⧫\n"
        f"┠ ◆ ˹ʏᴏᴜ ᴄᴀɴ ᴅᴏᴡɴʟᴏᴀᴅ ɪɴsᴛᴀɢʀᴀᴍ ʀᴇᴇʟs˼\n"
        f"┠ ◆ ˹ʏᴏᴜ ᴄᴀɴ ᴅᴏᴡɴʟᴏᴀᴅ ɪɴsᴛᴀɢʀᴀᴍ ᴘʜᴏᴛᴏs˼\n"
        f"┠ ◆ ˹ʏᴏᴜ ᴄᴀɴ ᴇxᴛʀᴀᴄᴛ ᴀᴜᴅɪᴏ ғʀᴏᴍ ᴠɪᴅᴇᴏs˼\n"
        f"┠ ◆ ˹ʜᴅ ᴠɪᴅᴇᴏ + ᴏʀɪɢɪɴᴀʟ ᴀᴜᴅɪᴏ sᴜᴘᴘᴏʀᴛ˼\n"
        f"┠ ◆ ˹ᴍᴜʟᴛɪᴘʟᴇ ᴘʜᴏᴛᴏ ᴅᴏᴡɴʟᴏᴀᴅ sᴜᴘᴘᴏʀᴛ˼\n"
        f"┠ ◆ ˹ɢʀᴏᴜᴘ sᴜᴘᴘᴏʀᴛ ᴀᴠᴀɪʟᴀʙʟᴇ˼\n"
        f"┗━━━━━━━━━━━━━━━━━⧫\n\n"
        f"⚡ ˹ᴸⁱⁿᵏ ᴮʰᵉʲᵒ → ⱽⁱᵈᵉᵒ ᴾᵃᵒ → ᴬᵘᵈⁱᵒ ᴺᵃᵃᵐ ᴮᵃᵗᵃᵒ → ᴬᵘᵈⁱᵒ ᴾᵃᵒ˼\n\n"
        f"⧫━━━━━✦◆ ◇ ◆ ◇ ◆ ◇✦━━━━━⧫\n"
        f"๏ ˹ᴄʟɪᴄᴋ ᴏɴ ᴛʜᴇ ᴀᴅᴅ ᴛᴏ ɢʀᴏᴜᴘ ʙᴜᴛᴛᴏɴ ʙᴇʟᴏᴡ ᴛᴏ ᴀᴅᴅ ᴛʜɪs ʙᴏᴛ ɪɴ ʏᴏᴜʀ ɢʀᴏᴜᴘ ᴀɴᴅ ᴇɴᴊᴏʏ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ ᴛʜᴇʀᴇ ᴛᴏᴏ˼\n\n"
        f"🫧 ˹ᴅᴇᴠᴇʟᴏᴩᴇʀ˼ 🪽 ➪ [𝜝𝜣𝜯 𝑭𝜟𝜯𝜢𝜮𝜞](https://t.me/FathersOfCreater) ✔︎"
    )

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("◆ ➪ ˹𝜟𝙙𝙙 𝜯𝜣 𝑮𝜞𝜭𝑼𝝆˼ ♪☬", url=f"https://t.me/{(await context.bot.get_me()).username}?startgroup=true")]
    ])

    if video_data and os.path.exists(video_data["path"]):
        await context.bot.send_video(chat_id, video_data["path"], caption=final_text, parse_mode="Markdown", reply_markup=kb)
    else:
        await context.bot.send_message(chat_id, final_text, parse_mode="Markdown", reply_markup=kb)

# ═══════════════════════════
# 🤖 COMMANDS
# ═══════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.id
    if user not in AUTHORIZED_USERS:
        return
    await welcome_animation(update, context)

# ═══════════════ /addemoji ═══════════════
async def add_emoji_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    
    if not update.message.reply_to_message or not update.message.reply_to_message.sticker:
        await update.message.reply_text(
            "⎘ **ADD EMOJI**\n\nReply to a premium emoji sticker with `/addemoji`",
            parse_mode="Markdown"
        )
        return
    
    emoji_id = update.message.reply_to_message.sticker.file_id
    success, total = add_emoji_db(emoji_id)
    
    if success:
        await update.message.reply_text(f"✅ **EMOJI ADDED!** 🎉\n🔹 Total Emojis: {total}")
    else:
        await update.message.reply_text("❌ This emoji is already in the list!")

# ═══════════════ /removeemoji ═══════════════
async def remove_emoji_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    
    parts = update.message.text.split()
    if len(parts) != 2:
        await update.message.reply_text("Use: `/removeemoji index`\nGet index from `/listemojis`", parse_mode="Markdown")
        return
    
    try:
        index = int(parts[1]) - 1
        success, total = remove_emoji_db(index)
        if success:
            await update.message.reply_text(f"✅ **EMOJI REMOVED!**\n🔹 Remaining: {total}")
        else:
            await update.message.reply_text(f"❌ Invalid index! Total emojis: {total}")
    except:
        await update.message.reply_text("❌ Invalid index!")

# ═══════════════ /listemojis ═══════════════
async def list_emojis_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    
    emojis = get_emojis()
    if not emojis:
        await update.message.reply_text("📭 No emojis added yet!")
        return
    
    text = "⌘ **EMOJI LIST**\n\n"
    for i, emoji_id in enumerate(emojis, 1):
        text += f"**{i}.** `{emoji_id[:30]}...`\n"
    text += f"\n🔹 Total: {len(emojis)}"
    await update.message.reply_text(text, parse_mode="Markdown")

# ═══════════════ /addsticker ═══════════════
async def add_sticker_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    
    if not update.message.reply_to_message or not update.message.reply_to_message.sticker:
        await update.message.reply_text(
            "⎘ **ADD STICKER**\n\nReply to a sticker with `/addsticker`",
            parse_mode="Markdown"
        )
        return
    
    sticker_id = update.message.reply_to_message.sticker.file_id
    success, total = add_sticker_db(sticker_id)
    
    if success:
        await update.message.reply_text(f"✅ **STICKER ADDED!** 🎉\n🔹 Total Stickers: {total}")
    else:
        await update.message.reply_text("❌ This sticker is already in the list!")

# ═══════════════ /removesticker ═══════════════
async def remove_sticker_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    
    parts = update.message.text.split()
    if len(parts) != 2:
        await update.message.reply_text("Use: `/removesticker index`\nGet index from `/liststickers`", parse_mode="Markdown")
        return
    
    try:
        index = int(parts[1]) - 1
        success, total = remove_sticker_db(index)
        if success:
            await update.message.reply_text(f"✅ **STICKER REMOVED!**\n🔹 Remaining: {total}")
        else:
            await update.message.reply_text(f"❌ Invalid index! Total stickers: {total}")
    except:
        await update.message.reply_text("❌ Invalid index!")

# ═══════════════ /liststickers ═══════════════
async def list_stickers_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    
    stickers = get_stickers()
    if not stickers:
        await update.message.reply_text("📭 No stickers added yet!")
        return
    
    text = "⌘ **STICKER LIST**\n\n"
    for i, sticker_id in enumerate(stickers, 1):
        text += f"**{i}.** `{sticker_id[:25]}...`\n"
    text += f"\n🔹 Total: {len(stickers)}"
    await update.message.reply_text(text, parse_mode="Markdown")

# ═══════════════ /addvideo ═══════════════
async def add_video_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    
    if not update.message.reply_to_message or not update.message.reply_to_message.video:
        await update.message.reply_text(
            "⎘ **ADD VIDEO**\n\nReply to a video with `/addvideo`",
            parse_mode="Markdown"
        )
        return
    
    msg = await update.message.reply_text("📂 Adding Video...")
    try:
        file = await update.message.reply_to_message.video.get_file()
        file_name = f"welcome_{int(time.time())}.mp4"
        file_path = os.path.join(VIDEO_DIR, file_name)
        await file.download_to_drive(file_path)
        
        vid, total = add_video_db(file_path)
        await msg.edit_text(f"✅ **VIDEO ADDED!** 🎉\n🆔 ID: {vid}\n📹 Total Videos: {total}")
    except Exception as e:
        await msg.edit_text(f"❌ Error: {e}")

# ═══════════════ /delvideo ═══════════════
async def del_video_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    
    parts = update.message.text.split()
    if len(parts) != 2:
        await update.message.reply_text("Use: `/delvideo ID`", parse_mode="Markdown")
        return
    
    try:
        vid = int(parts[1])
        success, total = delete_video_db(vid)
        if success:
            await update.message.reply_text(f"✅ Video #{vid} deleted!\n📹 Remaining: {total}")
        else:
            await update.message.reply_text(f"❌ Not found!")
    except:
        await update.message.reply_text("❌ Invalid ID!")

# ═══════════════ /videos ═══════════════
async def list_videos_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    
    vids = get_video_list()
    if not vids:
        await update.message.reply_text("📹 No videos added yet!")
        return
    
    text = "📹 **VIDEO LIST**\n\n"
    for v in vids:
        text += f"#{v['id']} {v['name'][:30]}\n"
    text += f"\n🔹 Total: {len(vids)}"
    await update.message.reply_text(text, parse_mode="Markdown")

# ═══════════════ /clearvideos ═══════════════
async def clear_videos_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        return
    
    n = clear_videos_db()
    await update.message.reply_text(f"🗑️ {n} videos cleared!")

# ═══════════════ MESSAGE HANDLER ═══════════════
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
        await update.message.reply_text("❌ Could not extract URL")
        return
    
    context.user_data['current_url'] = url
    
    msg = await update.message.reply_text("⏳ **Processing...**", parse_mode="Markdown")
    
    try:
        is_reel = '/reel/' in url or '/tv/' in url
        await msg.edit_text("📥 **Downloading...**", parse_mode="Markdown")
        
        result = InstaDownloader.download_media(url)
        
        if not result.get("success"):
            await msg.edit_text(f"❌ **Failed!**\n\n{result.get('error', 'Unknown')}", parse_mode="Markdown")
            return
        
        fp = result["file_path"]
        if not os.path.exists(fp) or os.path.getsize(fp) < 1000:
            await msg.edit_text("❌ File not found")
            return
        
        size_mb = os.path.getsize(fp) / (1024 * 1024)
        if size_mb > 50:
            await msg.edit_text(f"❌ File >50MB ({size_mb:.1f}MB)")
            InstaDownloader.cleanup(fp)
            return
        
        is_video = result.get("is_video", False) or fp.endswith(('.mp4', '.mov', '.webm'))
        
        if is_video:
            await msg.edit_text("📤 **Uploading Video...**", parse_mode="Markdown")
            keyboard = [[InlineKeyboardButton("🎵 Download Audio", callback_data="get_audio")]]
            
            with open(fp, 'rb') as f:
                await update.message.reply_video(
                    video=f,
                    caption=CAPTION,
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    supports_streaming=True
                )
        else:
            await msg.edit_text("📤 **Uploading Photo...**", parse_mode="Markdown")
            with open(fp, 'rb') as f:
                await update.message.reply_photo(
                    photo=f,
                    caption=CAPTION,
                    parse_mode="Markdown"
                )
        await msg.delete()
        InstaDownloader.cleanup(fp)
        
    except Exception as e:
        await msg.edit_text(f"❌ **Error:** {str(e)[:100]}", parse_mode="Markdown")
        for f in os.listdir(DOWNLOAD_DIR):
            try: os.remove(os.path.join(DOWNLOAD_DIR, f))
            except: pass

async def extract_and_send_audio(update, context, url, audio_name):
    status_msg = await update.message.reply_text(f"🎵 **Extracting: {audio_name}...**", parse_mode="Markdown")
    
    try:
        result = InstaDownloader.download_media(url)
        if not result.get("success"):
            await status_msg.edit_text("❌ Video download failed")
            return
        
        vp = result["file_path"]
        audio_result = InstaDownloader.extract_audio(vp, audio_name)
        
        if audio_result.get("success"):
            ap = audio_result["file_path"]
            await status_msg.edit_text("📤 **Uploading Audio...**", parse_mode="Markdown")
            
            with open(ap, 'rb') as f:
                await update.message.reply_audio(
                    audio=f, title=audio_name, performer="Instagram",
                    caption=CAPTION, parse_mode="Markdown"
                )
            
            await status_msg.edit_text(f"✅ **{audio_name} sent!** 🎵")
            try: os.remove(ap)
            except: pass
        else:
            await status_msg.edit_text(f"❌ {audio_result.get('error')}")
        
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
    
    print("╔══════════════════════════╗")
    print("║  🤖 INSTAGRAM BOT       ║")
    print("║  🎬 Welcome Animation   ║")
    print("╚══════════════════════════╝")
    
    ffmpeg = shutil.which('ffmpeg')
    if ffmpeg:
        print(f"✅ FFmpeg: {ffmpeg}")
    else:
        print("⚠️ Installing FFmpeg...")
        os.system('apt-get update && apt-get install ffmpeg -y 2>/dev/null')
    
    if os.path.exists('cookies.txt'):
        print(f"✅ cookies.txt found")
    else:
        print("ℹ️ cookies.txt not found")
    
    for f in os.listdir(DOWNLOAD_DIR):
        try: os.remove(os.path.join(DOWNLOAD_DIR, f))
        except: pass
    
    print(f"🎨 Emojis: {len(get_emojis())} | Stickers: {len(get_stickers())} | Videos: {len(get_video_list())}")
    print("✅ Bot Started! 🚀")
    
    app = Application.builder().token(BOT_TOKEN).build()
    
    # Commands
    app.add_handler(CommandHandler("start", start))
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
    
    # Message handler
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    app.run_polling()

if __name__ == "__main__":
    main()
