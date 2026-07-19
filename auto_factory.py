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

# 📌 2026년 기준 실무에서 가장 안정적인 최신 모델 라인업
MODELS_TO_TRY = ['gemini-2.0-flash', 'gemini-2.0-flash-lite', 'gemini-3.1-flash-lite', 'gemini-3.5-flash']

# ==========================================
# 2. 공통 유틸리티 (AI 요청 / JSON 클리닝)
# ==========================================
def clean_and_parse_json(raw_text):
    """AI가 뱉은 텍스트에서 순수 JSON만 완벽하게 추출하는 방어 코드"""
    # 1. 마크다운 블록 제거
    cleaned = re.sub(r'```json\s*|```\s*', '', raw_text).strip()
    
    # 2. 첫 번째 '[' 또는 '{' 부터 마지막 ']' 또는 '}' 까지만 잘라내기
    match = re.search(r'(\[.*\]|\{.*\})', cleaned, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
            
    # 정규식 실패 시 전통적인 방식 적용
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

    # 최신 SDK 클라이언트 생성
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    for model_name in MODELS_TO_TRY:
        try:
            print(f"🤖 AI 호출 중... ({model_name})")
            
            # 최신 SDK 호출 방식 규격 준수
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=genai.types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.2, # JSON 규격 일관성을 위해 낮춤
                    response_mime_type="application/json" # 📌 구글 서버단에서 JSON 강제
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
    """Step 2: 청사진을 바탕으로 실제 5장 원고 작성 (AI 쿼터 초과 시 로컬 청사진으로 무조건 완주)"""
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
    
    # 지정하신 4개 모델 순서대로 호출 시도
    ai_response = ask_ai(prompt, sys_inst)
    
    # 📌 [방어 로직] 4개 모델이 모두 쿼터 초과(429)로 원고를 못 가져왔을 때 작동
    if ai_response is None:
        print("⚠️ [🚨 API 쿼터 초과] 모든 지정 모델 호출에 실패했습니다. 로컬 청사진 데이터를 기반으로 원고를 자동 생성합니다.")
        blueprint = kb_data.get('story_blueprint', {})
        
        # KB의 청사진 데이터를 매핑하여 Reviewer를 통과할 수 있는 5장 구조 강제 생성
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
    """Step 4: 텍스트 레이아웃 및 렌더링 (힙한 미니멀 타이포그래피)"""
    print("▶️ [Agent 4] Designer 가동")
    # 4060 금융 매거진 감성의 고급스러운 딥차콜과 오프화이트 배경
    bg_colors = ["#121214", "#F8F9FA", "#1A2530"]
    main_bg = random.choice(bg_colors)
    text_color = "#FFFFFF" if main_bg in ["#121214", "#1A2530"] else "#1A1A1A"
    highlight_color = "#F59E0B" # 포인트 오렌지/골드

    generated_files = []
    
    for slide in draft_data:
        img = Image.new("RGB", (1080, 1350), main_bg)
        draw = ImageDraw.Draw(img)
        
        idx = slide["slide"]
        text = slide["text"]
        
        # 표지는 강렬하고 크게, 본문은 가독성 있게
        font_size = 80 if idx == 1 else 60
        font_main = get_font(font_size)
        
        # 줄바꿈 최적화 (가로 폭에 맞춰 자동 절단)
        lines = textwrap.wrap(text, width=14 if idx == 1 else 16)
        
        # 수직 중앙 정렬 계산
        total_height = 0
        line_images = []
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=font_main)
            h = bbox[3] - bbox[1]
            w = bbox[2] - bbox[0]
            line_images.append((line, w, h))
            total_height += h + 35
            
        y = (1350 - total_height) / 2
        
        for line, w, h in line_images:
            x = (1080 - w) / 2
            draw.text((x, y), line, font=font_main, fill=text_color)
            y += h + 35
            
        # 미니멀리즘 하단 페이지 인덱스 표시
        font_small = get_font(32)
        draw.text((90, 1230), f"0{idx} / 05", font=font_small, fill=highlight_color)

        filename = f"slide_{idx}.png"
        img.save(filename)
        generated_files.append(filename)
        
    return generated_files

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
