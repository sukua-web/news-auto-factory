import os
import json
import random
import smtplib
import re
import urllib.request
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

# ==========================================
# 2. 공통 유틸리티 (V6.1과 동일한 정밀 픽셀 엔진)
# ==========================================
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
# 3. 에이전트 파이프라인 (Agents)
# ==========================================
def question_selector_agent():
    print("▶️ [Agent 1] Question Selector 가동")
    # V7 테스트를 위해 카테고리를 '부동산/라이프' 계열로 임의 설정해 봅니다.
    return {
        "question": "전세금 반환 보증보험, 무조건 가입해야 할까?",
        "category": "부동산", 
        "story_blueprint": {
            "page1_hook": "내 피 같은 전세금, 100% 안전하다고 확신하시나요?",
            "page2_misconception": "집주인이 착하니까 괜찮다? 가장 위험한 착각입니다.",
            "page3_truth": "보증보험은 선택이 아니라 '필수 방어막'입니다.",
            "page4_example": "만기일 다음 날, 보험사가 내 전세금을 대신 입금해 줍니다.",
            "page5_cta": "지금 HUG 앱에서 내 집이 가입 가능한지 주소부터 조회하세요."
        }
    }

def writer_agent(kb_data):
    print("▶️ [Agent 2] Writer 가동")
    sys_inst = "당신은 트렌디한 잡지 에디터입니다. 한 슬라이드 안에서 시선을 끄는 '강렬한 한 줄(title)'과 '세부 설명(body)'을 명확히 분리해서 작성하세요."
    prompt = f"질문: {kb_data['question']}\n청사진: {json.dumps(kb_data['story_blueprint'], ensure_ascii=False)}"
    
    fallback_response = [
        {"slide": 1, "title": "내 피 같은 전세금\n안전하다 확신하나요", "body": "전세사기, 남의 일이라고만 생각하셨나요?"},
        {"slide": 2, "title": "집주인 믿는다는\n가장 위험한 착각", "body": "사람은 변하지 않아도, 집주인의 경제 상황은 하루아침에 변할 수 있습니다."},
        {"slide": 3, "title": "보증보험은 선택 아닌\n필수 방어막", "body": "집주인이 돈이 없어도, 기관에서 내 전세금을 안전하게 돌려줍니다."},
        {"slide": 4, "title": "만기일 다음 날\n칼같이 입금 완료", "body": "스트레스 없이 새로운 집으로 이사 갈 수 있는 유일한 방법입니다."},
        {"slide": 5, "title": "가입 가능 여부\n지금 바로 조회하세요", "body": "HUG 안심전세 앱에서 주소만 입력하면 1분 만에 확인 가능합니다."}
    ]
    
    ai_response = ask_ai(prompt, sys_inst)
    if not ai_response or not isinstance(ai_response, list):
        return fallback_response
    return ai_response

def reviewer_agent(draft_data):
    print("▶️ [Agent 3] Reviewer 가동")
    if not draft_data or not isinstance(draft_data, list) or len(draft_data) != 5: 
        return False, "데이터 오류"
    return True, "통과"

def designer_agent(draft_data, category):
    print("▶️ [Agent 4] Designer 가동 (V7.0 Multi-Theme Engine)")
    
    # [1] 폰트 로드 (현대카드 감성에 어울리는 프리텐다드 유지)
    url_bold = "https://github.com/orioncactus/pretendard/raw/main/packages/pretendard/dist/public/static/Alternative/Pretendard-Bold.ttf"
    url_medium = "https://github.com/orioncactus/pretendard/raw/main/packages/pretendard/dist/public/static/Alternative/Pretendard-Medium.ttf"
    font_massive = get_custom_font(url_bold, "Pretendard-Bold.ttf", 110) 
    font_title2 = get_custom_font(url_bold, "Pretendard-Bold.ttf", 85)   
    font_body = get_custom_font(url_medium, "Pretendard-Medium.ttf", 45) 
    font_tiny = get_custom_font(url_bold, "Pretendard-Bold.ttf", 35)     
    
    # 🛠️ [2] V7 핵심: 멀티 테마 스키마 (현대카드 디자인 벤치마크)
    THEMES = {
        "PASTEL_SAND": { # 추천: 에세이, 부동산, 라이프스타일 (차분하지만 강렬한 대비)
            "bg": "#F4F3EF",           # 차분한 샌드 베이지 
            "slide5_bg": "#111111",    # 5번 슬라이드는 딥블랙으로 묵직하게 반전
            "accent": "#FF3B30",       # 시선이 꽂히는 쨍한 레드 포인트
            "text_main": "#111111",    # 시인성 극대화 딥블랙 타이틀
            "text_sub": "#555555",     # 다크 그레이 본문
            "box_bg": "#111111",       # 일반 슬라이드 박스 컬러
            "box_text": "#F4F3EF",     # 박스 내 텍스트
            "line": "#D1CFCA"          # 은은한 구분선
        },
        "PASTEL_MINT": { # 추천: 금융, 주식, 트렌드 (프레시하고 신뢰감 있는 톤)
            "bg": "#E0F2F1",           # 페일 민트
            "slide5_bg": "#004D40",    # 5번 슬라이드 딥 그린 반전
            "accent": "#FF6D00",       # 보색 대비 오렌지 포인트
            "text_main": "#00251A",    # 아주 짙은 다크 그린 (거의 검정)
            "text_sub": "#455A64",     # 슬레이트 그레이
            "box_bg": "#00251A",
            "box_text": "#FFFFFF",
            "line": "#B2DFDB"
        },
        "MAGAZINE_DARK": { # V6.1 오리지널 다크 네온
            "bg": "#15151A", "slide5_bg": "#D4FF00", "accent": "#D4FF00",
            "text_main": "#F5F5F7", "text_sub": "#A0A0B0", 
            "box_bg": "#111111", "box_text": "#F5F5F7", "line": "#333344"
        }
    }
    
    # 🛠️ [3] 카테고리별 테마 자동 라우팅
    if category in ["부동산", "라이프", "에세이"]:
        theme = THEMES["PASTEL_SAND"]
    elif category in ["주식", "금융", "세무"]:
        theme = THEMES["PASTEL_MINT"]
    else:
        theme = THEMES["MAGAZINE_DARK"] # 기본값
        
    print(f"🎨 선택된 테마: {category} -> {theme['bg']} 배경")

    generated_files = []
    width, height = 1080, 1350
    max_text_width = 880
    
    for slide in draft_data:
        if not isinstance(slide, dict): continue
        idx = slide.get("slide", 1)
        title = slide.get("title", "")
        body = slide.get("body", "")
        
        # 5번 슬라이드는 주의를 끌기 위해 배경색 반전 (현대카드 패키징 느낌)
        current_bg = theme["slide5_bg"] if idx == 5 else theme["bg"]
        img = Image.new("RGB", (width, height), current_bg)
        draw = ImageDraw.Draw(img)
        
        if idx == 1:
            draw.text((100, 150), f"🔥 {category} 인사이트", font=font_tiny, fill=theme["accent"])
            draw_text_advanced(draw, title, font_massive, theme["text_main"], x=100, y=230, max_width=max_text_width, line_spacing=40)
            
            # 타이틀과 본문 사이의 포인트 컬러 라인 (현대카드식 비주얼 포인트)
            draw.rectangle([100, 750, 250, 760], fill=theme["accent"])
            
            draw_text_advanced(draw, body, font_body, theme["text_sub"], x=100, y=820, max_width=max_text_width, line_spacing=25)
            
        elif idx in [2, 3, 4]:
            # 우측 상단 거대한 워터마크 넘버링
            draw.text((800, 80), f"0{idx}", font=font_massive, fill=theme["line"])
            draw.text((100, 150), f"STEP 0{idx-1}", font=font_tiny, fill=theme["accent"])
            
            next_y = draw_text_advanced(draw, title, font_title2, theme["text_main"], x=100, y=270, max_width=max_text_width, line_spacing=30)
            draw_text_advanced(draw, body, font_body, theme["text_sub"], x=100, y=next_y + 90, max_width=max_text_width, line_spacing=35)
            
            draw.line([(100, 1200), (980, 1200)], fill=theme["line"], width=3)
            draw.text((100, 1230), "✦ PREMIUM INSIGHT", font=font_tiny, fill=theme["text_sub"])
            
        else: # Slide 5
            # 배경이 어두워졌으므로(또는 반전되었으므로), 텍스트 색상을 배경에 맞게 스위칭
            s5_text_main = theme["bg"] if idx == 5 else theme["text_main"] 
            s5_text_sub = theme["bg"] if idx == 5 else theme["text_sub"]
            
            draw.text((100, 150), "💡 ACTION PLAN", font=font_tiny, fill=theme["accent"])
            next_y = draw_text_advanced(draw, title, font_massive, s5_text_main, x=100, y=270, max_width=max_text_width, line_spacing=30)
            
            btn_y = next_y + 100
            box_height = 250
            # 마지막 버튼 박스는 액센트 컬러로 강렬하게 처리
            draw.rounded_rectangle([100, btn_y, 980, btn_y + box_height], radius=20, fill=theme["accent"])
            
            box_padding_x = 50
            inner_max_width = (980 - 100) - (box_padding_x * 2)
            body_lines = wrap_text_by_pixels(draw, body, font_body, max_width=inner_max_width)
            
            total_text_height = 0
            inner_line_spacing = 20
            for i, line in enumerate(body_lines):
                bbox = draw.textbbox((0, 0), line, font=font_body)
                total_text_height += (bbox[3] - bbox[1])
                if i < len(body_lines) - 1:
                    total_text_height += inner_line_spacing
                    
            text_y_start = btn_y + (box_height - total_text_height) / 2
            
            current_y = text_y_start
            for line in body_lines:
                # 버튼 안의 글씨는 배경색(Accent)과 대비되도록 솔리드한 색상 유지
                draw.text((100 + box_padding_x, current_y), line, font=font_body, fill=theme["box_bg"])
                bbox = draw.textbbox((0, 0), line, font=font_body)
                current_y += (bbox[3] - bbox[1]) + inner_line_spacing

            draw.line([(100, 1200), (980, 1200)], fill=theme["accent"], width=3)
            draw.text((100, 1230), "✦ PREMIUM INSIGHT", font=font_tiny, fill=theme["accent"])

        filename = f"slide_{idx}.png"
        img.save(filename)
        generated_files.append(filename)
        print(f"✅ 슬라이드 {idx} 디자인 완료")
        
    return [f for f in generated_files if os.path.exists(f)]

# ==========================================
# 4. 발송 (Mailer)
# ==========================================
def send_email(image_files, topic):
    print("▶️ [Agent 5] Mailer 가동")
    msg = MIMEMultipart()
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER
    msg['Date'] = formatdate(localtime=True)
    msg['Subject'] = f"[📬 V7.0 엔진] 파스텔톤 다이내믹 테마 생성 완료: {topic}"
    
    msg.attach(MIMEText("카테고리에 따라 최적의 컬러셋이 자동으로 매칭되는 V7.0 결과물입니다.", 'plain', 'utf-8'))
    
    for file in image_files:
        if os.path.exists(file):
            with open(file, 'rb') as f:
                img_data = f.read()
            msg.attach(MIMEImage(img_data, name=os.path.basename(file)))
            
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
    print("🚀 V7.0 파이프라인 가동을 시작합니다.")
    kb_data = question_selector_agent()
    
    draft_data = None
    for attempt in range(2):
        draft_data = writer_agent(kb_data)
        is_passed, msg = reviewer_agent(draft_data)
        if is_passed: break
        draft_data = None

    if not draft_data:
        print("❌ 데이터 오류로 종료.")
        return

    images = designer_agent(draft_data, kb_data.get('category', '은퇴금융'))
    send_email(images, kb_data['question'])
    print("🎉 파이프라인 전체 프로세스가 정상 종료되었습니다.")

if __name__ == "__main__":
    main()