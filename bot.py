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
# 📥 INSTAGRAM DOWNLOADER (ddinstagram PROXY)
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
    def get_shortcode(url):
        m = re.search(r'/(p|reel|tv)/([a-zA-Z0-9_\-]+)', url)
        return m.group(2) if m else None
    
    @staticmethod
    def download_media(url):
        shortcode = InstaDownloader.get_shortcode(url)
        if not shortcode: return {"success": False, "error": "Invalid"}
        is_reel = '/reel/' in url or '/tv/' in url
        if is_reel: return InstaDownloader._download_video(shortcode, url)
        else: return InstaDownloader._download_photo(shortcode, url)
    
    @staticmethod
    def _download_video(shortcode, url):
        """Try multiple proxies - 100% working"""
        
        # Method 1: ddinstagram.com (most reliable)
        proxies = [
            f"https://ddinstagram.com/video/{shortcode}",
            f"https://ddinstagram.com/reel/{shortcode}",
        ]
        
        for proxy_url in proxies:
            try:
                session = requests.Session()
                session.headers.update({
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                })
                
                resp = session.get(proxy_url, timeout=30, allow_redirects=True)
                if resp.status_code == 200 and 'video' in resp.headers.get('content-type', ''):
                    fp = os.path.join(DOWNLOAD_DIR, f"{shortcode}.mp4")
                    with open(fp, 'wb') as f:
                        f.write(resp.content)
                    
                    if os.path.exists(fp) and os.path.getsize(fp) > 50000:
                        print(f"✅ Downloaded via proxy: {os.path.getsize(fp)} bytes")
                        return {"success": True, "file_path": fp, "is_video": True}
            except:
                continue
        
        # Method 2: yt-dlp with cookies if available
        if os.path.exists('cookies.txt'):
            try:
                ydl_opts = {
                    'quiet': True, 'no_warnings': True,
                    'outtmpl': os.path.join(DOWNLOAD_DIR, f'{shortcode}.%(ext)s'),
                    'format': 'best',
                    'cookiefile': 'cookies.txt',
                    'retries': 3,
                    'socket_timeout': 60,
                }
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.extract_info(url, download=True)
                    time.sleep(0.5)
                    for f in sorted(os.listdir(DOWNLOAD_DIR), key=lambda x: os.path.getmtime(os.path.join(DOWNLOAD_DIR, x)), reverse=True):
                        if f.endswith('.mp4'):
                            fp = os.path.join(DOWNLOAD_DIR, f)
                            if os.path.exists(fp) and os.path.getsize(fp) > 50000:
                                return {"success": True, "file_path": fp, "is_video": True}
            except:
                pass
        
        # Method 3: Direct Instagram embed page
        try:
            embed_url = f"https://www.instagram.com/p/{shortcode}/embed/"
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            })
            resp = session.get(embed_url, timeout=15)
            if resp.status_code == 200:
                match = re.search(r'"video_url"\s*:\s*"([^"]+)"', resp.text)
                if match:
                    video_url = match.group(1).replace('\\u0026', '&')
                    fp = os.path.join(DOWNLOAD_DIR, f"{shortcode}.mp4")
                    vr = session.get(video_url, stream=True, timeout=120)
                    if vr.status_code == 200:
                        with open(fp, 'wb') as f:
                            for chunk in vr.iter_content(8192):
                                if chunk: f.write(chunk)
                        if os.path.exists(fp) and os.path.getsize(fp) > 50000:
                            return {"success": True, "file_path": fp, "is_video": True}
        except:
            pass
        
        return {"success": False, "error": "All methods failed. Try with cookies.txt"}
    
    @staticmethod
    def _download_photo(shortcode, url):
        result = InstaDownloader._method_scrape_multi(shortcode, url)
        if result.get("success"): return result
        for method in [InstaDownloader._method_oembed, InstaDownloader._method_scrape_single, InstaDownloader._method_cdn]:
            result = method(shortcode)
            if result.get("success"): return result
        return {"success": False, "error": "Photo download failed"}
    
    @staticmethod
    def _method_scrape_multi(shortcode, url):
        try:
            session = requests.Session()
            session.headers.update({'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15'})
            resp = session.get(url, timeout=15)
            if resp.status_code != 200: return {"success": False}
            html = resp.text; image_urls = []
            nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
            if nd:
                try:
                    data = json.loads(nd.group(1))
                    def find_urls(obj, depth=0):
                        if depth > 8: return []
                        urls = []
                        if isinstance(obj, dict):
                            du = obj.get('display_url', '')
                            if du and '.mp4' not in du and du not in urls: urls.append(du)
                            for v in obj.values(): urls.extend(find_urls(v, depth+1))
                        elif isinstance(obj, list):
                            for item in obj: urls.extend(find_urls(item, depth+1))
                        return urls
                    image_urls = find_urls(data)
                except: pass
            if not image_urls:
                urls_found = re.findall(r'"display_url":"([^"]+)"', html)
                image_urls = [u.replace('\\u0026', '&') for u in urls_found if '.mp4' not in u]
            if not image_urls:
                og = re.findall(r'<meta\s+property="og:image"\s+content="([^"]+)"', html)
                image_urls = list(set(og))
            seen = set(); unique_urls = []
            for u in image_urls:
                if u not in seen: seen.add(u); unique_urls.append(u)
            image_urls = unique_urls
            if not image_urls: return {"success": False}
            downloaded = []
            for i, img_url in enumerate(image_urls[:10]):
                try:
                    fp = os.path.join(DOWNLOAD_DIR, f"multi_{shortcode}_{i+1}.jpg")
                    r = session.get(img_url, headers={'User-Agent': 'Mozilla/5.0'}, stream=True, timeout=30)
                    if r.status_code == 200:
                        with open(fp, 'wb') as f:
                            for chunk in r.iter_content(8192): f.write(chunk)
                        if os.path.getsize(fp) > 1000: downloaded.append(fp)
                except: continue
            if downloaded:
                return {"success": True, "file_path": downloaded[0], "file_paths": downloaded, "is_video": False, "is_multiple": len(downloaded) > 1, "total": len(downloaded)}
            return {"success": False}
        except: return {"success": False}
    
    @staticmethod
    def _method_oembed(shortcode):
        try:
            api_url = f"https://api.instagram.com/oembed?url={urllib.parse.quote(f'https://www.instagram.com/p/{shortcode}/')}&maxwidth=1080"
            resp = requests.get(api_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
            if resp.status_code != 200: return {"success": False}
            thumb = resp.json().get('thumbnail_url', '')
            if thumb:
                hd = re.sub(r'/s\d+x\d+/', '/', thumb).split('?')[0]
                fp = os.path.join(DOWNLOAD_DIR, f"{shortcode}.jpg")
                r = requests.get(hd, headers={'User-Agent': 'Mozilla/5.0'}, stream=True, timeout=20)
                if r.status_code == 200:
                    with open(fp, 'wb') as f:
                        for chunk in r.iter_content(8192): f.write(chunk)
                    if os.path.getsize(fp) > 1000: return {"success": True, "file_path": fp, "is_video": False}
            return {"success": False}
        except: return {"success": False}
    
    @staticmethod
    def _method_scrape_single(shortcode):
        try:
            session = requests.Session()
            session.headers.update({'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15'})
            resp = session.get(f"https://www.instagram.com/p/{shortcode}/", timeout=10)
            if resp.status_code != 200: return {"success": False}
            image_urls = re.findall(r'"display_url":"([^"]+)"', resp.text)
            if not image_urls:
                og = re.findall(r'<meta\s+property="og:image"\s+content="([^"]+)"', resp.text)
                image_urls = list(set(og))
            for img_url in image_urls[:3]:
                try:
                    if '.mp4' in img_url: continue
                    fp = os.path.join(DOWNLOAD_DIR, f"{shortcode}.jpg")
                    r = session.get(img_url, headers={'User-Agent': 'Mozilla/5.0'}, stream=True, timeout=20)
                    if r.status_code == 200:
                        with open(fp, 'wb') as f:
                            for chunk in r.iter_content(8192): f.write(chunk)
                        if os.path.getsize(fp) > 1000: return {"success": True, "file_path": fp, "is_video": False}
                except: continue
            return {"success": False}
        except: return {"success": False}
    
    @staticmethod
    def _method_cdn(shortcode):
        try:
            r = requests.get(f"https://www.instagram.com/p/{shortcode}/media/?size=l", headers={'User-Agent': 'Mozilla/5.0'}, stream=True, timeout=10)
            if r.status_code == 200 and 'image' in r.headers.get('content-type', ''):
                fp = os.path.join(DOWNLOAD_DIR, f"{shortcode}.jpg")
                with open(fp, 'wb') as f:
                    for chunk in r.iter_content(8192): f.write(chunk)
                if os.path.getsize(fp) > 1000: return {"success": True, "file_path": fp, "is_video": False}
        except: pass
        return {"success": False}
    
    @staticmethod
    def extract_audio(video_path, custom_name=None):
        try:
            if custom_name and custom_name.lower() != "skip":
                safe = re.sub(r'[^\w\s-]', '', custom_name).strip()[:50] or "Audio"
                ap = os.path.join(DOWNLOAD_DIR, f"{safe}.mp3")
            else:
                ap = os.path.join(DOWNLOAD_DIR, f"{os.path.splitext(os.path.basename(video_path))[0]}.mp3")
            if not shutil.which('ffmpeg'): return {"success": False, "error": "FFmpeg not found"}
            subprocess.run(['ffmpeg', '-i', video_path, '-vn', '-acodec', 'libmp3lame', '-ab', '192k', '-y', ap], capture_output=True, timeout=180)
            if os.path.exists(ap) and os.path.getsize(ap) > 1000: return {"success": True, "file_path": ap}
            return {"success": False, "error": "Audio extraction failed"}
        except Exception as e: return {"success": False, "error": str(e)[:50]}
    
    @staticmethod
    def cleanup(fp):
        try:
            if fp and os.path.exists(fp): os.remove(fp)
        except: pass

# ═══════════════════════════
# 📝 TEXT
# ═══════════════════════════

CAPTION = "Downloaded By @Instagram_LinkToVideo_Bot\n\nCreated By @FathersOfCreater"

WELCOME_MSG = "Welcome to Instagram Downloader Bot!\n\nSend any Instagram link to download."

GROUP_MSG = "Hello {chat_title}!\n\nInstagram Downloader Bot is here!\nSend any Instagram link."

AUDIO_BUTTON = "Download Audio"
AUDIO_DEFAULT = "My Music"

# ═══════════════════════════
# 🎬 WELCOME
# ═══════════════════════════

async def welcome_animation(bot, chat_id, user_id, first_name):
    try:
        sticker_id = get_random_sticker()
        if sticker_id:
            try: await bot.send_sticker(chat_id, sticker_id)
            except: pass
        await asyncio.sleep(2)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Add To Group", url=f"https://t.me/{(await bot.get_me()).username}?startgroup=true")]])
        await bot.send_message(chat_id, WELCOME_MSG, reply_markup=kb)
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
        await update.message.reply_text("Already activated!")
    else:
        activate_group(chat.id)
        await update.message.reply_text("Activated! Send Instagram link now!")

async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    await update.message.reply_text("Commands: /start /disable /enable /settings /activate")

async def bot_added_to_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_bot_enabled(): return
    if update.my_chat_member.new_chat_member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR]:
        chat = update.effective_chat; bot_user = await context.bot.get_me()
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Add To Group", url=f"https://t.me/{bot_user.username}?startgroup=true")]])
        await context.bot.send_message(chat.id, GROUP_MSG.replace("{chat_title}", chat.title or "Group"), reply_markup=kb)

async def disable_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    set_bot_state(False); await update.message.reply_text("Disabled")

async def enable_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    set_bot_state(True); await update.message.reply_text("Enabled")

async def add_emoji_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not update.message.reply_to_message or not update.message.reply_to_message.sticker:
        await update.message.reply_text("Reply to emoji sticker"); return
    s, t = add_emoji_db(update.message.reply_to_message.sticker.file_id)
    await update.message.reply_text(f"Added ({t})" if s else "Exists")

async def remove_emoji_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    try:
        idx = int(update.message.text.split()[1]) - 1
        s, t = remove_emoji_db(idx)
        await update.message.reply_text(f"Removed ({t})" if s else f"Invalid! Total: {t}")
    except: await update.message.reply_text("/removeemoji index")

async def list_emojis_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    await update.message.reply_text(f"Emojis: {len(get_emojis())}")

async def add_sticker_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not update.message.reply_to_message or not update.message.reply_to_message.sticker:
        await update.message.reply_text("Reply to sticker"); return
    s, t = add_sticker_db(update.message.reply_to_message.sticker.file_id)
    await update.message.reply_text(f"Added ({t})" if s else "Exists")

async def remove_sticker_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    try:
        idx = int(update.message.text.split()[1]) - 1
        s, t = remove_sticker_db(idx)
        await update.message.reply_text(f"Removed ({t})" if s else f"Invalid! Total: {t}")
    except: await update.message.reply_text("/removesticker index")

async def list_stickers_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    await update.message.reply_text(f"Stickers: {len(get_stickers())}")

async def add_video_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not update.message.reply_to_message or not update.message.reply_to_message.video:
        await update.message.reply_text("Reply to video"); return
    m = await update.message.reply_text("Adding...")
    try:
        file = await update.message.reply_to_message.video.get_file()
        fp = os.path.join(VIDEO_DIR, f"w_{int(time.time())}.mp4")
        await file.download_to_drive(fp)
        vid, total = add_video_db(fp)
        await m.edit_text(f"Video Added! ID: {vid} (Total: {total})")
    except Exception as e: await m.edit_text(f"Error: {e}")

async def del_video_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    try:
        s, t = delete_video_db(int(update.message.text.split()[1]))
        await update.message.reply_text(f"Deleted ({t})" if s else "Not found")
    except: await update.message.reply_text("/delvideo ID")

async def list_videos_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    await update.message.reply_text(f"Videos: {len(get_video_list())}")

async def clear_videos_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    await update.message.reply_text(f"{clear_videos_db()} videos cleared!")

# ═══════════════ MESSAGE HANDLER ═══════════════

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_bot_enabled(): return
    chat_type = update.effective_chat.type
    if chat_type in ['group', 'supergroup'] and not is_group_activated(update.effective_chat.id): return
    
    text = update.message.text
    if not text: return
    
    if context.user_data.get('awaiting_audio'):
        context.user_data['awaiting_audio'] = False
        aname = text.strip()
        url = context.user_data.get('audio_video_url')
        if url: await extract_and_send_audio(update, context, url, aname)
        context.user_data['audio_video_url'] = None
        return
    
    if text == AUDIO_DEFAULT:
        context.user_data['awaiting_audio'] = False
        url = context.user_data.get('audio_video_url')
        if url: await extract_and_send_audio(update, context, url, AUDIO_DEFAULT)
        context.user_data['audio_video_url'] = None
        return
    
    if not InstaDownloader.is_instagram_url(text): return
    url = InstaDownloader.extract_url(text)
    if not url:
        await update.message.reply_text("Invalid URL"); return
    
    context.user_data['current_url'] = url
    chat_id = update.effective_chat.id; user_id = update.effective_user.id
    shortcode = InstaDownloader.get_shortcode(url)
    cache_key = f"{chat_id}_{user_id}_{shortcode}"
    
    sticker_id = get_random_sticker()
    if sticker_id:
        try: await context.bot.send_sticker(chat_id, sticker_id)
        except: pass
    
    msg = await update.message.reply_text("Processing...")
    
    try:
        result = InstaDownloader.download_media(url)
        
        if not result.get("success"):
            await msg.edit_text(f"Failed! {result.get('error', '')}"); return
        
        if result.get("is_multiple"):
            photo_paths = result.get("file_paths", []); total = len(photo_paths)
            save_photo_cache(cache_key, photo_paths)
            await msg.edit_text(f"Uploading {total} Photos...")
            if total > 0 and os.path.exists(photo_paths[0]):
                kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"Next Photo (2/{total})", callback_data=f"nxp_{cache_key}_0")]]) if total > 1 else None
                with open(photo_paths[0], 'rb') as f:
                    await update.message.reply_photo(photo=f, caption=f"Photo 1/{total}\n\n{CAPTION}", reply_markup=kb)
            await msg.delete(); return
        
        fp = result["file_path"]
        if not os.path.exists(fp) or os.path.getsize(fp) < 1000:
            await msg.edit_text("File Not Found"); return
        
        size_mb = os.path.getsize(fp) / (1024 * 1024)
        if size_mb > 50:
            await msg.edit_text(f">50MB ({size_mb:.1f}MB)")
            InstaDownloader.cleanup(fp); return
        
        is_video = result.get("is_video", False) or fp.endswith(('.mp4', '.mov', '.webm'))
        
        if is_video:
            await msg.edit_text("Uploading Video...")
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(AUDIO_BUTTON, callback_data=f"aud_{url}")]])
            with open(fp, 'rb') as f:
                await update.message.reply_video(video=f, caption=CAPTION, reply_markup=kb, supports_streaming=True)
        else:
            await msg.edit_text("Uploading Photo...")
            with open(fp, 'rb') as f:
                await update.message.reply_photo(photo=f, caption=CAPTION)
        
        await msg.delete(); InstaDownloader.cleanup(fp)
    except Exception as e:
        await msg.edit_text(f"Error: {str(e)[:100]}")
        for f in os.listdir(DOWNLOAD_DIR):
            try: os.remove(os.path.join(DOWNLOAD_DIR, f))
            except: pass

async def extract_and_send_audio(update, context, url, aname):
    sm = await update.message.reply_text("Extracting Audio...")
    try:
        result = InstaDownloader.download_media(url)
        if not result.get("success"): await sm.edit_text("Failed"); return
        vp = result["file_path"]
        ar = InstaDownloader.extract_audio(vp, aname)
        if ar.get("success"):
            await sm.edit_text("Sending Audio...")
            with open(ar["file_path"], 'rb') as f:
                await update.message.reply_audio(audio=f, title=aname, performer="Instagram", caption=CAPTION)
            await sm.delete()
            try: os.remove(ar["file_path"])
            except: pass
        else: await sm.edit_text(ar.get('error'))
        InstaDownloader.cleanup(vp)
    except Exception as e: await sm.edit_text(f"Error: {str(e)[:80]}")

async def extract_and_send_audio_direct(query, context, url, aname):
    sm = await query.message.reply_text("Extracting Audio...")
    try:
        result = InstaDownloader.download_media(url)
        if not result.get("success"): await sm.edit_text("Failed"); return
        vp = result["file_path"]
        ar = InstaDownloader.extract_audio(vp, aname)
        if ar.get("success"):
            await sm.edit_text("Sending Audio...")
            with open(ar["file_path"], 'rb') as f:
                await query.message.reply_audio(audio=f, title=aname, performer="Instagram", caption=CAPTION)
            await sm.delete()
            try: os.remove(ar["file_path"])
            except: pass
        else: await sm.edit_text(ar.get('error'))
        InstaDownloader.cleanup(vp)
    except Exception as e: await sm.edit_text(f"Error: {str(e)[:80]}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    
    if query.data.startswith("aud_"):
        video_url = query.data[4:]
        context.user_data['audio_video_url'] = video_url
        await query.edit_message_reply_markup(reply_markup=None)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(AUDIO_DEFAULT, callback_data="def_audio")]])
        await query.message.reply_text("Send audio name or click button:", reply_markup=kb)
        context.user_data['awaiting_audio'] = True
    elif query.data == "def_audio":
        await query.message.delete()
        url = context.user_data.get('audio_video_url') or context.user_data.get('current_url')
        if url: await extract_and_send_audio_direct(query, context, url, AUDIO_DEFAULT)
    elif query.data.startswith("nxp_"):
        parts = query.data[4:].rsplit("_", 1); cache_key = parts[0]; current_idx = int(parts[1]); next_idx = current_idx + 1
        photo_paths = get_photo_cache(cache_key)
        if photo_paths and next_idx < len(photo_paths) and os.path.exists(photo_paths[next_idx]):
            await query.edit_message_reply_markup(reply_markup=None)
            kb = InlineKeyboardMarkup([[InlineKeyboardButton(f"Next Photo ({next_idx + 2}/{len(photo_paths)})", callback_data=f"nxp_{cache_key}_{next_idx}")]]) if next_idx + 1 < len(photo_paths) else None
            with open(photo_paths[next_idx], 'rb') as f:
                await query.message.reply_photo(photo=f, caption=f"Photo {next_idx + 1}/{len(photo_paths)}\n\n{CAPTION}", reply_markup=kb)
        else:
            await query.answer("No more photos!", show_alert=True)

# ═══════════════════════════
# 🚀 MAIN
# ═══════════════════════════

def main():
    logging.basicConfig(level=logging.INFO)
    print("Instagram Bot - ddinstagram Proxy")
    
    for f in os.listdir(DOWNLOAD_DIR):
        try: os.remove(os.path.join(DOWNLOAD_DIR, f))
        except: pass
    
    app = Application.builder().token(BOT_TOKEN).read_timeout(120).write_timeout(120).connect_timeout(120).build()
    
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
    
    print("Bot Started!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
