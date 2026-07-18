import os
import json
import random
import requests
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
# 1. 환경 변수 및 설정
# ==========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.environ.get("EMAIL_RECEIVER")
SERPAPI_KEY = os.environ.get("SERPAPI_KEY")
PEXELS_KEY = os.environ.get("PEXELS_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# 📌 회원님이 검증하고 정립하신 진짜 황금 모델 리스트 완벽 복원 고정!
MODELS_TO_TRY = ['gemini-2.0-flash', 'gemini-2.0-flash-lite', 'gemini-3.1-flash-lite', 'gemini-3.5-flash']

# ==========================================
# 2. 인스타 감성 디자인 및 기획 데이터
# ==========================================
PASTEL_COLORS = [
    "#FFB3BA", "#FFDFBA", "#FFFFBA", "#B8E994", "#A2C2E6", 
    "#D5AAFF", "#FFC6FF", "#BDE0FE", "#FFDAC1", "#E2F0CB"
]

HOOK_STYLES = [
    "충격형: 방금 이것 때문에 난리났습니다. (사람들이 잘 모르는 충격적 사실)",
    "질문형: 이거 알고 계셨나요? 당신이라면 어떻게 할까요?",
    "숫자형: 특정 숫자(돈, 시간, 인원 등)를 강조하여 호기심 자극",
    "오해형: 모두가 이렇게 알고 있는데, 사실은 아닙니다.",
    "비교형: 어제와 오늘, 과거와 현재가 완전히 달라졌습니다.",
    "스토리형: 처음엔 아무도 믿지 않았습니다. 그런데..."
]

NARRATIVE_STRUCTURES = [
    "구조A (기본): 1장(후킹) -> 2장(사건 요약) -> 3장(원인) -> 4장(미래 영향) -> 5장(독자 생각 묻기)",
    "구조B (드라마): 1장(무슨 일일까?) -> 2장(충격적 결과) -> 3장(왜 그랬을까?) -> 4장(대반전) -> 5장(의견 묻기)",
    "구조C (미스터리): 1장(오해하고 있는 사실) -> 2장(대부분의 생각) -> 3장(숨겨진 진실) -> 4장(나에게 미치는 영향) -> 5장(저장/공유 유도)",
    "구조D (SNS형): 1장(실시간 반응/상황) -> 2장(사건 팩트) -> 3장(전문가/시장 반응) -> 4장(핵심 1줄 요약) -> 5장(다음 편 예고)",
    "구조E (퀴즈형): 1장(정답이 뭘까?) -> 2장(힌트 제공) -> 3장(사건 공개) -> 4장(의미와 파장) -> 5장(질문 던지기)"
]

def get_font(size):
    font_path = "NanumGothic.ttf"
    if not os.path.exists(font_path):
        print("폰트 다운로드 중...")
        font_url = "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Regular.ttf"
        urllib.request.urlretrieve(font_url, font_path)
    return ImageFont.truetype(font_path, size)

# ==========================================
# 3. AI 프롬프트 생성 및 JSON 추출
# ==========================================
def generate_news_content():
    selected_hook = random.choice(HOOK_STYLES)
    selected_structure = random.choice(NARRATIVE_STRUCTURES)
    
    prompt = f"""
    당신은 100만 팔로워를 가진 글로벌 뉴스 인스타그램 채널의 수석 에디터입니다.
    오늘 가장 이슈가 되는 글로벌 뉴스 1개를 골라 인스타그램 캐러셀(5장)을 기획하세요.

    [필수 기획 조건]
    1. 후킹 스타일: {selected_hook}
    2. 서사 구조: {selected_structure}
    3. 다음 장을 안 보면 못 배기는 쪼여오는 클리프행어 방식으로 문맥이 자연스럽게 이어지게 작성하세요.
    4. 각 슬라이드의 레이아웃 타입(1~4)을 완벽히 매칭하세요.
       - Type 1: 표지 전용 (거대한 후킹 카피)
       - Type 2: 상단 텍스트 + 하단 관련 이미지
       - Type 3: 중앙 집중형 (강렬한 대사/텍스트 단 1줄)
       - Type 4: 엔딩 전용 (독자 참여/댓글 유도)

    반드시 아래 JSON 형식으로만 5장의 데이터를 출력하세요. 다른 잡설은 일절 금지합니다.
    [
      {{
        "slide_number": 1,
        "layout_type": 1,
        "en_text": "HOOKING ENGLISH COPY",
        "kr_text": "한국어 후킹 카피",
        "jp_text": "일본어 후킹 카피",
        "search_keyword": "english keyword (e.g., ai robot, tech war)"
      }},
      ... (총 5개)
    ]
    """
    
    for model_name in MODELS_TO_TRY:
        try:
            print(f"🤖 AI 모델 시도 중: {model_name}")
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            raw_text = response.text.replace('```json', '').replace('```', '').strip()
            
            # JSON 배열만 안전하게 잘라내기
            if "[" in raw_text and "]" in raw_text:
                raw_text = raw_text[raw_text.find("["):raw_text.rfind("]")+1]
                
            data = json.loads(raw_text)
            if len(data) == 5:
                print(f"✅ 기획 성공: [{selected_hook}] / [{selected_structure[:15]}...]")
                return data
        except Exception as e:
            print(f"⚠️ {model_name} 실패: {e}")
            continue
    return None

# ==========================================
# 4. 하이브리드 이미지 수집 (SerpApi -> Pexels 하이패스)
# ==========================================
def fetch_image(keyword):
    if not keyword or keyword.strip() == "":
        return None

    if SERPAPI_KEY:
        try:
            url = f"https://serpapi.com/search.json?q={keyword}&tbm=isch&api_key={SERPAPI_KEY}"
            res = requests.get(url, timeout=7).json()
            if "images_results" in res and len(res["images_results"]) > 0:
                img_url = res["images_results"][0]["original"]
                img_data = requests.get(img_url, timeout=5).content
                temp_path = "temp_serp.jpg"
                with open(temp_path, "wb") as f:
                    f.write(img_data)
                img = Image.open(temp_path).convert("RGB")
                print(f"✅ SerpApi 이미지 연동 성공: {keyword}")
                return img
        except Exception as e:
            print(f"⚠️ SerpApi 시도 누락/실패: {e}")

    if PEXELS_KEY:
        try:
            headers = {"Authorization": PEXELS_KEY}
            url = f"https://api.pexels.com/v1/search?query={keyword}&per_page=1"
            res = requests.get(url, headers=headers, timeout=7).json()
            if "photos" in res and len(res["photos"]) > 0:
                img_url = res["photos"][0]["src"]["large"]
                img_data = requests.get(img_url, timeout=5).content
                temp_path = "temp_pexels.jpg"
                with open(temp_path, "wb") as f:
                    f.write(img_data)
                print(f"✅ Pexels 보조 이미지 성공: {keyword}")
                return Image.open(temp_path).convert("RGB")
        except Exception as e:
            print(f"⚠️ Pexels 최종 백업 실패: {e}")
            
    return None

# ==========================================
# 5. 스마트 다국어 렌더링 시스템
# ==========================================
def draw_text_wrapped(draw, text, font, x, y, max_width, fill="black"):
    # 글자가 가질 수 있는 폭에 대응하기 위해 textwrap 크기 유연하게 조정
    lines = textwrap.wrap(text, width=max_width)
    current_y = y
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        draw.text(((1080 - w) / 2, current_y), line, font=font, fill=fill)
        current_y += h + 20
    return current_y

def create_slide(slide_data, bg_color):
    img = Image.new("RGB", (1080, 1080), bg_color)
    draw = ImageDraw.Draw(img)
    
    layout = slide_data.get("layout_type", 2)
    en_text = slide_data["en_text"]
    kr_text = slide_data["kr_text"]
    jp_text = slide_data["jp_text"]
    
    font_large = get_font(65)
    font_medium = get_font(45)
    font_small = get_font(35)
    
    fetched_img = fetch_image(slide_data.get("search_keyword", ""))
    
    # 레이아웃 리듬 분쇄 템플릿 알고리즘
    if layout == 1: 
        if fetched_img:
            fetched_img = fetched_img.resize((1080, 1080), Image.Resampling.LANCZOS)
            dark_layer = Image.new("RGBA", (1080, 1080), (0, 0, 0, 160))
            img.paste(fetched_img, (0,0))
            img.paste(dark_layer, (0,0), dark_layer)
            text_color = "white"
        else:
            text_color = "#1E293B"
            
        y = 280
        y = draw_text_wrapped(draw, en_text.upper(), font_large, 0, y, 22, fill=text_color)
        y += 60
        y = draw_text_wrapped(draw, kr_text, font_medium, 0, y, 24, fill=text_color)
        y += 30
        draw_text_wrapped(draw, jp_text, font_small, 0, y, 28, fill=text_color)

    elif layout == 2: 
        text_color = "#1E293B"
        y = 100
        y = draw_text_wrapped(draw, en_text, font_medium, 0, y, 32, fill=text_color)
        y += 25
        y = draw_text_wrapped(draw, kr_text, font_small, 0, y, 32, fill=text_color)
        y += 15
        draw_text_wrapped(draw, jp_text, font_small, 0, y, 36, fill=text_color)
        
        if fetched_img:
            aspect_ratio = fetched_img.height / fetched_img.width
            new_h = int(900 * aspect_ratio)
            if new_h > 480: new_h = 480 # 텍스트 영역을 침범하지 않도록 제한
            fetched_img = fetched_img.resize((900, new_h), Image.Resampling.LANCZOS)
            img.paste(fetched_img, (90, 520))

    elif layout == 3: 
        text_color = "#1E293B"
        y = 420
        y = draw_text_wrapped(draw, f'"{kr_text}"', font_large, 0, y, 20, fill=text_color)
        y += 40
        draw_text_wrapped(draw, en_text, font_small, 0, y, 38, fill=text_color)

    else: 
        text_color = "#1E293B"
        y = 320
        y = draw_text_wrapped(draw, "👇 What do you think?", font_medium, 0, y, 30, fill=text_color)
        y += 50
        y = draw_text_wrapped(draw, kr_text, font_large, 0, y, 20, fill=text_color)
        y += 90
        draw_text_wrapped(draw, "💾 저장하고 나중에 다시 보세요!", font_small, 0, y, 30, fill="#4B5563")

    filename = f"slide_{slide_data['slide_number']}.png"
    img.save(filename)
    return filename

# ==========================================
# 6. 메일 발송
# ==========================================
def send_email_with_images(image_files):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER
    msg['Date'] = formatdate(localtime=True)
    msg['Subject'] = "[인스타 자동화] 스토리/후킹 적용 카드뉴스 도착! 🚀"
    
    body = "성공적으로 인스타형 다국어 카드뉴스가 완성되었습니다. 첨부된 5장의 이미지를 피드에 올리세요!"
    msg.attach(MIMEText(body, 'plain', 'utf-8'))
    
    for file in image_files:
        if os.path.exists(file):
            with open(file, 'rb') as f:
                img_data = f.read()
            image = MIMEImage(img_data, name=os.path.basename(file))
            msg.attach(image)
            
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
        server.quit()
        print("✅ 이메일 발송 완벽 성공!")
    except Exception as e:
        print(f"❌ 이메일 전송 도중 에러: {e}")

# ==========================================
# 메인 실행 엔지니어링
# ==========================================
if __name__ == "__main__":
    print("🚀 인스타 카드뉴스 자동화 스크립트 시작...")
    
    # 겹치지 않는 5개의 무작위 색상 사전 배정
    selected_bg_colors = random.sample(PASTEL_COLORS, 5)
    slides_data = generate_news_content()
    
    if slides_data:
        generated_files = []
        for i, slide in enumerate(slides_data):
            bg_color = selected_bg_colors[i] 
            file_name = create_slide(slide, bg_color)
            generated_files.append(file_name)
            
        send_email_with_images(generated_files)
    else:
        print("❌ AI 기획 실패로 스크립트를 종료합니다.")