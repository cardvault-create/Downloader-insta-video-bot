import logging
import os
import re
import subprocess
import shutil
import time
import json
import urllib.parse
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
import yt_dlp
import requests

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
    
    # ═══════════════════════════
    # 🎬 MAIN
    # ═══════════════════════════
    
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
    # 🎬 VIDEO - DIRECT INSTAGRAM STREAM WITH AUDIO
    # ═══════════════════════════
    
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
                print("📡 Fetching Instagram API...")
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
                            if 'video_dash_manifest' in data_dict:
                                manifest = data_dict['video_dash_manifest']
                                if isinstance(manifest, str):
                                    return manifest
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
                    
                    if video_url:
                        print(f"✅ Found video URL from API")
                    
            except Exception as e:
                print(f"⚠️ API method failed: {e}")
            
            if not video_url:
                print("📡 API failed, using yt-dlp with forced audio...")
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
                
                ffmpeg = shutil.which('ffmpeg')
                if ffmpeg:
                    ydl_opts['ffmpeg_location'] = ffmpeg
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    
                    if not info:
                        return {"success": False, "error": "No response from Instagram"}
                    
                    file_path = None
                    for f in os.listdir(DOWNLOAD_DIR):
                        if shortcode in f and f.endswith('.mp4'):
                            fp = os.path.join(DOWNLOAD_DIR, f)
                            if os.path.exists(fp) and os.path.getsize(fp) > 5000:
                                file_path = fp
                                break
                    
                    if not file_path:
                        mp4_files = sorted(
                            [f for f in os.listdir(DOWNLOAD_DIR) if f.endswith('.mp4')],
                            key=lambda x: os.path.getmtime(os.path.join(DOWNLOAD_DIR, x)),
                            reverse=True
                        )
                        if mp4_files:
                            file_path = os.path.join(DOWNLOAD_DIR, mp4_files[0])
                    
                    if file_path:
                        print(f"✅ Video via yt-dlp: {os.path.basename(file_path)}")
                        return {"success": True, "file_path": file_path, "is_video": True}
                    
                return {"success": False, "error": "File not found after download"}
            
            if video_url:
                print(f"📥 Downloading directly from Instagram CDN...")
                
                video_url = video_url.replace('\\u0026', '&')
                
                file_path = os.path.join(DOWNLOAD_DIR, f"{shortcode}.mp4")
                
                dl_headers = {
                    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1',
                    'Accept': '*/*',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'identity',
                    'Referer': 'https://www.instagram.com/',
                    'Origin': 'https://www.instagram.com',
                    'Connection': 'keep-alive',
                    'Sec-Fetch-Dest': 'video',
                    'Sec-Fetch-Mode': 'cors',
                    'Sec-Fetch-Site': 'cross-site',
                }
                
                video_response = session.get(video_url, headers=dl_headers, stream=True, timeout=60)
                
                if video_response.status_code == 200:
                    total_size = int(video_response.headers.get('content-length', 0))
                    
                    with open(file_path, 'wb') as f:
                        downloaded = 0
                        for chunk in video_response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                    
                    if os.path.exists(file_path) and os.path.getsize(file_path) > 5000:
                        print(f"✅ Direct download: {os.path.basename(file_path)} ({os.path.getsize(file_path)} bytes)")
                        return {"success": True, "file_path": file_path, "is_video": True}
                    else:
                        print(f"⚠️ Direct download too small, trying yt-dlp fallback...")
                        os.remove(file_path)
                else:
                    print(f"⚠️ Direct download failed with status {video_response.status_code}")
            
            print("📡 Final fallback using yt-dlp...")
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'outtmpl': os.path.join(DOWNLOAD_DIR, f'{shortcode}.%(ext)s'),
                'format': 'mp4',
                'retries': 3,
            }
            
            if os.path.exists('cookies.txt'):
                ydl_opts['cookiefile'] = 'cookies.txt'
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                
                if not info:
                    return {"success": False, "error": "No response from Instagram"}
                
                file_path = None
                for f in os.listdir(DOWNLOAD_DIR):
                    if shortcode in f and f.endswith('.mp4'):
                        fp = os.path.join(DOWNLOAD_DIR, f)
                        if os.path.exists(fp) and os.path.getsize(fp) > 5000:
                            file_path = fp
                            break
                
                if file_path:
                    print(f"✅ Video via yt-dlp fallback: {os.path.basename(file_path)}")
                    return {"success": True, "file_path": file_path, "is_video": True}
            
            return {"success": False, "error": "File not found"}
            
        except Exception as e:
            err = str(e)
            if 'HTTP Error 403' in err or 'HTTP Error 401' in err:
                return {"success": False, "error": "❌ cookies.txt expired! Naya banao."}
            return {"success": False, "error": f"❌ {err[:80]}"}
    
    # ═══════════════════════════
    # 📸 PHOTO - 100% WORKING
    # ═══════════════════════════
    
    @staticmethod
    def _download_photo(shortcode):
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
    
    # ═══════════════════════════
    # 🎵 AUDIO
    # ═══════════════════════════
    
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
            
            probe = subprocess.run(
                ['ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_entries', 'stream=codec_type', '-of', 'csv=p=0', video_path],
                capture_output=True, text=True, timeout=30
            )
            
            if not probe.stdout.strip():
                return {"success": False, "error": "❌ No audio track in this video"}
            
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
    "𝘋𝘰𝘸𝘯𝘭𝘰𝘢𝘥𝘦𝘥 𝘉𝘺 [˹𝚰𝖓𝖘𝖙𝖆𝖌𝖗𝖆𝖒 ✘ 𝚫𝐨𝐰𝐧𝐥𝐨𝐚𝐝𝐞𝐫˼ ♪�҉](https://t.me/Instagram_LinkToVideo_Bot)\n"
    "�҉ ˹𝐂𝛄𝛆𝛂𝛕𝛆𝛄˼ 🪽 ➪ [𝜝𝜣𝜯 𝑭𝜟𝜯𝜢𝜮𝜞](https://t.me/FathersOfCreater) ┏༼ ◉ ╭╮ ◉༽┓�҉"
)

# ═══════════════════════════
# 🤖 TELEGRAM HANDLERS
# ═══════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.id
    if user not in AUTHORIZED_USERS:
        return
    
    user_name = update.effective_user.first_name
    user_mention = f"[{user_name}](tg://user?id={user})"
    
    await update.message.reply_text(
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
        f"🫧 ˹ᴅᴇᴠᴇʟᴏᴩᴇʀ˼ 🪽 ➪ [𝜝𝜣𝜯 𝑭𝜟𝜯𝜢𝜮𝜞](https://t.me/FathersOfCreater) ✔︎",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("◆ ➪ ˹𝜟𝙙𝙙 𝜯𝜣 𝑮𝜞𝜭𝑼𝝆˼ ♪☬", url=f"https://t.me/{(await context.bot.get_me()).username}?startgroup=true")]
        ])
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
        
        await msg.edit_text("📥 **Downloading Video...**" if is_reel else "📥 **Downloading Photo...**")
        
        result = InstaDownloader.download_media(url)
        
        if not result.get("success"):
            error = result.get('error', 'Unknown')
            await msg.edit_text(
                f"❌ **Failed!**\n\n{error}\n\n"
                f"💡 **Solution:** Fresh cookies.txt banao aur GitHub pe upload karo.",
                parse_mode="Markdown"
            )
            return
        
        if result.get("is_multiple"):
            photo_paths = result.get("file_paths", [])
            await msg.edit_text(f"📤 **Uploading {len(photo_paths)} photos...**")
            for i, fp in enumerate(photo_paths):
                if os.path.exists(fp) and os.path.getsize(fp) > 1000:
                    try:
                        with open(fp, 'rb') as f:
                            await update.message.reply_photo(
                                photo=f,
                                caption=CAPTION,
                                parse_mode="Markdown"
                            )
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
            await msg.edit_text("📤 **Uploading Video...**")
            keyboard = [[InlineKeyboardButton("🎵 Download Audio", callback_data="get_audio")]]
            
            with open(fp, 'rb') as f:
                await update.message.reply_video(
                    video=f,
                    caption=CAPTION,
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    supports_streaming=True
                )
            await msg.delete()
        else:
            await msg.edit_text("📤 **Uploading Photo...**")
            with open(fp, 'rb') as f:
                await update.message.reply_photo(
                    photo=f,
                    caption=CAPTION,
                    parse_mode="Markdown"
                )
            await msg.delete()
        
        InstaDownloader.cleanup(fp)
        
    except Exception as e:
        await msg.edit_text(f"❌ **Error:** {str(e)[:100]}")
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
            await status_msg.edit_text("📤 **Uploading Audio...**")
            
            with open(ap, 'rb') as f:
                await update.message.reply_audio(
                    audio=f,
                    title=audio_name,
                    performer="Instagram",
                    caption=CAPTION,
                    parse_mode="Markdown"
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
            "Jaise: `Meri Song`\n"
            "Ya: `skip`\n\n"
            "⬇️ Type karo:",
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
    print("╚══════════════════════════╝")
    
    ffmpeg = shutil.which('ffmpeg')
    if ffmpeg:
        print(f"✅ FFmpeg: {ffmpeg}")
    else:
        print("⚠️ Installing FFmpeg...")
        os.system('apt-get update && apt-get install ffmpeg -y 2>/dev/null')
    
    if os.path.exists('cookies.txt'):
        size = os.path.getsize('cookies.txt')
        has_session = 'sessionid' in open('cookies.txt').read()
        print(f"✅ cookies.txt ({size} bytes) - sessionid: {'✅' if has_session else '❌'}")
    else:
        print("ℹ️ cookies.txt not found")
    
    for f in os.listdir(DOWNLOAD_DIR):
        try: os.remove(os.path.join(DOWNLOAD_DIR, f))
        except: pass
    
    print("✅ Bot Started! 🚀")
    print("📸 Photos: oEmbed API + yt-dlp + Scrape + Bibliogram + CDN")
    print("🎬 Videos: Direct Instagram API + yt-dlp fallback")
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    app.run_polling()

if __name__ == "__main__":
    main()
