import json
import threading
from oauth2client.service_account import ServiceAccountCredentials
import gspread

# ═══════════ YEH 2 CHEEZEIN BHARO ═══════════
SHEET_ID = "YOUR_SHEET_ID_HERE"           # Google Sheet ID
SHEET_NAME = "Sheet1"                     # Sheet ka naam
# ═══════════════════════════════════════════

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("creds.json", scope)
client = gspread.authorize(creds)
sheet = client.open_by_key(SHEET_ID).worksheet(SHEET_NAME)

ALL_DATA = {}

# Load data
try:
    data_str = sheet.acell('A1').value
    if data_str and data_str != '{}':
        ALL_DATA = json.loads(data_str)
        print(f"✅ Sheet data loaded!")
    else:
        ALL_DATA = {}
        sheet.update('A1', '{}')
        print("🆕 Fresh start")
except:
    ALL_DATA = {}
    sheet.update('A1', '{}')

def save_sheet():
    try:
        sheet.update('A1', json.dumps(ALL_DATA, ensure_ascii=False))
    except: pass

import sys
main = sys.modules.get('__main__')
if main:
    def new_jload(f, d=None):
        key = f.replace('.json', '')
        return ALL_DATA.get(key, d if d is not None else {})
    
    def new_jsave(f, d):
        key = f.replace('.json', '')
        ALL_DATA[key] = d
        threading.Thread(target=save_sheet, daemon=True).start()
    
    main.jload = new_jload
    main.jsave = new_jsave
    main.__dict__['jload'] = new_jload
    main.__dict__['jsave'] = new_jsave
