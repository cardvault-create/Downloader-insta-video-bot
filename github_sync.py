import os
import json
import requests
import base64
import threading

# ═══════════ APNI DETAILS ═══════════
PART1 = "ghp_yMim1gFOu0XAFljb6D0"
PART2 = "E43TxuNSRrg4dX9Sw"
GITHUB_TOKEN = PART1 + PART2

GITHUB_USER = "card-shop"
REPO_NAME = "Downloader-insta-video-bot"
# ═════════════════════════════════════

ALL_DATA = {}

def save_github():
    try:
        url = f"https://api.github.com/repos/{GITHUB_USER}/{REPO_NAME}/contents/all_bot_data.json"
        h = {"Authorization": f"token {GITHUB_TOKEN}"}
        r = requests.get(url, headers=h)
        sha = r.json()["sha"] if r.status_code == 200 else None
        content = base64.b64encode(json.dumps(ALL_DATA).encode()).decode()
        body = {"message": "save", "content": content}
        if sha: body["sha"] = sha
        requests.put(url, json=body, headers=h)
    except: pass

try:
    url = f"https://raw.githubusercontent.com/{GITHUB_USER}/{REPO_NAME}/main/all_bot_data.json"
    ALL_DATA = requests.get(url).json()
except: ALL_DATA = {}

import sys
main = sys.modules.get('__main__')
if main:
    def new_jload(f, d=None):
        key = os.path.basename(f).replace('.json', '')
        return ALL_DATA.get(key, d if d is not None else {})
    
    def new_jsave(f, d):
        key = os.path.basename(f).replace('.json', '')
        ALL_DATA[key] = d
        threading.Thread(target=save_github, daemon=True).start()
    
    main.jload = new_jload
    main.jsave = new_jsave
    main.__dict__['jload'] = new_jload
    main.__dict__['jsave'] = new_jsave
