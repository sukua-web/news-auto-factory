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
# 1. 환경 변수 및 파일 경로 설정
# ==========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.environ.get("EMAIL_RECEIVER")

MODELS_TO_TRY = ['gemini-2.0-flash', 'gemini-2.0-flash-lite', 'gemini-3.1-flash-lite', 'gemini-3.5-flash']
THEME_HISTORY_FILE = "theme_history.json"
KB_FILE = "questions_kb.json"
USED_QUESTIONS_FILE = "used_questions.json"

# ==========================================
# 2. 🎨 현대카드 스타일 프리미엄 테마 시스템 (14종)
# ==========================================
THEMES_14 = {
    # Vivid 테마 (강렬한 보색 대비)
    "Vivid_Red": {"mainBg": "#FF0000", "mainText": "#FFFFFF", "subBg": "#00FFFF", "subText": "#000000"},
    "Vivid_Blue": {"mainBg": "#0052CC", "mainText": "#FFFFFF", "subBg": "#FFAD00", "subText": "#000000"},
    "Vivid_Yellow": {"mainBg": "#FFD600", "mainText": "#000000", "subBg": "#2900FF", "subText": "#FFFFFF"},
    "Vivid_Green": {"mainBg": "#00C853", "mainText": "#FFFFFF", "subBg": "#C80075", "subText": "#FFFFFF"},
    "Vivid_Purple": {"mainBg": "#7B61FF", "mainText": "#FFFFFF", "subBg": "#E5FF61", "subText": "#000000"},
    "Vivid_Orange": {"mainBg": "#FF6D00", "mainText": "#FFFFFF", "subBg": "#0092FF", "subText": "#FFFFFF"},
    "Vivid_Sky": {"mainBg": "#00B4D8", "mainText": "#FFFFFF", "subBg": "#D82400", "subText": "#FFFFFF"},
    # Deep & Premium 테마 (무게감과 신뢰감)
    "Deep_Black": {"mainBg": "#000000", "mainText": "#FFFFFF", "subBg": "#333333", "subText": "#FFFFFF"},
    "Deep_Navy": {"mainBg": "#001F3F", "mainText": "#FFFFFF", "subBg": "#FFD700", "subText": "#000000"},
    "Deep_Gold": {"mainBg": "#B8860B", "mainText": "#FFFFFF", "subBg": "#1a1a1a", "subText": "#FFFFFF"},
    "Deep_Burgundy": {"mainBg": "#800020", "mainText": "#FFFFFF", "subBg": "#008060", "subText": "#FFFFFF"},
    "Deep_RoyalPurple": {"mainBg": "#4B0082", "mainText": "#FFFFFF", "subBg": "#FF7F50", "subText": "#000000"},
    "Deep_Platinum": {"mainBg": "#C0C0C0", "mainText": "#000000", "subBg": "#1a1a1a", "subText": "#FFFFFF"},
    "Deep_Charcoal": {"mainBg": "#333333", "mainText": "#FFFFFF", "subBg": "#FF4500", "subText": "#FFFFFF"}
}

# ==========================================
# 3. 공통 유틸리티 및 스마트 파일 매니저
# ==========================================
def get_smart_random_theme():
    history = []
    if os.path.exists(THEME_HISTORY_FILE):
        try:
            with open(THEME_HISTORY_FILE, "r") as f:
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
        with open(THEME_HISTORY_FILE, "w") as f:
            json.dump({
                "recent_themes": history, 
                "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }, f)
    except Exception as e:
        print(f"⚠️ 히스토리 저장 실패: {e}")
        
    return chosen_theme_name, THEMES_14[chosen_theme_name]

def clean_and_parse_json(raw_text):
    cleaned = re.sub(r'`{3}json\s*|`{3}\s*', '', raw_text).strip()
    match = re.search(r'(\[.*\]|\{.*\})', cleaned, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(1))
            if isinstance(data, list) and len(data) > 0:
                return data
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
            print(f"⚠️ {model_name} 에러 발생: {e}")
            continue
    return None

def get_custom_font(font_url, font_name, size):
    if not os.path.exists(font_name):
        print(f"📥 폰트 다운로드 중... ({font_name})")
        try:
            req = urllib.request.Request(
                font_url, 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            )
            with urllib.request.urlopen(req) as response:
                font_data = response.read()
                if len(font_data) < 1000:
                    raise ValueError("다운로드된 폰트 파일이 너무 작거나 유효하지 않습니다.")
                with open(font_name, 'wb') as out_file:
                    out_file.write(font_data)
            print(f"✅ 폰트 다운로드 성공: {font_name}")
        except Exception as e:
            print(f"⚠️ {font_name} 다운로드 실패: {e}. 나눔고딕으로 백업합니다.")
            fallback_name = "NanumGothic-Bold.ttf"
            if not os.path.exists(fallback_name):
                try:
                    fallback_url = "https://raw.githubusercontent.com/google/fonts/main/ofl/nanumgothic/NanumGothic-Bold.ttf"
                    req_fb = urllib.request.Request(fallback_url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req_fb) as response, open(fallback_name, 'wb') as out_file:
                        out_file.write(response.read())
                except:
                    return ImageFont.load_default()
            return ImageFont.truetype(fallback_name, size)
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

def draw_text_advanced(draw, text, font, color, x, y, max_width, line_spacing=25):
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
# 4. 에이전트 파이프라인 (지식 베이스 연동형)
# ==========================================
def question_selector_agent():
    print("▶️ [Agent 1] Question Selector 가동 (지식 베이스 파싱 및 중복 제어)")
    
    # 1. 지식 베이스 파일 검증 및 자동 초기화 (파일이 없을 경우 샘플 자동 생성)
    if not os.path.exists(KB_FILE):
        sample_kb = [
            {
                "question_id": "pension_001",
                "category": "국민연금",
                "question": "국민연금을 늦게 받으면 정말 이득일까?",
                "story_blueprint": {
                    "page1_hook": "'빨리 받는 게 무조건 이득'이라는 말의 치명적 함정",
                    "page2_misconception": "당장 눈앞에 들어오는 돈만 계산하셨나요?",
                    "page3_truth": "1년 연기할 때마다 수령액은 7.2%씩 영구적으로 늘어납니다.",
                    "page4_example": "65세 수령 vs 70세 수령, 80세가 넘어가면 역전됩니다.",
                    "page5_cta": "지금 국민연금공단 앱에서 내 예상수령액을 확인하세요."
                }
            }
        ]
        with open(KB_FILE, "w", encoding="utf-8") as f:
            json.dump(sample_kb, f, ensure_ascii=False, indent=2)
            
    # 2. 파일 로드
    with open(KB_FILE, "r", encoding="utf-8") as f:
        kb_data = json.load(f)
        
    used_ids = []
    if os.path.exists(USED_QUESTIONS_FILE):
        try:
            with open(USED_QUESTIONS_FILE, "r", encoding="utf-8") as f:
                used_ids = json.load(f)
        except:
            pass
            
    # 3. 미사용 질문 필터링 및 중복 소진 제어
    available_questions = [q for q in kb_data if q.get("question_id") not in used_ids]
    
    if not available_questions:
        print("🔄 모든 주제를 소진하여 히스토리를 초기화합니다.")
        available_questions = kb_data
        used_ids = []
        
    selected_item = random.choice(available_questions)
    used_ids.append(selected_item["question_id"])
    
    # 4. 히스토리 파일 저장
    with open(USED_QUESTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(used_ids, f, ensure_ascii=False, indent=2)
        
    return selected_item

def writer_agent(kb_data):
    print("▶️ [Agent 2] Writer 가동")
    sys_inst = (
        "당신은 현대카드 카피라이터 스타일의 트렌디한 에디터입니다. 제목은 극도로 짧고 강렬하게 팩트 위주로 조지며, 본문은 여백의 미를 살릴 수 있도록 정갈하게 요약하세요. "
        "반드시 [ {\"slide\": 1, \"title\": \"...\", \"body\": \"...\"}, ... ] 형태의 JSON '배열(List)'로 응답해야 하며, "
        "정확히 5개의 슬라이드 데이터가 포함되어야 합니다."
    )
    prompt = f"질문: {kb_data['question']}\n청사진: {json.dumps(kb_data['story_blueprint'], ensure_ascii=False)}"
    
    fallback = [
        {"slide": 1, "title": kb_data['story_blueprint']['page1_hook'], "body": "당연하다고 믿었던 원칙을 의심하는 것부터 자산 관리는 시작됩니다."},
        {"slide": 2, "title": kb_data['story_blueprint']['page2_misconception'], "body": "눈앞의 현금 흐름에 갇히면 장기적인 복리 기회를 완전히 잃게 됩니다."},
        {"slide": 3, "title": kb_data['story_blueprint']['page3_truth'], "body": "숫자는 거짓말을 하지 않습니다. 확정된 수익률의 가치를 계산하십시오."},
        {"slide": 4, "title": kb_data['story_blueprint']['page4_example'], "body": "인생 후반전의 타임라인을 다시 설계할 시간입니다."},
        {"slide": 5, "title": kb_data['story_blueprint']['page5_cta'], "body": "생각만으로는 바뀌지 않습니다. 지금 바로 확인하고 최적의 타이밍을 고르세요."}
    ]
    
    ai_response = ask_ai(prompt, sys_inst)
    return ai_response if ai_response else fallback

def reviewer_agent(draft_data):
    print("▶️ [Agent 3] Reviewer 가동")
    if not draft_data or not isinstance(draft_data, list) or len(draft_data) != 5: 
        return False, "데이터 구조 불일치"
    return True, "통과"

def designer_agent(draft_data, category):
    print("▶️ [Agent 4] Designer 가동 (현대카드 디자인 가이드 및 프리미엄 테마 시스템 최적화)")
    
    theme_name, theme = get_smart_random_theme()
    print(f"🎨 활성화된 현대카드 테마: {theme_name}")
    
    url_bold = "https://github.com/orioncactus/pretendard/raw/main/packages/pretendard/dist/public/static/Alternative/Pretendard-Bold.ttf"
    url_medium = "https://github.com/orioncactus/pretendard/raw/main/packages/pretendard/dist/public/static/Alternative/Pretendard-Medium.ttf"
    
    font_massive = get_custom_font(url_bold, "Pretendard-Bold.ttf", 100) 
    font_title2 = get_custom_font(url_bold, "Pretendard-Bold.ttf", 80)    
    font_body = get_custom_font(url_medium, "Pretendard-Medium.ttf", 42) 
    font_tiny = get_custom_font(url_bold, "Pretendard-Bold.ttf", 32)     

    generated_files = []
    width, height = 1080, 1350
    max_text_width = 880 # 좌우 100px씩 안전 여백(Padding) 보장
    
    for slide in draft_data:
        if not isinstance(slide, dict): continue
        idx = slide.get("slide", 1)
        title = slide.get("title", "")
        body = slide.get("body", "")
        
        # S1, S5는 메인 테마 컬러 / S2, S3, S4는 서브 테마 컬러로 정밀 분기
        is_main_slide = idx in [1, 5]
        current_bg = theme["mainBg"] if is_main_slide else theme["subBg"]
        current_text = theme["mainText"] if is_main_slide else theme["subText"]
        
        contrast_bg = theme["subBg"] if is_main_slide else theme["mainBg"]
        contrast_text = theme["subText"] if is_main_slide else theme["mainText"]

        img = Image.new("RGB", (width, height), current_bg)
        draw = ImageDraw.Draw(img)
        
        # 📌 현대카드 미학의 엣지: 슬라이드 전체 외곽에 초정밀 프레임 라인 생성
        draw.rectangle([25, 25, width - 25, height - 25], outline=contrast_bg, width=3)
        
        if idx == 1:
            draw.text((100, 150), f"✦ {category} 인사이트", font=font_tiny, fill=current_text)
            next_y = draw_text_advanced(draw, title, font_massive, current_text, x=100, y=240, max_width=max_text_width, line_spacing=45)
            draw.rectangle([100, next_y + 40, 250, next_y + 48], fill=contrast_bg)
            draw_text_advanced(draw, body, font_body, current_text, x=100, y=next_y + 110, max_width=max_text_width, line_spacing=30)
            
        elif idx in [2, 3, 4]:
            draw.text((850, 90), f"0{idx}", font=font_massive, fill=contrast_bg) 
            draw.text((100, 150), f"STEP 0{idx-1}", font=font_tiny, fill=current_text)
            
            next_y = draw_text_advanced(draw, title, font_title2, current_text, x=100, y=280, max_width=max_text_width, line_spacing=35)
            draw_text_advanced(draw, body, font_body, current_text, x=100, y=next_y + 80, max_width=max_text_width, line_spacing=30)
            
            draw.line([(100, 1200), (980, 1200)], fill=contrast_bg, width=2)
            draw.text((100, 1225), "✦ MODERN INSIGHT ENGINE", font=font_tiny, fill=current_text)
            
        else: 
            draw.text((100, 150), "💡 ACTION PLAN", font=font_tiny, fill=current_text)
            next_y = draw_text_advanced(draw, title, font_massive, current_text, x=100, y=260, max_width=max_text_width, line_spacing=35)
            
            btn_y = next_y + 80
            box_height = 240
            draw.rounded_rectangle([100, btn_y, 980, btn_y + box_height], radius=12, fill=contrast_bg)
            
            box_padding_x = 50
            inner_max_width = (980 - 100) - (box_padding_x * 2)
            body_lines = wrap_text_by_pixels(draw, body, font_body, max_width=inner_max_width)
            
            total_text_height = sum([draw.textbbox((0, 0), line, font=font_body)[3] - draw.textbbox((0, 0), line, font=font_body)[1] for line in body_lines]) + 20 * (len(body_lines) - 1)
            current_y = btn_y + (box_height - total_text_height) / 2
            
            for line in body_lines:
                draw.text((100 + box_padding_x, current_y), line, font=font_body, fill=contrast_text)
                current_y += (draw.textbbox((0, 0), line, font=font_body)[3] - draw.textbbox((0, 0), line, font=font_body)[1]) + 20

            draw.line([(100, 1200), (980, 1200)], fill=contrast_bg, width=2)
            draw.text((100, 1225), "✦ MODERN INSIGHT ENGINE", font=font_tiny, fill=contrast_bg)

        filename = f"slide_{idx}.png"
        img.save(filename)
        generated_files.append(filename)
        print(f"✅ 슬라이드 {idx} 디자인 및 프레이밍 완료")
        
    return [f for f in generated_files if os.path.exists(f)]

def send_email(image_files, topic):
    print("▶️ [Agent 5] Mailer 가동")
    msg = MIMEMultipart()
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER
    msg['Date'] = formatdate(localtime=True)
    msg['Subject'] = f"[📬 현대카드 스타일] 오늘의 인사이트 큐레이션: {topic}"
    
    msg.attach(MIMEText("현대카드 고유의 브랜드 자산 컬러 및 그리드가 적용된 고화질 슬라이드 세트입니다.", 'plain', 'utf-8'))
    for file in image_files:
        if os.path.exists(file):
            with open(file, 'rb') as f:
                msg.attach(MIMEImage(f.read(), name=os.path.basename(file)))
            
    try:
        if not EMAIL_SENDER or not EMAIL_PASSWORD:
            print("⚠️ 메일 계정 정보가 누락되어 로컬 이미지 생성 단계까지만 완료합니다.")
            return
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
        server.quit()
        print("✅ 메일 발송 전송 완료!")
    except Exception as e:
        print(f"❌ 메일 발송 실패: {e}")

# ==========================================
# 5. 메인 파이프라인 컨트롤러
# ==========================================
def main():
    print("🚀 현대카드 스타일 프리미엄 자동화 파이프라인 2.0 인스턴스 시작")
    kb_data = question_selector_agent()
    print(f"🎯 선택된 주제 ID: {kb_data['question_id']} | 키워드: {kb_data['question']}")
    
    draft_data = None
    for attempt in range(2):
        draft_data = writer_agent(kb_data)
        is_passed, msg = reviewer_agent(draft_data)
        if is_passed: 
            break
        draft_data = None

    if not draft_data:
        print("❌ 심사 에러 및 예외 발생으로 프로세스를 조기 종료합니다.")
        return
        
    images = designer_agent(draft_data, kb_data.get('category', '지식'))
    send_email(images, kb_data['question'])
    print("🎉 카드뉴스 제작 파이프라인 전체 프로세스가 정상 종료되었습니다.")

if __name__ == "__main__":
    main()