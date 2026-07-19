import os
import json
import random
import textwrap
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
    """안정적인 SUIT 폰트 다운로드 로직"""
    if not os.path.exists(font_name):
        print(f"📥 폰트 다운로드 중... ({font_name})")
        try:
            req = urllib.request.Request(
                font_url, 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            )
            with urllib.request.urlopen(req) as response, open(font_name, 'wb') as out_file:
                out_file.write(response.read())
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

def draw_text_left(draw, text, font, color, x, y, wrap_width, line_spacing=20):
    if not text: return y
    lines = textwrap.wrap(text, width=wrap_width)
    current_y = y
    for line in lines:
        draw.text((x, current_y), line, font=font, fill=color)
        bbox = draw.textbbox((0, 0), line, font=font)
        current_y += (bbox[3] - bbox[1]) + line_spacing
    return current_y

# ==========================================
# 3. 에이전트 파이프라인 (Agents)
# ==========================================
def question_selector_agent():
    print("▶️ [Agent 1] Question Selector 가동")
    try:
        with open("questions_kb.json", "r", encoding="utf-8") as f:
            kb_data = json.load(f)
        selected = random.choice(kb_data)
        return selected
    except:
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
    
    출력 형식 JSON 스키마 예시:
    [
      {{"slide": 1, "title": "빨리 받는 게 이득?\n치명적인 함정", "body": "국민연금, 언제 받아야 가장 유리할까요?"}},
      {{"slide": 2, "title": "눈앞의 돈만\n계산하셨나요", "body": "당장의 수령액만 보고 선택하면 장기적으로 손해일 수 있습니다."}},
      {{"slide": 3, "title": "1년 연기할 때마다\n7.2% 영구 인상", "body": "연기연금을 활용하면 평생 수령액이 늘어납니다."}},
      {{"slide": 4, "title": "80세가 넘으면\n완전한 역전", "body": "80세 이후부터는 늦게 받는 것이 압도적으로 유리해집니다."}},
      {{"slide": 5, "title": "내 예상수령액\n지금 확인하세요", "body": "앱에서 나의 정확한 손익분기점을 직접 계산해보세요."}}
    ]
    """
    ai_response = ask_ai(prompt, sys_inst)
    if not ai_response:
        ai_response = [
            {"slide": 1, "title": "빨리 받는 게 이득?\n치명적인 함정", "body": "국민연금, 언제 받아야 가장 유리할까요?"},
            {"slide": 2, "title": "눈앞의 돈만\n계산하셨나요", "body": "당장의 수령액만 보고 선택하면 장기적으로 손해일 수 있습니다."},
            {"slide": 3, "title": "1년 연기할 때마다\n7.2% 영구 인상", "body": "연기연금을 활용하면 평생 수령액이 늘어납니다."},
            {"slide": 4, "title": "80세가 넘으면\n완전한 역전", "body": "80세 이후부터는 늦게 받는 것이 압도적으로 유리해집니다."},
            {"slide": 5, "title": "내 예상수령액\n지금 확인하세요", "body": "앱에서 나의 정확한 손익분기점을 직접 계산해보세요."}
        ]
    return ai_response

def reviewer_agent(draft_data):
    print("▶️ [Agent 3] Reviewer 가동")
    if not draft_data or len(draft_data) != 5: return False, "슬라이드 수 오류"
    return True, "통과"

def designer_agent(draft_data, category):
    print("▶️ [Agent 4] Designer 가동 (Magazine Style V5.1)")
    
    # 📌 프리텐다드 대신 100% 안정적인 트렌디 폰트 'SUIT(수트)'로 전면 교체
    url_bold = "https://raw.githubusercontent.com/sunn-us/SUIT/master/fonts/ttf/SUIT-Bold.ttf"
    url_medium = "https://raw.githubusercontent.com/sunn-us/SUIT/master/fonts/ttf/SUIT-Medium.ttf"
    
    font_massive = get_custom_font(url_bold, "SUIT-Bold.ttf", 110) 
    font_title2 = get_custom_font(url_bold, "SUIT-Bold.ttf", 85)   
    font_body = get_custom_font(url_medium, "SUIT-Medium.ttf", 45) 
    font_tiny = get_custom_font(url_bold, "SUIT-Bold.ttf", 35)     
    
    bg_color = "#15151A"       
    bg_accent = "#D4FF00"      
    text_white = "#F5F5F7"
    text_dim = "#A0A0B0"
    text_dark = "#111111"
    
    generated_files = []
    width, height = 1080, 1350
    
    for slide in draft_data:
        idx = slide["slide"]
        title = slide.get("title", "")
        body = slide.get("body", "")
        
        img = Image.new("RGB", (width, height), bg_color if idx != 5 else bg_accent)
        draw = ImageDraw.Draw(img)
        
        if idx == 1:
            draw.text((100, 150), f"🔥 {category} 인사이트", font=font_tiny, fill=bg_accent)
            draw_text_left(draw, title, font_massive, text_white, x=100, y=230, wrap_width=12, line_spacing=40)
            draw.rectangle([100, 750, 250, 760], fill=bg_accent)
            draw_text_left(draw, body, font_body, text_dim, x=100, y=820, wrap_width=20)
            
        elif idx in [2, 3, 4]:
            draw.text((800, 80), f"0{idx}", font=font_massive, fill="#2A2A35")
            draw.text((100, 150), f"STEP 0{idx-1}", font=font_tiny, fill=bg_accent)
            next_y = draw_text_left(draw, title, font_title2, text_white, x=100, y=250, wrap_width=14, line_spacing=30)
            draw_text_left(draw, body, font_body, text_dim, x=100, y=next_y + 80, wrap_width=22, line_spacing=25)
            draw.line([(100, 1200), (980, 1200)], fill="#333344", width=3)
            
        else:
            draw.text((100, 150), "💡 ACTION PLAN", font=font_tiny, fill=text_dark)
            next_y = draw_text_left(draw, title, font_massive, text_dark, x=100, y=250, wrap_width=12, line_spacing=30)
            btn_y = next_y + 80
            
            # 📌 치명적 에러 해결: rectangle -> rounded_rectangle 로 함수명 변경
            draw.rounded_rectangle([100, btn_y, 980, btn_y + 250], radius=20, fill=text_dark)
            draw_text_left(draw, body, font_body, text_white, x=150, y=btn_y + 60, wrap_width=18, line_spacing=20)

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
    msg['Subject'] = f"[📬 V5 엔진 가동] 완전 개편된 잡지 레이아웃: {topic}"
    
    msg.attach(MIMEText("부장님 PPT를 탈출하여, 시각적 계층화와 비대칭 레이아웃이 적용된 V5 결과물입니다.", 'plain', 'utf-8'))
    
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
    print("🚀 V5 파이프라인 가동을 시작합니다.")
    kb_data = question_selector_agent()
    
    draft_data = None
    for attempt in range(2):
        draft_data = writer_agent(kb_data)
        is_passed, msg = reviewer_agent(draft_data)
        if is_passed: break
        draft_data = None

    if not draft_data:
        return

    images = designer_agent(draft_data, kb_data.get('category', '은퇴금융'))
    send_email(images, kb_data['question'])
    print("🎉 파이프라인 전체 프로세스가 정상적으로 성공 종료되었습니다.")

if __name__ == "__main__":
    main()