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

# 📌 회원님 전용 황금 모델 리스트 (절대 변경 금지)
MODELS_TO_TRY = ['gemini-2.0-flash', 'gemini-2.0-flash-lite', 'gemini-3.1-flash-lite', 'gemini-3.5-flash']

# ==========================================
# 2. 디자인 및 기획 데이터
# ==========================================
PASTEL_COLORS = [
    "#FFB3BA", "#FFDFBA", "#FFFFBA", "#B8E994", "#A2C2E6", 
    "#D5AAFF", "#FFC6FF", "#BDE0FE", "#FFDAC1", "#E2F0CB"
]

def get_font(size):
    font_path = "NanumGothic.ttf"
    if not os.path.exists(font_path):
        print("폰트 다운로드 중...")
        font_url = "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Regular.ttf"
        urllib.request.urlretrieve(font_url, font_path)
    return ImageFont.truetype(font_path, size)

# ==========================================
# 3. AI 프롬프트 (극단적 요약 & 키워드 단순화)
# ==========================================
def generate_news_content():
    prompt = """
    당신은 100만 팔로워를 가진 글로벌 뉴스 인스타그램 채널의 수석 에디터입니다.
    오늘 가장 이슈가 되는 글로벌 뉴스 1개를 골라 5장의 캐러셀 기획안을 JSON으로 작성하세요.

    [가독성 극대화 필수 규칙 - 위반 금지]
    1. 글자 수 제한 (매우 중요):
       - en_text: 최대 3~6 단어로 아주 짧게 작성.
       - kr_text: 최대 15~20자 이내. (예: "충격적인 애플의 결단") 절대 구구절절 설명하지 마세요.
       - jp_text: 최대 15자 이내의 짧은 일본어 번역.
    2. 내용 전개: 1장(어그로 표지) -> 2장(핵심 사건) -> 3장(원인/배경) -> 4장(결과/전망) -> 5장(질문/참여 유도)
    3. 이미지 검색 키워드(search_keyword): 검색이 무조건 되도록 구체적인 명사 1~2개로만 작성 (예: "apple office", "broken smartphone", "crying man"). 문장형 절대 금지.

    반드시 아래 JSON 형식으로만 5장의 데이터를 출력하세요.
    [
      {
        "slide_number": 1,
        "en_text": "ENGLISH SHORT COPY",
        "kr_text": "한국어 짧은 카피",
        "jp_text": "일본어 짧은 카피",
        "search_keyword": "keyword"
      },
      ...
    ]
    """
    
    for model_name in MODELS_TO_TRY:
        try:
            print(f"🤖 AI 모델 시도 중: {model_name}")
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            raw_text = response.text.replace('```json', '').replace('```', '').strip()
            
            if "[" in raw_text and "]" in raw_text:
                raw_text = raw_text[raw_text.find("["):raw_text.rfind("]")+1]
                
            data = json.loads(raw_text)
            if len(data) == 5:
                print(f"✅ 기획 성공 ({model_name})")
                return data
        except Exception as e:
            print(f"⚠️ {model_name} 실패: {e}")
            continue
    return None

# ==========================================
# 4. 이미지 수집 시스템
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
                return Image.open(temp_path).convert("RGB")
        except Exception as e:
            print(f"⚠️ SerpApi 실패: {e}")

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
                return Image.open(temp_path).convert("RGB")
        except Exception as e:
            print(f"⚠️ Pexels 실패: {e}")
            
    return None

# ==========================================
# 5. 1080x1350 최적화 렌더링 (가독성/주부 역전)
# ==========================================
def draw_text_wrapped(draw, text, font, y, max_width, fill="black"):
    lines = textwrap.wrap(text, width=max_width)
    current_y = y
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        draw.text(((1080 - w) / 2, current_y), line, font=font, fill=fill)
        current_y += h + 20 # 줄 간격 넉넉하게
    return current_y

def create_slide(slide_data, bg_color):
    # 인스타 세로형 해상도 1080x1350 적용
    img = Image.new("RGB", (1080, 1350), bg_color)
    draw = ImageDraw.Draw(img)
    
    idx = slide_data['slide_number']
    en_text = slide_data["en_text"]
    kr_text = slide_data["kr_text"]
    jp_text = slide_data["jp_text"]
    
    font_massive = get_font(90)
    font_large = get_font(75)
    font_sub = get_font(35)
    
    fetched_img = fetch_image(slide_data.get("search_keyword", ""))
    
    if idx == 1:
        # 슬라이드 1: 영어가 메인, 한/일은 작게
        y = 250
        y = draw_text_wrapped(draw, en_text.upper(), font_massive, y, 18, fill="#111827")
        y += 80 # 언어 간 여백 확보
        y = draw_text_wrapped(draw, kr_text, font_sub, y, 40, fill="#4B5563")
        y += 20
        y = draw_text_wrapped(draw, jp_text, font_sub, y, 40, fill="#4B5563")
    else:
        # 슬라이드 2~5: 한글이 메인, 영/일은 작게
        y = 200
        y = draw_text_wrapped(draw, kr_text, font_large, y, 16, fill="#111827")
        y += 60
        y = draw_text_wrapped(draw, en_text, font_sub, y, 40, fill="#6B7280")
        y += 20
        y = draw_text_wrapped(draw, jp_text, font_sub, y, 40, fill="#6B7280")

    # 남는 하단 공간에 시원하게 이미지 배치 (텍스트와 절대 안 겹치게 Y좌표 650부터 시작)
    if fetched_img:
        aspect_ratio = fetched_img.height / fetched_img.width
        new_w = 900
        new_h = int(new_w * aspect_ratio)
        
        # 이미지가 너무 길면 자르기 (최대 높이 600 제한)
        if new_h > 600: 
            new_h = 600
        
        fetched_img = fetched_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        # 이미지를 화면 정중앙(가로)에, 세로는 y=650 위치에 고정 배치
        img.paste(fetched_img, (90, 650))

    filename = f"slide_{idx}.png"
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
    msg['Subject'] = "[인스타 자동화] 가독성 개선 버전 도착! 🚀"
    
    body = "가독성 최적화(1080x1350) 및 모델 픽스 버전입니다."
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
        print("✅ 이메일 발송 완료!")
    except Exception as e:
        print(f"❌ 이메일 전송 실패: {e}")

# ==========================================
# 메인 실행
# ==========================================
if __name__ == "__main__":
    print("🚀 스크립트 시작...")
    
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
        print("❌ 실패로 스크립트를 종료합니다.")