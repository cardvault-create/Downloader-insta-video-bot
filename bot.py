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
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, ReactionTypeEmoji
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, TypeHandler
from telegram.constants import ChatMemberStatus
import yt_dlp
import requests

# ═══════════════════════════
# 🔐 CONFIG
# ═══════════════════════════

BOT_TOKEN = "8518787964:AAHdWIiFAh1SMNDSB8v5KhYKRJElgkfPl_c"
OWNER_ID = 1987818347

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Add this line
download_semaphore = asyncio.Semaphore(2)  # Max 2 parallel downloads

# ═══════════════ PREMIUM EMOJI IDs ═══════════════
PREMIUM_EMOJIS = [
    "6266929318673260530",   # 🌟
    "6267288322104631486",   # 🌟
    "6267035498854753531",   # 🤖
    "6264978127915590987",   # 🤖
    "6265058787401408793",   # 🤖
    "6266919702241485132",   # 🤖
    "6264733744276447254",   # 🤖
    "6266917876880384064",   # 🤖
    "6267207984741359666",   # 🤖
    "6267022480808877913",   # 🤖
    "6267146356255629216",   # 🤖
    "6265004228431849829",   # 🤖
    "6265047087910494495",   # 🤖
    "6264778407641358116",   # 🤖
    "6264591580858949353",   # 🤖
    "6264558101588877276",   # 🤖
    "6264895041773248756",   # 🤖
    "6267140016883900263",   # 🤖
    "6264930711476641645",   # 🤖
    "6264692881957593710",   # 🤖
    "6265066226284764940",   # 🤖
    "6267213997695573870",   # 🤖
    "6267212417147608719",   # 🤖
    "6264732576045343546",   # 🤖
    "6267257866491534260",   # 🤖
    "6266884758387564041",   # 🤖
    "6266914651359944313",   # 🤖
    "6267137753436134358",   # 🤖
    "6265045850959913888",   # 🤖
    "6264689544768004433",   # 🤖
    "6264518948667006892",   # 🤖
    "6264548798689714303",   # 🤖
    "6267300360897961392",   # 🤖
]

def get_random_emoji_id():
    return random.choice(PREMIUM_EMOJIS)

import random

LOVE_EMOJIS = [
    "5474548985463056592",
    "5188650080768371488",
    "5188481821129583527",
    "5474538119195797886",
    "5404408875279458778",
    "5407131175875518700",
    "6023847192060499006",
    "6023660820544623088",
    "6026256492619895014",
    "6026321200597176575",
    "5384337002751630535",
    "5373041818583738556",
    "5325888970368762082",
]

# ═══════════════ RANDOM BUTTON COLOUR ═══════════════
def get_random_style():
    styles = ["primary", "success", "danger"]
    return random.choice(styles)

def get_random_peach_emoji():
    peach_emojis = [
        "6334598469746952256", "6334771638533359276", "6334492173601343643",
        "6097980951814475221", "6334517028577085717", "6334569891034564332",
        "6334331674968458665", "6334672948774831861", "6334719188392740438",
        "6334406334384965287", "6334832949191509666", "6334525760245597578",
        "6334529303593617491", "6334406115341633473", "6334338293513062290",
        "6334346776073471787", "6334381440754517833", "6334867575217850170",
        "6334681229471779175", "6334648089504122382", "6334696528145286813",
        "6334471179801200139", "6332227450231064055", "6332316673881671142",
        "6334667726094599941", "6334333036473091884", "6334528491844798409",
        "6334443421427566103", "6334578712897390468", "6334453153823459140",
        "6334669809153738968", "6334426975997789902", "6334789677396002338",
        "6332569548671158159", "6334647913410463156", "6334547209312274007",
        "6334499483635682210", "6334754651937703379", "6334693345574520541",
        "6334323261127526515", "6334511376400123673", "6334861944515725070",
        "6334670114096416744", "6334726730355312892", "6334476252157576766",
        "6334517080116692923", "6334649794606139137", "6334663250738677354",
        "6334485301653669393", "6334374298223904196", "6334691657652373356",
        "6334572562504222352", "6334495652524852896", "6334344405251524411",
        "6334540251465254516", "6334555537253860831", "6334379727062566543",
        "6334847951512274754", "6332077087720998905", "6318655091582699201",
        "6334834495379736183", "6334666703892383392", "6332501387540170887",
        "6334564290397210736", "6334768318523639311", "6334638215374309049",
        "6334599522013939256", "6332440708242212451", "6334474392436737730",
        "6334739267364849295", "6334377300406044372", "6332476463844951514",
        "6334664298710697689", "6334475719581632634", "6334508984103339934",
        "6334836947806062568", "6334371081293399674", "6332418984297629099",
        "6334355533511787932", "6334804684011734898", "6334812853039531693",
    ]
    return random.choice(peach_emojis)

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

# ═══════════════ CHANNELS DATABASE ═══════════════
CHANNELS_DB = "channels.json"
AUTO_FORWARD_DB = "auto_forward.json"
AUTO_SEND_VOICE_DB = "auto_send_voice.json"

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
    if eid not in data["emojis"]: 
        data["emojis"].append(eid)
        jsave(EMOJI_DB, data)
        return True, len(data["emojis"])
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
    vids = get_video_list()
    if not vids: return None
    # Har baar pure random - bina kisi global state ke
    chosen = random.choice(vids)
    # Return copy with unique ID to avoid Telegram duplicate detection
    import copy
    result = copy.deepcopy(chosen)
    # Add timestamp to make each call unique
    result["_ts"] = time.time()
    return result
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

# ═══════════════ CHANNEL FUNCTIONS ═══════════════
def get_channels():
    return jload(CHANNELS_DB, [])

def add_channel_db(channel_id):
    channels = get_channels()
    channel_id = str(channel_id)
    if channel_id not in channels:
        channels.append(channel_id)
        jsave(CHANNELS_DB, channels)
        return True, len(channels)
    return False, len(channels)

def remove_channel_db(channel_id):
    channels = get_channels()
    channel_id = str(channel_id)
    if channel_id in channels:
        channels.remove(channel_id)
        jsave(CHANNELS_DB, channels)
        return True, len(channels)
    return False, len(channels)

def is_auto_forward_enabled():
    return jload(AUTO_FORWARD_DB, {"enabled": False})["enabled"]

def set_auto_forward(enabled):
    jsave(AUTO_FORWARD_DB, {"enabled": enabled})

def is_auto_send_voice_enabled(user_id=None):
    data = jload(AUTO_SEND_VOICE_DB, {})
    if user_id is None:
        return False
    return str(user_id) in data.get("users", [])

def set_auto_send_voice(user_id, enabled):
    data = jload(AUTO_SEND_VOICE_DB, {"users": []})
    user_id = str(user_id)
    if enabled:
        if user_id not in data["users"]:
            data["users"].append(user_id)
    else:
        if user_id in data["users"]:
            data["users"].remove(user_id)
    jsave(AUTO_SEND_VOICE_DB, data)

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
        if not shortcode: return {"success": False, "error": "Invalid"}
        is_reel = '/reel/' in url or '/tv/' in url
        if is_reel: return InstaDownloader._download_video(shortcode)
        else: return InstaDownloader._download_photo(shortcode, url)
    
    @staticmethod
    def _download_video(shortcode):
        """FAST DOWNLOAD - ALWAYS WITH AUDIO"""
        url = f'https://www.instagram.com/reel/{shortcode}/'
    
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'outtmpl': os.path.join(DOWNLOAD_DIR, f'{shortcode}.%(ext)s'),
            'format': 'bv*+ba/b[height<=1080]/bv[height<=1080]+ba/b[height<=1080]/b[height<=1080]/best',
            'merge_output_format': 'mp4',
            'socket_timeout': 60,
            'extractor_retries': 5,
            'retries': 10,
            'fragment_retries': 10,
            'force_overwrites': True,
            'ignoreerrors': True,
            'no_color': True,
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Referer': 'https://www.instagram.com/',
            }
        }
    
        if os.path.exists('cookies.txt'):
            ydl_opts['cookiefile'] = 'cookies.txt'
    
        if shutil.which('ffmpeg'):
            ydl_opts['ffmpeg_location'] = shutil.which('ffmpeg')
    
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except:
            pass
    
        time.sleep(2)
    
        for f in sorted(os.listdir(DOWNLOAD_DIR), key=lambda x: os.path.getmtime(os.path.join(DOWNLOAD_DIR, x)), reverse=True):
            if f.endswith(('.mp4', '.mkv', '.webm')):
                fp = os.path.join(DOWNLOAD_DIR, f)
                if os.path.exists(fp) and os.path.getsize(fp) > 50000:
                    return {"success": True, "file_path": fp, "is_video": True}
    
        if 'cookiefile' in ydl_opts:
            del ydl_opts['cookiefile']
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
            except:
                pass
            time.sleep(2)
            for f in sorted(os.listdir(DOWNLOAD_DIR), key=lambda x: os.path.getmtime(os.path.join(DOWNLOAD_DIR, x)), reverse=True):
                if f.endswith(('.mp4', '.mkv', '.webm')):
                    fp = os.path.join(DOWNLOAD_DIR, f)
                    if os.path.exists(fp) and os.path.getsize(fp) > 50000:
                        return {"success": True, "file_path": fp, "is_video": True}
    
        ydl_opts['format'] = 'best[ext=mp4]/best'
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
        except:
            pass
        time.sleep(2)
        for f in sorted(os.listdir(DOWNLOAD_DIR), key=lambda x: os.path.getmtime(os.path.join(DOWNLOAD_DIR, x)), reverse=True):
            if f.endswith(('.mp4', '.mkv', '.webm')):
                fp = os.path.join(DOWNLOAD_DIR, f)
                if os.path.exists(fp) and os.path.getsize(fp) > 50000:
                    return {"success": True, "file_path": fp, "is_video": True}
    
        return {"success": False, "error": "<tg-emoji emoji-id=\"5850414922294365618\">🚫</tg-emoji> 𝐒𝐞𝐫𝐯𝐞𝐫 𝐁𝐮𝐬𝐲, 𝐓𝐫𝐲 𝐀𝐠𝐚𝐢𝐧 <tg-emoji emoji-id=\"5850600963097759409\">🚫</tg-emoji>"}
    
    # ═══════════════ PHOTO METHODS ═══════════════
    
    @staticmethod
    def _download_photo(shortcode, url):
        """PHOTOS - 5 methods"""
        result = InstaDownloader._method_scrape_multi(shortcode, url)
        if result.get("success"): return result
        for method in [InstaDownloader._method_oembed, InstaDownloader._method_ytdlp, InstaDownloader._method_scrape_single, InstaDownloader._method_cdn]:
            result = method(shortcode)
            if result.get("success"): return result
        return {"success": False, "error": "<tg-emoji emoji-id=\"5850414922294365618\">🚫</tg-emoji> 𝐒𝐞𝐫𝐯𝐞𝐫 𝐢𝐬𝐬𝐮𝐞, 𝐩𝐥𝐞𝐚𝐬𝐞 𝐭𝐫𝐲 𝐚𝐠𝐚𝐢𝐧 <tg-emoji emoji-id=\"5850600963097759409\">🚫</tg-emoji>"}
    
    @staticmethod
    def _method_scrape_multi(shortcode, url):
        """Multiple photos from carousel posts"""
        try:
            session = requests.Session()
            session.headers.update({'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15'})
            resp = session.get(url, timeout=15)
            if resp.status_code != 200: return {"success": False}
            html = resp.text
            image_urls = []
            
            nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
            if nd:
                try:
                    data = json.loads(nd.group(1))
                    data_str = json.dumps(data)
                    
                    carousel_matches = re.findall(r'"edge_sidecar_to_children"[^}]*"edges":\s*\[(.*?)\]', data_str, re.DOTALL)
                    if carousel_matches:
                        for carousel in carousel_matches:
                            display_urls = re.findall(r'"display_url":"([^"]+)"', carousel)
                            for du in display_urls:
                                cleaned = du.replace('\\u0026', '&')
                                if cleaned not in image_urls and '.mp4' not in cleaned:
                                    image_urls.append(cleaned)
                    
                    if not image_urls:
                        display_urls = re.findall(r'"display_url":"([^"]+)"', data_str)
                        for du in display_urls:
                            cleaned = du.replace('\\u0026', '&')
                            if cleaned not in image_urls and '.mp4' not in cleaned:
                                image_urls.append(cleaned)
                except: pass
            
            if not image_urls:
                urls_found = re.findall(r'"display_url":"([^"]+)"', html)
                image_urls = [u.replace('\\u0026', '&') for u in urls_found if '.mp4' not in u]
            
            if not image_urls:
                og = re.findall(r'<meta\s+property="og:image"\s+content="([^"]+)"', html)
                image_urls = list(set(og))
            
            seen = set()
            unique_urls = []
            for u in image_urls:
                if u not in seen:
                    seen.add(u)
                    unique_urls.append(u)
            image_urls = unique_urls
            
            if not image_urls:
                return {"success": False}
            
            downloaded = []
            for i, img_url in enumerate(image_urls[:10]):
                try:
                    fp = os.path.join(DOWNLOAD_DIR, f"multi_{shortcode}_{i+1}.jpg")
                    r = session.get(img_url, headers={'User-Agent': 'Mozilla/5.0'}, stream=True, timeout=30)
                    if r.status_code == 200:
                        with open(fp, 'wb') as f:
                            for chunk in r.iter_content(8192):
                                f.write(chunk)
                        if os.path.getsize(fp) > 1000:
                            downloaded.append(fp)
                except: continue
            
            if downloaded:
                return {
                    "success": True,
                    "file_path": downloaded[0],
                    "file_paths": downloaded,
                    "is_video": False,
                    "is_multiple": len(downloaded) > 1,
                    "total": len(downloaded)
                }
            return {"success": False}
        except: return {"success": False}
    
    @staticmethod
    def _method_oembed(shortcode):
        """Instagram Official oEmbed API"""
        try:
            post_url = f"https://www.instagram.com/p/{shortcode}/"
            api_url = f"https://api.instagram.com/oembed?url={urllib.parse.quote(post_url)}&maxwidth=1080"
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', 'Accept': 'application/json'}
            resp = requests.get(api_url, headers=headers, timeout=15)
            if resp.status_code != 200: return {"success": False}
            data = resp.json()
            thumbnail_url = data.get('thumbnail_url', '')
            embed_html = data.get('html', '')
            image_urls = []
            if thumbnail_url:
                hd_url = re.sub(r'/s\d+x\d+/', '/', thumbnail_url).split('?')[0]
                image_urls.append(hd_url)
                image_urls.append(thumbnail_url)
            if embed_html:
                img_matches = re.findall(r'<img[^>]+src="([^"]+)"', embed_html)
                for img_url in img_matches:
                    if img_url not in image_urls: image_urls.append(img_url)
            if not image_urls: return {"success": False}
            downloaded = []
            for img_url in image_urls:
                try:
                    if img_url.startswith('//'): img_url = 'https:' + img_url
                    if '.mp4' in img_url or '.mov' in img_url: continue
                    ext = 'jpg'
                    if '.png' in img_url: ext = 'png'
                    elif '.webp' in img_url: ext = 'webp'
                    fp = os.path.join(DOWNLOAD_DIR, f"{shortcode}.{ext}")
                    img_headers = {'User-Agent': 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36', 'Accept': 'image/*', 'Referer': 'https://www.instagram.com/'}
                    r = requests.get(img_url, headers=img_headers, stream=True, timeout=30)
                    if r.status_code == 200:
                        with open(fp, 'wb') as f:
                            for chunk in r.iter_content(8192): f.write(chunk)
                        if os.path.getsize(fp) > 1000: downloaded.append(fp)
                        break
                except: continue
            if downloaded: return {"success": True, "file_path": downloaded[0], "is_video": False}
            return {"success": False}
        except: return {"success": False}
    
    @staticmethod
    def _method_ytdlp(shortcode):
        """yt-dlp for photos"""
        try:
            url = f"https://www.instagram.com/p/{shortcode}/"
            ydl_opts = {'quiet': True, 'outtmpl': os.path.join(DOWNLOAD_DIR, f'{shortcode}.%(ext)s'), 'format': 'best', 'retries': 3}
            if os.path.exists('cookies.txt'): ydl_opts['cookiefile'] = 'cookies.txt'
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.extract_info(url, download=True)
                time.sleep(0.3)
                for f in os.listdir(DOWNLOAD_DIR):
                    if shortcode in f and not f.endswith(('.mp4','.mov','.webm')):
                        fp = os.path.join(DOWNLOAD_DIR, f)
                        if os.path.getsize(fp) > 1000: return {"success": True, "file_path": fp, "is_video": False}
        except: pass
        return {"success": False}
    
    @staticmethod
    def _method_scrape_single(shortcode):
        """Direct page scrape for single photo"""
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
        """Direct Instagram CDN"""
        try:
            cdn_urls = [
                f"https://www.instagram.com/p/{shortcode}/media/?size=l",
                f"https://i.instagram.com/{shortcode}.jpg",
            ]
            for cdn_url in cdn_urls:
                try:
                    headers = {'User-Agent': 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36', 'Accept': 'image/*', 'Referer': 'https://www.instagram.com/'}
                    r = requests.get(cdn_url, headers=headers, stream=True, timeout=30)
                    if r.status_code == 200 and 'image' in r.headers.get('content-type', ''):
                        fp = os.path.join(DOWNLOAD_DIR, f"{shortcode}.jpg")
                        with open(fp, 'wb') as f:
                            for chunk in r.iter_content(8192): f.write(chunk)
                        if os.path.getsize(fp) > 1000: return {"success": True, "file_path": fp, "is_video": False}
                except: continue
        except: pass
        return {"success": False}
    
    @staticmethod
    def extract_audio(video_path, custom_name=None):
        try:
            if custom_name and custom_name.lower() != "skip":
                safe = re.sub(r'[^\w\s-]', '', custom_name).strip()[:50] or "Audio"
                # Audio file VIDEO file ke SAME folder mein banao
                ap = os.path.join(os.path.dirname(video_path), f"{safe}.mp3")
            else:
                ap = os.path.join(os.path.dirname(video_path), f"{os.path.splitext(os.path.basename(video_path))[0]}.mp3")
            if not shutil.which('ffmpeg'): return {"success": False, "error": "FFmpeg not found"}
            subprocess.run(['ffmpeg', '-i', video_path, '-vn', '-acodec', 'libmp3lame', '-ab', '192k', '-y', ap], capture_output=True, timeout=300)
            if os.path.exists(ap) and os.path.getsize(ap) > 1000: return {"success": True, "file_path": ap}
            return {"success": False, "error": "Audio extraction failed"}
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
    "<tg-emoji emoji-id=\"5233303721873523335\">🌟</tg-emoji><tg-emoji emoji-id=\"5233466922040838637\">🌟</tg-emoji><tg-emoji emoji-id=\"5233548264426456836\">🌟</tg-emoji><tg-emoji emoji-id=\"5233322134398320334\">🌟</tg-emoji><tg-emoji emoji-id=\"5233414046698455589\">🌟</tg-emoji><tg-emoji emoji-id=\"5233256442873530845\">🌟</tg-emoji><tg-emoji emoji-id=\"5233650763820974838\">🌟</tg-emoji><tg-emoji emoji-id=\"5233727798354397359\">🌟</tg-emoji>\n"
    "\n"
    "<tg-emoji emoji-id=\"5458829250540879218\">🌟</tg-emoji><tg-emoji emoji-id=\"5233326833092542997\">🌟</tg-emoji><tg-emoji emoji-id=\"5233241990308578649\">🌟</tg-emoji><tg-emoji emoji-id=\"5233182986047866199\">🌟</tg-emoji><tg-emoji emoji-id=\"5233340418074102629\">🌟</tg-emoji><tg-emoji emoji-id=\"5233544652358962131\">🌟</tg-emoji><tg-emoji emoji-id=\"5233619423444616550\">🌟</tg-emoji><tg-emoji emoji-id=\"5233286945731267091\">🌟</tg-emoji><tg-emoji emoji-id=\"6035210073502913033\">🌟</tg-emoji>\n"
    "\n"
    "<tg-emoji emoji-id=\"5447410659077661506\">🌟</tg-emoji><a href=\"https://t.me/Instagram_LinkToVideo_Bot\">˹𝚰𝖓𝖘𝖙𝖆𝖌𝖗𝖆𝖒 ✘ 𝚫𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐞𝐫˼ ♪</a><tg-emoji emoji-id=\"5859300243262148377\">🌟</tg-emoji>\n"
    "\n"
    "<tg-emoji emoji-id=\"6325560643080424064\">🌟</tg-emoji><tg-emoji emoji-id=\"6325460845220334365\">🌟</tg-emoji><tg-emoji emoji-id=\"6325756901611015187\">🌟</tg-emoji><tg-emoji emoji-id=\"6323380178378558793\">🌟</tg-emoji><tg-emoji emoji-id=\"6325600852564249078\">🌟</tg-emoji><tg-emoji emoji-id=\"6323154370472971909\">🌟</tg-emoji><tg-emoji emoji-id=\"6325554574291636199\">🌟</tg-emoji><tg-emoji emoji-id=\"6323195679468423939\">🌟</tg-emoji>\n"
    "\n"
    "<tg-emoji emoji-id=\"6035338166607550430\">🌟</tg-emoji><tg-emoji emoji-id=\"5230945011733907341\">🌟</tg-emoji><tg-emoji emoji-id=\"5233301832087912725\">🌟</tg-emoji><tg-emoji emoji-id=\"5231082918838816097\">🌟</tg-emoji><tg-emoji emoji-id=\"5233493705456895584\">🌟</tg-emoji><tg-emoji emoji-id=\"5230998179134064133\">🌟</tg-emoji><tg-emoji emoji-id=\"5233649290647193551\">🌟</tg-emoji><tg-emoji emoji-id=\"5233356906453550762\">🌟</tg-emoji><tg-emoji emoji-id=\"5233598717407282431\">🌟</tg-emoji><tg-emoji emoji-id=\"6034832099200995975\">🌟</tg-emoji>\n"
    "\n"
    "<tg-emoji emoji-id=\"5233365393308928165\">🌟</tg-emoji><tg-emoji emoji-id=\"5233415751800475615\">🌟</tg-emoji><tg-emoji emoji-id=\"5233334533968905917\">🌟</tg-emoji><tg-emoji emoji-id=\"5233223341560578191\">🌟</tg-emoji><tg-emoji emoji-id=\"5233217440275514440\">🌟</tg-emoji><tg-emoji emoji-id=\"5233615300276012638\">🌟</tg-emoji><tg-emoji emoji-id=\"5233660942893466534\">🌟</tg-emoji><tg-emoji emoji-id=\"5233532686580075326\">🌟</tg-emoji>\n"
    "\n"
    "<tg-emoji emoji-id=\"6275939064843603913\">🌟</tg-emoji><tg-emoji emoji-id=\"6275853229922193308\">🌟</tg-emoji><tg-emoji emoji-id=\"6278459282933419717\">🌟</tg-emoji><tg-emoji emoji-id=\"6276014351325337415\">🌟</tg-emoji><tg-emoji emoji-id=\"6278369556771639533\">🌟</tg-emoji><tg-emoji emoji-id=\"6311813346119127281\">🌟</tg-emoji><tg-emoji emoji-id=\"6311996676798157611\">🌟</tg-emoji><tg-emoji emoji-id=\"6312329283360526701\">🌟</tg-emoji><tg-emoji emoji-id=\"6312143036398703364\">🌟</tg-emoji><tg-emoji emoji-id=\"6312056651721478657\">🌟</tg-emoji><tg-emoji emoji-id=\"6314426361272340738\">🌟</tg-emoji>\n"
    "\n"
    "<tg-emoji emoji-id=\"5816442521256989067\">🌟</tg-emoji><tg-emoji emoji-id=\"5805226514811197705\">🌟</tg-emoji><tg-emoji emoji-id=\"5805588073748108621\">🌟</tg-emoji><a href=\"https://t.me/FathersOfCreater\">𝜝𝜣𝜯 𝑭𝜟𝜯𝜢𝜮𝜞</a><tg-emoji emoji-id=\"5805652747365651935\">🌟</tg-emoji><tg-emoji emoji-id=\"5805659537708947764\">🌟</tg-emoji><tg-emoji emoji-id=\"5816505996578657193\">🌟</tg-emoji>"
)

WELCOME_TEXT = f"""ʜᴇʏ, {{mention}} . ˚◞<tg-emoji emoji-id="5460831783337599621">🌟</tg-emoji> ◟˚ .
ɪ'ᴍ <a href="https://t.me/Instagram_LinkToVideo_Bot">˹𝚰𝖓𝖘𝖙𝖆𝖌𝖗𝖆𝖒 ✘ 𝚫𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐞𝐫˼ ♪</a>, <tg-emoji emoji-id="5224334236726600040">🌟</tg-emoji>

┏━━━━━━━━━━━━━━━━━⧫
┠ <tg-emoji emoji-id="5327760901799956030">🌟</tg-emoji><tg-emoji emoji-id="5328241392676260170">🌟</tg-emoji> ˹ɪ ʜᴀᴠᴇ sᴘᴇᴄɪᴀʟ ғᴇᴀᴛᴜʀᴇs˼
┠ <tg-emoji emoji-id="5983582264502523326">🌟</tg-emoji> ˹ᴀʟʟ-ɪɴ-ᴏɴᴇ ʙᴏᴛ˼
┗━━━━━━━━━━━━━━━━━⧫
┏━━━━━━━━━━━━━━━━━⧫
┠ <tg-emoji emoji-id="6032730511573521800">🌟</tg-emoji> ˹ʏᴏᴜ ᴄᴀɴ ᴅᴏᴡɴʟᴏᴀᴅ ɪɴsᴛᴀɢʀᴀᴍ ʀᴇᴇʟs˼
┠ <tg-emoji emoji-id="5345783679790639018">🌟</tg-emoji> ˹ʏᴏᴜ ᴄᴀɴ ᴅᴏᴡɴʟᴏᴀᴅ ɪɴsᴛᴀɢʀᴀᴍ ᴘʜᴏᴛᴏs˼
┠ <tg-emoji emoji-id="4918382043827537873">🌟</tg-emoji> ˹ʏᴏᴜ ᴄᴀɴ ᴇxᴛʀᴀᴄᴛ ᴀᴜᴅɪᴏ ғʀᴏᴍ ᴠɪᴅᴇᴏs˼
┠ <tg-emoji emoji-id="5269416373833972738">🌟</tg-emoji> ˹ʜᴅ ᴠɪᴅᴇᴏ + ᴏʀɪɢɪɴᴀʟ ᴀᴜᴅɪᴏ sᴜᴘᴘᴏʀᴛ˼
┠ <tg-emoji emoji-id="5319175438268913255">🌟</tg-emoji> ˹ᴍᴜʟᴛɪᴘʟᴇ ᴘʜᴏᴛᴏ ᴅᴏᴡɴʟᴏᴀᴅ sᴜᴘᴘᴏʀᴛ˼
┠ <tg-emoji emoji-id="5841494459904168607">🌟</tg-emoji> ˹ɢʀᴏᴜᴘ sᴜᴘᴘᴏʀᴛ ᴀᴠᴀɪʟᴀʙʟᴇ˼
┗━━━━━━━━━━━━━━━━━⧫

<tg-emoji emoji-id="5801170880272797821">🌟</tg-emoji> ˹ᴸⁱⁿᵏ ᴮʰᵉʲᵒ → ⱽⁱᵈᵉᵒ ᴾᵃᵒ → ᴰᵒʷⁿˡᵒᵃᵈ ⱽⁱᵈᵉᵒ ᴬᵘᵈⁱᵒ → <tg-emoji emoji-id="5339433596413304050">🌟</tg-emoji><tg-emoji emoji-id="5339432312218081255">🌟</tg-emoji> ᴮᵘᵗᵗᵒⁿ ᴰᵃᵇᵃᵒ <tg-emoji emoji-id="5805545944413900887">🌟</tg-emoji> 
→ ᴬᵘᵈⁱᵒ ᴾᵃᵒ˼<tg-emoji emoji-id="4976878570686120597">🌟</tg-emoji>⋆˚ · .<tg-emoji emoji-id="5891005743380828183">🌟</tg-emoji>. · ˚⋆

<tg-emoji emoji-id="5233365393308928165">🌟</tg-emoji><tg-emoji emoji-id="5233415751800475615">🌟</tg-emoji><tg-emoji emoji-id="5233334533968905917">🌟</tg-emoji><tg-emoji emoji-id="5233223341560578191">🌟</tg-emoji><tg-emoji emoji-id="5233217440275514440">🌟</tg-emoji><tg-emoji emoji-id="5233615300276012638">🌟</tg-emoji><tg-emoji emoji-id="5233660942893466534">🌟</tg-emoji><tg-emoji emoji-id="5233532686580075326">🌟</tg-emoji>
<tg-emoji emoji-id="6127672662027146442">🌟</tg-emoji> ˹ᴄʟɪᴄᴋ ᴏɴ ᴛʜᴇ ᴀᴅᴅ ᴛᴏ ɢʀᴏᴜᴘ ʙᴜᴛᴛᴏɴ ʙᴇʟᴏᴡ ᴛᴏ ᴀᴅᴅ ᴛʜɪs ʙᴏᴛ ɪɴ ʏᴏᴜʀ ɢʀᴏᴜᴘ ᴀɴᴅ ᴇɴᴊᴏʏ ᴅᴏᴡɴʟᴏᴀᴅɪɴɢ ᴛʜᴇʀᴇ ᴛᴏᴏ˼ <tg-emoji emoji-id="5237707944547592720">🌟</tg-emoji>

<tg-emoji emoji-id="5825690573687754521">🌟</tg-emoji> ˹ᴅᴇᴠᴇʟᴏᴩᴇʀ˼ <tg-emoji emoji-id="5814637011495031358">🪽</tg-emoji> ➪ <a href="https://t.me/FathersOfCreater">𝜝𝜣𝜯 𝑭𝜟𝜯𝜢𝜮𝜞</a> <tg-emoji emoji-id="5825889735616238150">🌟</tg-emoji>"""

GROUP_WELCOME = f"""👋🏻 ʜᴇʟʟᴏ {{chat_title}} <tg-emoji emoji-id="5801170880272797821">🌟</tg-emoji> ⋆｡°✩

ɪ'ᴍ <a href="https://t.me/Instagram_LinkToVideo_Bot">˹𝚰𝖓𝖘𝖙𝖆𝖌𝖗𝖆𝖒 ✘ 𝚫𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐞𝐫˼ ♪</a>, <tg-emoji emoji-id="5224334236726600040">🌟</tg-emoji>

┏━━━━━━━━━━━━━━━━━⧫
┠ <tg-emoji emoji-id="6032730511573521800">🌟</tg-emoji> ˹ᴅᴏᴡɴʟᴏᴀᴅ ɪɴsᴛᴀɢʀᴀᴍ ʀᴇᴇʟs, ᴘʜᴏᴛᴏs & ᴀᴜᴅɪᴏ˼
┠ <tg-emoji emoji-id="5269416373833972738">🌟</tg-emoji><tg-emoji emoji-id="5400144011409251972">🌟</tg-emoji> ˹ʜᴅ ᴠɪᴅᴇᴏ + ᴏʀɪɢɪɴᴀʟ ᴀᴜᴅɪᴏ ɢᴜᴀʀᴀɴᴛᴇᴇᴅ˼
┠ <tg-emoji emoji-id="6127672662027146442">🌟</tg-emoji> ˹ᴊᴜsᴛ sᴇɴᴅ ɪɴsᴛᴀɢʀᴀᴍ ʟɪɴᴋ ɪɴ ɢʀᴏᴜᴘ˼
┗━━━━━━━━━━━━━━━━━⧫

<tg-emoji emoji-id="5801170880272797821">🌟</tg-emoji> ˹sɪʀғ ʟɪɴᴋ ʙʜᴇᴊᴏ, ʙᴀᴋɪ ʙᴏᴛ ᴅᴇᴋʜ ʟᴇɢᴀ˼✧ ⋆˚ · . 　 ☽ 　 . · ˚⋆

<tg-emoji emoji-id="5825690573687754521">🌟</tg-emoji> ˹ᴅᴇᴠᴇʟᴏᴩᴇʀ˼ <tg-emoji emoji-id="5814637011495031358">🪽</tg-emoji> ➪ <a href="https://t.me/FathersOfCreater">𝜝𝜣𝜯 𝑭𝜟𝜯𝜢𝜮𝜞</a> <tg-emoji emoji-id="5825889735616238150">🌟</tg-emoji>"""

BOT_DISABLED_MSG = "<tg-emoji emoji-id=\"5352865784508980799\">🚫</tg-emoji><tg-emoji emoji-id=\"5325878958799994800\">🚫</tg-emoji><tg-emoji emoji-id=\"5293991227513914037\">🚫</tg-emoji><tg-emoji emoji-id=\"5330292450013494017\">🚫</tg-emoji><tg-emoji emoji-id=\"5463362571341942623\">🚫</tg-emoji><tg-emoji emoji-id=\"5327938799345349736\">🚫</tg-emoji><tg-emoji emoji-id=\"5328162635860948105\">🚫</tg-emoji><tg-emoji emoji-id=\"5352708339597844431\">🚫</tg-emoji>\n\n<tg-emoji emoji-id=\"5352901995378252828\">⛔</tg-emoji> 𝗕𝗢𝗧 𝗦𝗧𝗢𝗣 𝗕𝗬 𝗢𝗪𝗡𝗘𝗥\n\n𝗕𝗼𝘁 𝗶𝘀 𝗰𝘂𝗿𝗿𝗲𝗻𝘁𝗹𝘆 𝗱𝗶𝘀𝗮𝗯𝗹𝗲𝗱 <tg-emoji emoji-id=\"5415914740478130417\">😢</tg-emoji> (˃̣̣̥᷄⌓˂̣̣̥᷅)"

AUDIO_BUTTON_TEXT = "➪ ˹𝐃𝐨𝐰𝐧𝐥𝐨𝐚𝐝 𝐕𝐢𝐝𝐞𝐨 𝐀𝐮𝐝𝐢𝐨˼  ♪"
AUDIO_DEFAULT_NAME = "⁂ ╰◉♡ ˹𝐌𝐲𐙚𝐌𝐮𝐬𝐢𝐜˼→♪◟˚ . ⋆˚ · ♪◉╯"

# Premium emoji IDs for Default Name button
AUDIO_DEFAULT_EMOJIS = [
    "5411627375274270720",
    "5474153401795225186",
    "5474576928520283468",
    "5188234160430394078",
    "5474220343155500449",
]

def get_random_audio_default_emoji():
    return random.choice(AUDIO_DEFAULT_EMOJIS)

AUDIO_NAME_PROMPT = (
    "<tg-emoji emoji-id=\"5411081618074914372\">🌟</tg-emoji><tg-emoji emoji-id=\"6050914707320083722\">🌟</tg-emoji><tg-emoji emoji-id=\"5764630982145610731\">🌟</tg-emoji><tg-emoji emoji-id=\"5764887915679191809\">🌟</tg-emoji><tg-emoji emoji-id=\"5764841332463900746\">🌟</tg-emoji><tg-emoji emoji-id=\"5764651288750987888\">🌟</tg-emoji><tg-emoji emoji-id=\"5765035898777376683\">🌟</tg-emoji><tg-emoji emoji-id=\"5765028352519837021\">🌟</tg-emoji><tg-emoji emoji-id=\"5765001367240316190\">🌟</tg-emoji><tg-emoji emoji-id=\"5764960925828257912\">🌟</tg-emoji><tg-emoji emoji-id=\"5411145510008409639\">🌟</tg-emoji>\n"
    "<tg-emoji emoji-id=\"5978900887588834499\">🌟</tg-emoji> 𝙊𝙠𝙖𝙮，𝙂𝙖𝙫𝙚 𝙈𝙚 𝘼𝙪𝙙𝙞𝙤 𝙉𝙖𝙢𝙚<tg-emoji emoji-id=\"5314504236132747481\">🌟</tg-emoji>\n\n"
    "<tg-emoji emoji-id=\"5857233612373495568\">🌟</tg-emoji> 𝐄𝐱𝐚𝐦𝐩𝐥𝐞 ：𝐌𝐲 𝐌𝐮𝐬𝐢𝐜 <tg-emoji emoji-id=\"5859300243262148377\">🌟</tg-emoji>\n"
    "<tg-emoji emoji-id=\"6035338166607550430\">🌟</tg-emoji> ˹ησ ι∂єα вє¢αυѕє уσυ gαу˼ ♪ <tg-emoji emoji-id=\"6032754146778551433\">🌟</tg-emoji>\n\n"
    "𝐘𝐨𝐮 𝐇𝐚𝐯𝐞 𝐍𝐨 𝐈𝐝𝐞𝐚 𝐓𝐡𝐚𝐧 𝐂𝐥𝐢𝐜𝐤 𝐓𝐡𝐢𝐬 𝐁𝐮𝐭𝐭𝐨𝐧 <tg-emoji emoji-id=\"6278196164646932941\">🌟</tg-emoji>"
)

SETTINGS_TEXT = f"""<tg-emoji emoji-id="5327760901799956030">⚙️</tg-emoji> 𝗖𝗢𝗠𝗠𝗔𝗡𝗗𝗦 ：

<tg-emoji emoji-id="5352540225987943305">👑</tg-emoji> 𝗢𝗪𝗡𝗘𝗥 ：
┣ <tg-emoji emoji-id="5801170880272797821">🌟</tg-emoji> /start ➪ 𝗦𝘁𝗮𝗿𝘁 𝗕𝗼𝘁
┣ <tg-emoji emoji-id="5353060840448727534">🌟</tg-emoji> /disable ➪ 𝗗𝗶𝘀𝗮𝗯𝗹𝗲 𝗕𝗼𝘁
┣ <tg-emoji emoji-id="6226399941388928924">🌟</tg-emoji> /enable ➪ 𝗘𝗻𝗮𝗯𝗹𝗲 𝗕𝗼𝘁
┗ <tg-emoji emoji-id="6127410617482484040">🌟</tg-emoji> /settings ➪ 𝗕𝗼𝘁 𝗦𝗲𝘁𝘁𝗶𝗻𝗴𝘀

<tg-emoji emoji-id="5841494459904168607">👥</tg-emoji> 𝗚𝗥𝗢𝗨𝗣 ：
┗ <tg-emoji emoji-id="6127672662027146442">🌟</tg-emoji> /activate ➪ 𝗔𝗰𝘁𝗶𝘃𝗮𝘁𝗲 𝗚𝗿𝗼𝘂𝗽

<tg-emoji emoji-id="5352555352862765789">🎨</tg-emoji> 𝗘𝗠𝗢𝗝𝗜 ：
┣ <tg-emoji emoji-id="6170160969600212116">🌟</tg-emoji> /addemoji ➪ 𝗔𝗱𝗱 𝗘𝗺𝗼𝗷𝗶
┣ <tg-emoji emoji-id="5929358014627713883">🌟</tg-emoji> /removeemoji ➪ 𝗥𝗲𝗺𝗼𝘃𝗲 𝗘𝗺𝗼𝗷𝗶
┗ <tg-emoji emoji-id="6172671064452111943">🌟</tg-emoji> /listemojis ➪ 𝗟𝗶𝘀𝘁 𝗘𝗺𝗼𝗷𝗶𝘀

<tg-emoji emoji-id="5983582264502523326">❄</tg-emoji> 𝗦𝗧𝗜𝗖𝗞𝗘𝗥 ：
┣ <tg-emoji emoji-id="5237707944547592720">🌟</tg-emoji> /addsticker ➪ 𝗔𝗱𝗱 𝗦𝘁𝗶𝗰𝗸𝗲𝗿
┣ <tg-emoji emoji-id="5233540769708526063">🌟</tg-emoji> /removesticker ➪ 𝗥𝗲𝗺𝗼𝘃𝗲 𝗦𝘁𝗶𝗰𝗸𝗲𝗿
┗ <tg-emoji emoji-id="5233455454478156666">🌟</tg-emoji> /liststickers ➪ 𝗟𝗶𝘀𝘁 𝗦𝘁𝗶𝗰𝗸𝗲𝗿𝘀

<tg-emoji emoji-id="5269416373833972738">📹</tg-emoji> 𝗩𝗜𝗗𝗘𝗢 ：
┣ <tg-emoji emoji-id="5400144011409251972">🌟</tg-emoji> /addvideo ➪ 𝗔𝗱𝗱 𝗩𝗶𝗱𝗲𝗼
┣ <tg-emoji emoji-id="4918382043827537873">🌟</tg-emoji> /delvideo ➪ 𝗗𝗲𝗹𝗲𝘁𝗲 𝗩𝗶𝗱𝗲𝗼
┣ <tg-emoji emoji-id="5319175438268913255">🌟</tg-emoji> /videos ➪ 𝗟𝗶𝘀𝘁 𝗩𝗶𝗱𝗲𝗼𝘀
┗ <tg-emoji emoji-id="6032730511573521800">🌟</tg-emoji> /clearvideos ➪ 𝗖𝗹𝗲𝗮𝗿 𝗔𝗹𝗹 𝗩𝗶𝗱𝗲𝗼𝘀

<tg-emoji emoji-id="5841494459904168607">📢</tg-emoji> 𝗖𝗛𝗔𝗡𝗡𝗘𝗟𝗦 ：
┣ <tg-emoji emoji-id="6127672662027146442">🌟</tg-emoji> /addchannel ➪ 𝗔𝗱𝗱 𝗖𝗵𝗮𝗻𝗻𝗲𝗹
┣ <tg-emoji emoji-id="5929358014627713883">🌟</tg-emoji> /removechannel ➪ 𝗥𝗲𝗺𝗼𝘃𝗲 𝗖𝗵𝗮𝗻𝗻𝗲𝗹
┣ <tg-emoji emoji-id="6172671064452111943">🌟</tg-emoji> /listchannels ➪ 𝗟𝗶𝘀𝘁 𝗖𝗵𝗮𝗻𝗻𝗲𝗹𝘀
┣ <tg-emoji emoji-id="5237707944547592720">🌟</tg-emoji> /send ➪ 𝗙𝗼𝗿𝘄𝗮𝗿𝗱 𝘁𝗼 𝗖𝗵𝗮𝗻𝗻𝗲𝗹𝘀
┣ <tg-emoji emoji-id="5269416373833972738">🌟</tg-emoji> /autoforward ➪ 𝗧𝗼𝗴𝗴𝗹𝗲 𝗔𝘂𝘁𝗼
┗ <tg-emoji emoji-id="6032730511573521800">🌟</tg-emoji> /autosendvoice ➪ 𝗔𝘂𝘁𝗼 𝗦𝗲𝗻𝗱 𝗔𝘂𝗱𝗶𝗼

⧫━━━━━✦◆ ◇ ◆ ◇ ◆ ◇✦━━━━━⧫
<tg-emoji emoji-id="5825690573687754521">🌟</tg-emoji> ˹𝗗𝗲𝘃𝗲𝗹𝗼𝗽𝗲𝗿˼ <tg-emoji emoji-id="5814637011495031358">🪽</tg-emoji> ➪ <a href="https://t.me/FathersOfCreater">𝜝𝜣𝜯 𝑭𝜟𝜯𝜢𝜮𝜞</a>"""

async def welcome_animation(bot, chat_id, user_id, first_name):
    try:
        user_mention = f'<a href="tg://user?id={user_id}">{first_name}</a>'
        
        # Sirf /addemoji wale emoji DB se
        emoji_msg = None
        emoji_id = get_random_emoji()
        if emoji_id:
            try:
                emoji_msg = await bot.send_message(
                    chat_id,
                    f'<tg-emoji emoji-id="{emoji_id}">🌟</tg-emoji>',
                    parse_mode="HTML"
                )
            except:
                pass
        
        await asyncio.sleep(1)
        
        # Pehle CUSTOM_EMOJIS define karo
        CUSTOM_EMOJIS = [
            "6102783446805912845",
            "6100403729981249405", 
            "6293839298827392714",
            "6292037822039726255",
            "6140908222225062523",
            "6170425187398326458",
            "6190405409619057730",
            "6240286103232845684",
            "6239848162597537817",
            "6239796184903321679",
            "6239781500410136622",
            "6242511531947329664",
            "6239745830706743108",
        ]

        # Fixed emojis
        WELCOME_EMOJI = "5805511481596319315"  # Sabse aage
        BACK_EMOJI = "5802893875123067320"     # Sabse piche

        # Welcome ke upar wale 13 emojis
        TOP_EMOJIS = [
            "5233540769708526063",
            "5233455454478156666",
            "5233208322059944071",
            "5233607294456974103",
            "5233682374780276698",
            "5233388903959906921",
            "5233493370449446389",
            "5233354862049116785",
            "5233464439549744169",
            "5233618173609133398",
            "5233547018885941243",
            "5233228323722641627",
            "5233419454062282254",
        ]

        # 13 emojis ki line banao
        top_line = "".join([f'<tg-emoji emoji-id="{eid}">🔊</tg-emoji>' for eid in TOP_EMOJIS])

        # Ab welcome_msg banao
        love_id = LOVE_EMOJIS[0]
        custom_id = CUSTOM_EMOJIS[0]
        welcome_msg = await bot.send_message(
            chat_id, 
            f"{top_line}\n \n<tg-emoji emoji-id=\"{WELCOME_EMOJI}\">🌟</tg-emoji>𝐖𝐞𝐥𝐜𝐨𝐦𝐞 𝐁ᴀʙʏ<tg-emoji emoji-id=\"{love_id}\">❤️</tg-emoji>{user_mention}<tg-emoji emoji-id=\"{custom_id}\">🩷</tg-emoji><tg-emoji emoji-id=\"{BACK_EMOJI}\">🌸</tg-emoji>", 
            parse_mode="HTML"
        )

        # 12 edits
        for i in range(1, 13):
            await asyncio.sleep(0.5)
            try:
                love_id = LOVE_EMOJIS[i]
                custom_id = CUSTOM_EMOJIS[i]
                await welcome_msg.edit_text(
                    f"{top_line}\n \n<tg-emoji emoji-id=\"{WELCOME_EMOJI}\">🌟</tg-emoji>𝐖𝐞𝐥𝐜𝐨𝐦𝐞 𝐁ᴀʙʏ<tg-emoji emoji-id=\"{love_id}\">❤️</tg-emoji>{user_mention}<tg-emoji emoji-id=\"{custom_id}\">🩷</tg-emoji><tg-emoji emoji-id=\"{BACK_EMOJI}\">🌸</tg-emoji>",
                    parse_mode="HTML"
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
        
        starting_emojis = []
        for eid in CUSTOM_EMOJIS:
            starting_emojis.append(f'<tg-emoji emoji-id="{eid}">🌸</tg-emoji>')
        
        words = ["𝙨", "𝙩", "α", "я", "†", "ι", "и", "g", ".", ".", ".", ".", "."]

        for i in range(len(words)):
            await asyncio.sleep(0.08)

            try: 
                await welcome_msg.edit_text(
                    f"<b>{starting_emojis[i%len(starting_emojis)]} " + "".join(words[:i+1]) + "</b>",  
                    parse_mode="HTML"
                )
            except: 
                break

        # Starting khatam - turant STICKER bhejo
        await welcome_msg.delete()

        sticker_id = get_random_sticker()
        if sticker_id:
            try:
                sticker_msg = await bot.send_sticker(chat_id, sticker_id)
            except:
                sticker_msg = None
        else:
            sticker_msg = None
        
        await asyncio.sleep(3)
        
        video_data = get_random_video()
        final_text = WELCOME_TEXT.replace("{mention}", user_mention)
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("◆ ➪ ˹𝜟𝙙𝙙 𝜯𝜣 𝑮𝜞𝜭𝑼𝝆˼ ♪☬", url=f"https://t.me/{(await bot.get_me()).username}?startgroup=true", style=get_random_style(), icon_custom_emoji_id=get_random_emoji_id())]])
        
        video_sent = False
        try:
            if video_data and os.path.exists(video_data["path"]):
                await bot.send_video(chat_id, video_data["path"], caption=final_text, parse_mode="HTML", reply_markup=kb)
                video_sent = True
        except:
            pass
        
        if not video_sent:
            await bot.send_message(chat_id, final_text, parse_mode="HTML", reply_markup=kb)
        
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
            user_link = f"<a href='https://t.me/{username}'>{first_name}</a>"
        else:
            user_link = f"<a href='tg://user?id={user_id}'>{first_name}</a>"
        
        # Owner ka real name with username link
        try:
            owner_info = await context.bot.get_chat(OWNER_ID)
            owner_name = owner_info.first_name or "Owner"
            if owner_info.username:
                owner_link = f"<a href='https://t.me/{owner_info.username}'>{owner_name}</a>"
            else:
                owner_link = f"<a href='tg://user?id={OWNER_ID}'>{owner_name}</a>"
        except:
            owner_link = "<a href='https://t.me/FathersOfCreater'>Owner</a>"
        
        # Send notification to owner with video
        owner_msg = (
            f"<tg-emoji emoji-id=\"5805511481596319315\">🌟</tg-emoji> ʜᴇʟʟᴏ {owner_link} <tg-emoji emoji-id=\"5237707944547592720\">🌟</tg-emoji>\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"<tg-emoji emoji-id=\"6032730511573521800\">🌟</tg-emoji> 𝗡𝗲𝘄 𝗨𝘀𝗲𝗿 𝗝𝗼𝗶𝗻𝗲𝗱\n"
            f"<tg-emoji emoji-id=\"5345783679790639018\">🌟</tg-emoji> 𝗡𝗮𝗺𝗲 ➪ {user_link}\n"
            f"<tg-emoji emoji-id=\"4918382043827537873\">🌟</tg-emoji> 𝗨𝘀𝗲𝗿 𝗜𝗗 ➪ <code>{user_id}</code>\n"
            f"<tg-emoji emoji-id=\"5319175438268913255\">🌟</tg-emoji> 𝗨𝘀𝗲𝗿𝗻𝗮𝗺𝗲 ➪ {user_link}\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"<tg-emoji emoji-id=\"5841494459904168607\">🌟</tg-emoji> 𝗧𝗼𝘁𝗮𝗹 𝗨𝘀𝗲𝗿𝘀 ➪ {len(started_users)}\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"<tg-emoji emoji-id=\"5825690573687754521\">🌟</tg-emoji> 𝚰𝛈𝒇𝛉𝛄𝒎 𝚩𝛙 ➪ <a href=\"https://t.me/FathersOfCreater\">𝜝𝜣𝜯 𝑭𝜟𝜯𝜢𝜮𝜞</a>"
        )
        
        try:
            # Send welcome video if available
            video_data = get_random_video()
            if video_data and os.path.exists(video_data["path"]):
                await context.bot.send_video(OWNER_ID, video_data["path"], caption=owner_msg, parse_mode="HTML")
            else:
                await context.bot.send_message(OWNER_ID, owner_msg, parse_mode="HTML")
        except:
            pass
    
    if is_bot_enabled() or user_id == OWNER_ID:
        asyncio.create_task(welcome_animation(context.bot, update.effective_chat.id, user_id, first_name))
    else:
        await update.message.reply_text(BOT_DISABLED_MSG, parse_mode="HTML")
    
async def activate_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    if chat.type not in ['group', 'supergroup']: return
    if is_group_activated(chat.id):
        await update.message.reply_text("<tg-emoji emoji-id=\"5393121447822510594\">✅</tg-emoji> 𝗔𝗹𝗿𝗲𝗮𝗱𝘆 𝗮𝗰𝘁𝗶𝘃𝗮𝘁𝗲𝗱 <tg-emoji emoji-id=\"5837175591115167366\">✅</tg-emoji>", parse_mode="HTML")
    else:
        activate_group(chat.id)
        await update.message.reply_text("<tg-emoji emoji-id=\"5469843333394221689\">🚀</tg-emoji> 𝗔𝗰𝘁𝗶𝘃𝗮𝘁𝗲𝗱 <tg-emoji emoji-id=\"5368654333397199941\">🚀</tg-emoji>\n<tg-emoji emoji-id=\"5830394890021770129\">📎</tg-emoji> 𝗦𝗲𝗻𝗱 𝗜𝗻𝘀𝘁𝗮𝗴𝗿𝗮𝗺 𝗹𝗶𝗻𝗸 𝗻𝗼𝘄 <tg-emoji emoji-id=\"5294347069849359957\">📎</tg-emoji>", parse_mode="HTML")

async def settings_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    await update.message.reply_text(SETTINGS_TEXT, parse_mode="HTML", disable_web_page_preview=True)

async def ego_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: 
        await update.message.reply_text(
            f'<tg-emoji emoji-id="5353060840448727534">❌</tg-emoji> 𝘼𝙘𝙘𝙚𝙨𝙨 𝘿𝙚𝙣𝙞𝙚𝙙！',
            parse_mode="HTML"
        )
        return
    
    add_emoji_btn = InlineKeyboardMarkup([
        [InlineKeyboardButton(
            "𝐀𝐝𝐝 𝐄𝐦𝐨𝐣𝐢",
            callback_data="owner_add_emoji",
            style=get_random_style(),
            icon_custom_emoji_id="5352555352862765789"
        )]
    ])
    await update.message.reply_text(
        f'<tg-emoji emoji-id="5352540225987943305">👑</tg-emoji> <b>𓆩#ＫＡＲＴＩＫ𓆪</b>',
        reply_markup=add_emoji_btn,
        parse_mode="HTML"
    )
    
async def bot_added_to_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"DEBUG: bot_added_to_group called!")
    chat = update.effective_chat
    bot_user = await context.bot.get_me()
    print(f"DEBUG: Bot ID: {bot_user.id}, Chat: {chat.title}")
    
    # Bot disabled hone pe alag message
    if not is_bot_enabled():
        if update.message and update.message.new_chat_members:
            for member in update.message.new_chat_members:
                if member.id == bot_user.id:
                    try: 
                        await update.message.reply_text(BOT_DISABLED_MSG, parse_mode="HTML")
                    except: pass
                    break
        return
    
    # Check if bot was added via new_chat_members
    if update.message and update.message.new_chat_members:
        for member in update.message.new_chat_members:
            if member.id == bot_user.id:
                kb = InlineKeyboardMarkup([[InlineKeyboardButton("◆ ➪ ˹𝜟𝙙𝙙 𝜯𝜣 𝑮𝜞𝜭𝑼𝝆˼ ♪☬", url=f"https://t.me/{context.bot.username}?startgroup=true", style=get_random_style(), icon_custom_emoji_id=get_random_emoji_id())]])
                try:
                    # Try to send welcome video if available
                    video_data = get_random_video()
                    if video_data and os.path.exists(video_data["path"]):
                        await update.message.reply_video(
                            video=open(video_data["path"], 'rb'),
                            caption=GROUP_WELCOME.replace("{chat_title}", chat.title or "Group"),
                            parse_mode="HTML",
                            reply_markup=kb
                        )
                    else:
                        await update.message.reply_text(
                            GROUP_WELCOME.replace("{chat_title}", chat.title or "Group"),
                            parse_mode="HTML",
                            reply_markup=kb
                        )
                    print(f"DEBUG: Group welcome message sent!")
                except Exception as e:
                    print(f"ERROR sending group welcome: {e}")
                break

async def disable_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    set_bot_state(False)
    await update.message.reply_text("<tg-emoji emoji-id=\"6269372661143441677\">🚫</tg-emoji> 𝗗𝗜𝗦𝗔𝗕𝗟𝗘𝗗 <tg-emoji emoji-id=\"5816642280185929122\">🚫</tg-emoji>", parse_mode="HTML")

async def enable_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    set_bot_state(True)
    await update.message.reply_text("<tg-emoji emoji-id=\"5368451104134685900\">✅</tg-emoji> 𝗘𝗡𝗔𝗕𝗟𝗘𝗗 <tg-emoji emoji-id=\"5064672027248427816\">✅</tg-emoji>", parse_mode="HTML")

async def add_emoji_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    
    # Sticker reply ko ignore karo - sirf emoji ID allow karo
    if update.message.reply_to_message and update.message.reply_to_message.sticker:
        await update.message.reply_text("<tg-emoji emoji-id=\"6269566961168944843\">❌</tg-emoji> 𝗨𝘀𝗲  /𝗮𝗱𝗱𝘀𝘁𝗶𝗰𝗸𝗲𝗿 𝗳𝗼𝗿 𝘀𝘁𝗶𝗰𝗸𝗲𝗿𝘀 <tg-emoji emoji-id=\"5406835879694050722\">🖇️</tg-emoji>", parse_mode="HTML")
        return
    
    # Command ke saath emoji ID di hai?
    parts = update.message.text.split()
    if len(parts) >= 2:
        emoji_id = parts[1].strip()
        if emoji_id.isdigit() and len(emoji_id) >= 15:
            s, t = add_emoji_db(emoji_id)
            if s:
                await update.message.reply_text(f"<tg-emoji emoji-id=\"5325888970368762082\">✅</tg-emoji> 𝗘𝗠𝗢𝗝𝗜 𝗜𝗗 𝗔𝗗𝗗𝗘𝗗 <tg-emoji emoji-id=\"5773652573835758861\">📋</tg-emoji>{t}<tg-emoji emoji-id=\"5773706269516893619\">📋</tg-emoji>", parse_mode="HTML")
                await update.message.reply_text(f'<tg-emoji emoji-id="{emoji_id}">🌟</tg-emoji>', parse_mode="HTML")
            else:
                await update.message.reply_text("<tg-emoji emoji-id=\"5352542184493031170\">❌</tg-emoji> 𝗔𝗹𝗿𝗲𝗮𝗱𝘆 𝗘𝘅𝗶𝘀𝘁𝘀 <tg-emoji emoji-id=\"5352703271536454445\">❌</tg-emoji>", parse_mode="HTML")
            return
        else:
            await update.message.reply_text("𝗜𝗻𝘃𝗮𝗹𝗶𝗱 𝗘𝗺𝗼𝗷𝗶 𝗜𝗗 <tg-emoji emoji-id=\"5420323339723881652\">❌</tg-emoji>", parse_mode="HTML")
            return
    
    # Kuch nahi diya
    await update.message.reply_text(
        "<tg-emoji emoji-id=\"5017088445353296841\">🔎</tg-emoji> Ｕｓａｇｅ ➪\n"
        "𝟏. ˹/addemoji˼ ˹𝐞𝐦𝐨𝐣𝐢_𝐢𝐝♪ → 𝚺𝒎𝛉𝒋𝒊 𝚰𝐃 𝒔𝛆 𝛂𝛅𝛅 𝛋𝛂𝛄𝛉 <tg-emoji emoji-id=\"5337135183319542200\">✅</tg-emoji>\n"
        "𝟐. 𝐒𝛕𝒊𝛓𝛋𝛆𝛄 𝛒𝛆 𝛄𝛆𝛒𝛊𝛙 𝛋𝛂𝛄𝛋𝛆 ˹/addemoji˼ → 𝘚𝘵𝘪𝘤𝘬𝘦𝘳 𝘢𝘥𝘥 𝘬𝘢𝘳𝘰 <tg-emoji emoji-id=\"5933931304394428667\">✅</tg-emoji>",
        parse_mode="HTML"
    )
async def remove_emoji_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    try:
        idx = int(update.message.text.split()[1]) - 1
        s, t = remove_emoji_db(idx)
        await update.message.reply_text(f"<tg-emoji emoji-id=\"5352542184493031170\">✅</tg-emoji> 𝗥𝗲𝗺𝗼𝘃𝗲𝗱 ༼{t}༽ <tg-emoji emoji-id=\"5352542184493031170\">✅</tg-emoji>" if s else f"<tg-emoji emoji-id=\"6260436084035949371\">❌</tg-emoji> 𝗜𝗻𝘃𝗮𝗹𝗶𝗱 Ｔｏｔａｌ： ༼{t}༽ <tg-emoji emoji-id=\"5814637011495031358\">❌</tg-emoji>", parse_mode="HTML")
    except: await update.message.reply_text("<tg-emoji emoji-id=\"5310097750010901912\">🌟</tg-emoji><tg-emoji emoji-id=\"5321450791683241246\">🌟</tg-emoji><tg-emoji emoji-id=\"5294029641701407930\">🌟</tg-emoji><tg-emoji emoji-id=\"5327938799345349736\">🌟</tg-emoji><tg-emoji emoji-id=\"5334637865995352639\">🌟</tg-emoji> /removeemoji", parse_mode="HTML")

async def list_emojis_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    emojis = get_emojis()
    if not emojis: await update.message.reply_text("<tg-emoji emoji-id=\"6098344001105038370\">📭</tg-emoji> 𝗡𝗼 𝗲𝗺𝗼𝗷𝗶𝘀 <tg-emoji emoji-id=\"6098344001105038370\">📭</tg-emoji>", parse_mode="HTML"); return
    text = "<tg-emoji emoji-id=\"5352555352862765789\">🎨</tg-emoji> 𝗘𝗠𝗢𝗝𝗜𝗦\n" + "\n".join([f"<b>{i+1}.</b> <code>{e[:30]}</code>" for i, e in enumerate(emojis)])
    await update.message.reply_text(text + f"\n\n<tg-emoji emoji-id=\"5352555352862765789\">🔹</tg-emoji> 𝗧𝗼𝘁𝗮𝗹 {len(emojis)}", parse_mode="HTML")

async def add_sticker_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not update.message.reply_to_message or not update.message.reply_to_message.sticker:
        await update.message.reply_text("⎘ 𝗥𝗲𝗽𝗹𝘆 𝘁𝗼 𝘀𝘁𝗶𝗰𝗸𝗲𝗿"); return
    s, t = add_sticker_db(update.message.reply_to_message.sticker.file_id)
    await update.message.reply_text(f"<tg-emoji emoji-id=\"5442874134231008257\">✅</tg-emoji> 𝗔𝗗𝗗𝗘𝗗 ༼{t}༽ <tg-emoji emoji-id=\"5442874134231008257\">✅</tg-emoji>" if s else f"<tg-emoji emoji-id=\"5438630285635757876\">❌</tg-emoji> 𝗘𝘅𝗶𝘀𝘁𝘀 <tg-emoji emoji-id=\"5438630285635757876\">❌</tg-emoji>", parse_mode="HTML")

async def remove_sticker_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    try:
        idx = int(update.message.text.split()[1]) - 1
        s, t = remove_sticker_db(idx)
        await update.message.reply_text(f"<tg-emoji emoji-id=\"5442874134231008257\">✅</tg-emoji> 𝗥𝗲𝗺𝗼𝘃𝗲𝗱 ༼{t}༽ <tg-emoji emoji-id=\"5442874134231008257\">✅</tg-emoji>" if s else f"<tg-emoji emoji-id=\"5438630285635757876\">❌</tg-emoji> 𝗜𝗻𝘃𝗮𝗹𝗶𝗱 Ｔｏｔａｌ： ༼{t}༽ <tg-emoji emoji-id=\"5438630285635757876\">❌</tg-emoji>", parse_mode="HTML")
    except: await update.message.reply_text("<tg-emoji emoji-id=\"5310097750010901912\">🌟</tg-emoji><tg-emoji emoji-id=\"5321450791683241246\">🌟</tg-emoji><tg-emoji emoji-id=\"5294029641701407930\">🌟</tg-emoji><tg-emoji emoji-id=\"5327938799345349736\">🌟</tg-emoji><tg-emoji emoji-id=\"5334637865995352639\">🌟</tg-emoji> /removesticker", parse_mode="HTML")
async def list_stickers_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    stickers = get_stickers()
    if not stickers: await update.message.reply_text("<tg-emoji emoji-id=\"5438630285635757876\">📭</tg-emoji> 𝗡𝗼 𝘀𝘁𝗶𝗰𝗸𝗲𝗿𝘀 <tg-emoji emoji-id=\"5438630285635757876\">📭</tg-emoji>", parse_mode="HTML"); return
    text = "❄ 𝗦𝗧𝗜𝗖𝗞𝗘𝗥𝗦\n" + "\n".join([f"**{i+1}.** `{s[:25]}`" for i, s in enumerate(stickers)])
    await update.message.reply_text(text + f"\n\n🔹 𝗧𝗼𝘁𝗮𝗹 {len(stickers)}", parse_mode="Markdown")

async def add_video_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not update.message.reply_to_message or not update.message.reply_to_message.video:
        await update.message.reply_text("⎘ 𝗥𝗲𝗽𝗹𝘆 𝘁𝗼 𝘃𝗶𝗱𝗲𝗼")
        return
    m = await update.message.reply_text("<tg-emoji emoji-id=\"5357315181649076022\">📂</tg-emoji> 𝗔𝗱𝗱𝗶𝗻𝗴 𝗩𝗶𝗱𝗲𝗼... <tg-emoji emoji-id=\"5357315181649076022\">📂</tg-emoji>", parse_mode="HTML")
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
            f"<tg-emoji emoji-id=\"5352901995378252828\">✅</tg-emoji> 𝐕𝐈𝐃𝐄𝐎 𝐀𝐃𝐃𝐄𝐃 𝐒𝐔𝐂𝐂𝐄𝐒𝐒𝐅𝐔𝐋𝐋𝐘 <tg-emoji emoji-id=\"5352901995378252828\">✅</tg-emoji>\n\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"<tg-emoji emoji-id=\"6289762537344864636\">🆔</tg-emoji> Ｖｉｄｅｏ ＩＤ ： {vid}\n"
            f"<tg-emoji emoji-id=\"5150269119139939490\">📁</tg-emoji> Ｎａｍｅ ： {os.path.basename(fp)[:30]}\n"
            f"<tg-emoji emoji-id=\"5192706539940488777\">📹</tg-emoji> Ｔｏｔａｌ Ｖｉｄｅｏｓ ： {total}\n"
            f"<tg-emoji emoji-id=\"5267421370114914946\">⏱️</tg-emoji> Ｄｕｒａｔｉｏｎ ： {duration}\n"
            f"━━━━━━━━━━━━━━━━━━━\n\n"
            f"<tg-emoji emoji-id=\"5260547274957672345\">🎲</tg-emoji> 𝘝𝘪𝘥𝘦𝘰 𝘸𝘪𝘭𝘭 𝘱𝘭𝘢𝘺 𝘳𝘢𝘯𝘥𝘰𝘮𝘭𝘺 𝘰𝘯 𝘸𝘦𝘭𝘤𝘰𝘮𝘦!\n"
            f"<tg-emoji emoji-id=\"5352765106180610755\">📋</tg-emoji> /videos ｔｏ ｓｅｅ ａｌｌ ｖｉｄｅｏ"
        )
        await m.edit_text(text, parse_mode="HTML")
    except Exception as e:
        await m.edit_text(f"<tg-emoji emoji-id=\"5438630285635757876\">❌</tg-emoji> Ｅｒｒｏｒ ： ༼e༽", parse_mode="HTML")

async def del_video_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    try:
        vid = int(update.message.text.split()[1])
        s, t = delete_video_db(vid)
        await update.message.reply_text(f"<tg-emoji emoji-id=\"5337135183319542200\">✅</tg-emoji> Ｄｅｌｅｔｅｄ！ ༼{t}༽ <tg-emoji emoji-id=\"5337135183319542200\">✅</tg-emoji>" if s else f"<tg-emoji emoji-id=\"5017088445353296841\">❌</tg-emoji> Ｎｏｔ ｆｏｕｎｄ！ <tg-emoji emoji-id=\"5017088445353296841\">❌</tg-emoji>", parse_mode="HTML")
    except:
        await update.message.reply_text("Ｕｓｅ ： /delvideo <tg-emoji emoji-id=\"6289762537344864636\">🆔</tg-emoji>", parse_mode="HTML")

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

# ═══════════════ CHANNEL COMMANDS ═══════════════

async def add_channel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text(
            f'<tg-emoji emoji-id="5353060840448727534">❌</tg-emoji> <b>𝙊𝙣𝙡𝙮 𝙊𝙬𝙣𝙚𝙧 𝘾𝙖𝙣 𝙐𝙨𝙚 𝙏𝙝𝙞𝙨 𝘾𝙤𝙢𝙢𝙖𝙣𝙙</b> <tg-emoji emoji-id="5353060840448727534">❌</tg-emoji>',
            parse_mode="HTML"
        )
        return
    
    try:
        channel_input = update.message.text.split()[1].strip()
        channel_input = channel_input.replace('@', '')
        
        if not channel_input.startswith('-100'):
            try:
                chat = await context.bot.get_chat(f"@{channel_input}")
                channel_id = str(chat.id)
            except:
                await update.message.reply_text(
                    f'<tg-emoji emoji-id="5929358014627713883">❌</tg-emoji> <b>𝙄𝙣𝙫𝙖𝙡𝙞𝙙 𝘾𝙝𝙖𝙣𝙣𝙚𝙡! 𝙐𝙨𝙚 @𝙪𝙨𝙚𝙧𝙣𝙖𝙢𝙚 𝙤𝙧 -100𝙭𝙭𝙭𝙭</b> <tg-emoji emoji-id="5929358014627713883">❌</tg-emoji>',
                    parse_mode="HTML"
                )
                return
        else:
            channel_id = channel_input
        
        success, total = add_channel_db(channel_id)
        
        if success:
            try:
                channel_info = await context.bot.get_chat(int(channel_id))
                channel_name = channel_info.title or "Unknown"
            except:
                channel_name = channel_id
            
            await update.message.reply_text(
                f'<tg-emoji emoji-id="6226399941388928924">✅</tg-emoji> <b>𝘾𝙝𝙖𝙣𝙣𝙚𝙡 𝘼𝙙𝙙𝙚𝙙 𝙎𝙪𝙘𝙘𝙚𝙨𝙨𝙛𝙪𝙡𝙡𝙮</b> <tg-emoji emoji-id="6127410617482484040">✅</tg-emoji>\n'
                f'<tg-emoji emoji-id="5841494459904168607">📢</tg-emoji> <b>𝙉𝙖𝙢𝙚:</b> {channel_name}\n'
                f'<tg-emoji emoji-id="6289762537344864636">🆔</tg-emoji> <b>𝙄𝘿:</b> <code>{channel_id}</code>\n'
                f'<tg-emoji emoji-id="6172671064452111943">📊</tg-emoji> <b>𝙏𝙤𝙩𝙖𝙡 𝘾𝙝𝙖𝙣𝙣𝙚𝙡𝙨:</b> {total}',
                parse_mode="HTML"
            )
        else:
            await update.message.reply_text(
                f'<tg-emoji emoji-id="5334637865995352639">⚠️</tg-emoji> <b>𝘾𝙝𝙖𝙣𝙣𝙚𝙡 𝘼𝙡𝙧𝙚𝙖𝙙𝙮 𝙀𝙭𝙞𝙨𝙩𝙨!</b> <tg-emoji emoji-id="5334637865995352639">⚠️</tg-emoji>',
                parse_mode="HTML"
            )
            
    except IndexError:
        await update.message.reply_text(
            f'<tg-emoji emoji-id="6170160969600212116">📝</tg-emoji> <b>𝙐𝙨𝙖𝙜𝙚:</b>\n'
            f'<tg-emoji emoji-id="5237707944547592720">🌟</tg-emoji> <code>/addchannel @username</code>\n'
            f'<tg-emoji emoji-id="5233540769708526063">🌟</tg-emoji> <code>/addchannel -1001234567890</code>',
            parse_mode="HTML"
        )

async def remove_channel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text(
            f'<tg-emoji emoji-id="5353060840448727534">❌</tg-emoji> <b>𝙊𝙣𝙡𝙮 𝙊𝙬𝙣𝙚𝙧 𝘾𝙖𝙣 𝙐𝙨𝙚 𝙏𝙝𝙞𝙨 𝘾𝙤𝙢𝙢𝙖𝙣𝙙</b> <tg-emoji emoji-id="5353060840448727534">❌</tg-emoji>',
            parse_mode="HTML"
        )
        return
    
    try:
        channel_id = update.message.text.split()[1].strip()
        success, total = remove_channel_db(channel_id)
        
        if success:
            await update.message.reply_text(
                f'<tg-emoji emoji-id="5352542184493031170">✅</tg-emoji> <b>𝘾𝙝𝙖𝙣𝙣𝙚𝙡 𝙍𝙚𝙢𝙤𝙫𝙚𝙙 𝙎𝙪𝙘𝙘𝙚𝙨𝙨𝙛𝙪𝙡𝙡𝙮</b> <tg-emoji emoji-id="5352542184493031170">✅</tg-emoji>\n'
                f'<tg-emoji emoji-id="6172671064452111943">📊</tg-emoji> <b>𝙍𝙚𝙢𝙖𝙞𝙣𝙞𝙣𝙜 𝘾𝙝𝙖𝙣𝙣𝙚𝙡𝙨:</b> {total}',
                parse_mode="HTML"
            )
        else:
            await update.message.reply_text(
                f'<tg-emoji emoji-id="5929358014627713883">❌</tg-emoji> <b>𝘾𝙝𝙖𝙣𝙣𝙚𝙡 𝙉𝙤𝙩 𝙁𝙤𝙪𝙣𝙙!</b> <tg-emoji emoji-id="5929358014627713883">❌</tg-emoji>',
                parse_mode="HTML"
            )
            
    except IndexError:
        await update.message.reply_text(
            f'<tg-emoji emoji-id="6170160969600212116">📝</tg-emoji> <b>𝙐𝙨𝙖𝙜𝙚:</b> <code>/removechannel -1001234567890</code>',
            parse_mode="HTML"
        )

async def list_channels_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text(
            f'<tg-emoji emoji-id="5353060840448727534">❌</tg-emoji> <b>𝙊𝙣𝙡𝙮 𝙊𝙬𝙣𝙚𝙧 𝘾𝙖𝙣 𝙐𝙨𝙚 𝙏𝙝𝙞𝙨 𝘾𝙤𝙢𝙢𝙖𝙣𝙙</b> <tg-emoji emoji-id="5353060840448727534">❌</tg-emoji>',
            parse_mode="HTML"
        )
        return
    
    channels = get_channels()
    if not channels:
        await update.message.reply_text(
            f'<tg-emoji emoji-id="6098344001105038370">📭</tg-emoji> <b>𝙉𝙤 𝘾𝙝𝙖𝙣𝙣𝙚𝙡𝙨 𝘼𝙙𝙙𝙚𝙙 𝙔𝙚𝙩!</b> <tg-emoji emoji-id="6098344001105038370">📭</tg-emoji>\n'
            f'<tg-emoji emoji-id="5237707944547592720">🌟</tg-emoji> <b>𝙐𝙨𝙚</b> <code>/addchannel</code> <b>𝙩𝙤 𝙖𝙙𝙙</b>',
            parse_mode="HTML"
        )
        return
    
    text = f'<tg-emoji emoji-id="5841494459904168607">📢</tg-emoji> <b>𝘼𝘿𝘿𝙀𝘿 𝘾𝙃𝘼𝙉𝙉𝙀𝙇𝙎:</b>\n\n'
    
    for i, ch_id in enumerate(channels, 1):
        try:
            chat = await context.bot.get_chat(int(ch_id))
            name = chat.title or "Unknown"
            text += f'<tg-emoji emoji-id="5233303721873523335">🌟</tg-emoji> <b>{i}.</b> {name} ➪ <code>{ch_id}</code>\n'
        except:
            text += f'<tg-emoji emoji-id="5334637865995352639">⚠️</tg-emoji> <b>{i}.</b> <code>{ch_id}</code> (𝙄𝙣𝙖𝙘𝙘𝙚𝙨𝙨𝙞𝙗𝙡𝙚)\n'
    
    text += f'\n<tg-emoji emoji-id="6172671064452111943">📊</tg-emoji> <b>𝙏𝙤𝙩𝙖𝙡 𝘾𝙝𝙖𝙣𝙣𝙚𝙡𝙨:</b> {len(channels)}'
    
    await update.message.reply_text(text, parse_mode="HTML")

async def send_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.reply_to_message:
        await update.message.reply_text(
            f'<tg-emoji emoji-id="6170160969600212116">📝</tg-emoji> <b>𝙍𝙚𝙥𝙡𝙮 𝙠𝙖𝙧𝙤 𝙠𝙞𝙨𝙞 𝙢𝙚𝙨𝙨𝙖𝙜𝙚 𝙥𝙚 𝙖𝙪𝙧</b> <code>/send</code> <b>𝙠𝙖𝙧𝙤!</b>\n'
            f'<tg-emoji emoji-id="5237707944547592720">🌟</tg-emoji> <b>𝙑𝙞𝙙𝙚𝙤/𝙋𝙝𝙤𝙩𝙤/𝘼𝙪𝙙𝙞𝙤/𝙏𝙚𝙭𝙩 𝙨𝙖𝙗 𝙘𝙝𝙖𝙡𝙚𝙜𝙖</b>',
            parse_mode="HTML"
        )
        return
    
    channels = get_channels()
    if not channels:
        await update.message.reply_text(
            f'<tg-emoji emoji-id="6098344001105038370">📭</tg-emoji> <b>𝙆𝙤𝙞 𝘾𝙝𝙖𝙣𝙣𝙚𝙡 𝘼𝙙𝙙 𝙉𝙖𝙝𝙞 𝙃𝙖𝙞!</b>\n'
            f'<tg-emoji emoji-id="5237707944547592720">🌟</tg-emoji> <b>𝙋𝙚𝙝𝙡𝙚</b> <code>/addchannel @username</code> <b>𝙠𝙖𝙧𝙤</b>',
            parse_mode="HTML"
        )
        return
    
    replied_msg = update.message.reply_to_message
    
    loading_emojis = [
        "5357315181649076022", "5294261750324042913", "5293990986995768044",
        "5275974823254725631", "5384337002751630535", "5325888970368762082"
    ]
    load_emoji = random.choice(loading_emojis)
    
    status_msg = await update.message.reply_text(
        f'<tg-emoji emoji-id="{load_emoji}">📤</tg-emoji> <b>𝙎𝙚𝙣𝙙𝙞𝙣𝙜 𝙩𝙤 {len(channels)} 𝘾𝙝𝙖𝙣𝙣𝙚𝙡𝙨...</b> <tg-emoji emoji-id="{load_emoji}">📤</tg-emoji>',
        parse_mode="HTML"
    )
    
    success_count = 0
    failed_channels = []
    forward_used = False
    
    for ch_id in channels:
        try:
            # ⭐ PEHLE FORWARD TRY KARO (EMOJI SAFE) - Bot apne channel pe forward kar sakta hai
            await context.bot.forward_message(
                chat_id=int(ch_id),
                from_chat_id=update.effective_chat.id,
                message_id=replied_msg.message_id,
                disable_notification=True
            )
            forward_used = True
            success_count += 1
            await asyncio.sleep(1)
            
        except Exception as e:
            # Forward fail hua - direct send try karo
            try:
                msg = replied_msg
                
                # TEXT
                if msg.text and not msg.photo and not msg.video and not msg.audio and not msg.voice and not msg.document and not msg.sticker and not msg.animation:
                    await context.bot.send_message(
                        chat_id=int(ch_id),
                        text=msg.text,
                        entities=msg.entities,
                        reply_markup=msg.reply_markup
                    )
                
                # PHOTO
                elif msg.photo:
                    await context.bot.send_photo(
                        chat_id=int(ch_id),
                        photo=msg.photo[-1].file_id,
                        caption=msg.caption or "",
                        caption_entities=msg.caption_entities,
                        reply_markup=msg.reply_markup
                    )
                
                # VIDEO
                elif msg.video:
                    await context.bot.send_video(
                        chat_id=int(ch_id),
                        video=msg.video.file_id,
                        caption=msg.caption or "",
                        caption_entities=msg.caption_entities,
                        reply_markup=msg.reply_markup,
                        supports_streaming=True
                    )
                
                # AUDIO
                elif msg.audio:
                    await context.bot.send_audio(
                        chat_id=int(ch_id),
                        audio=msg.audio.file_id,
                        caption=msg.caption or "",
                        caption_entities=msg.caption_entities,
                        reply_markup=msg.reply_markup,
                        title=msg.audio.title,
                        performer=msg.audio.performer
                    )
                
                # ANIMATION
                elif msg.animation:
                    await context.bot.send_animation(
                        chat_id=int(ch_id),
                        animation=msg.animation.file_id,
                        caption=msg.caption or "",
                        caption_entities=msg.caption_entities,
                        reply_markup=msg.reply_markup
                    )
                
                # STICKER
                elif msg.sticker:
                    await context.bot.send_sticker(
                        chat_id=int(ch_id),
                        sticker=msg.sticker.file_id,
                        reply_markup=msg.reply_markup
                    )
                
                # VOICE
                elif msg.voice:
                    await context.bot.send_voice(
                        chat_id=int(ch_id),
                        voice=msg.voice.file_id,
                        caption=msg.caption or "",
                        caption_entities=msg.caption_entities,
                        reply_markup=msg.reply_markup
                    )
                
                # DOCUMENT
                elif msg.document:
                    await context.bot.send_document(
                        chat_id=int(ch_id),
                        document=msg.document.file_id,
                        caption=msg.caption or "",
                        caption_entities=msg.caption_entities,
                        reply_markup=msg.reply_markup
                    )
                
                # VIDEO NOTE
                elif msg.video_note:
                    await context.bot.send_video_note(
                        chat_id=int(ch_id),
                        video_note=msg.video_note.file_id,
                        reply_markup=msg.reply_markup
                    )
                
                # POLL
                elif msg.poll:
                    await context.bot.forward_message(
                        chat_id=int(ch_id),
                        from_chat_id=update.effective_chat.id,
                        message_id=msg.message_id,
                        disable_notification=True
                    )
                
                else:
                    await context.bot.forward_message(
                        chat_id=int(ch_id),
                        from_chat_id=update.effective_chat.id,
                        message_id=msg.message_id,
                        disable_notification=True
                    )
                
                success_count += 1
                
            except Exception as e2:
                failed_channels.append(ch_id)
                logging.error(f"All methods failed for {ch_id}: {e} | {e2}")
            
            await asyncio.sleep(1)
    
    if success_count == len(channels):
        result_emoji = "6226399941388928924"
        result_text = (
            f'<tg-emoji emoji-id="{result_emoji}">✅</tg-emoji> <b>𝙎𝙪𝙘𝙘𝙚𝙨𝙨𝙛𝙪𝙡𝙡𝙮 𝙎𝙚𝙣𝙩!</b> <tg-emoji emoji-id="{result_emoji}">✅</tg-emoji>\n'
            f'<tg-emoji emoji-id="6172671064452111943">📊</tg-emoji> <b>{success_count}/{len(channels)} 𝘾𝙝𝙖𝙣𝙣𝙚𝙡𝙨</b>'
        )
    else:
        result_emoji = "5334637865995352639"
        result_text = (
            f'<tg-emoji emoji-id="{result_emoji}">⚠️</tg-emoji> <b>𝙋𝙖𝙧𝙩𝙞𝙖𝙡𝙡𝙮 𝙎𝙚𝙣𝙩!</b> <tg-emoji emoji-id="{result_emoji}">⚠️</tg-emoji>\n'
            f'<tg-emoji emoji-id="6226399941388928924">✅</tg-emoji> <b>𝙎𝙪𝙘𝙘𝙚𝙨𝙨:</b> {success_count}\n'
            f'<tg-emoji emoji-id="5929358014627713883">❌</tg-emoji> <b>𝙁𝙖𝙞𝙡𝙚𝙙:</b> {len(failed_channels)}'
        )
    
    await status_msg.edit_text(result_text, parse_mode="HTML")
    
async def auto_forward_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text(
            f'<tg-emoji emoji-id="5353060840448727534">❌</tg-emoji> <b>𝙊𝙣𝙡𝙮 𝙊𝙬𝙣𝙚𝙧 𝘾𝙖𝙣 𝙐𝙨𝙚 𝙏𝙝𝙞𝙨 𝘾𝙤𝙢𝙢𝙖𝙣𝙙</b> <tg-emoji emoji-id="5353060840448727534">❌</tg-emoji>',
            parse_mode="HTML"
        )
        return
    
    try:
        action = update.message.text.split()[1].lower()
        if action == "on":
            set_auto_forward(True)
            await update.message.reply_text(
                f'<tg-emoji emoji-id="5368451104134685900">✅</tg-emoji> <b>𝘼𝙪𝙩𝙤 𝙁𝙤𝙧𝙬𝙖𝙧𝙙 𝙊𝙉 𝙃𝙤 𝙂𝙖𝙮𝙖!</b> <tg-emoji emoji-id="5064672027248427816">✅</tg-emoji>\n'
                f'<tg-emoji emoji-id="5841494459904168607">📢</tg-emoji> <b>𝘼𝙗 𝙝𝙖𝙧 𝙙𝙤𝙬𝙣𝙡𝙤𝙖𝙙 𝙘𝙝𝙖𝙣𝙣𝙚𝙡 𝙥𝙚 𝙗𝙝𝙞 𝙟𝙖𝙮𝙚𝙜𝙖</b>',
                parse_mode="HTML"
            )
        elif action == "off":
            set_auto_forward(False)
            await update.message.reply_text(
                f'<tg-emoji emoji-id="6269372661143441677">🚫</tg-emoji> <b>𝘼𝙪𝙩𝙤 𝙁𝙤𝙧𝙬𝙖𝙧𝙙 𝙊𝙁𝙁 𝙃𝙤 𝙂𝙖𝙮𝙖!</b> <tg-emoji emoji-id="5816642280185929122">🚫</tg-emoji>',
                parse_mode="HTML"
            )
        else:
            raise ValueError
    except:
        is_on = is_auto_forward_enabled()
        status = "𝙊𝙉 ✅" if is_on else "𝙊𝙁𝙁 🚫"
        status_emoji = "5368451104134685900" if is_on else "6269372661143441677"
        
        await update.message.reply_text(
            f'<tg-emoji emoji-id="{status_emoji}">⚙️</tg-emoji> <b>𝘼𝙪𝙩𝙤 𝙁𝙤𝙧𝙬𝙖𝙧𝙙 𝙎𝙩𝙖𝙩𝙪𝙨:</b> {status}\n\n'
            f'<tg-emoji emoji-id="6170160969600212116">📝</tg-emoji> <b>𝙐𝙨𝙖𝙜𝙚:</b>\n'
            f'<tg-emoji emoji-id="5237707944547592720">🌟</tg-emoji> <code>/autoforward on</code> - 𝙀𝙣𝙖𝙗𝙡𝙚\n'
            f'<tg-emoji emoji-id="5233540769708526063">🌟</tg-emoji> <code>/autoforward off</code> - 𝘿𝙞𝙨𝙖𝙗𝙡𝙚',
            parse_mode="HTML"
        )

async def autosendvoice_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    try:
        action = update.message.text.split()[1].lower()
        if action == "on":
            set_auto_send_voice(user_id, True)
            await update.message.reply_text(
                f'<tg-emoji emoji-id="5368451104134685900">✅</tg-emoji> <b>𝘼𝙪𝙩𝙤 𝙎𝙚𝙣𝙙 𝙑𝙤𝙞𝙘𝙚 𝙊𝙉!</b> <tg-emoji emoji-id="5064672027248427816">✅</tg-emoji>\n'
                f'<tg-emoji emoji-id="5841494459904168607">🎵</tg-emoji> <b>𝘼𝙗 𝙖𝙖𝙥𝙠𝙖 𝙝𝙖𝙧 𝙖𝙪𝙙𝙞𝙤 𝙘𝙝𝙖𝙣𝙣𝙚𝙡 𝙥𝙚 𝙗𝙝𝙞 𝙟𝙖𝙮𝙚𝙜𝙖</b>',
                parse_mode="HTML"
            )
        elif action == "off":
            set_auto_send_voice(user_id, False)
            await update.message.reply_text(
                f'<tg-emoji emoji-id="6269372661143441677">🚫</tg-emoji> <b>𝘼𝙪𝙩𝙤 𝙎𝙚𝙣𝙙 𝙑𝙤𝙞𝙘𝙚 𝙊𝙁𝙁!</b> <tg-emoji emoji-id="5816642280185929122">🚫</tg-emoji>',
                parse_mode="HTML"
            )
        else:
            raise ValueError
    except:
        is_on = is_auto_send_voice_enabled(user_id)
        status = "𝙊𝙉 ✅" if is_on else "𝙊𝙁𝙁 🚫"
        status_emoji = "5368451104134685900" if is_on else "6269372661143441677"
        
        await update.message.reply_text(
            f'<tg-emoji emoji-id="{status_emoji}">⚙️</tg-emoji> <b>𝘼𝙪𝙩𝙤 𝙎𝙚𝙣𝙙 𝙑𝙤𝙞𝙘𝙚:</b> {status}\n\n'
            f'<tg-emoji emoji-id="6170160969600212116">📝</tg-emoji> <b>𝙐𝙨𝙖𝙜𝙚:</b>\n'
            f'<tg-emoji emoji-id="5237707944547592720">🌟</tg-emoji> <code>/autosendvoice on</code> - 𝙀𝙣𝙖𝙗𝙡𝙚\n'
            f'<tg-emoji emoji-id="5233540769708526063">🌟</tg-emoji> <code>/autosendvoice off</code> - 𝘿𝙞𝙨𝙖𝙗𝙡𝙚',
            parse_mode="HTML"
        )
# ═══════════════ MESSAGE HANDLER ═══════════════

async def process_download(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
    chat_id = update.effective_chat.id; user_id = update.effective_user.id
    shortcode = InstaDownloader.get_shortcode(url)
    import uuid
    unique_id = str(uuid.uuid4())[:8]
    cache_key = f"{chat_id}_{user_id}_{shortcode}"
    
    sticker_id = get_random_sticker(); sticker_msg = None
    if sticker_id:
        try: sticker_msg = await context.bot.send_sticker(chat_id, sticker_id)
        except: sticker_msg = None
    
    msg = await update.message.reply_text("<tg-emoji emoji-id=\"5454415424319931791\">⏳</tg-emoji> 𝗣𝗿𝗼𝗰𝗲𝘀𝘀𝗶𝗻𝗴...", parse_mode="HTML")
    
    async with download_semaphore:
        try:
            is_reel = '/reel/' in url or '/tv/' in url
            await msg.edit_text("<tg-emoji emoji-id=\"5294261750324042913\">📥</tg-emoji><tg-emoji emoji-id=\"5293990986995768044\">📥</tg-emoji> 𝗗𝗼𝘄𝗻𝗹𝗼𝗮𝗱𝗶𝗻𝗴 𝗩𝗶𝗱𝗲𝗼..." if is_reel else "<tg-emoji emoji-id=\"5294261750324042913\">📥</tg-emoji><tg-emoji emoji-id=\"5293990986995768044\">📥</tg-emoji> 𝗗𝗼𝘄𝗻𝗹𝗼𝗮𝗱𝗶𝗻𝗴 𝗣𝗵𝗼𝘁𝗼...", parse_mode="HTML")
            task_dir = os.path.join("downloads", f"task_{unique_id}")
            os.makedirs(task_dir, exist_ok=True)
    
            global DOWNLOAD_DIR
            original_dir = DOWNLOAD_DIR
            DOWNLOAD_DIR = task_dir

            import concurrent.futures
            result = None
            for attempt in range(3):
                try:
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(InstaDownloader.download_media, url)
                        result = future.result(timeout=180)
                    if result and result.get("success"):
                        break
                except concurrent.futures.TimeoutError:
                    await asyncio.sleep(2)
                    continue
                except Exception:
                    await asyncio.sleep(2)
                    continue

            DOWNLOAD_DIR = original_dir
            
            if result is None or not result.get("success"):
                await msg.edit_text("<tg-emoji emoji-id=\"5850414922294365618\">❌</tg-emoji> 𝗙𝗮𝗶𝗹𝗲𝗱！ <tg-emoji emoji-id=\"5850600963097759409\">🚫</tg-emoji> 𝐒𝐞𝐫𝐯𝐞𝐫 𝐁𝐮𝐬𝐲 (˃̣̣̥᷄⌓˂̣̣̥᷅)", parse_mode="HTML")
                if sticker_msg:
                    try: await sticker_msg.delete()
                    except: pass
                return
            
            if result.get("is_multiple"):
                photo_paths = result.get("file_paths", [])
                total = len(photo_paths)
                save_photo_cache(cache_key, photo_paths)
                await msg.edit_text(f"<tg-emoji emoji-id=\"5325888970368762082\">🪂</tg-emoji> 𝗨𝗽𝗹𝗼𝗮𝗱𝗶𝗻𝗴 {total} 𝗣𝗵𝗼𝘁𝗼𝘀...", parse_mode="HTML")
    
                for i, path in enumerate(photo_paths):
                    if os.path.exists(path):
                        with open(path, 'rb') as f:
                            if i == 0:
                                await update.message.reply_photo(photo=f, caption=f"📸 {i+1}/{total}\n\n{CAPTION}", parse_mode="Markdown", reply_to_message_id=update.message.message_id)
                            else:
                                await update.message.reply_photo(photo=f, caption=f"📸 {i+1}/{total}", reply_to_message_id=update.message.message_id)
                        await asyncio.sleep(0.5)
    
                await msg.delete()
                if sticker_msg:
                    try: await sticker_msg.delete()
                    except: pass
                return
            
            fp = result["file_path"]
            if not os.path.exists(fp) or os.path.getsize(fp) < 1000:
                await msg.edit_text("❌ 𝗙𝗶𝗹𝗲 𝗡𝗼𝘁 𝗙𝗼𝘂𝗻𝗱", parse_mode="Markdown")
                if sticker_msg:
                    try: await sticker_msg.delete()
                    except: pass
                return
            
            size_mb = os.path.getsize(fp) / (1024 * 1024)
            if size_mb > 50:
                await msg.edit_text(f"❌ >𝟱𝟬𝗠𝗕 ({size_mb:.1f}MB)", parse_mode="Markdown")
                InstaDownloader.cleanup(fp)
                if sticker_msg:
                    try: await sticker_msg.delete()
                    except: pass
                return
            
            is_video = result.get("is_video", False) or fp.endswith(('.mp4', '.mov', '.webm'))
            
            if is_video:
                await msg.edit_text("<tg-emoji emoji-id=\"5275974823254725631\">🪂</tg-emoji> 𝗨𝗽𝗹𝗼𝗮𝗱𝗶𝗻𝗴 𝗩𝗶𝗱𝗲𝗼 . ˚◞♡ ◟˚ .", parse_mode="HTML")
                keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(AUDIO_BUTTON_TEXT, callback_data=f"aud_{shortcode}", style=get_random_style(), icon_custom_emoji_id=get_random_emoji_id())]])
                await context.bot.send_chat_action(chat_id=chat_id, action='upload_video')
                with open(fp, 'rb') as f:
                    sent_msg = await update.message.reply_video(video=f, caption=CAPTION, parse_mode="HTML", reply_markup=keyboard, supports_streaming=True, reply_to_message_id=update.message.message_id)
            else:
                await msg.edit_text("<tg-emoji emoji-id=\"5384337002751630535\">🪂</tg-emoji> 𝗨𝗽𝗹𝗼𝗮𝗱𝗶𝗻𝗴 𝗣𝗵𝗼𝘁𝗼♡ ⋆｡°✩", parse_mode="HTML")
                with open(fp, 'rb') as f:
                    sent_msg = await update.message.reply_photo(photo=f, caption=CAPTION, parse_mode="HTML", reply_to_message_id=update.message.message_id)
         
            # ⭐ AUTO-FORWARD TO CHANNELS
            if is_auto_forward_enabled():
                channels = get_channels()
                if channels:
                    for ch_id in channels:
                        try:
                            await sent_msg.forward(chat_id=int(ch_id))
                            await asyncio.sleep(1)
                        except Exception as e:
                            logging.error(f"Auto-forward failed to {ch_id}: {e}")
                
            await msg.delete(); InstaDownloader.cleanup(fp)
            if sticker_msg:
                await asyncio.sleep(3)
                try: await sticker_msg.delete()
                except: pass
                
        except Exception as e:
            logging.error(f"Process error: {e}")
            try: await msg.edit_text(f"<tg-emoji emoji-id=\"5438630285635757876\">❌</tg-emoji> 𝗘𝗿𝗿𝗼𝗿 ： {str(e)[:80]}", parse_mode="HTML")
            except: pass
            # ERROR PE STICKER DELETE - GUARANTEED
            if sticker_msg:
                try: await sticker_msg.delete()
                except: pass

async def extract_and_send_audio_msg(update, context, url, audio_name, video_msg_id=None):
    """Text message se audio extract - video ke reply mein bhejega"""
    chat_id = update.effective_chat.id
    reply_msg_id = video_msg_id or update.message.message_id
    
    status_msg = await context.bot.send_message(
        chat_id=chat_id,
        text="<tg-emoji emoji-id=\"5859300243262148377\">💽</tg-emoji> 𝗘𝘅𝘁𝗿𝗮𝗰𝘁𝗶𝗻𝗴 𝗔𝘂𝗱𝗶𝗼. ˚◞♡ ◟˚ .",
        parse_mode="HTML"
    )
    
    async with download_semaphore:
        try:
            import uuid
            audio_uid = str(uuid.uuid4())[:8]
            audio_dir = os.path.join("downloads", f"audio_{audio_uid}")
            os.makedirs(audio_dir, exist_ok=True)
    
            global DOWNLOAD_DIR
            original_dir = DOWNLOAD_DIR
            DOWNLOAD_DIR = audio_dir

            import concurrent.futures
            result = None
            for attempt in range(2):
                try:
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(InstaDownloader.download_media, url)
                        result = future.result(timeout=90)
                    if result.get("success"):
                        break
                except concurrent.futures.TimeoutError:
                    time.sleep(2)
                    continue
                except Exception:
                    time.sleep(2)
                    continue

            if result is None:
                result = {"success": False}

            DOWNLOAD_DIR = original_dir
            
            if not result.get("success"): 
                await status_msg.edit_text("<tg-emoji emoji-id=\"5334637865995352639\">❌</tg-emoji> 𝗙𝗮𝗶𝗹𝗲𝗱", parse_mode="HTML")
                return
            vp = result["file_path"]
            ar = InstaDownloader.extract_audio(vp, audio_name)
            if ar.get("success"):
                await status_msg.edit_text("<tg-emoji emoji-id=\"6032754146778551433\">🎻</tg-emoji> 𝗦𝗲𝗻𝗱𝗶𝗻𝗴 𝗔𝘂𝗱𝗶𝗼♡ ⋆｡°✩", parse_mode="HTML")
                await context.bot.send_chat_action(chat_id=chat_id, action='upload_audio')
                with open(ar["file_path"], 'rb') as f:
                    sent_audio = await context.bot.send_audio(
                        chat_id=chat_id,
                        audio=f,
                        title=audio_name,
                        performer="✩⋆｡°𝗕𝘆 ➪ 𓆩#ＫＡＲＴＩＫ𓆪 ♡",
                        caption=CAPTION,
                        parse_mode="HTML",
                        reply_to_message_id=reply_msg_id
                    )
                # ⭐ AUTO-SEND AUDIO TO CHANNELS
                if is_auto_send_voice_enabled(update.effective_user.id):
                    channels = get_channels()
                    if channels:
                        for ch_id in channels:
                            try:
                                await sent_audio.forward(chat_id=int(ch_id))
                                await asyncio.sleep(1)
                            except Exception as e:
                                logging.error(f"Auto-send voice failed to {ch_id}: {e}")
                await asyncio.sleep(2)
                await status_msg.delete()
                try: os.remove(ar["file_path"])
                except: pass
            else: 
                await status_msg.edit_text(f"❌ {ar.get('error')}", parse_mode="Markdown")
            InstaDownloader.cleanup(vp)
        except Exception as e: 
            try: await status_msg.edit_text(f"❌ {str(e)[:80]}", parse_mode="Markdown")
            except: pass

async def extract_and_send_audio_def(context, url, audio_name, chat_id, reply_to_msg_id, user_id=None):
    """Default audio button ke liye - video message ke reply mein audio bhejega"""
    status_msg = await context.bot.send_message(
        chat_id=chat_id,
        text="<tg-emoji emoji-id=\"5859300243262148377\">💽</tg-emoji> 𝗘𝘅𝘁𝗿𝗮𝗰𝘁𝗶𝗻𝗴 𝗔𝘂𝗱𝗶𝗼. ˚◞♡ ◟˚ .",
        parse_mode="HTML"
    )
    
    async with download_semaphore:
        try:
            import uuid
            audio_uid = str(uuid.uuid4())[:8]
            audio_dir = os.path.join("downloads", f"audio_{audio_uid}")
            os.makedirs(audio_dir, exist_ok=True)
    
            global DOWNLOAD_DIR
            original_dir = DOWNLOAD_DIR
            DOWNLOAD_DIR = audio_dir

            import concurrent.futures
            result = None
            for attempt in range(2):
                try:
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(InstaDownloader.download_media, url)
                        result = future.result(timeout=90)
                    if result.get("success"):
                        break
                except concurrent.futures.TimeoutError:
                    time.sleep(2)
                    continue
                except Exception:
                    time.sleep(2)
                    continue

            if result is None:
                result = {"success": False}

            DOWNLOAD_DIR = original_dir
            
            if not result.get("success"): 
                await status_msg.edit_text("<tg-emoji emoji-id=\"5334637865995352639\">❌</tg-emoji> 𝗙𝗮𝗶𝗹𝗲𝗱", parse_mode="HTML")
                return
                
            vp = result["file_path"]
            ar = InstaDownloader.extract_audio(vp, audio_name)
            
            if ar.get("success"):
                await status_msg.edit_text("<tg-emoji emoji-id=\"6032754146778551433\">🎻</tg-emoji> 𝗦𝗲𝗻𝗱𝗶𝗻𝗴 𝗔𝘂𝗱𝗶𝗼♡ ⋆｡°✩", parse_mode="HTML")
                await context.bot.send_chat_action(chat_id=chat_id, action='upload_audio')
                
                with open(ar["file_path"], 'rb') as f:
                    sent_audio = await context.bot.send_audio(
                        chat_id=chat_id,
                        audio=f,
                        title=audio_name,
                        performer="✩⋆｡°𝗕𝘆 ➪ 𓆩#ＫＡＲＴＩＫ𓆪 ♡",
                        caption=CAPTION,
                        parse_mode="HTML",
                        reply_to_message_id=reply_to_msg_id
                    )

                # ⭐ AUTO-SEND AUDIO TO CHANNELS
                if is_auto_send_voice_enabled(user_id):
                    channels = get_channels()
                    if channels:
                        for ch_id in channels:
                            try:
                                await sent_audio.forward(chat_id=int(ch_id))
                                await asyncio.sleep(1)
                            except Exception as e:
                                logging.error(f"Auto-send voice failed to {ch_id}: {e}")
                await asyncio.sleep(2)
                await status_msg.delete()
                try: os.remove(ar["file_path"])
                except: pass
            else: 
                await status_msg.edit_text(f"❌ {ar.get('error')}", parse_mode="Markdown")
                
            InstaDownloader.cleanup(vp)
            
        except Exception as e: 
            try: await status_msg.edit_text(f"❌ {str(e)[:80]}", parse_mode="Markdown")
            except: pass

async def extract_and_send_audio_direct(query, context, url, audio_name):
    chat_id = query.message.chat_id
    
    try:
        search_msg = await query.message.reply_text("🔎")
        await asyncio.sleep(3)
        await search_msg.delete()
    except:
        pass
    
    status_msg = await context.bot.send_message(
        chat_id=chat_id,
        text="<tg-emoji emoji-id=\"5859300243262148377\">💽</tg-emoji> 𝗘𝘅𝘁𝗿𝗮𝗰𝘁𝗶𝗻𝗴 𝗔𝘂𝗱𝗶𝗼. ˚◞♡ ◟˚ .",
        parse_mode="HTML"
    )
    
    async with download_semaphore:
        try:
            import uuid
            audio_uid = str(uuid.uuid4())[:8]
            audio_dir = os.path.join("downloads", f"audio_{audio_uid}")
            os.makedirs(audio_dir, exist_ok=True)
    
            global DOWNLOAD_DIR
            original_dir = DOWNLOAD_DIR
            DOWNLOAD_DIR = audio_dir

            import concurrent.futures
            result = None
            for attempt in range(2):
                try:
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(InstaDownloader.download_media, url)
                        result = future.result(timeout=90)
                    if result.get("success"):
                        break
                except concurrent.futures.TimeoutError:
                    time.sleep(2)
                    continue
                except Exception:
                    time.sleep(2)
                    continue

            if result is None:
                result = {"success": False}

            DOWNLOAD_DIR = original_dir
            
            if not result.get("success"): 
                await status_msg.edit_text("<tg-emoji emoji-id=\"5334637865995352639\">❌</tg-emoji> 𝗙𝗮𝗶𝗹𝗲𝗱", parse_mode="HTML")
                return
            vp = result["file_path"]
            ar = InstaDownloader.extract_audio(vp, audio_name)
            if ar.get("success"):
                await status_msg.edit_text("<tg-emoji emoji-id=\"6032754146778551433\">🎻</tg-emoji> 𝗦𝗲𝗻𝗱𝗶𝗻𝗴 𝗔𝘂𝗱𝗶𝗼♡ ⋆｡°✩", parse_mode="HTML")
                await context.bot.send_chat_action(chat_id=chat_id, action='upload_audio')
                with open(ar["file_path"], 'rb') as f:
                    await context.bot.send_audio(
                        chat_id=chat_id,
                        audio=f,
                        title=audio_name,
                        performer="✩⋆｡°𝗕𝘆 ➪ 𓆩#ＫＡＲＴＩＫ𓆪 ♡",
                        caption=CAPTION,
                        parse_mode="HTML"
                    )
                await asyncio.sleep(2)
                await status_msg.delete()
                try: os.remove(ar["file_path"])
                except: pass
            else: 
                await status_msg.edit_text(f"❌ {ar.get('error')}", parse_mode="Markdown")
            InstaDownloader.cleanup(vp)
        except Exception as e: 
            try: await status_msg.edit_text(f"❌ {str(e)[:80]}", parse_mode="Markdown")
            except: pass
                
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
            pass
        else:
            if InstaDownloader.is_instagram_url(text):
                await update.message.reply_text(BOT_DISABLED_MSG, parse_mode="HTML")
            return  # ⬅️ Ye return zaroori hai!
    
    # User-specific checks
    user_data = context.user_data
    
    # Owner emoji ID input
    if user_data.get('awaiting_emoji_id') and user_id == OWNER_ID:
        emoji_id = text.strip()
        # Pehle ][ ko , me badlo
        emoji_id = emoji_id.replace('][', ',')
        # Phir brackets hatao
        emoji_id = emoji_id.replace('[', '').replace(']', '').replace('(', '').replace(')', '')

        # Multiple IDs handle karo (comma ya space separated)
        if ',' in emoji_id or ' ' in emoji_id:
            # Split by comma or space
            if ',' in emoji_id:
                emoji_ids = [eid.strip() for eid in emoji_id.split(',') if eid.strip()]
            else:
                emoji_ids = [eid.strip() for eid in emoji_id.split() if eid.strip()]
    
            added = 0
            already = 0
            for eid in emoji_ids:
                if eid.isdigit() and len(eid) >= 15:
                    s, _ = add_emoji_db(eid)
                    if s:
                        added += 1
                    else:
                        already += 1
    
            emojis = get_emojis()
            # Added emojis ka preview line banao
            added_preview = ""
            for eid in emoji_ids:
                if eid.isdigit() and len(eid) >= 15:
                    added_preview += f'<tg-emoji emoji-id="{eid}">🌟</tg-emoji>'

            if added_preview:
                await update.message.reply_text(
                    f'{added_preview}\n'
                    f'<tg-emoji emoji-id="6226399941388928924">✅</tg-emoji> {added} 𝘼𝙙𝙙𝙚𝙙, ⚠️ {already} 𝘼𝙡𝙧𝙚𝙖𝙙𝙮 𝙀𝙭𝙞𝙨𝙩𝙨\n'
                    f'📦 𝙏𝙤𝙩𝙖𝙡: {len(emojis)}',
                    parse_mode="HTML"
                )
            else:
                await update.message.reply_text(
                    f'⚠️ {already} 𝘼𝙡𝙧𝙚𝙖𝙙𝙮 𝙀𝙭𝙞𝙨𝙩𝙨\n'
                    f'📦 𝙏𝙤𝙩𝙖𝙡: {len(emojis)}',
                    parse_mode="HTML"
                )
            return

        # Single ID
        if emoji_id.isdigit() and len(emoji_id) >= 15:
            context.user_data['pending_emoji_id'] = emoji_id
            # ... baaki same

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(
                    "𝐀𝐝𝐝 𝐓𝐡𝐢𝐬",
                    callback_data="owner_add_this",
                    style=get_random_style(),
                    icon_custom_emoji_id="5353034963270771323"
                )]
            ])
            await update.message.reply_text(
                f'<tg-emoji emoji-id="{emoji_id}">🌟</tg-emoji>\n\n'
                f'<code>{emoji_id}</code>\n\n'
                '<b>Add this emoji?</b>',
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            return
        else:
            # ✅ INSTAGRAM LINK CHECK KARO
            if InstaDownloader.is_instagram_url(text):
                user_data['awaiting_emoji_id'] = False  # ← emoji mode band
            else:
                await update.message.reply_text(
                    f'<tg-emoji emoji-id="5929358014627713883">❌</tg-emoji> <b>𝐈𝐧𝐯𝐚𝐥𝐢𝐝 𝐈𝐃！𝐒𝐞𝐧𝐝 𝐚𝐠𝐚𝐢𝐧 ：</b>',
                    parse_mode="HTML"                
                )
                return
    
    # User-specific audio awaiting check
    if user_data.get('awaiting_audio'):
        user_data['awaiting_audio'] = False
        audio_name = text.strip()
        url = user_data.get('audio_video_url')
        video_msg_id = user_data.get('video_msg_id')  # Saved video ID
        if 'audio_prompt_msg' in user_data:
            try: await user_data['audio_prompt_msg'].delete()
            except: pass
            user_data['audio_prompt_msg'] = None
        if url: asyncio.create_task(extract_and_send_audio_msg(update, context, url, audio_name, video_msg_id))
        user_data['audio_video_url'] = None
        user_data['video_msg_id'] = None
        return
    
    if text == AUDIO_DEFAULT_NAME:
        user_data['awaiting_audio'] = False
        url = user_data.get('audio_video_url')
        video_msg_id = user_data.get('video_msg_id')
        if 'audio_prompt_msg' in user_data:
            try: await user_data['audio_prompt_msg'].delete()
            except: pass
            user_data['audio_prompt_msg'] = None
        if url: asyncio.create_task(extract_and_send_audio_msg(update, context, url, AUDIO_DEFAULT_NAME, video_msg_id))
        user_data['audio_video_url'] = None
        user_data['video_msg_id'] = None
        return
    
    if not InstaDownloader.is_instagram_url(text): return
    url = InstaDownloader.extract_url(text)
    if not url:
        await update.message.reply_text(
            f'<tg-emoji emoji-id="5929358014627713883">❌</tg-emoji> <b>𝗜𝗻𝘃𝗮𝗹𝗶𝗱 𝗨𝗥𝗟</b>',
            parse_mode="HTML"
        )
        return  # ✅ YEH REHNE DO

    asyncio.create_task(process_download(update, context, url))
    return

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_data = context.user_data

    if query.data == "owner_add_emoji":
        user_data['awaiting_emoji_id'] = True
        await query.message.reply_text(
            f'<tg-emoji emoji-id="6170160969600212116">📝</tg-emoji> <b>𝙎𝙚𝙣𝙙 𝙋𝙧𝙚𝙢𝙞𝙪𝙢 𝙀𝙢𝙤𝙟𝙞 𝙄𝙙 </b> <tg-emoji emoji-id="6172671064452111943">📝</tg-emoji>',
            parse_mode="HTML"
        )
        return

    if query.data == "owner_add_this":
        emoji_id = user_data.get('pending_emoji_id')

        if emoji_id:
            success, total = add_emoji_db(emoji_id)
            try:
                await query.message.delete()
            except:
                pass
            if success:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f'<tg-emoji emoji-id="6226399941388928924">✅</tg-emoji> 𝗘𝗠𝗢𝗝𝗜 𝗔𝗗𝗗𝗘𝗗 ༼{total}༽ <tg-emoji emoji-id="6127410617482484040">✅</tg-emoji>',
                    parse_mode="HTML"
                )
                await asyncio.sleep(0.3)
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f'<tg-emoji emoji-id="{emoji_id}">🌟</tg-emoji>',
                    parse_mode="HTML"
                )
            else:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f'<tg-emoji emoji-id="5929358014627713883">❌</tg-emoji> <b>𝗔𝗹𝗿𝗲𝗮𝗱𝘆 𝗘𝘅𝗶𝘀𝘁𝘀</b>',
                    parse_mode="HTML"
                )
        else:
            await query.answer("No ID found!", show_alert=True)
        user_data['pending_emoji_id'] = None
        user_data['awaiting_emoji_id'] = True
        return
    
    if query.data.startswith("aud_"):
        shortcode = query.data[4:]
        video_url = f"https://www.instagram.com/reel/{shortcode}/"
        user_data['audio_video_url'] = video_url
        user_data['awaiting_audio'] = True
        # ORIGINAL VIDEO MESSAGE ID SAVE KARO - query.message is the video message
        user_data['video_msg_id'] = query.message.message_id
    
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                AUDIO_DEFAULT_NAME,
                callback_data="def_audio",
                style=get_random_style(),
                icon_custom_emoji_id=get_random_audio_default_emoji()
            )
        ]])
        prompt_msg = await query.message.reply_text(
            AUDIO_NAME_PROMPT,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        user_data['audio_prompt_msg'] = prompt_msg
        await query.edit_message_reply_markup(reply_markup=None)
        await query.answer("Send audio name or click Default!")
        return
    elif query.data == "def_audio":
        chat_id = query.message.chat_id
        # Saved video message ID use karo
        video_msg_id = user_data.get('video_msg_id', query.message.message_id)

        try:
            await query.message.delete()
        except:
            pass

        user_data['awaiting_audio'] = False
        user_data['audio_prompt_msg'] = None
        url = user_data.get('audio_video_url') or user_data.get('current_url')

        if url:
            asyncio.create_task(extract_and_send_audio_def(context, url, AUDIO_DEFAULT_NAME, chat_id, video_msg_id, update.effective_user.id))

        user_data['audio_video_url'] = None
        user_data['video_msg_id'] = None
        return
    elif query.data.startswith("nxp_"):
        parts = query.data[4:].rsplit("_", 1)
        cache_key = parts[0]
        current_idx = int(parts[1])
        next_idx = current_idx + 1
        photo_paths = get_photo_cache(cache_key)
        if photo_paths and next_idx < len(photo_paths) and os.path.exists(photo_paths[next_idx]):
            await query.edit_message_reply_markup(reply_markup=None)
            keyboard = None
            if next_idx + 1 < len(photo_paths):
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton(
                        f"➪ 𝗡𝗲𝘅𝘁 𝗣𝗵𝗼𝘁𝗼 ➤ ({next_idx + 2}/{len(photo_paths)})",
                        callback_data=f"nxp_{cache_key}_{next_idx}",
                        style=get_random_style(),
                        icon_custom_emoji_id=get_random_emoji_id()
                    )
                ]])
            with open(photo_paths[next_idx], 'rb') as f:
                await query.message.reply_photo(
                    photo=f,
                    caption=f"📸 𝗣𝗵𝗼𝘁𝗼 {next_idx + 1}/{len(photo_paths)}\n\n{CAPTION}",
                    parse_mode="Markdown",
                    reply_markup=keyboard
                )
        else:
            await query.answer("No more photos!", show_alert=True)

# ═══════════════ AUTO REACTION ═══════════════

REACTION_EMOJIS = ["👍", "❤️", "🔥", "😂", "🎉", "👏", "😮"]

async def auto_react(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        if update.message:
            await update.message.set_reaction([ReactionTypeEmoji(random.choice(REACTION_EMOJIS))])
    except Exception:
        pass

# ═══════════════ BOT KE APNE MESSAGES PAR ANIMATED REACTION ═══════════════
# Ye patch bot ke har send method ko wrap karta hai — jo bhi message bot
# bhejega, uspar turant animated (is_big) reaction lag jayega.

import functools
from telegram import Bot

def _with_animated_reaction(func):
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        msg = await func(*args, **kwargs)   # pehle message bhejo
        try:
            # Ab us message par random animated reaction laga do
            if msg is not None and hasattr(msg, "set_reaction"):
                await msg.set_reaction(
                    [ReactionTypeEmoji(random.choice(REACTION_EMOJIS))],
                    is_big=True              # is_big=True = ANIMATED EFFECT
                )
        except Exception:
            pass                             # koi error aaye toh silently skip
        return msg
    return wrapper

# Bot ke saare send methods par patch laga do
for _method_name in [
    "send_message", "send_video", "send_photo", "send_audio",
    "send_sticker", "send_animation", "send_document", "send_voice",
    "send_video_note", "forward_message",
]:
    if hasattr(Bot, _method_name):
        setattr(Bot, _method_name, _with_animated_reaction(getattr(Bot, _method_name)))
        
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
    
    # HAR MESSAGE PAR REACTION (commands, text, photo, video, sticker — sab par)
    app.add_handler(TypeHandler(Update, auto_react), -1)
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("activate", activate_cmd))
    app.add_handler(CommandHandler("settings", settings_cmd))
    app.add_handler(CommandHandler("ego", ego_cmd))
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
    app.add_handler(CommandHandler("addchannel", add_channel_cmd))
    app.add_handler(CommandHandler("removechannel", remove_channel_cmd))
    app.add_handler(CommandHandler("listchannels", list_channels_cmd))
    app.add_handler(CommandHandler("send", send_cmd))
    app.add_handler(CommandHandler("autoforward", auto_forward_cmd))
    app.add_handler(CommandHandler("autosendvoice", autosendvoice_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    print("✅ Bot Started! FAST & RELIABLE! 🚀")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
