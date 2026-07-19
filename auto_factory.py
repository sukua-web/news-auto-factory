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
# 2. 공통 유틸리티
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
    """안정적인 폰트 다운로드 및 유효성 검사"""
    if not os.path.exists(font_name):
        print(f"📥 폰트 다운로드 중... ({font_name})")
        try:
            req = urllib.request.Request(
                font_url, 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            )
            with urllib.request.urlopen(req) as response:
                font_data = response.read()
                # 404 페이지가 텍스트로 저장되는 걸 방지하기 위한 최소한의 파일 크기 검사
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
    return {
        "question": "국민연금을 늦게 받으면 정말 이득일까?",
        "category": "국민연금",
        "story_blueprint": {
            "page1_hook": "'빨리 받는 게 무조건 이득'이라는 말의 치명적 함정",
            "page2_misconception": "당장 눈앞에 들어오는 돈만 계산하셨나요?",
            "page3_truth": "1년 연기할 때마다 수령액은 7.2%씩 영구적으로 늘어납니다.",
            "page4_example": "65세 수령 vs 70세 수령, 80세가 넘어가면 역전됩니다.",
            "page5_cta": "지금 국민연금공단 앱에서 내 예상수령액을 확인하세요."
        }
    }

def writer_agent(kb_data):
    print("▶️ [Agent 2] Writer 가동")
    sys_inst = "당신은 트렌디한 잡지 에디터입니다. 한 슬라이드 안에서 시선을 끄는 '강렬한 한 줄(title)'과 '세부 설명(body)'을 명확히 분리해서 작성하세요."
    
    prompt = f"""
    반드시 다음 JSON 구조로만 응답하세요.
    질문: {kb_data['question']}
    청사진: {json.dumps(kb_data['story_blueprint'], ensure_ascii=False)}
    """
    
    # 기본 백업 데이터 정의
    fallback_response = [
        {"slide": 1, "title": "빨리 받는 게 이득?\n치명적인 함정", "body": "국민연금, 언제 받아야 가장 유리할까요?"},
        {"slide": 2, "title": "눈앞의 돈만\n계산하셨나요", "body": "당장의 수령액만 보고 선택하면 장기적으로 손해일 수 있습니다."},
        {"slide": 3, "title": "1년 연기할 때마다\n7.2% 영구 인상", "body": "연기연금을 활용하면 평생 수령액이 늘어납니다."},
        {"slide": 4, "title": "80세가 넘으면\n완전한 역전", "body": "80세 이후부터는 늦게 받는 것이 압도적으로 유리해집니다."},
        {"slide": 5, "title": "내 예상수령액\n지금 확인하세요", "body": "앱에서 나의 정확한 손익분기점을 직접 계산해보세요."}
    ]
    
    ai_response = ask_ai(prompt, sys_inst)
    
    # 🛠️ 안전장치 강화: 리스트 타입이 아니거나 파싱 실패 문자열일 경우 백업 데이터 강제 적용
    if not ai_response or not isinstance(ai_response, list):
        print("⚠️ AI 응답 형식이 올바르지 않아 백업 데이터를 사용합니다.")
        return fallback_response
        
    return ai_response

def reviewer_agent(draft_data):
    print("▶️ [Agent 3] Reviewer 가동")
    if not draft_data or not isinstance(draft_data, list) or len(draft_data) != 5: 
        return False, "슬라이드 데이터 형태 오류"
    return True, "통과"

def designer_agent(draft_data, category):
    print("▶️ [Agent 4] Designer 가동 (Magazine Style V6.1)")
    
    # 🛠️ 안정성이 검증된 프리텐다드(Pretendard) 공식 배포처 주소로 전면 리프레시
    url_bold = "https://github.com/orioncactus/pretendard/raw/main/packages/pretendard/dist/public/static/Alternative/Pretendard-Bold.ttf"
    url_medium = "https://github.com/orioncactus/pretendard/raw/main/packages/pretendard/dist/public/static/Alternative/Pretendard-Medium.ttf"
    
    font_massive = get_custom_font(url_bold, "Pretendard-Bold.ttf", 110) 
    font_title2 = get_custom_font(url_bold, "Pretendard-Bold.ttf", 85)   
    font_body = get_custom_font(url_medium, "Pretendard-Medium.ttf", 45) 
    font_tiny = get_custom_font(url_bold, "Pretendard-Bold.ttf", 35)     
    
    bg_color = "#15151A"       
    bg_accent = "#D4FF00"      
    text_white = "#F5F5F7"
    text_dim = "#A0A0B0"
    text_dark = "#111111"
    
    generated_files = []
    width, height = 1080, 1350
    max_text_width = 880
    
    for slide in draft_data:
        # 안전한 딕셔너리 데이터 추출
        if not isinstance(slide, dict): continue
        
        idx = slide.get("slide", 1)
        title = slide.get("title", "")
        body = slide.get("body", "")
        
        img = Image.new("RGB", (width, height), bg_color if idx != 5 else bg_accent)
        draw = ImageDraw.Draw(img)
        
        if idx == 1:
            draw.text((100, 150), f"🔥 {category} 인사이트", font=font_tiny, fill=bg_accent)
            draw_text_advanced(draw, title, font_massive, text_white, x=100, y=230, max_width=max_text_width, line_spacing=40)
            draw.rectangle([100, 750, 250, 760], fill=bg_accent)
            draw_text_advanced(draw, body, font_body, text_dim, x=100, y=820, max_width=max_text_width, line_spacing=25)
            
        elif idx in [2, 3, 4]:
            draw.text((800, 80), f"0{idx}", font=font_massive, fill="#2A2A35")
            draw.text((100, 150), f"STEP 0{idx-1}", font=font_tiny, fill=bg_accent)
            
            next_y = draw_text_advanced(draw, title, font_title2, text_white, x=100, y=270, max_width=max_text_width, line_spacing=30)
            draw_text_advanced(draw, body, font_body, text_dim, x=100, y=next_y + 90, max_width=max_text_width, line_spacing=35)
            
            draw.line([(100, 1200), (980, 1200)], fill="#333344", width=3)
            draw.text((100, 1230), "✦ RETIREMENT INSIGHT", font=font_tiny, fill="#555566")
            
        else: # Slide 5
            draw.text((100, 150), "💡 ACTION PLAN", font=font_tiny, fill=text_dark)
            next_y = draw_text_advanced(draw, title, font_massive, text_dark, x=100, y=270, max_width=max_text_width, line_spacing=30)
            
            btn_y = next_y + 100
            box_height = 250
            draw.rounded_rectangle([100, btn_y, 980, btn_y + box_height], radius=20, fill=text_dark)
            
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
                draw.text((100 + box_padding_x, current_y), line, font=font_body, fill=text_white)
                bbox = draw.textbbox((0, 0), line, font=font_body)
                current_y += (bbox[3] - bbox[1]) + inner_line_spacing

            draw.line([(100, 1200), (980, 1200)], fill="#A0C000", width=3)
            draw.text((100, 1230), "✦ RETIREMENT INSIGHT", font=font_tiny, fill="#809900")

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
    msg['Subject'] = f"[📬 V6.1 엔진 가동] 예외 처리 완료 레이아웃: {topic}"
    
    msg.attach(MIMEText("타입 에러 방어 및 프리텐다드 고해상도 폰트가 적용된 결과물입니다.", 'plain', 'utf-8'))
    
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
    print("🚀 V6.1 파이프라인 가동을 시작합니다.")
    kb_data = question_selector_agent()
    
    draft_data = None
    for attempt in range(2):
        draft_data = writer_agent(kb_data)
        is_passed, msg = reviewer_agent(draft_data)
        if is_passed: break
        draft_data = None

    if not draft_data:
        print("❌ 유효한 슬라이드 데이터를 확보하지 못해 종료합니다.")
        return

    images = designer_agent(draft_data, kb_data.get('category', '은퇴금융'))
    send_email(images, kb_data['question'])
    print("🎉 파이프라인 전체 프로세스가 정상적으로 성공 종료되었습니다.")

if __name__ == "__main__":
    main()