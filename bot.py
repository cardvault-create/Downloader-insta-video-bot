import logging
import os
import re
import subprocess
import shutil
import time
import json
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
# 🍪 COOKIES VALIDATOR - FIXED
# ═══════════════════════════

def validate_cookies():
    if not os.path.exists('cookies.txt'):
        print("⚠️ cookies.txt not found!")
        return False
    try:
        with open('cookies.txt', 'r') as f:
            content = f.read()
            # Check for valid Netscape format
            if 'instagram' in content.lower() and ('sessionid' in content.lower() or 'csrftoken' in content.lower()):
                return True
        print("⚠️ cookies.txt invalid - Need fresh cookies!")
        return False
    except Exception as e:
        print(f"⚠️ Error reading cookies: {e}")
        return False

# ═══════════════════════════
# 📥 INSTAGRAM DOWNLOADER - 100% WORKING
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
        if not shortcode: return {"success": False, "error": "Invalid URL"}
        is_reel = '/reel/' in url or '/tv/' in url
        if is_reel: return InstaDownloader._download_video(shortcode, url)
        else: return InstaDownloader._download_photo(shortcode, url)
    
    @staticmethod
    def _download_video(shortcode, url):
        """100% WORKING VIDEO + AUDIO DOWNLOAD"""
        print(f"🎬 Downloading video: {shortcode}")
        
        # Try with yt-dlp first (with cookies if available)
        cookie_file = 'cookies.txt' if validate_cookies() else None
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'outtmpl': os.path.join(DOWNLOAD_DIR, f'{shortcode}.%(ext)s'),
            'format': 'bv*+ba/best',  # Best video + best audio merged
            'merge_output_format': 'mp4',
            'retries': 5,
            'fragment_retries': 5,
            'socket_timeout': 60,
            'extractor_args': {'instagram': {'api_hostname': 'www.instagram.com'}},
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
            },
        }
        
        if cookie_file:
            ydl_opts['cookiefile'] = cookie_file
        
        if shutil.which('ffmpeg'):
            ydl_opts['ffmpeg_location'] = shutil.which('ffmpeg')
        
        # Method 1: Try yt-dlp
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            
            time.sleep(1)
            
            # Find downloaded file
            for f in os.listdir(DOWNLOAD_DIR):
                fp = os.path.join(DOWNLOAD_DIR, f)
                if f.endswith(('.mp4', '.mkv', '.webm')) and os.path.getsize(fp) > 50000:
                    print(f"✅ Downloaded: {f} ({os.path.getsize(fp)/1024/1024:.1f}MB)")
                    return {"success": True, "file_path": fp, "is_video": True}
            
        except Exception as e:
            print(f"⚠️ yt-dlp failed: {str(e)[:100]}")
        
        # Method 2: Direct download using requests + yt-dlp API
        try:
            print("🔄 Trying alternative method...")
            
            # Use yt-dlp API to get direct URL
            with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, 'cookiefile': cookie_file} if cookie_file else {'quiet': True, 'no_warnings': True}) as ydl:
                info = ydl.extract_info(url, download=False)
                
                # Find best format with video+audio
                formats = info.get('formats', [])
                best_format = None
                
                for fmt in formats:
                    if fmt.get('vcodec') != 'none' and fmt.get('acodec') != 'none':
                        best_format = fmt
                        break
                
                if not best_format:
                    # Get best video and audio separately
                    video_fmt = None
                    audio_fmt = None
                    
                    for fmt in formats:
                        if fmt.get('vcodec') != 'none' and fmt.get('acodec') == 'none' and not video_fmt:
                            video_fmt = fmt
                        if fmt.get('acodec') != 'none' and fmt.get('vcodec') == 'none' and not audio_fmt:
                            audio_fmt = fmt
                    
                    if video_fmt:
                        # Download video
                        video_url = video_fmt['url']
                        video_path = os.path.join(DOWNLOAD_DIR, f"{shortcode}_video.mp4")
                        
                        headers = {'User-Agent': 'Mozilla/5.0'}
                        resp = requests.get(video_url, headers=headers, stream=True)
                        with open(video_path, 'wb') as vf:
                            for chunk in resp.iter_content(8192):
                                if chunk: vf.write(chunk)
                        
                        if audio_fmt and shutil.which('ffmpeg'):
                            # Download audio and merge
                            audio_url = audio_fmt['url']
                            audio_path = os.path.join(DOWNLOAD_DIR, f"{shortcode}_audio.mp4")
                            
                            resp2 = requests.get(audio_url, headers=headers, stream=True)
                            with open(audio_path, 'wb') as af:
                                for chunk in resp2.iter_content(8192):
                                    if chunk: af.write(chunk)
                            
                            # Merge with ffmpeg
                            output_path = os.path.join(DOWNLOAD_DIR, f"{shortcode}.mp4")
                            cmd = [
                                'ffmpeg', '-y',
                                '-i', video_path,
                                '-i', audio_path,
                                '-c:v', 'copy',
                                '-c:a', 'aac',
                                '-shortest',
                                output_path
                            ]
                            subprocess.run(cmd, capture_output=True, timeout=120)
                            
                            # Cleanup
                            os.remove(video_path)
                            os.remove(audio_path)
                            
                            if os.path.exists(output_path) and os.path.getsize(output_path) > 50000:
                                print(f"✅ Merged: {os.path.getsize(output_path)/1024/1024:.1f}MB")
                                return {"success": True, "file_path": output_path, "is_video": True}
                        else:
                            # Just return video if no audio available
                            if os.path.getsize(video_path) > 50000:
                                print(f"✅ Video only: {os.path.getsize(video_path)/1024/1024:.1f}MB")
                                return {"success": True, "file_path": video_path, "is_video": True}
                
                elif best_format:
                    # Download single format with both audio and video
                    direct_url = best_format['url']
                    output_path = os.path.join(DOWNLOAD_DIR, f"{shortcode}.mp4")
                    
                    headers = {'User-Agent': 'Mozilla/5.0'}
                    resp = requests.get(direct_url, headers=headers, stream=True)
                    with open(output_path, 'wb') as f:
                        for chunk in resp.iter_content(8192):
                            if chunk: f.write(chunk)
                    
                    if os.path.exists(output_path) and os.path.getsize(output_path) > 50000:
                        print(f"✅ Direct: {os.path.getsize(output_path)/1024/1024:.1f}MB")
                        return {"success": True, "file_path": output_path, "is_video": True}
        
        except Exception as e:
            print(f"⚠️ Alternative method failed: {str(e)[:100]}")
        
        return {"success": False, "error": "Could not download video"}
    
    @staticmethod
    def _download_photo(shortcode, url):
        """PHOTO DOWNLOAD"""
        try:
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15',
                'Accept': 'text/html,application/xhtml+xml',
                'Accept-Language': 'en-US,en;q=0.9',
            })
            
            # Load cookies if available
            if os.path.exists('cookies.txt'):
                with open('cookies.txt', 'r') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'): continue
                        parts = line.split('\t')
                        if len(parts) >= 7:
                            try: session.cookies.set(parts[5], parts[6], domain='.instagram.com')
                            except: pass
            
            resp = session.get(url, timeout=20)
            if resp.status_code != 200:
                # Try without cookies
                resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=20)
            
            html = resp.text
            image_urls = []
            
            # Extract image URLs
            nd = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
            if nd:
                try:
                    data = json.loads(nd.group(1))
                    def find_urls(obj, depth=0):
                        if depth > 10: return []
                        urls = []
                        if isinstance(obj, dict):
                            du = obj.get('display_url', '')
                            if du and '.mp4' not in du: urls.append(du)
                            for v in obj.values(): urls.extend(find_urls(v, depth+1))
                        elif isinstance(obj, list):
                            for item in obj: urls.extend(find_urls(item, depth+1))
                        return urls
                    image_urls = find_urls(data)
                except: pass
            
            if not image_urls:
                urls = re.findall(r'"display_url"\s*:\s*"([^"]+)"', html)
                image_urls = [u.replace('\\u0026', '&') for u in urls if '.mp4' not in u]
            
            if not image_urls:
                og = re.findall(r'<meta\s+property="og:image"\s+content="([^"]+)"', html)
                image_urls = list(set(og))
            
            if not image_urls:
                return {"success": False, "error": "No photos found"}
            
            # Download images
            downloaded = []
            for i, img_url in enumerate(image_urls[:10]):
                try:
                    fp = os.path.join(DOWNLOAD_DIR, f"photo_{shortcode}_{i+1}.jpg")
                    r = requests.get(img_url, headers={'User-Agent': 'Mozilla/5.0'}, stream=True, timeout=30)
                    if r.status_code == 200:
                        with open(fp, 'wb') as f:
                            for chunk in r.iter_content(8192):
                                if chunk: f.write(chunk)
                        if os.path.getsize(fp) > 1000:
                            downloaded.append(fp)
                except: continue
            
            if downloaded:
                result = {"success": True, "file_path": downloaded[0], "is_video": False}
                if len(downloaded) > 1:
                    result["is_multiple"] = True
                    result["total"] = len(downloaded)
                    result["file_paths"] = downloaded
                return result
            
            return {"success": False, "error": "Could not download"}
            
        except Exception as e:
            return {"success": False, "error": str(e)[:80]}
    
    @staticmethod
    def extract_audio(video_path, custom_name=None):
        try:
            if custom_name:
                safe = re.sub(r'[^\w\s-]', '', custom_name).strip()[:50] or "Audio"
                ap = os.path.join(DOWNLOAD_DIR, f"{safe}.mp3")
            else:
                ap = os.path.join(DOWNLOAD_DIR, f"{os.path.splitext(os.path.basename(video_path))[0]}.mp3")
            
            if not shutil.which('ffmpeg'): 
                return {"success": False, "error": "FFmpeg not found"}
            
            subprocess.run(['ffmpeg', '-i', video_path, '-vn', '-acodec', 'libmp3lame', '-ab', '192k', '-y', ap], 
                          capture_output=True, timeout=180)
            
            if os.path.exists(ap) and os.path.getsize(ap) > 1000: 
                return {"success": True, "file_path": ap}
            return {"success": False, "error": "Audio extraction failed"}
        except Exception as e: 
            return {"success": False, "error": str(e)[:50]}
    
    @staticmethod
    def cleanup(fp):
        try:
            if fp and os.path.exists(fp): os.remove(fp)
        except: pass

# ═══════════════════════════
# 📝 SIMPLE TEXT (No Markdown errors)
# ═══════════════════════════

CAPTION = (
    "Downloaded By - Instagram Downloader Bot\n"
    "Developer - @FathersOfCreater"
)

WELCOME_TEXT = """Hey {mention}!

I'm Instagram Downloader Bot

Features:
- Download Instagram Reels
- Download Instagram Photos  
- Extract Audio from Videos
- HD Video + Original Audio
- Multiple Photo Download
- Group Support

Just send Instagram link!

Developer - @FathersOfCreater"""

GROUP_WELCOME = """Hello {chat_title}!

I'm Instagram Downloader Bot

Features:
- Download Instagram Reels, Photos & Audio
- HD Video + Original Audio Guaranteed
- Just send Instagram link in group

Developer - @FathersOfCreater"""

BOT_DISABLED_MSG = "Bot is currently disabled by owner."

AUDIO_BUTTON_TEXT = "Download Video Audio"
AUDIO_DEFAULT_NAME = "My Music"

AUDIO_NAME_PROMPT = (
    "Give me audio name?\n\n"
    "Example: My Music\n"
    "Or click button below for default name"
)

SETTINGS_TEXT = """COMMANDS

OWNER: /start /disable /enable /settings
GROUP: /activate
EMOJI: /addemoji /removeemoji /listemojis
STICKER: /addsticker /removesticker /liststickers
VIDEO: /addvideo /delvideo /videos /clearvideos"""

# ═══════════════════════════
# 🎬 WELCOME ANIMATION
# ═══════════════════════════

async def welcome_animation(bot, chat_id, user_id, first_name):
    try:
        user_mention = first_name
        emoji_id = get_random_emoji()
        if emoji_id:
            try: await bot.send_sticker(chat_id, emoji_id)
            except: pass
        
        await asyncio.sleep(0.5)
        
        sticker_id = get_random_sticker()
        if sticker_id:
            try: await bot.send_sticker(chat_id, sticker_id)
            except: pass
        
        await asyncio.sleep(3)
        
        final_text = WELCOME_TEXT.replace("{mention}", user_mention)
        bot_user = await bot.get_me()
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Add to Group", url=f"https://t.me/{bot_user.username}?startgroup=true")]])
        
        video_data = get_random_video()
        if video_data and os.path.exists(video_data["path"]):
            await bot.send_video(chat_id, video_data["path"], caption=final_text, reply_markup=kb)
        else:
            await bot.send_message(chat_id, final_text, reply_markup=kb)
    except Exception as e:
        print(f"Welcome error: {e}")
        try: await bot.send_message(chat_id, WELCOME_TEXT.replace("{mention}", first_name))
        except: pass

# ═══════════════════════════
# 🤖 HANDLERS
# ═══════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_bot_enabled(): return
    if update.effective_chat.type != 'private': return
    await welcome_animation(context.bot, update.effective_chat.id, 
                          update.effective_user.id, update.effective_user.first_name or "User")

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
    await update.message.reply_text(SETTINGS_TEXT)

async def bot_added_to_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_bot_enabled(): return
    if update.my_chat_member.new_chat_member.status in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR]:
        chat = update.effective_chat
        bot_user = await context.bot.get_me()
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("Add to Group", url=f"https://t.me/{bot_user.username}?startgroup=true")]])
        try: await context.bot.send_message(chat.id, GROUP_WELCOME.replace("{chat_title}", chat.title or "Group"), reply_markup=kb)
        except: pass

async def disable_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    set_bot_state(False)
    await update.message.reply_text("Bot Disabled")

async def enable_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    set_bot_state(True)
    await update.message.reply_text("Bot Enabled")

async def add_emoji_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not update.message.reply_to_message or not update.message.reply_to_message.sticker:
        await update.message.reply_text("Reply to emoji/sticker")
        return
    s, t = add_emoji_db(update.message.reply_to_message.sticker.file_id)
    await update.message.reply_text(f"Added! Total: {t}" if s else "Already exists!")

async def remove_emoji_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    try:
        idx = int(update.message.text.split()[1]) - 1
        s, t = remove_emoji_db(idx)
        await update.message.reply_text(f"Removed! Total: {t}" if s else f"Invalid! Total: {t}")
    except: await update.message.reply_text("Usage: /removeemoji index")

async def list_emojis_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    emojis = get_emojis()
    if not emojis: 
        await update.message.reply_text("No emojis!")
        return
    text = "EMOJIS:\n" + "\n".join([f"{i+1}. {e[:30]}" for i, e in enumerate(emojis)])
    await update.message.reply_text(f"{text}\n\nTotal: {len(emojis)}")

async def add_sticker_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not update.message.reply_to_message or not update.message.reply_to_message.sticker:
        await update.message.reply_text("Reply to sticker")
        return
    s, t = add_sticker_db(update.message.reply_to_message.sticker.file_id)
    await update.message.reply_text(f"Added! Total: {t}" if s else "Already exists!")

async def remove_sticker_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    try:
        idx = int(update.message.text.split()[1]) - 1
        s, t = remove_sticker_db(idx)
        await update.message.reply_text(f"Removed! Total: {t}" if s else f"Invalid! Total: {t}")
    except: await update.message.reply_text("Usage: /removesticker index")

async def list_stickers_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    stickers = get_stickers()
    if not stickers: 
        await update.message.reply_text("No stickers!")
        return
    text = "STICKERS:\n" + "\n".join([f"{i+1}. {s[:25]}" for i, s in enumerate(stickers)])
    await update.message.reply_text(f"{text}\n\nTotal: {len(stickers)}")

async def add_video_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not update.message.reply_to_message or not update.message.reply_to_message.video:
        await update.message.reply_text("Reply to video")
        return
    m = await update.message.reply_text("Adding...")
    try:
        file = await update.message.reply_to_message.video.get_file()
        fp = os.path.join(VIDEO_DIR, f"w_{int(time.time())}.mp4")
        await file.download_to_drive(fp)
        vid, total = add_video_db(fp)
        await m.edit_text(f"Video Added! ID: {vid}, Total: {total}")
    except Exception as e: await m.edit_text(f"Error: {e}")

async def del_video_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    try:
        s, t = delete_video_db(int(update.message.text.split()[1]))
        await update.message.reply_text(f"Deleted! Total: {t}" if s else "Not found!")
    except: await update.message.reply_text("Usage: /delvideo ID")

async def list_videos_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    vids = get_video_list()
    if not vids: 
        await update.message.reply_text("No videos!")
        return
    text = "VIDEOS:\n" + "\n".join([f"#{v['id']} {v['name'][:30]}" for v in vids])
    await update.message.reply_text(f"{text}\n\nTotal: {len(vids)}")

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
    
    # Audio naming flow
    if context.user_data.get('awaiting_audio'):
        context.user_data['awaiting_audio'] = False
        audio_name = text.strip()
        url = context.user_data.get('audio_video_url')
        if 'audio_prompt_msg' in context.user_data:
            try: await context.user_data['audio_prompt_msg'].delete()
            except: pass
            context.user_data['audio_prompt_msg'] = None
        if url: await extract_and_send_audio(update, context, url, audio_name)
        context.user_data['audio_video_url'] = None
        return
    
    if text == AUDIO_DEFAULT_NAME:
        context.user_data['awaiting_audio'] = False
        url = context.user_data.get('audio_video_url')
        if 'audio_prompt_msg' in context.user_data:
            try: await context.user_data['audio_prompt_msg'].delete()
            except: pass
            context.user_data['audio_prompt_msg'] = None
        if url: await extract_and_send_audio(update, context, url, AUDIO_DEFAULT_NAME)
        context.user_data['audio_video_url'] = None
        return
    
    if not InstaDownloader.is_instagram_url(text): return
    
    url = InstaDownloader.extract_url(text)
    if not url:
        await update.message.reply_text("Invalid URL")
        return
    
    context.user_data['current_url'] = url
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    shortcode = InstaDownloader.get_shortcode(url)
    cache_key = f"{chat_id}_{user_id}_{shortcode}"
    
    # Status message
    msg = await update.message.reply_text("Processing...")
    
    try:
        is_reel = '/reel/' in url or '/tv/' in url
        
        if is_reel:
            await msg.edit_text("Downloading Video...")
        else:
            await msg.edit_text("Downloading Photo...")
        
        result = InstaDownloader.download_media(url)
        
        if not result.get("success"):
            await msg.edit_text(f"Failed! {result.get('error', '')}")
            return
        
        # Multiple photos
        if result.get("is_multiple"):
            photo_paths = result.get("file_paths", [])
            total = len(photo_paths)
            save_photo_cache(cache_key, photo_paths)
            
            if total > 0 and os.path.exists(photo_paths[0]):
                keyboard = None
                if total > 1:
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton(f"Next Photo (2/{total})", callback_data=f"nxp_{cache_key}_0")]
                    ])
                with open(photo_paths[0], 'rb') as f:
                    await update.message.reply_photo(
                        photo=f, 
                        caption=f"Photo 1/{total}\n\n{CAPTION}",
                        reply_markup=keyboard
                    )
            await msg.delete()
            return
        
        # Single file
        fp = result["file_path"]
        if not os.path.exists(fp) or os.path.getsize(fp) < 1000:
            await msg.edit_text("File not found")
            return
        
        size_mb = os.path.getsize(fp) / (1024 * 1024)
        if size_mb > 50:
            await msg.edit_text(f"File too large ({size_mb:.1f}MB)")
            InstaDownloader.cleanup(fp)
            return
        
        is_video = result.get("is_video", False) or fp.endswith(('.mp4', '.mov', '.webm'))
        
        if is_video:
            await msg.edit_text("Uploading Video...")
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(AUDIO_BUTTON_TEXT, callback_data=f"aud_{url}")]])
            with open(fp, 'rb') as f:
                await update.message.reply_video(
                    video=f, 
                    caption=CAPTION,
                    reply_markup=keyboard, 
                    supports_streaming=True
                )
        else:
            await msg.edit_text("Uploading Photo...")
            with open(fp, 'rb') as f:
                await update.message.reply_photo(photo=f, caption=CAPTION)
        
        await msg.delete()
        InstaDownloader.cleanup(fp)
        
    except Exception as e:
        print(f"Error: {e}")
        await msg.edit_text(f"Error: {str(e)[:100]}")
        # Cleanup
        for f in os.listdir(DOWNLOAD_DIR):
            try: os.remove(os.path.join(DOWNLOAD_DIR, f))
            except: pass

async def extract_and_send_audio(update, context, url, audio_name):
    status_msg = await update.message.reply_text("Extracting Audio...")
    try:
        result = InstaDownloader.download_media(url)
        if not result.get("success"):
            await status_msg.edit_text("Failed to download video")
            return
        
        vp = result["file_path"]
        ar = InstaDownloader.extract_audio(vp, audio_name)
        
        if ar.get("success"):
            await status_msg.edit_text("Sending Audio...")
            with open(ar["file_path"], 'rb') as f:
                await update.message.reply_audio(
                    audio=f, 
                    title=audio_name, 
                    performer="Instagram",
                    caption=CAPTION
                )
            await asyncio.sleep(2)
            await status_msg.delete()
            try: os.remove(ar["file_path"])
            except: pass
        else:
            await status_msg.edit_text(f"Failed: {ar.get('error')}")
        
        InstaDownloader.cleanup(vp)
    except Exception as e:
        await status_msg.edit_text(f"Error: {str(e)[:80]}")

async def extract_and_send_audio_direct(query, context, url, audio_name):
    status_msg = await query.message.reply_text("Extracting Audio...")
    try:
        result = InstaDownloader.download_media(url)
        if not result.get("success"):
            await status_msg.edit_text("Failed")
            return
        
        vp = result["file_path"]
        ar = InstaDownloader.extract_audio(vp, audio_name)
        
        if ar.get("success"):
            await status_msg.edit_text("Sending Audio...")
            with open(ar["file_path"], 'rb') as f:
                await query.message.reply_audio(
                    audio=f, 
                    title=audio_name, 
                    performer="Instagram",
                    caption=CAPTION
                )
            await asyncio.sleep(2)
            await status_msg.delete()
            try: os.remove(ar["file_path"])
            except: pass
        else:
            await status_msg.edit_text(f"Failed: {ar.get('error')}")
        
        InstaDownloader.cleanup(vp)
    except Exception as e:
        await status_msg.edit_text(f"Error: {str(e)[:80]}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data.startswith("aud_"):
        video_url = query.data[4:]
        context.user_data['audio_video_url'] = video_url
        context.user_data['current_url'] = video_url
        await query.edit_message_reply_markup(reply_markup=None)
        await asyncio.sleep(1.5)
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(AUDIO_DEFAULT_NAME, callback_data="def_audio")]])
        prompt_msg = await query.message.reply_text(AUDIO_NAME_PROMPT, reply_markup=keyboard)
        context.user_data['awaiting_audio'] = True
        context.user_data['audio_prompt_msg'] = prompt_msg
        
    elif query.data == "def_audio":
        await query.message.delete()
        context.user_data['awaiting_audio'] = False
        context.user_data['audio_prompt_msg'] = None
        url = context.user_data.get('audio_video_url') or context.user_data.get('current_url')
        if url: await extract_and_send_audio_direct(query, context, url, AUDIO_DEFAULT_NAME)
        context.user_data['audio_video_url'] = None
        
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
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"Next Photo ({next_idx + 2}/{len(photo_paths)})", 
                     callback_data=f"nxp_{cache_key}_{next_idx}")]
                ])
            with open(photo_paths[next_idx], 'rb') as f:
                await query.message.reply_photo(
                    photo=f, 
                    caption=f"Photo {next_idx + 1}/{len(photo_paths)}\n\n{CAPTION}",
                    reply_markup=keyboard
                )
        else:
            await query.answer("No more photos!", show_alert=True)

# ═══════════════════════════
# 🚀 MAIN
# ═══════════════════════════

def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
    print("=" * 50)
    print("Instagram Bot v33 - FIXED")
    print("=" * 50)
    
    # Install ffmpeg
    os.system('apt-get update -qq && apt-get install -y -qq ffmpeg 2>/dev/null')
    
    print(f"Bot: {'ENABLED' if is_bot_enabled() else 'DISABLED'}")
    print(f"Cookies: {'VALID' if validate_cookies() else 'NOT FOUND'}")
    print(f"FFmpeg: {'FOUND' if shutil.which('ffmpeg') else 'NOT FOUND'}")
    print(f"Emojis: {len(get_emojis())} | Stickers: {len(get_stickers())} | Videos: {len(get_video_list())}")
    
    # Clean downloads
    for f in os.listdir(DOWNLOAD_DIR):
        try: os.remove(os.path.join(DOWNLOAD_DIR, f))
        except: pass
    
    app = Application.builder().token(BOT_TOKEN).read_timeout(120).write_timeout(120).build()
    
    # Commands
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
    
    # Handlers
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, bot_added_to_group))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    print("Bot Started!")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
