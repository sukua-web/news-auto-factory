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
# 3. 공통 유틸리티
# ==========================================
def get_smart_random_theme():
    """
    최근 10번 사용한 테마를 기억하여 
    1) 전날/다음날 연속 방지
    2) 같은 요일(7일 전) 테마 중복 방지를 자동으로 해결합니다.
    (10개의 히스토리를 유지하면 14개 중 4개만 후보가 되어 완벽히 사이클링됨)
    """
    history = []
    
    # 1. 히스토리 파일 읽기
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r") as f:
                data = json.load(f)
                history = data.get("recent_themes", [])
        except json.JSONDecodeError:
            pass
            
    # 2. 사용 가능한 테마 필터링 (최근 10개 제외)
    available_themes = [t for t in THEMES_14.keys() if t not in history[-10:]]
    
    # 만약 남은 테마가 없다면(비상시) 히스토리 초기화 후 전체에서 랜덤
    if not available_themes:
        available_themes = list(THEMES_14.keys())
        if history:
            available_themes.remove(history[-1]) # 최소 직전 테마만은 제외
            
    # 3. 새로운 테마 랜덤 선택
    chosen_theme_name = random.choice(available_themes)
    
    # 4. 선택된 테마를 히스토리에 추가 후 저장 (최대 10개 유지)
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
    """AI가 생성한 텍스트에서 명확하게 JSON '배열(List)' 구조만 추출하여 슬라이드 누락 방지"""
    try:
        # 배열 시작 '['과 끝 ']'을 명시적으로 찾아 파싱
        start = raw_text.find('[')
        end = raw_text.rfind(']')
        if start != -1 and end != -1:
            json_str = raw_text[start:end+1]
            data = json.loads(json_str)
            if isinstance(data, list) and len(data) > 0:
                return data
    except Exception as e:
        print(f"JSON 파싱 오류: {e}")
    return None

def ask_ai(prompt, system_instruction=""):
    if not GEMINI_API_KEY:
        print("⚠️ GEMINI_API_KEY가 없습니다.")
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
            if result and len(result) == 5: # 5장인지 검증
                return result
            else:
                print("⚠️ AI 응답이 5장이 아니거나 파싱에 실패했습니다. 다음 모델을 시도합니다.")
        except Exception as e:
            print(f"⚠️ {model_name} 호출 에러: {e}")
            continue
    return None

def get_custom_font(font_url, font_name, size):
    if not os.path.exists(font_name):
        try:
            req = urllib.request.Request(font_url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req) as response:
                with open(font_name, 'wb') as out_file:
                    out_file.write(response.read())
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
    # 시스템 프롬프트 강력 강화: 반드시 5개의 요소가 있는 배열 형태로 반환하도록 지시
    sys_inst = (
        "당신은 트렌디한 에디터입니다. 제목은 짧고 굵게, 본문은 친절하게 작성하세요. "
        "반드시 [ {\"slide\": 1, \"title\": \"...\", \"body\": \"...\"}, ... ] 형태의 JSON '배열(List)'로 응답해야 하며, "
        "정확히 5개의 슬라이드 데이터가 포함되어야 합니다."
    )
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
    print("▶️ [Agent 3] Designer 가동")
    
    # [1] 스마트 테마 선택 (히스토리 기반 중복 방지 적용됨)
    theme_name, theme = get_smart_random_theme()
    print(f"🎨 선택된 테마: {theme_name}")
    
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
        
        # [핵심 로직] S1, S5는 main 컬러 / S2, S3, S4는 sub 컬러 적용
        is_main_slide = idx in [1, 5]
        current_bg = theme["mainBg"] if is_main_slide else theme["subBg"]
        current_text = theme["mainText"] if is_main_slide else theme["subText"]
        
        # 반전 효과를 줄 대비 색상 (텍스트 박스나 라인용)
        contrast_bg = theme["subBg"] if is_main_slide else theme["mainBg"]
        contrast_text = theme["subText"] if is_main_slide else theme["mainText"]

        img = Image.new("RGB", (width, height), current_bg)
        draw = ImageDraw.Draw(img)
        
        if idx == 1:
            # S1 (Main)
            draw.text((100, 150), f"🔥 {category} 인사이트", font=font_tiny, fill=current_text)
            draw_text_advanced(draw, title, font_massive, current_text, x=100, y=230, max_width=max_text_width, line_spacing=40)
            # 포인트 디자인 (대비 색상 활용)
            draw.rectangle([100, 750, 250, 760], fill=contrast_bg)
            draw_text_advanced(draw, body, font_body, current_text, x=100, y=820, max_width=max_text_width, line_spacing=25)
            
        elif idx in [2, 3, 4]:
            # S2, S3, S4 (Sub)
            draw.text((800, 80), f"0{idx}", font=font_massive, fill=contrast_bg) # 우상단 큰 숫자 번호
            draw.text((100, 150), f"STEP 0{idx-1}", font=font_tiny, fill=current_text)
            
            next_y = draw_text_advanced(draw, title, font_title2, current_text, x=100, y=270, max_width=max_text_width, line_spacing=30)
            draw_text_advanced(draw, body, font_body, current_text, x=100, y=next_y + 90, max_width=max_text_width, line_spacing=35)
            
            draw.line([(100, 1200), (980, 1200)], fill=contrast_bg, width=3)
            draw.text((100, 1230), "✦ PREMIUM INSIGHT", font=font_tiny, fill=current_text)
            
        else: 
            # S5 (Main)
            draw.text((100, 150), "💡 ACTION PLAN", font=font_tiny, fill=current_text)
            next_y = draw_text_advanced(draw, title, font_massive, current_text, x=100, y=270, max_width=max_text_width, line_spacing=30)
            
            # Action 박스를 서브 컬러로 구성
            btn_y = next_y + 100
            box_height = 250
            draw.rounded_rectangle([100, btn_y, 980, btn_y + box_height], radius=20, fill=contrast_bg)
            
            box_padding_x = 50
            inner_max_width = (980 - 100) - (box_padding_x * 2)
            body_lines = wrap_text_by_pixels(draw, body, font_body, max_width=inner_max_width)
            
            total_text_height = sum([draw.textbbox((0, 0), line, font=font_body)[3] - draw.textbbox((0, 0), line, font=font_body)[1] for line in body_lines]) + 20 * (len(body_lines) - 1)
            current_y = btn_y + (box_height - total_text_height) / 2
            
            for line in body_lines:
                draw.text((100 + box_padding_x, current_y), line, font=font_body, fill=contrast_text)
                current_y += (draw.textbbox((0, 0), line, font=font_body)[3] - draw.textbbox((0, 0), line, font=font_body)[1]) + 20

            draw.line([(100, 1200), (980, 1200)], fill=contrast_bg, width=3)
            draw.text((100, 1230), "✦ PREMIUM INSIGHT", font=font_tiny, fill=contrast_bg)

        filename = f"slide_{idx}.png"
        img.save(filename)
        generated_files.append(filename)
        print(f"✅ 슬라이드 {idx} 디자인 완료")
        
    return [f for f in generated_files if os.path.exists(f)]

def send_email(image_files, topic):
    print("▶️ [Agent 4] Mailer 가동")
    msg = MIMEMultipart()
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER
    msg['Date'] = formatdate(localtime=True)
    msg['Subject'] = f"[📬 신규 테마] 오늘의 카드뉴스: {topic}"
    
    msg.attach(MIMEText("현대카드 스타일 프리미엄 테마가 적용된 5장 슬라이드입니다.", 'plain', 'utf-8'))
    for file in image_files:
        if os.path.exists(file):
            with open(file, 'rb') as f:
                msg.attach(MIMEImage(f.read(), name=os.path.basename(file)))
            
    try:
        if not EMAIL_SENDER or not EMAIL_PASSWORD:
            print("⚠️ 메일 계정 정보가 없어 메일 발송을 건너뜁니다.")
            return
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
        server.quit()
        print("✅ 메일 발송 성공!")
    except Exception as e:
        print(f"❌ 메일 발송 실패: {e}")

def main():
    print("🚀 현대카드 스타일 파이프라인 가동")
    kb_data = question_selector_agent()
    draft_data = writer_agent(kb_data)
    images = designer_agent(draft_data, kb_data.get('category', '지식'))
    send_email(images, kb_data['question'])
    print("🎉 전체 프로세스가 정상 종료되었습니다.")

if __name__ == "__main__":
    main()