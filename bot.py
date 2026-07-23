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
            print(f"📸 Downloading Photo(s): {shortcode}")
            return InstaDownloader._download_photo(shortcode)
    
    # ═══════════════════════════
    # 🎬 VIDEO
    # ═══════════════════════════
    
    @staticmethod
    def _download_video(shortcode, url):
        try:
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'outtmpl': os.path.join(DOWNLOAD_DIR, f'{shortcode}.%(ext)s'),
                'format': 'best[ext=mp4]/best',
                'retries': 3,
            }
            
            if os.path.exists('cookies.txt'):
                ydl_opts['cookiefile'] = 'cookies.txt'
            
            ffmpeg = shutil.which('ffmpeg')
            if ffmpeg:
                ydl_opts['ffmpeg_location'] = ffmpeg
                ydl_opts['postprocessors'] = [{
                    'key': 'FFmpegVideoConvertor',
                    'preferedformat': 'mp4',
                }]
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                
                if not info:
                    return {"success": False, "error": "No response from Instagram"}
                
                file_path = None
                for f in os.listdir(DOWNLOAD_DIR):
                    if shortcode in f and f.endswith('.mp4'):
                        file_path = os.path.join(DOWNLOAD_DIR, f)
                        break
                
                if not file_path:
                    mp4_files = sorted(
                        [f for f in os.listdir(DOWNLOAD_DIR) if f.endswith('.mp4')],
                        key=lambda x: os.path.getmtime(os.path.join(DOWNLOAD_DIR, x)),
                        reverse=True
                    )
                    if mp4_files:
                        file_path = os.path.join(DOWNLOAD_DIR, mp4_files[0])
                
                if file_path and os.path.exists(file_path) and os.path.getsize(file_path) > 5000:
                    print(f"✅ Video: {os.path.basename(file_path)}")
                    return {"success": True, "file_path": file_path, "is_video": True}
                
                return {"success": False, "error": "File not found"}
                
        except Exception as e:
            err = str(e)
            if 'HTTP Error 403' in err or 'HTTP Error 401' in err:
                return {"success": False, "error": "❌ cookies.txt expired! Naya banao."}
            return {"success": False, "error": f"❌ {err[:80]}"}
    
    # ═══════════════════════════
    # 📸 PHOTO - ENHANCED FOR MULTIPLE PHOTOS
    # ═══════════════════════════
    
    @staticmethod
    def _download_photo(shortcode):
        """Photo download - Enhanced to get ALL photos from carousel/album posts"""
        
        # First, try to detect if it's a carousel/album post
        print("🔍 Checking for multiple photos...")
        
        # METHOD 1: yt-dlp with all formats (best for multiple photos)
        print("📥 Method 1: yt-dlp (checking for multiple photos)")
        result = InstaDownloader._method_ytdlp_all_photos(shortcode)
        if result.get("success"):
            return result
        
        # METHOD 2: oEmbed API (may give first photo only)
        print("📥 Method 2: Instagram oEmbed API")
        result = InstaDownloader._method_oembed(shortcode)
        if result.get("success"):
            return result
        
        # METHOD 3: Direct page scrape with carousel detection
        print("📥 Method 3: Page scrape with carousel detection")
        result = InstaDownloader._method_scrape_all(shortcode)
        if result.get("success"):
            return result
        
        # METHOD 4: Bibliogram
        print("📥 Method 4: Bibliogram")
        result = InstaDownloader._method_bibliogram(shortcode)
        if result.get("success"):
            return result
        
        # METHOD 5: Direct CDN
        print("📥 Method 5: Direct CDN")
        result = InstaDownloader._method_cdn(shortcode)
        if result.get("success"):
            return result
        
        return {"success": False, "error": "Photo download failed. Instagram may be blocking."}
    
    @staticmethod
    def _method_ytdlp_all_photos(shortcode):
        """Method 1: yt-dlp - Downloads ALL photos from carousel posts"""
        try:
            url = f"https://www.instagram.com/p/{shortcode}/"
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'outtmpl': os.path.join(DOWNLOAD_DIR, f'{shortcode}_%(playlist_index)s.%(ext)s'),
                'format': 'best',
                'retries': 3,
                'ignoreerrors': True,
                'no_playlist': False,  # Allow playlist download for carousel
            }
            if os.path.exists('cookies.txt'):
                ydl_opts['cookiefile'] = 'cookies.txt'
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                if info:
                    # Check if it's a multi-photo post
                    entries = info.get('entries', [])
                    
                    # If no entries, it might be a single photo
                    if not entries:
                        # Try single download
                        ydl_opts_single = {
                            'quiet': True,
                            'no_warnings': True,
                            'outtmpl': os.path.join(DOWNLOAD_DIR, f'{shortcode}.%(ext)s'),
                            'format': 'best',
                            'retries': 3,
                        }
                        if os.path.exists('cookies.txt'):
                            ydl_opts_single['cookiefile'] = 'cookies.txt'
                        
                        with yt_dlp.YoutubeDL(ydl_opts_single) as ydl2:
                            info2 = ydl2.extract_info(url, download=True)
                            time.sleep(1)
                            
                            photo_files = []
                            for f in os.listdir(DOWNLOAD_DIR):
                                if shortcode in f and not f.endswith(('.mp4', '.mov', '.webm')):
                                    fp = os.path.join(DOWNLOAD_DIR, f)
                                    if os.path.exists(fp) and os.path.getsize(fp) > 1000:
                                        photo_files.append(fp)
                            
                            if photo_files:
                                print(f"✅ Found {len(photo_files)} photo(s) via yt-dlp")
                                if len(photo_files) == 1:
                                    return {"success": True, "file_path": photo_files[0], "is_video": False}
                                else:
                                    return {"success": True, "file_paths": sorted(photo_files), "is_video": False, "is_multiple": True}
                    
                    # Multiple photos found
                    if entries:
                        print(f"📸 Detected {len(entries)} photos in carousel")
                        
                        # Download all photos
                        ydl_opts_download = {
                            'quiet': True,
                            'no_warnings': True,
                            'outtmpl': os.path.join(DOWNLOAD_DIR, f'{shortcode}_%(playlist_index)s.%(ext)s'),
                            'format': 'best',
                            'retries': 3,
                            'ignoreerrors': True,
                            'no_playlist': False,
                        }
                        if os.path.exists('cookies.txt'):
                            ydl_opts_download['cookiefile'] = 'cookies.txt'
                        
                        with yt_dlp.YoutubeDL(ydl_opts_download) as ydl3:
                            ydl3.download([url])
                        
                        time.sleep(2)
                        
                        photo_files = []
                        for f in sorted(os.listdir(DOWNLOAD_DIR)):
                            if shortcode in f and not f.endswith(('.mp4', '.mov', '.webm')):
                                fp = os.path.join(DOWNLOAD_DIR, f)
                                if os.path.exists(fp) and os.path.getsize(fp) > 1000:
                                    photo_files.append(fp)
                        
                        if photo_files:
                            print(f"✅ Downloaded {len(photo_files)} photos from carousel")
                            if len(photo_files) == 1:
                                return {"success": True, "file_path": photo_files[0], "is_video": False}
                            else:
                                return {"success": True, "file_paths": sorted(photo_files), "is_video": False, "is_multiple": True}
            
        except Exception as e:
            print(f"⚠️ yt-dlp all photos error: {e}")
        
        return {"success": False}
    
    @staticmethod
    def _method_oembed(shortcode):
        """Method 2: Instagram Official oEmbed API"""
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
            
            print(f"🔗 Found {len(image_urls)} image URLs from oEmbed")
            
            # Download images
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
    def _method_scrape_all(shortcode):
        """Method 3: Enhanced page scrape that detects and downloads ALL carousel photos"""
        try:
            session = requests.Session()
            
            # Load cookies if available
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
            
            # Find all possible image URLs - enhanced for carousel
            all_image_urls = []
            
            # 1. __NEXT_DATA__ - This usually contains ALL carousel images
            nd = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.DOTALL)
            if nd:
                try:
                    data = json.loads(nd.group(1))
                    
                    # Navigate through the JSON to find carousel media
                    def find_all_urls(obj, depth=0):
                        if depth > 10:
                            return []
                        urls = []
                        if isinstance(obj, dict):
                            # Check for carousel media
                            if 'carousel_media' in obj:
                                carousel = obj['carousel_media']
                                if isinstance(carousel, list):
                                    for item in carousel:
                                        if isinstance(item, dict):
                                            for media_item in item.get('images', {}).values():
                                                url = media_item.get('url') or media_item.get('display_url')
                                                if url and url not in urls:
                                                    urls.append(url)
                            elif 'image_versions2' in obj:
                                candidates = obj['image_versions2'].get('candidates', [])
                                for candidate in candidates:
                                    url = candidate.get('url')
                                    if url and url not in urls:
                                        urls.append(url)
                            
                            # Check all values
                            for v in obj.values():
                                urls.extend(find_all_urls(v, depth + 1))
                        elif isinstance(obj, list):
                            for item in obj:
                                urls.extend(find_all_urls(item, depth + 1))
                        return urls
                    
                    all_image_urls = find_all_urls(data)
                    if all_image_urls:
                        print(f"📸 Found {len(all_image_urls)} carousel images in __NEXT_DATA__")
                except Exception as e:
                    print(f"⚠️ Error parsing __NEXT_DATA__: {e}")
            
            # 2. Fallback: Regex for multiple display_url
            if not all_image_urls:
                display_urls = re.findall(r'"display_url":"([^"]+)"', html)
                all_image_urls = [u.replace('\\u0026', '&') for u in display_urls]
                if all_image_urls:
                    print(f"📸 Found {len(all_image_urls)} images via display_url regex")
            
            # 3. Fallback: og:image
            if not all_image_urls:
                og = re.findall(r'<meta\s+property="og:image"\s+content="([^"]+)"', html)
                all_image_urls = list(set(og))
                if all_image_urls:
                    print(f"📸 Found {len(all_image_urls)} images via og:image")
            
            # Remove duplicates while preserving order
            seen = set()
            unique_urls = []
            for url in all_image_urls:
                # Clean up URL
                url = url.split('?')[0]
                if url not in seen and '.mp4' not in url and '.mov' not in url:
                    seen.add(url)
                    unique_urls.append(url)
            
            all_image_urls = unique_urls
            
            if not all_image_urls:
                print("⚠️ No image URLs found in page")
                return {"success": False}
            
            print(f"🔗 Total unique images to download: {len(all_image_urls)}")
            
            # Download ALL images
            downloaded = []
            for i, img_url in enumerate(all_image_urls):
                try:
                    if img_url.startswith('//'):
                        img_url = 'https:' + img_url
                    if img_url.startswith('http://'):
                        img_url = img_url.replace('http://', 'https://')
                    
                    img_url = img_url.split('?')[0]
                    
                    ext = 'jpg'
                    if '.png' in img_url: ext = 'png'
                    elif '.webp' in img_url: ext = 'webp'
                    
                    # Number photos if multiple
                    if len(all_image_urls) > 1:
                        file_name = f"{shortcode}_{i+1}.{ext}"
                    else:
                        file_name = f"{shortcode}.{ext}"
                    
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
                            print(f"✅ Downloaded photo {i+1}/{len(all_image_urls)}: {os.path.basename(file_path)} ({os.path.getsize(file_path)} bytes)")
                except Exception as e:
                    print(f"⚠️ Download error for image {i+1}: {e}")
                    continue
            
            if downloaded:
                print(f"✅ Successfully downloaded {len(downloaded)} photos")
                if len(downloaded) == 1:
                    return {"success": True, "file_path": downloaded[0], "is_video": False}
                else:
                    return {"success": True, "file_paths": sorted(downloaded), "is_video": False, "is_multiple": True, "total_photos": len(downloaded)}
            
            return {"success": False}
            
        except Exception as e:
            print(f"⚠️ Scrape all method error: {e}")
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
                    downloaded = []
                    
                    for i, img_url in enumerate(imgs):
                        if shortcode in img_url or 'jpg' in img_url or 'png' in img_url:
                            if img_url.startswith('//'):
                                img_url = 'https:' + img_url
                            
                            if len(imgs) > 1:
                                file_path = os.path.join(DOWNLOAD_DIR, f"{shortcode}_{i+1}.jpg")
                            else:
                                file_path = os.path.join(DOWNLOAD_DIR, f"{shortcode}.jpg")
                            
                            img_headers = {'User-Agent': 'Mozilla/5.0', 'Referer': instance_url}
                            
                            ir = requests.get(img_url, headers=img_headers, stream=True, timeout=30)
                            if ir.status_code == 200:
                                with open(file_path, 'wb') as f:
                                    for chunk in ir.iter_content(chunk_size=8192):
                                        if chunk: f.write(chunk)
                                
                                if os.path.exists(file_path) and os.path.getsize(file_path) > 1000:
                                    downloaded.append(file_path)
                    
                    if downloaded:
                        print(f"✅ Found {len(downloaded)} photos via Bibliogram")
                        if len(downloaded) == 1:
                            return {"success": True, "file_path": downloaded[0], "is_video": False}
                        else:
                            return {"success": True, "file_paths": downloaded, "is_video": False, "is_multiple": True}
            except:
                continue
        
        return {"success": False}
    
    @staticmethod
    def _method_cdn(shortcode):
        """Method 5: Direct Instagram CDN"""
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
# 🤖 TELEGRAM HANDLERS
# ═══════════════════════════

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.id
    if user not in AUTHORIZED_USERS:
        return
    
    await update.message.reply_text(
        "📥 **Instagram Downloader Bot**\n\n"
        "✅ **Reel link** → HD Video + Audio 🎬\n"
        "✅ **Post link** → HD Photo(s) 📸\n"
        "✅ **Multiple photos** → Ek ke baad ek bhejega! 🔄\n"
        "✅ **Audio button** → Naam do → MP3 ⚡\n\n"
        "**Sirf link bhejo!** 🔗",
        parse_mode="Markdown"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user.id
    if user not in AUTHORIZED_USERS:
        return
    
    text = update.message.text
    if not text:
        return
    
    # Audio name
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
        
        await msg.edit_text("📥 **Downloading Video...**" if is_reel else "📥 **Downloading Photo(s)...**")
        
        result = InstaDownloader.download_media(url)
        
        if not result.get("success"):
            error = result.get('error', 'Unknown')
            await msg.edit_text(
                f"❌ **Failed!**\n\n{error}\n\n"
                f"💡 **Solution:** Fresh cookies.txt banao aur GitHub pe upload karo.",
                parse_mode="Markdown"
            )
            return
        
        # Multiple photos - SEND ONE BY ONE WITH DELAY
        if result.get("is_multiple"):
            photo_paths = result.get("file_paths", [])
            total = len(photo_paths)
            
            await msg.edit_text(f"📤 **{total} Photos mil gaye! Ek ek karke bhej raha hun...**")
            
            for i, fp in enumerate(photo_paths, 1):
                if os.path.exists(fp) and os.path.getsize(fp) > 1000:
                    try:
                        # Send status update for current photo
                        if i > 1:
                            # For subsequent photos, send a brief notification
                            status_msg = await update.message.reply_text(
                                f"📤 **Photo {i}/{total} bhej raha hun...**",
                                parse_mode="Markdown"
                            )
                        
                        with open(fp, 'rb') as f:
                            if i == 1:
                                # First photo with URL caption
                                await update.message.reply_photo(
                                    photo=f,
                                    caption=f"✅ **Photo {i}/{total}** ✅\n📸 Instagram Post se downloaded\n🔗 [Post Link]({url})",
                                    parse_mode="Markdown"
                                )
                            else:
                                # Subsequent photos with simple caption
                                await update.message.reply_photo(
                                    photo=f,
                                    caption=f"✅ **Photo {i}/{total}** ✅",
                                    parse_mode="Markdown"
                                )
                        
                        # Delete status message if created
                        if i > 1 and 'status_msg' in locals():
                            try:
                                await status_msg.delete()
                            except:
                                pass
                        
                        # Small delay between photos to avoid rate limiting
                        if i < total:
                            time.sleep(0.5)
                            
                    except Exception as e:
                        await update.message.reply_text(f"❌ Photo {i} bhejne mein error: {str(e)[:50]}")
                    
                    # Cleanup
                    InstaDownloader.cleanup(fp)
            
            # Final status
            try:
                await msg.edit_text(f"✅ **Sab {total} Photos bhej diye!** 🔥", parse_mode="Markdown")
            except:
                await update.message.reply_text(f"✅ **Sab {total} Photos bhej diye!** 🔥", parse_mode="Markdown")
            
            # Delete the status message after a delay
            try:
                await asyncio.sleep(2)
                await msg.delete()
            except:
                pass
            
            return
        
        # Single file
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
                    caption=f"✅ **Video + Audio** ✅\n🔗 [Instagram Link]({url})",
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
                    caption=f"✅ **Photo Downloaded** ✅\n🔗 [Instagram Link]({url})",
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
        
        # If multiple, get first video
        if result.get("is_multiple"):
            vp = result["file_paths"][0]
        else:
            vp = result["file_path"]
        
        audio_result = InstaDownloader.extract_audio(vp, audio_name)
        
        if audio_result.get("success"):
            ap = audio_result["file_path"]
            await status_msg.edit_text("📤 **Uploading Audio...**")
            
            with open(ap, 'rb') as f:
                await update.message.reply_audio(
                    audio=f, title=audio_name, performer="Instagram",
                    caption=f"🎵 **{audio_name}** ✅"
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

import asyncio

def main():
    logging.basicConfig(level=logging.INFO)
    
    print("╔══════════════════════════╗")
    print("║  🤖 INSTAGRAM BOT v2.0  ║")
    print("║  Multi-Photo Support!   ║")
    print("╚══════════════════════════╝")
    
    # FFmpeg
    ffmpeg = shutil.which('ffmpeg')
    if ffmpeg:
        print(f"✅ FFmpeg: {ffmpeg}")
    else:
        print("⚠️ Installing FFmpeg...")
        os.system('apt-get update && apt-get install ffmpeg -y 2>/dev/null')
    
    # cookies.txt
    if os.path.exists('cookies.txt'):
        size = os.path.getsize('cookies.txt')
        has_session = 'sessionid' in open('cookies.txt').read()
        print(f"✅ cookies.txt ({size} bytes) - sessionid: {'✅' if has_session else '❌'}")
    else:
        print("ℹ️ cookies.txt not found")
    
    # Clean
    for f in os.listdir(DOWNLOAD_DIR):
        try: os.remove(os.path.join(DOWNLOAD_DIR, f))
        except: pass
    
    print("✅ Bot Started! 🚀")
    print("📸 Photos: Multiple photos support enabled!")
    print("🎬 Videos: yt-dlp best format")
    print("🔄 Carousel: All photos will be sent one by one!")
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button_handler))
    
    app.run_polling()

if __name__ == "__main__":
    main()
