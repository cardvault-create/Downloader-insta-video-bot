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

EMOJI_DISPLAY_TIME = 3  # seconds
STICKER_DELETE_AFTER_FINAL = 5  # seconds

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
    
    # ═══════════════════════════
    # 🎬 VIDEO - DIRECT INSTAGRAM WITH AUDIO
    # ═══════════════════════════
    
    @staticmethod
    def _download_video(shortcode, url):
        try:
            # Method 1: Direct Instagram API
            session = requests.Session()
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Referer': 'https://www.instagram.com/',
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
            
            # Try to get direct video URL from Instagram page
            page_url = f"https://www.instagram.com/p/{shortcode}/"
            try:
                resp = session.get(page_url, timeout=15)
                if resp.status_code == 200:
                    html = resp.text
                    # Extract video URL
                    video_match = re.search(r'"video_url":"([^"]+)"', html)
                    if video_match:
                        video_url = video_match.group(1).replace('\\u0026', '&')
                        file_path = os.path.join(DOWNLOAD_DIR, f"{shortcode}.mp4")
                        
                        dl_headers = {
                            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)',
                            'Referer': 'https://www.instagram.com/',
                            'Accept': '*/*',
                        }
                        
                        vr = session.get(video_url, headers=dl_headers, stream=True, timeout=120)
                        if vr.status_code == 200:
                            with open(file_path, 'wb') as f:
                                for chunk in vr.iter_content(chunk_size=8192):
                                    if chunk: f.write(chunk)
                            
                            if os.path.exists(file_path) and os.path.getsize(file_path) > 5000:
                                print(f"✅ Direct video with audio: {shortcode}")
                                return {"success": True, "file_path": file_path, "is_video": True}
            except:
                pass
            
            # Method 2: yt-dlp with best format
            print("📡 Using yt-dlp...")
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'outtmpl': os.path.join(DOWNLOAD_DIR, f'{shortcode}.%(ext)s'),
                'format': 'bestvideo+bestaudio/best',
                'merge_output_format': 'mp4',
                'retries': 5,
                'fragment_retries': 5,
            }
            
            if os.path.exists('cookies.txt'):
                ydl_opts['cookiefile'] = 'cookies.txt'
            
            ffmpeg = shutil.which('ffmpeg')
            if ffmpeg:
                ydl_opts['ffmpeg_location'] = ffmpeg
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if info:
                    time.sleep(1)
                    for f in os.listdir(DOWNLOAD_DIR):
                        if shortcode in f and f.endswith('.mp4'):
                            fp = os.path.join(DOWNLOAD_DIR, f)
                            if os.path.exists(fp) and os.path.getsize(fp) > 5000:
                                print(f"✅ Video via yt-dlp: {os.path.basename(fp)}")
                                return {"success": True, "file_path": fp, "is_video": True}
            
            return {"success": False, "error": "Video download failed"}
            
        except Exception as e:
            err = str(e)
            if 'HTTP Error 403' in err or 'HTTP Error 401' in err:
                return {"success": False, "error": "cookies.txt expired!"}
            return {"success": False, "error": f"{err[:80]}"}
    
    # ═══════════════════════════
    # 📸 PHOTO - ORIGINAL 5 METHODS (RESTORED)
    # ═══════════════════════════
    
    @staticmethod
    def _download_photo(shortcode):
        """Photo download - 5 methods, ek to pakka kaam karega"""
        
        print("📥 Method 1: Instagram oEmbed API")
        result = InstaDownloader._method_oembed(shortcode)
        if result.get("success"):
            return result
        
        print("📥 Method 2: yt-dlp")
        result = InstaDownloader._method_ytdlp(shortcode)
        if result.get("success"):
            return result
        
        print("📥 Method 3: Page scrape")
        result = InstaDownloader._method_scrape(shortcode)
        if result.get("success"):
            return result
        
        print("📥 Method 4: Bibliogram")
        result = InstaDownloader._method_bibliogram(shortcode)
        if result.get("success"):
            return result
        
        print("📥 Method 5: Direct CDN")
        result = InstaDownloader._method_cdn(shortcode)
        if result.get("success"):
            return result
        
        return {"success": False, "error": "Photo download failed. Instagram may be blocking."}
    
    @staticmethod
    def _method_oembed(shortcode):
        """Method 1: Instagram Official oEmbed API - PUBLIC, NO LOGIN NEEDED"""
        try:
            post_url = f"https://www.instagram.com/p/{shortcode}/"
            api_url = f"https://api.instagram.com/oembed?url={urllib.parse.quote(post_url)}&maxwidth=1080"
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json',
            }
            
            resp = requests.get(api_url, headers=headers, timeout=15)
            
            if resp.status_code != 200:
                print(f"⚠️ oEmbed returned {resp.status_code}")
                return {"success": False}
            
            data = resp.json()
            
            thumbnail_url = data.get('thumbnail_url', '')
            embed_html = data.get('html', '')
            
            image_urls = []
            
            if thumbnail_url:
                hd_url = re.sub(r'/s\d+x\d+/', '/', thumbnail_url)
                hd_url = hd_url.split('?')[0]
                image_urls.append(hd_url)
                image_urls.append(thumbnail_url)
            
            if embed_html:
                img_matches = re.findall(r'<img[^>]+src="([^"]+)"', embed_html)
                for img_url in img_matches:
                    if img_url not in image_urls:
                        image_urls.append(img_url)
            
            if not image_urls:
                print("⚠️ No image URLs found in oEmbed response")
                return {"success": False}
            
            print(f"🔗 Found {len(image_urls)} image URLs")
            
            downloaded = []
            for img_url in image_urls:
                try:
                    if img_url.startswith('//'):
                        img_url = 'https:' + img_url
                    if img_url.startswith('http://'):
                        img_url = img_url.replace('http://', 'https://')
                    
                    if '.mp4' in img_url or '.mov' in img_url:
                        continue
                    
                    ext = 'jpg'
                    if '.png' in img_url: ext = 'png'
                    elif '.webp' in img_url: ext = 'webp'
                    
                    file_name = f"{shortcode}.{ext}"
                    file_path = os.path.join(DOWNLOAD_DIR, file_name)
                    
                    img_headers = {
                        'User-Agent': 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
                        'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
                        'Referer': 'https://www.instagram.com/',
                        'Sec-Fetch-Dest': 'image',
                        'Sec-Fetch-Mode': 'no-cors',
                        'Sec-Fetch-Site': 'cross-site',
                    }
                    
                    r = requests.get(img_url, headers=img_headers, stream=True, timeout=30)
                    if r.status_code == 200:
                        with open(file_path, 'wb') as f:
                            for chunk in r.iter_content(chunk_size=8192):
                                if chunk: f.write(chunk)
                        
                        if os.path.exists(file_path) and os.path.getsize(file_path) > 1000:
                            downloaded.append(file_path)
                            print(f"✅ Photo via oEmbed: {os.path.basename(file_path)} ({os.path.getsize(file_path)} bytes)")
                            break
                except Exception as e:
                    print(f"⚠️ oEmbed download error: {e}")
                    continue
            
            if downloaded:
                return {"success": True, "file_path": downloaded[0], "is_video": False}
            
            return {"success": False}
            
        except Exception as e:
            print(f"⚠️ oEmbed method error: {e}")
            return {"success": False}
    
    @staticmethod
    def _method_ytdlp(shortcode):
        """Method 2: yt-dlp"""
        try:
            url = f"https://www.instagram.com/p/{shortcode}/"
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'outtmpl': os.path.join(DOWNLOAD_DIR, f'{shortcode}.%(ext)s'),
                'format': 'best',
                'retries': 3,
            }
            if os.path.exists('cookies.txt'):
                ydl_opts['cookiefile'] = 'cookies.txt'
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if info:
                    time.sleep(1)
                    
                    for f in os.listdir(DOWNLOAD_DIR):
                        if shortcode in f:
                            fp = os.path.join(DOWNLOAD_DIR, f)
                            if os.path.exists(fp) and os.path.getsize(fp) > 1000:
                                if not f.endswith(('.mp4', '.mov', '.webm')):
                                    print(f"✅ Photo via yt-dlp: {f}")
                                    return {"success": True, "file_path": fp, "is_video": False}
                    
                    for f in os.listdir(DOWNLOAD_DIR):
                        if shortcode in f and f.endswith('.mp4'):
                            fp = os.path.join(DOWNLOAD_DIR, f)
                            print(f"⚠️ yt-dlp returned video for photo URL: {f}")
                            try: os.remove(fp)
                            except: pass
        except Exception as e:
            print(f"⚠️ yt-dlp photo error: {e}")
        return {"success": False}
    
    @staticmethod
    def _method_scrape(shortcode):
        """Method 3: Direct page scrape with session"""
        try:
            session = requests.Session()
            
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
            
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Linux; Android 13; SM-S908B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Cache-Control': 'max-age=0',
            })
            
            page_url = f"https://www.instagram.com/p/{shortcode}/"
            resp = session.get(page_url, timeout=15)
            
            if resp.status_code != 200:
                print(f"⚠️ Page scrape returned {resp.status_code}")
                return {"success": False}
            
            html = resp.text
            
            image_urls = []
            
            nd = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.DOTALL)
            if nd:
                try:
                    data = json.loads(nd.group(1))
                    def find_urls(obj, depth=0):
                        if depth > 5:
                            return []
                        urls = []
                        if isinstance(obj, dict):
                            du = obj.get('display_url') or obj.get('display_src') or ''
                            if isinstance(du, str) and du.startswith('http') and '.mp4' not in du:
                                urls.append(du)
                            for v in obj.values():
                                urls.extend(find_urls(v, depth + 1))
                        elif isinstance(obj, list):
                            for item in obj:
                                urls.extend(find_urls(item, depth + 1))
                        return urls
                    image_urls = find_urls(data)
                except:
                    pass
            
            if not image_urls:
                urls = re.findall(r'"display_url":"([^"]+)"', html)
                for u in urls:
                    image_urls.append(u.replace('\\u0026', '&'))
            
            if not image_urls:
                urls = re.findall(r'"display_src":"([^"]+)"', html)
                for u in urls:
                    image_urls.append(u.replace('\\u0026', '&'))
            
            if not image_urls:
                og = re.findall(r'<meta\s+property="og:image"\s+content="([^"]+)"', html)
                image_urls = list(set(og))
            
            if not image_urls:
                all_imgs = re.findall(r'<img[^>]+src="([^"]+)"', html)
                for img in all_imgs:
                    if shortcode in img or 'cdninstagram' in img or 'instagram' in img:
                        if '.mp4' not in img:
                            image_urls.append(img)
            
            if not image_urls:
                print("⚠️ No image URLs found in page")
                return {"success": False}
            
            print(f"🔗 Found {len(image_urls)} image URLs from page scrape")
            
            downloaded = []
            for i, img_url in enumerate(image_urls[:10]):
                try:
                    if img_url.startswith('//'):
                        img_url = 'https:' + img_url
                    if img_url.startswith('http://'):
                        img_url = img_url.replace('http://', 'https://')
                    
                    img_url = img_url.split('?')[0]
                    
                    ext = 'jpg'
                    if '.png' in img_url: ext = 'png'
                    elif '.webp' in img_url: ext = 'webp'
                    
                    file_name = f"{shortcode}_{i+1}.{ext}" if len(image_urls) > 1 else f"{shortcode}.{ext}"
                    file_path = os.path.join(DOWNLOAD_DIR, file_name)
                    
                    img_headers = {
                        'User-Agent': 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36',
                        'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
                        'Referer': 'https://www.instagram.com/',
                        'Sec-Fetch-Dest': 'image',
                        'Sec-Fetch-Mode': 'no-cors',
                        'Sec-Fetch-Site': 'cross-site',
                    }
                    
                    ir = session.get(img_url, headers=img_headers, stream=True, timeout=30)
                    if ir.status_code == 200:
                        with open(file_path, 'wb') as f:
                            for chunk in ir.iter_content(chunk_size=8192):
                                if chunk: f.write(chunk)
                        
                        if os.path.exists(file_path) and os.path.getsize(file_path) > 1000:
                            downloaded.append(file_path)
                            print(f"✅ Downloaded: {os.path.basename(file_path)} ({os.path.getsize(file_path)} bytes)")
                            if len(image_urls) == 1:
                                break
                except Exception as e:
                    print(f"⚠️ Download error: {e}")
                    continue
            
            if downloaded:
                if len(downloaded) == 1:
                    return {"success": True, "file_path": downloaded[0], "is_video": False}
                else:
                    return {"success": True, "file_paths": downloaded, "is_video": False, "is_multiple": True}
            
            return {"success": False}
            
        except Exception as e:
            print(f"⚠️ Scrape method error: {e}")
            return {"success": False}
    
    @staticmethod
    def _method_bibliogram(shortcode):
        """Method 4: Bibliogram"""
        bibliogram_instances = [
            f"https://bibliogram.art/u/p/{shortcode}/",
            f"https://bibliogram.pussthecat.org/u/p/{shortcode}/",
            f"https://bibliogram.nixnet.services/u/p/{shortcode}/",
        ]
        
        for instance_url in bibliogram_instances:
            try:
                headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
                resp = requests.get(instance_url, headers=headers, timeout=15)
                
                if resp.status_code == 200:
                    imgs = re.findall(r'<img[^>]+src="([^"]+)"', resp.text)
                    for img_url in imgs:
                        if shortcode in img_url or 'jpg' in img_url or 'png' in img_url:
                            if img_url.startswith('//'):
                                img_url = 'https:' + img_url
                            
                            file_path = os.path.join(DOWNLOAD_DIR, f"{shortcode}.jpg")
                            img_headers = {'User-Agent': 'Mozilla/5.0', 'Referer': instance_url}
                            
                            ir = requests.get(img_url, headers=img_headers, stream=True, timeout=30)
                            if ir.status_code == 200:
                                with open(file_path, 'wb') as f:
                                    for chunk in ir.iter_content(chunk_size=8192):
                                        if chunk: f.write(chunk)
                                
                                if os.path.exists(file_path) and os.path.getsize(file_path) > 1000:
                                    print(f"✅ Photo via Bibliogram: {os.path.basename(file_path)}")
                                    return {"success": True, "file_path": file_path, "is_video": False}
            except:
                continue
        
        return {"success": False}
    
    @staticmethod
    def _method_cdn(shortcode):
        """Method 5: Direct CDN"""
        try:
            cdn_urls = [
                f"https://www.instagram.com/p/{shortcode}/media/?size=l",
                f"https://i.instagram.com/{shortcode}.jpg",
            ]
            
            for cdn_url in cdn_urls:
                try:
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36',
                        'Accept': 'image/*',
                        'Referer': 'https://www.instagram.com/',
                    }
                    
                    r = requests.get(cdn_url, headers=headers, stream=True, timeout=30)
                    if r.status_code == 200 and 'image' in r.headers.get('content-type', ''):
                        file_path = os.path.join(DOWNLOAD_DIR, f"{shortcode}.jpg")
                        with open(file_path, 'wb') as f:
                            for chunk in r.iter_content(chunk_size=8192):
                                if chunk: f.write(chunk)
                        
                        if os.path.exists(file_path) and os.path.getsize(file_path) > 1000:
                            print(f"✅ Photo via CDN: {os.path.basename(file_path)}")
                            return {"success": True, "file_path": file_path, "is_video": False}
                except:
                    continue
        except:
            pass
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

    # Step 1: Send random emoji sticker (3 sec display)
    emoji_id = get_random_emoji()
    emoji_msg = None
    if emoji_id:
        try:
            emoji_msg = await context.bot.send_sticker(chat_id, emoji_id)
        except:
            pass

    await asyncio.sleep(EMOJI_DISPLAY_TIME)

    # Delete emoji after 3 seconds
    if emoji_msg:
        try:
            await emoji_msg.delete()
        except:
            pass

    await asyncio.sleep(0.2)

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
    sticker_msg = None
    if sticker_id:
        try:
            sticker_msg = await context.bot.send_sticker(chat_id, sticker_id)
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

    # Step 6: Delete sticker 5 seconds after final message
    if sticker_msg:
        await asyncio.sleep(STICKER_DELETE_AFTER_FINAL)
        try:
            await sticker_msg.delete()
        except:
            pass

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
        await update.message.reply_text("⎘ **ADD EMOJI**\n\nReply to a premium emoji sticker with `/addemoji`", parse_mode="Markdown")
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
        await update.message.reply_text("⎘ **ADD STICKER**\n\nReply to a sticker with `/addsticker`", parse_mode="Markdown")
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
        await update.message.reply_text("⎘ **ADD VIDEO**\n\nReply to a video with `/addvideo`", parse_mode="Markdown")
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
    
    # Send random sticker before processing
    sticker_id = get_random_sticker()
    if sticker_id:
        try:
            await context.bot.send_sticker(update.effective_chat.id, sticker_id)
        except:
            pass
    
    msg = await update.message.reply_text("⏳ **Processing...**", parse_mode="Markdown")
    
    try:
        await msg.edit_text("📥 **Downloading...**", parse_mode="Markdown")
        
        result = InstaDownloader.download_media(url)
        
        if not result.get("success"):
            await msg.edit_text(f"❌ **Failed!**\n\n{result.get('error', 'Unknown')}", parse_mode="Markdown")
            return
        
        if result.get("is_multiple"):
            photo_paths = result.get("file_paths", [])
            await msg.edit_text(f"📤 **Uploading {len(photo_paths)} photos...**", parse_mode="Markdown")
            for fp in photo_paths:
                if os.path.exists(fp) and os.path.getsize(fp) > 1000:
                    try:
                        with open(fp, 'rb') as f:
                            await update.message.reply_photo(photo=f, caption=CAPTION, parse_mode="Markdown")
                    except Exception as e:
                        await update.message.reply_text(f"❌ Error: {str(e)[:50]}")
                    InstaDownloader.cleanup(fp)
            await msg.delete()
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
                    video=f, caption=CAPTION, parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(keyboard), supports_streaming=True
                )
        else:
            await msg.edit_text("📤 **Uploading Photo...**", parse_mode="Markdown")
            with open(fp, 'rb') as f:
                await update.message.reply_photo(photo=f, caption=CAPTION, parse_mode="Markdown")
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
            "🎵 **Audio ka naam likhein:**\n\nJaise: `Meri Song`\nYa: `skip`\n\n⬇️ Type karo:",
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
    
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    app.run_polling()

if __name__ == "__main__":
    main()
