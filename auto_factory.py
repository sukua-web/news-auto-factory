import os
import json
import random
import textwrap
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from email.utils import formatdate
from PIL import Image, ImageDraw, ImageFont
import google.generativeai as genai
import urllib.request

# ==========================================
# 1. 환경 변수 및 기본 설정
# ==========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.environ.get("EMAIL_RECEIVER")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# 📌 회원님 전용 황금 모델 리스트 (변경 금지)
MODELS_TO_TRY = ['gemini-2.0-flash', 'gemini-2.0-flash-lite', 'gemini-3.1-flash-lite', 'gemini-3.5-flash']

# ==========================================
# 2. 공통 유틸리티 (AI 요청 / 폰트)
# ==========================================
def ask_ai(prompt, system_instruction=""):
    for model_name in MODELS_TO_TRY:
        try:
            print(f"🤖 AI 호출 중... ({model_name})")
            model = genai.GenerativeModel(model_name=model_name, system_instruction=system_instruction)
            response = model.generate_content(prompt)
            raw_text = response.text.replace('```json', '').replace('```', '').strip()
            
            # JSON 포맷 안전 추출
            if "{" in raw_text and "}" in raw_text:
                raw_text = raw_text[raw_text.find("{"):raw_text.rfind("}")+1]
            elif "[" in raw_text and "]" in raw_text:
                raw_text = raw_text[raw_text.find("["):raw_text.rfind("]")+1]
                
            return json.loads(raw_text)
        except Exception as e:
            print(f"⚠️ {model_name} 실패: {e}")
            continue
    return None

def get_font(size):
    font_path = "NanumGothic.ttf"
    if not os.path.exists(font_path):
        font_url = "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Bold.ttf"
        urllib.request.urlretrieve(font_url, font_path)
    return ImageFont.truetype(font_path, size)

# ==========================================
# 3. 에이전트 파이프라인 (Agents)
# ==========================================

def question_selector_agent():
    """Step 1: 지식 베이스(KB)에서 오늘의 질문 선택"""
    print("▶️ [Agent 1] Question Selector 가동")
    try:
        with open("questions_kb.json", "r", encoding="utf-8") as f:
            kb_data = json.load(f)
        # 우선순위가 높거나 랜덤으로 하나 선택 (현재는 랜덤)
        selected = random.choice(kb_data)
        print(f"✅ 오늘 선정된 질문: {selected['question']}")
        return selected
    except FileNotFoundError:
        print("❌ questions_kb.json 파일이 없습니다. 기본 데이터를 사용합니다.")
        return {
            "question": "퇴직금 한 번에 받으면 세금 폭탄 맞는다는데 진짜일까?",
            "category": "퇴직금",
            "story_blueprint": {
                "page1_hook": "퇴직금 일시불 수령의 치명적 함정",
                "page2_misconception": "다들 통장에 꽂히는 목돈만 생각합니다.",
                "page3_truth": "IRP로 이전하면 퇴직소득세 30%를 절감할 수 있습니다.",
                "page4_example": "1억 기준, 150만 원 이상 차이나는 실제 계산",
                "page5_cta": "퇴직 전 반드시 IRP 계좌부터 개설하세요."
            }
        }

def writer_agent(kb_data):
    """Step 2: 청사진을 바탕으로 실제 5장 원고 작성"""
    print("▶️ [Agent 2] Writer 가동")
    sys_inst = "당신은 4060 세대의 돈 걱정을 해결해주는 금융 전문 카피라이터입니다. 1장당 최대 30자 이내로 팩트 기반의 짧고 강렬한 문장을 작성하세요."
    prompt = f"""
    아래 스토리 청사진을 바탕으로 인스타그램 5장 캐러셀 텍스트를 JSON으로 작성하세요.
    - 대상 질문: {kb_data['question']}
    - 청사진: {json.dumps(kb_data['story_blueprint'], ensure_ascii=False)}
    
    출력 형식:
    [
      {{"slide": 1, "text": "...", "highlight": "강조할 단어"}},
      ... (총 5개)
    ]
    """
    return ask_ai(prompt, sys_inst)

def reviewer_agent(draft_data):
    """Step 3: 원고 품질 및 가독성 검수"""
    print("▶️ [Agent 3] Reviewer 가동")
    # V3 초기 단계이므로 복잡한 로직 대신 길이와 형식 검증만 수행
    if not draft_data or len(draft_data) != 5:
        return False, "슬라이드 5장이 생성되지 않았습니다."
    
    for slide in draft_data:
        if len(slide.get('text', '')) > 50:
            return False, f"슬라이드 {slide.get('slide')}의 텍스트가 너무 깁니다."
    return True, "통과"

def designer_agent(draft_data):
    """Step 4: 텍스트 레이아웃 및 렌더링 (이미지 없는 힙한 타이포그래피)"""
    print("▶️ [Agent 4] Designer 가동")
    bg_colors = ["#1A1A1A", "#F4F4F5", "#2C3E50", "#E8ECEF"]
    main_bg = random.choice(bg_colors)
    text_color = "#FFFFFF" if main_bg in ["#1A1A1A", "#2C3E50"] else "#111827"
    highlight_color = "#F59E0B" if text_color == "#FFFFFF" else "#D97706"

    generated_files = []
    
    for slide in draft_data:
        img = Image.new("RGB", (1080, 1350), main_bg)
        draw = ImageDraw.Draw(img)
        
        # 텍스트 배치 로직
        idx = slide["slide"]
        text = slide["text"]
        
        font_large = get_font(85 if idx == 1 else 65)
        
        # 줄바꿈 처리
        lines = textwrap.wrap(text, width=15 if idx == 1 else 18)
        y = 400
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font_large)
            w = bbox[2] - bbox[0]
            draw.text(((1080 - w) / 2, y), line, font=font_large, fill=text_color)
            y += bbox[3] - bbox[1] + 30
            
        # 페이지 번호 (하단 여백 활용)
        font_small = get_font(30)
        draw.text((90, 1250), f"Slide {idx} / 5", font=font_small, fill=highlight_color)

        filename = f"slide_{idx}.png"
        img.save(filename)
        generated_files.append(filename)
        
    return generated_files

# ==========================================
# 4. 발송 및 오케스트레이션 (Mailer & Main)
# ==========================================
def send_email(image_files, topic):
    print("▶️ [Agent 5] Mailer 가동")
    msg = MIMEMultipart()
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER
    msg['Date'] = formatdate(localtime=True)
    msg['Subject'] = f"[V4 지식 베이스] 오늘의 콘텐츠: {topic}"
    
    msg.attach(MIMEText("완벽한 역할 분담으로 생성된 오늘의 결과물입니다.", 'plain', 'utf-8'))
    
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
    
    # Retry Logic (최대 2회)
    max_retries = 2
    draft_data = None
    
    for attempt in range(max_retries):
        draft_data = writer_agent(kb_data)
        is_passed, msg = reviewer_agent(draft_data)
        
        if is_passed:
            print("✅ Reviewer 승인 완료.")
            break
        else:
            print(f"⚠️ Reviewer 반려 ({msg}). 재작성 시도 {attempt + 1}/{max_retries}")
            draft_data = None
            
    if not draft_data:
        print("❌ 최대 재시도 횟수를 초과하여 파이프라인을 종료합니다.")
        return

    images = designer_agent(draft_data)
    send_email(images, kb_data['category'])
    print("🎉 파이프라인 정상 종료.")

if __name__ == "__main__":
    main()