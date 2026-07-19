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
HISTORY_FILE = "theme_history.json" # 직전 테마를 기억할 파일

# ==========================================
# 2. 🎨 14 프리미엄 테마 스키마 (V7.2 핵심)
# ==========================================
THEMES_14 = {
    # --- VIVID (원색 그룹: 시인성 극대화) ---
    "Vivid_Red": {"bg": "#FF0000", "slide5_bg": "#111111", "accent": "#FFFFFF", "text_main": "#FFFFFF", "text_sub": "#FFE5E5", "box_bg": "#111111", "box_text": "#FFFFFF", "line": "#CC0000"},
    "Vivid_Blue": {"bg": "#0052CC", "slide5_bg": "#111111", "accent": "#FFD600", "text_main": "#FFFFFF", "text_sub": "#E5F0FF", "box_bg": "#111111", "box_text": "#FFFFFF", "line": "#003D99"},
    "Vivid_Yellow": {"bg": "#FFD600", "slide5_bg": "#111111", "accent": "#000000", "text_main": "#000000", "text_sub": "#333333", "box_bg": "#111111", "box_text": "#FFD600", "line": "#CCA800"},
    "Vivid_Green": {"bg": "#00C853", "slide5_bg": "#111111", "accent": "#FFFFFF", "text_main": "#FFFFFF", "text_sub": "#E5FFE5", "box_bg": "#111111", "box_text": "#FFFFFF", "line": "#009933"},
    "Vivid_Purple": {"bg": "#7B61FF", "slide5_bg": "#111111", "accent": "#FFD600", "text_main": "#FFFFFF", "text_sub": "#F0E5FF", "box_bg": "#111111", "box_text": "#FFFFFF", "line": "#5C40D9"},
    "Vivid_Orange": {"bg": "#FF6D00", "slide5_bg": "#111111", "accent": "#FFFFFF", "text_main": "#FFFFFF", "text_sub": "#FFEBE5", "box_bg": "#111111", "box_text": "#FFFFFF", "line": "#CC5200"},
    "Vivid_Sky": {"bg": "#00B4D8", "slide5_bg": "#111111", "accent": "#FFFFFF", "text_main": "#FFFFFF", "text_sub": "#E5FAFF", "box_bg": "#111111", "box_text": "#FFFFFF", "line": "#008AAB"},
    
    # --- PASTEL (파스텔 그룹: 세련된 톤앤매너) ---
    "Pastel_Pink": {"bg": "#FFE4E6", "slide5_bg": "#881337", "accent": "#E11D48", "text_main": "#881337", "text_sub": "#9F1239", "box_bg": "#E11D48", "box_text": "#FFE4E6", "line": "#FECDD3"},
    "Pastel_Blue": {"bg": "#DBEAFE", "slide5_bg": "#1E3A8A", "accent": "#2563EB", "text_main": "#1E3A8A", "text_sub": "#1D4ED8", "box_bg": "#2563EB", "box_text": "#DBEAFE", "line": "#BFDBFE"},
    "Pastel_Mint": {"bg": "#D1FAE5", "slide5_bg": "#064E3B", "accent": "#059669", "text_main": "#064E3B", "text_sub": "#047857", "box_bg": "#059669", "box_text": "#D1FAE5", "line": "#A7F3D0"},
    "Pastel_Peach": {"bg": "#FFEDD5", "slide5_bg": "#7C2D12", "accent": "#EA580C", "text_main": "#7C2D12", "text_sub": "#9A3412", "box_bg": "#EA580C", "box_text": "#FFEDD5", "line": "#FED7AA"},
    "Pastel_Lavender": {"bg": "#EDE9FE", "slide5_bg": "#4C1D95", "accent": "#7C3AED", "text_main": "#4C1D95", "text_sub": "#5B21B6", "box_bg": "#7C3AED", "box_text": "#EDE9FE", "line": "#DDD6FE"},
    "Pastel_Lemon": {"bg": "#FEF9C3", "slide5_bg": "#713F12", "accent": "#CA8A04", "text_main": "#713F12", "text_sub": "#854D0E", "box_bg": "#CA8A04", "box_text": "#FEF9C3", "line": "#FEF08A"},
    "Pastel_Sand": {"bg": "#F4F3EF", "slide5_bg": "#111111", "accent": "#8B7355", "text_main": "#4A4036", "text_sub": "#5C5042", "box_bg": "#8B7355", "box_text": "#F4F3EF", "line": "#E5E3DB"}
}

# ==========================================
# 3. 공통 유틸리티
# ==========================================
def get_smart_random_theme():
    """직전 테마를 기억하고, 그것을 제외한 나머지 중 하나를 랜덤으로 뽑는 로직"""
    last_theme = None
    
    # 1. 히스토리 파일 읽기
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                data = json.load(f)
                last_theme = data.get("last_theme")
        except json.JSONDecodeError:
            pass
            
    # 2. 직전 테마를 제외한 후보군 생성
    available_themes = list(THEMES_14.keys())
    if last_theme in available_themes:
        available_themes.remove(last_theme)
        
    # 3. 새로운 테마 랜덤 선택
    chosen_theme_name = random.choice(available_themes)
    
    # 4. 선택된 테마를 히스토리에 저장
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump({
                "last_theme": chosen_theme_name, 
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }, f)
    except Exception as e:
        print(f"⚠️ 히스토리 저장 실패 (진행에는 문제없음): {e}")
        
    return chosen_theme_name, THEMES_14[chosen_theme_name]

def clean_and_parse_json(raw_text):
    cleaned = re.sub(r'```json\s*|```\s*', '', raw_text).strip()
    match = re.search(r'(\[.*\]|\{.*\})', cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    return None

def ask_ai(prompt, system_instruction=""):
    if not GEMINI_API_KEY:
        return None
    client = genai.Client(api_key=GEMINI_API_KEY)
    for model_name in MODELS_TO_TRY:
        try:
            print(f"🤖 AI 호출 중... ({model_name})")
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=genai.types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.3,
                    response_mime_type="application/json"
                )
            )
            result = clean_and_parse_json(response.text)
            if result:
                return result
        except Exception as e:
            continue
    return None

def get_custom_font(font_url, font_name, size):
    if not os.path.exists(font_name):
        try:
            req = urllib.request.Request(font_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                font_data = response.read()
                with open(font_name, 'wb') as out_file:
                    out_file.write(font_data)
        except Exception:
            return ImageFont.load_default()
    try:
        return ImageFont.truetype(font_name, size)
    except:
        return ImageFont.load_default()

def wrap_text_by_pixels(draw, text, font, max_width):
    if not text: return []
    paragraphs = text.split('\n')
    lines = []
    for para in paragraphs:
        if not para:
            lines.append("")
            continue
        current_line = ""
        for char in para:
            test_line = current_line + char
            bbox = draw.textbbox((0, 0), test_line, font=font)
            text_width = bbox[2] - bbox[0]
            if text_width <= max_width:
                current_line = test_line
            else:
                lines.append(current_line)
                current_line = char
        if current_line:
            lines.append(current_line)
    return lines

def draw_text_advanced(draw, text, font, color, x, y, max_width, line_spacing=20):
    lines = wrap_text_by_pixels(draw, text, font, max_width)
    current_y = y
    for line in lines:
        if line:
            draw.text((x, current_y), line, font=font, fill=color)
            bbox = draw.textbbox((0, 0), line, font=font)
            current_y += (bbox[3] - bbox[1]) + line_spacing
        else:
            bbox = draw.textbbox((0, 0), "A", font=font)
            current_y += (bbox[3] - bbox[1]) + line_spacing
    return current_y

# ==========================================
# 4. 에이전트 파이프라인
# ==========================================
def question_selector_agent():
    print("▶️ [Agent 1] Question Selector 가동")
    return {
        "question": "워렌 버핏이 말하는 장기투자의 3가지 비밀",
        "category": "투자/금융", 
        "story_blueprint": {
            "page1_hook": "왜 항상 내가 사면 떨어지고 팔면 오를까?",
            "page2_misconception": "매일 주식 창을 들여다본다고 수익률이 오르지 않습니다.",
            "page3_truth": "워렌 버핏의 비밀은 '타이밍'이 아니라 '시간'입니다.",
            "page4_example": "좋은 기업을 고르고, 수면제를 먹고 10년 뒤에 깨어나세요.",
            "page5_cta": "오늘부터 단타의 유혹을 끊어낼 나만의 원칙을 적어보세요."
        }
    }

def writer_agent(kb_data):
    print("▶️ [Agent 2] Writer 가동")
    sys_inst = "당신은 트렌디한 에디터입니다. 제목은 짧고 굵게, 본문은 친절하게 작성하세요."
    prompt = f"질문: {kb_data['question']}\n청사진: {json.dumps(kb_data['story_blueprint'], ensure_ascii=False)}"
    
    fallback = [
        {"slide": 1, "title": "내가 사면 떨어지고\n팔면 오르는 이유", "body": "혹시 오늘도 주식 창만 하루 종일 들여다보셨나요?"},
        {"slide": 2, "title": "매일 확인하는 습관\n수익률의 적입니다", "body": "시장의 노이즈에 반응할수록 계좌는 조금씩 녹아내립니다."},
        {"slide": 3, "title": "버핏의 진짜 비밀은\n타이밍이 아닌 시간", "body": "언제 살지가 아니라, 얼마나 오래 보유할지가 승패를 가릅니다."},
        {"slide": 4, "title": "좋은 기업을 샀다면\n수면제를 드세요", "body": "코스톨라니의 명언처럼, 기다림이 최고의 투자 기술입니다."},
        {"slide": 5, "title": "단타의 유혹을 끊을\n나만의 원칙 만들기", "body": "오늘 밤, 흔들리지 않는 나만의 투자 원칙 1가지를 적어보세요."}
    ]
    
    ai_response = ask_ai(prompt, sys_inst)
    return ai_response if ai_response else fallback

def designer_agent(draft_data, category):
    print("▶️ [Agent 4] Designer 가동")
    
    # [1] 스마트 테마 선택 (히스토리 기반 중복 방지)
    theme_name, theme = get_smart_random_theme()
    print(f"🎨 선택된 테마: {theme_name} (배경: {theme['bg']})")
    
    # [2] 폰트 로드
    url_bold = "https://github.com/orioncactus/pretendard/raw/main/packages/pretendard/dist/public/static/Alternative/Pretendard-Bold.ttf"
    font_massive = get_custom_font(url_bold, "Pretendard-Bold.ttf", 110) 
    font_title2 = get_custom_font(url_bold, "Pretendard-Bold.ttf", 85)   
    font_body = get_custom_font(url_bold, "Pretendard-Bold.ttf", 45) 
    font_tiny = get_custom_font(url_bold, "Pretendard-Bold.ttf", 35)     

    generated_files = []
    width, height = 1080, 1350
    max_text_width = 880
    
    for slide in draft_data:
        if not isinstance(slide, dict): continue
        idx = slide.get("slide", 1)
        title = slide.get("title", "")
        body = slide.get("body", "")
        
        # 슬라이드 5번 반전 효과
        current_bg = theme["slide5_bg"] if idx == 5 else theme["bg"]
        img = Image.new("RGB", (width, height), current_bg)
        draw = ImageDraw.Draw(img)
        
        if idx == 1:
            draw.text((100, 150), f"🔥 {category} 인사이트", font=font_tiny, fill=theme["accent"])
            draw_text_advanced(draw, title, font_massive, theme["text_main"], x=100, y=230, max_width=max_text_width, line_spacing=40)
            
            draw.rectangle([100, 750, 250, 760], fill=theme["accent"])
            draw_text_advanced(draw, body, font_body, theme["text_sub"], x=100, y=820, max_width=max_text_width, line_spacing=25)
            
        elif idx in [2, 3, 4]:
            draw.text((800, 80), f"0{idx}", font=font_massive, fill=theme["line"])
            draw.text((100, 150), f"STEP 0{idx-1}", font=font_tiny, fill=theme["accent"])
            
            next_y = draw_text_advanced(draw, title, font_title2, theme["text_main"], x=100, y=270, max_width=max_text_width, line_spacing=30)
            draw_text_advanced(draw, body, font_body, theme["text_sub"], x=100, y=next_y + 90, max_width=max_text_width, line_spacing=35)
            
            draw.line([(100, 1200), (980, 1200)], fill=theme["line"], width=3)
            draw.text((100, 1230), "✦ PREMIUM INSIGHT", font=font_tiny, fill=theme["text_sub"])
            
        else: # Slide 5
            # 배경 반전에 따른 텍스트 컬러 스위칭
            s5_text_main = theme["bg"] if idx == 5 and "Vivid" in theme_name else theme["text_main"] 
            
            # 파스텔 톤 등 5번 슬라이드 색상이 고정된 경우 시인성을 위해 화이트/밝은 색상을 사용
            if "Pastel" in theme_name:
                s5_text_main = "#FFFFFF"

            draw.text((100, 150), "💡 ACTION PLAN", font=font_tiny, fill=theme["accent"])
            next_y = draw_text_advanced(draw, title, font_massive, s5_text_main, x=100, y=270, max_width=max_text_width, line_spacing=30)
            
            btn_y = next_y + 100
            box_height = 250
            draw.rounded_rectangle([100, btn_y, 980, btn_y + box_height], radius=20, fill=theme["box_bg"])
            
            box_padding_x = 50
            inner_max_width = (980 - 100) - (box_padding_x * 2)
            body_lines = wrap_text_by_pixels(draw, body, font_body, max_width=inner_max_width)
            
            total_text_height = sum([draw.textbbox((0, 0), line, font=font_body)[3] - draw.textbbox((0, 0), line, font=font_body)[1] for line in body_lines]) + 20 * (len(body_lines) - 1)
            current_y = btn_y + (box_height - total_text_height) / 2
            
            for line in body_lines:
                draw.text((100 + box_padding_x, current_y), line, font=font_body, fill=theme["box_text"])
                current_y += (draw.textbbox((0, 0), line, font=font_body)[3] - draw.textbbox((0, 0), line, font=font_body)[1]) + 20

            draw.line([(100, 1200), (980, 1200)], fill=theme["accent"], width=3)
            draw.text((100, 1230), "✦ PREMIUM INSIGHT", font=font_tiny, fill=theme["accent"])

        filename = f"slide_{idx}.png"
        img.save(filename)
        generated_files.append(filename)
        print(f"✅ 슬라이드 {idx} 디자인 완료")
        
    return [f for f in generated_files if os.path.exists(f)]

def send_email(image_files, topic):
    print("▶️ [Agent 5] Mailer 가동")
    msg = MIMEMultipart()
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER
    msg['Date'] = formatdate(localtime=True)
    msg['Subject'] = f"[📬 V7.2 스마트 테마] 오늘의 카드뉴스: {topic}"
    
    msg.attach(MIMEText("어제와 겹치지 않는 새로운 디자인 테마가 적용되었습니다.", 'plain', 'utf-8'))
    for file in image_files:
        if os.path.exists(file):
            with open(file, 'rb') as f:
                msg.attach(MIMEImage(f.read(), name=os.path.basename(file)))
            
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
        server.quit()
        print("✅ 메일 발송 성공!")
    except Exception as e:
        print(f"❌ 메일 발송 실패: {e}")

def main():
    print("🚀 V7.2 스마트 테마 롤링 파이프라인 가동")
    kb_data = question_selector_agent()
    draft_data = writer_agent(kb_data)
    images = designer_agent(draft_data, kb_data.get('category', '지식'))
    send_email(images, kb_data['question'])
    print("🎉 전체 프로세스가 정상 종료되었습니다.")

if __name__ == "__main__":
    main()