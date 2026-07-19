import os
import json
import random
import smtplib
import re
import urllib.request
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.utils import formatdate
from PIL import Image, ImageDraw, ImageFont
import google.genai as genai

# ==========================================
# 1. 환경 변수 및 기본 설정
# ==========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.environ.get("EMAIL_RECEIVER")

MODELS_TO_TRY = ['gemini-2.0-flash', 'gemini-2.0-flash-lite', 'gemini-3.1-flash-lite', 'gemini-3.5-flash']
HISTORY_FILE = "theme_history.json" # 테마 히스토리 저장용

# ==========================================
# 2. 🎨 14 프리미엄 테마 스키마 (현대카드 스타일)
# ==========================================
THEMES_14 = {
    # Vivid 7
    "Vivid_Red": {"mainBg": "#FF0000", "mainText": "#FFFFFF", "subBg": "#00FFFF", "subText": "#000000"},
    "Vivid_Blue": {"mainBg": "#0052CC", "mainText": "#FFFFFF", "subBg": "#FFAD00", "subText": "#000000"},
    "Vivid_Yellow": {"mainBg": "#FFD600", "mainText": "#000000", "subBg": "#2900FF", "subText": "#FFFFFF"},
    "Vivid_Green": {"mainBg": "#00C853", "mainText": "#FFFFFF", "subBg": "#C80075", "subText": "#FFFFFF"},
    "Vivid_Purple": {"mainBg": "#7B61FF", "mainText": "#FFFFFF", "subBg": "#E5FF61", "subText": "#000000"},
    "Vivid_Orange": {"mainBg": "#FF6D00", "mainText": "#FFFFFF", "subBg": "#0092FF", "subText": "#FFFFFF"},
    "Vivid_Sky": {"mainBg": "#00B4D8", "mainText": "#FFFFFF", "subBg": "#D82400", "subText": "#FFFFFF"},
    # Deep & Premium 7
    "Deep_Black": {"mainBg": "#000000", "mainText": "#FFFFFF", "subBg": "#333333", "subText": "#FFFFFF"},
    "Deep_Navy": {"mainBg": "#001F3F", "mainText": "#FFFFFF", "subBg": "#FFD700", "subText": "#000000"},
    "Deep_Gold": {"mainBg": "#B8860B", "mainText": "#FFFFFF", "subBg": "#1a1a1a", "subText": "#FFFFFF"},
    "Deep_Burgundy": {"mainBg": "#800020", "mainText": "#FFFFFF", "subBg": "#008060", "subText": "#FFFFFF"},
    "Deep_RoyalPurple": {"mainBg": "#4B0082", "mainText": "#FFFFFF", "subBg": "#FF7F50", "subText": "#000000"},
    "Deep_Platinum": {"mainBg": "#C0C0C0", "mainText": "#000000", "subBg": "#1a1a1a", "subText": "#FFFFFF"},
    "Deep_Charcoal": {"mainBg": "#333333", "mainText": "#FFFFFF", "subBg": "#FF4500", "subText": "#FFFFFF"}
}

# ==========================================
# 3. 공통 유틸리티 (폰트/파싱 안정성 강화)
# ==========================================
def get_smart_random_theme():
    history = []
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                data = json.load(f)
                history = data.get("recent_themes", [])
        except json.JSONDecodeError:
            pass
            
    available_themes = [t for t in THEMES_14.keys() if t not in history[-10:]]
    if not available_themes:
        available_themes = list(THEMES_14.keys())
        if history:
            available_themes.remove(history[-1])
            
    chosen_theme_name = random.choice(available_themes)
    
    history.append(chosen_theme_name)
    history = history[-10:] 
    
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump({
                "recent_themes": history, 
                "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }, f)
    except Exception as e:
        print(f"⚠️ 히스토리 저장 실패: {e}")
        
    return chosen_theme_name, THEMES_14[chosen_theme_name]

def clean_and_parse_json(raw_text):
    cleaned = re.sub(r'```json\s*|