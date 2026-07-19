import os
import json
import random
import textwrap
import smtplib
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.utils import formatdate
from PIL import Image, ImageDraw, ImageFont
import google.genai as genai  # 📌 최신 패키지로 전면 전환 (FutureWarning 제거)
import urllib.request

# ==========================================
# 1. 환경 변수 및 기본 설정
# ==========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.environ.get("EMAIL_RECEIVER")

# 📌 2026년 기준 실무에서 가장 안정적인 최신 모델 라인업 (절대 변경 금지)
MODELS_TO_TRY = ['gemini-2.0-flash', 'gemini-2.0-flash-lite', 'gemini-3.1-flash-lite', 'gemini-3.5-flash']

# ==========================================
# 2. 공통 유틸리티 (AI 요청 / JSON 클리닝 / 디자인 도우미)
# ==========================================
def clean_and_parse_json(raw_text):
    """AI가 뱉은 텍스트에서 순수 JSON만 완벽하게 추출하는 방어 코드"""
    cleaned = re.sub(r'```json\s*|```\s*', '', raw_text).strip()
    
    match = re.search(r'(\[.*\]|\{.*\})', cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
            
    try:
        if "[" in cleaned and "]" in cleaned:
            start = cleaned.find("[")
            end = cleaned.rfind("]") + 1
            return json.loads(cleaned[start:end])
        elif "{" in cleaned and "}" in cleaned:
            start = cleaned.find("{")
            end = cleaned.rfind("}") + 1
            return json.loads(cleaned[start:end])
    except Exception:
        return None
    return None

def ask_ai(prompt, system_instruction=""):
    if not GEMINI_API_KEY:
        print("❌ GEMINI_API_KEY 환경 변수가 없습니다.")
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
                    temperature=0.2, 
                    response_mime_type="application/json" 
                )
            )
            
            result = clean_and_parse_json(response.text)
            if result:
                return result
            else:
                print(f"⚠️ {model_name}의 응답이 올바른 JSON 형식이 아닙니다.")
        except Exception as e:
            print(f"⚠️ {model_name} 에러 발생: {e}")
            continue
            
    return None

# 📌 🛠️ 403 Forbidden 우회 기능이 추가된 폰트 다운로드 시스템
def get_custom_font(font_url, font_name, size):
    """보안 차단을 우회하여 프리텐다드를 다운로드하고, 실패 시 나눔고딕으로 복구하는 방어 코드"""
    if not os.path.exists(font_name):
        print(f"📥 폰트 다운로드 중... ({font_name})")
        try:
            # 💡 일반 브라우저로 위장하여 깃허브/CDN 차단 우회
            req = urllib.request.Request(
                font_url, 
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            )
            with urllib.request.urlopen(req) as response, open(font_name, 'wb') as out_file:
                out_file.write(response.read())
            print(f"✅ 폰트 다운로드 성공: {font_name}")
        except Exception as e:
            print(f"⚠️ {font_name} 1차 다운로드 실패: {e}. 구글 나눔고딕으로 백업 다운로드를 시도합니다.")
            
            # 프리텐다드 차단 시, 구글 공식 저장소의 나눔고딕 백업 가동
            fallback_name = "NanumGothic-Bold.ttf"
            if not os.path.exists(fallback_name):
                try:
                    fallback_url = "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Bold.ttf"
                    req_fb = urllib.request.Request(fallback_url, headers={'User-Agent': 'Mozilla/5.0'})
                    with urllib.request.urlopen(req_fb) as response, open(fallback_name, 'wb') as out_file:
                        out_file.write(response.read())
                    print("✅ 백업 폰트(나눔고딕) 다운로드 성공")
                except Exception as fb_err:
                    print(f"❌ 백업 폰트마저 실패: {fb_err}. 시스템 기본 폰트를 사용합니다.")
                    return ImageFont.load_default()
            
            try:
                return ImageFont.truetype(fallback_name, size)
            except:
                return ImageFont.load_default()
                
    try:
        return ImageFont.truetype(font_name, size)
    except Exception as e:
        print(f"⚠️ {font_name} 로드 에러: {e}")
        return ImageFont.load_default()

# 📌 텍스트 중앙 정렬 렌더링 도우미
def draw_text_centered(draw, text, font, color, y_start, img_width, wrap_width):
    lines = textwrap.wrap(text, width=wrap_width)
    y = y_start
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        x = (img_width - w) / 2
        draw.text((x, y), line, font=font, fill=color)
        y += h + 40  # 시원한 줄 간격

# ==========================================
# 3. 에이전트 파이프라인 (Agents)
# ==========================================
def question_selector_agent():
    """Step 1: 지식 베이스(KB)에서 오늘의 질문 선택"""
    print("▶️ [Agent 1] Question Selector 가동")
    try:
        with open("questions_kb.json", "r", encoding="utf-8") as f:
            kb_data = json.load(f)
        selected = random.choice(kb_data)
        print(f"✅ 오늘 선정된 질문: {selected['question']}")
        return selected
    except Exception as e:
        print(f"❌ KB 로드 실패 ({e}). 폴백 데이터를 적용합니다.")
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
    """Step 2: 청사진을 바탕으로 실제 5장 원고 작성"""
    print("▶️ [Agent 2] Writer 가동")
    sys_inst = "당신은 4060 세대의 은퇴/돈 걱정을 해결하는 금융 전문 카피라이터입니다. 핵심 메시지를 명확하고 신뢰감 있게 표현하되, 각 슬라이드의 텍스트는 절대로 40자를 넘지 마세요."
    
    prompt = f"""
    반드시 다음 JSON 구조로만 응답하세요. 다른 설명 텍스트는 절대 포함하지 마십시오.
    아래 질문과 청사진을 바탕으로 인스타그램 카드뉴스용 원고 5장을 작성하세요.
    
    질문: {kb_data['question']}
    청사진: {json.dumps(kb_data['story_blueprint'], ensure_ascii=False)}
    
    출력 형식 JSON 스키마 예시:
    [
      {{"slide": 1, "text": "1장 표지 문구"}},
      {{"slide": 2, "text": "2장 흔한 오해 내용"}},
      {{"slide": 3, "text": "3장 팩트 체크 및 진실"}},
      {{"slide": 4, "text": "4장 구체적인 비교 계산"}},
      {{"slide": 5, "text": "5장 행동 지침 (CTA)"}}
    ]
    """
    
    ai_response = ask_ai(prompt, sys_inst)
    
    if ai_response is None:
        print("⚠️ [🚨 API 쿼터 초과] 모든 지정 모델 호출에 실패했습니다. 로컬 청사진 데이터를 기반으로 원고를 자동 생성합니다.")
        blueprint = kb_data.get('story_blueprint', {})
        ai_response = [
            {"slide": 1, "text": blueprint.get("page1_hook", f"{kb_data['question']}의 진실")},
            {"slide": 2, "text": blueprint.get("page2_misconception", "당장 눈앞의 이득만 보면 안 되는 이유")},
            {"slide": 3, "text": blueprint.get("page3_truth", "알고 보면 엄청난 혜택이 숨어있습니다.")},
            {"slide": 4, "text": blueprint.get("page4_example", "꼼꼼하게 비교해 보고 결정해야 합니다.")},
            {"slide": 5, "text": blueprint.get("page5_cta", "지금 자세한 내용을 확인해 보세요.")}
        ]
        
    return ai_response

def reviewer_agent(draft_data):
    """Step 3: 원고 품질 및 가독성 검수"""
    print("▶️ [Agent 3] Reviewer 가동")
    if not draft_data or not isinstance(draft_data, list) or len(draft_data) != 5:
        return False, "데이터가 유효하지 않거나 슬라이드가 정확히 5장이 아닙니다."
    
    for slide in draft_data:
        text = slide.get('text', '')
        if not text:
            return False, "텍스트가 비어 있는 슬라이드가 존재합니다."
        if len(text) > 50:
            return False, f"슬라이드 {slide.get('slide')}의 글자 수가 너무 깁니다. ({len(text)}자)"
    return True, "통과"

def designer_agent(draft_data):
    """Step 4: 매력적인 잡지 스타일 템플릿 렌더링"""
    print("▶️ [Agent 4] Designer 가동 (Magazine Style)")
    
    url_bold = "https://cdn.jsdelivr.net/gh/orioncactus/pretendard/packages/pretendard/dist/public/static/Pretendard-Bold.ttf"
    url_medium = "https://cdn.jsdelivr.net/gh/orioncactus/pretendard/packages/pretendard/dist/public/static/Pretendard-Medium.ttf"
    
    font_title = get_custom_font(url_bold, "Pretendard-Bold.ttf", 95)
    font_body = get_custom_font(url_medium, "Pretendard-Medium.ttf", 65)
    font_small = get_custom_font(url_bold, "Pretendard-Bold.ttf", 40)
    
    bg_dark = "#171719"       
    bg_accent = "#FFC83D"     
    text_white = "#FFFFFF"
    text_dark = "#1A1A1A"
    text_point = "#FFD700"    
    
    generated_files = []
    width, height = 1080, 1350
    
    for slide in draft_data:
        idx = slide["slide"]
        text = slide["text"]
        
        if idx == 1:
            img = Image.new("RGB", (width, height), bg_dark)
            draw = ImageDraw.Draw(img)
            draw_text_centered(draw, text, font_title, text_white, y_start=450, img_width=width, wrap_width=12)
            
        elif idx in [2, 3, 4]:
            img = Image.new("RGB", (width, height), bg_dark)
            draw = ImageDraw.Draw(img)
            
            index_text = f"0{idx} / 금융 팩트체크"
            draw.text((120, 150), index_text, font=font_small, fill=text_point)
            
            lines = textwrap.wrap(text, width=17)
            y = 350
            for line in lines:
                draw.text((120, y), line, font=font_body, fill=text_white)
                y += 100 
                
        else:
            img = Image.new("RGB", (width, height), bg_accent)
            draw = ImageDraw.Draw(img)
            
            draw_text_centered(draw, "💡 다음 스텝", font_small, text_dark, y_start=300, img_width=width, wrap_width=15)
            draw_text_centered(draw, text, font_title, text_dark, y_start=500, img_width=width, wrap_width=12)

        filename = f"slide_{idx}.png"
        img.save(filename)
        generated_files.append(filename)
        print(f"✅ 슬라이드 {idx} 디자인 완료")
        
    confirmed_files = [f for f in generated_files if os.path.exists(f)]
    return confirmed_files

# ==========================================
# 5. 발송 및 전체 파이프라인 관리 (Mailer & Main)
# ==========================================
def send_email(image_files, topic):
    print("▶️ [Agent 5] Mailer 가동")
    msg = MIMEMultipart()
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER
    msg['Date'] = formatdate(localtime=True)
    msg['Subject'] = f"[📬 V4 엔진 가동] 오늘의 은퇴금융 콘텐츠: {topic}"
    
    msg.attach(MIMEText("성공적으로 조율된 멀티 에이전트 시스템의 카드뉴스 렌더링 파일입니다.", 'plain', 'utf-8'))
    
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
    print("🚀 V4 파이프라인 가동을 시작합니다.")
    
    kb_data = question_selector_agent()
    
    max_retries = 2
    draft_data = None
    
    for attempt in range(max_retries):
        draft_data = writer_agent(kb_data)
        is_passed, msg = reviewer_agent(draft_data)
        
        if is_passed:
            print("✅ Reviewer 최종 승인 완료.")
            break
        else:
            print(f"⚠️ Reviewer 반려 ({msg}). 재작성 시도 {attempt + 1}/{max_retries}")
            draft_data = None
            
    if not draft_data:
        print("❌ 최대 재시도 횟수를 초과했습니다. 데이터 추출 결함으로 파이프라인을 종료합니다.")
        return

    images = designer_agent(draft_data)
    send_email(images, kb_data['question'])
    print("🎉 파이프라인 전체 프로세스가 정상적으로 성공 종료되었습니다.")

if __name__ == "__main__":
    main()