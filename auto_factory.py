import os
import json
import random
import re
import time
import smtplib
import requests
import xml.etree.ElementTree as ET
from io import BytesIO
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
import google.generativeai as genai

# ==========================================
# 1. 환경 변수 설정
# ==========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.environ.get("EMAIL_RECEIVER")
SERPAPI_KEY = os.environ.get("SERPAPI_KEY")
PEXELS_KEY = os.environ.get("PEXELS_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# ==========================================
# 2. 오늘의 뉴스 자동 수집 (구글 RSS + 네이버 백업)
# ==========================================
def get_today_news_topic():
    current_timestamp = int(time.time())
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0',
        'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8'
    }
    try:
        url = f"https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko&t={current_timestamp}"
        response = requests.get(url, headers=headers, timeout=10)
        if "<rss" in response.text or "<?xml" in response.text:
            root = ET.fromstring(response.content)
            top_news_title = root.find('.//item/title').text
            return top_news_title.split(" - ")[0] if " - " in top_news_title else top_news_title
        else:
            raise ValueError("구글 RSS 차단됨")
    except Exception as e:
        print(f"⚠️ 구글 뉴스 수집 실패 ➔ 네이버 백업 가동: {e}")
        try:
            backup_url = f"https://news.naver.com/rss/main/105.xml?t={current_timestamp}"
            response = requests.get(backup_url, headers=headers, timeout=10)
            root = ET.fromstring(response.content)
            return root.find('.//item/title').text
        except:
            return "오늘의 주요 글로벌 시사 및 트렌드 요약"

# ==========================================
# 3. 이미지 검색 (Pexels & SerpApi) - 모듈 에러 방지 처리
# ==========================================
def fetch_pexels_image(query, api_key):
    """표지(1장)용 힙한 감성 고화질 배경 수집"""
    if not api_key: return None
    url = f"https://api.pexels.com/v1/search?query={query}&per_page=5&orientation=portrait"
    headers = {"Authorization": api_key}
    try:
        res = requests.get(url, headers=headers, timeout=10).json()
        if res.get("photos"):
            img_url = res["photos"][0]["src"]["large2x"]
            img_res = requests.get(img_url, timeout=10)
            return Image.open(BytesIO(img_res.content)).convert("RGB")
    except Exception as e:
        print(f"⚠️ Pexels 에러: {e}")
    return None

def fetch_serpapi_image(query, api_key):
    """본문(2~5장)용 정확한 뉴스 관련 실사 수집 (REST API 방식)"""
    if not api_key: return None
    url = "https://serpapi.com/search"
    params = {"engine": "google_images", "q": query, "api_key": api_key, "ijn": "0"}
    try:
        res = requests.get(url, params=params, timeout=10).json()
        if "images_results" in res:
            for img_data in res["images_results"][:5]:
                img_url = img_data.get("original")
                if not img_url: continue
                try:
                    img_res = requests.get(img_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
                    if img_res.status_code == 200:
                        return Image.open(BytesIO(img_res.content)).convert("RGB")
                except:
                    continue
    except Exception as e:
        print(f"⚠️ SerpApi 에러: {e}")
    return None

# ==========================================
# 4. 스마트 텍스트 렌더링
# ==========================================
def smart_wrap_text(text, font, max_width, draw):
    lines = []
    paragraphs = str(text).split('\n')
    for paragraph in paragraphs:
        words = paragraph.split(' ')
        current_line = ""
        for word in words:
            if draw.textbbox((0, 0), word, font=font)[2] > max_width:
                if current_line:
                    lines.append(current_line)
                    current_line = ""
                for char in word:
                    test_line = current_line + char
                    if draw.textbbox((0, 0), test_line, font=font)[2] <= max_width:
                        current_line = test_line
                    else:
                        if current_line: lines.append(current_line)
                        current_line = char
            else:
                test_line = f"{current_line} {word}".strip() if current_line else word
                if draw.textbbox((0, 0), test_line, font=font)[2] <= max_width:
                    current_line = test_line
                else:
                    lines.append(current_line)
                    current_line = word
        if current_line:
            lines.append(current_line)
    return lines

def draw_smart_text_with_outline(draw, position, text, font, text_color, outline_color, max_width, outline_width=2, line_spacing=15):
    lines = smart_wrap_text(text, font, max_width, draw)
    line_heights = [draw.textbbox((0,0), line, font=font)[3] - draw.textbbox((0,0), line, font=font)[1] for line in lines]
    total_height = sum(line_heights) + line_spacing * (len(lines) - 1)
    current_y = position[1] - total_height // 2
    for line, h in zip(lines, line_heights):
        x, y = position[0], current_y + h // 2
        for dx in range(-outline_width, outline_width+1):
            for dy in range(-outline_width, outline_width+1):
                draw.text((x+dx, y+dy), line, fill=outline_color, font=font, anchor="mm", align="center")
        draw.text((x, y), line, fill=text_color, font=font, anchor="mm", align="center")
        current_y += h + line_spacing

# ==========================================
# 5. 메인 카드뉴스 제작 로직 (3개 국어 & 하이브리드 이미지)
# ==========================================
def create_card_news(user_topic):
    prompt = f"""
주제: '{user_topic}'
위 뉴스 주제로 인스타그램 카드뉴스 5장 기획을 작성해줘. 
1장은 뉴스의 가장 핵심적이고 강렬한 헤드라인, 2~5장은 뉴스의 구체적인 내용을 담아줘.
출력은 오직 아래 키를 가진 JSON 배열만 출력해.
- slide_num: 슬라이드 번호
- main_en: 아주 짧고 강렬한 영어 핵심 구절 (대제목 역할, 1~4단어)
- sub_ko: 한국어 서브 설명 문장
- sub_ja: 일본어 서브 번역 문장
- search_keyword: 이 슬라이드에 어울리는 구체적 이미지 검색용 영단어 1~2개
"""
    
    print("🤖 Gemini AI 다국어 카드뉴스 기획 중...")
    
    # 📌 고정된 모델 리스트
    models_to_try = ['gemini-2.0-flash', 'gemini-2.0-flash-lite', 'gemini-3.1-flash-lite', 'gemini-3.5-flash']
    response = None
    
    for m_name in models_to_try:
        try:
            model = genai.GenerativeModel(m_name)
            response = model.generate_content(prompt)
            break
        except Exception as e:
            continue
            
    if not response:
        raise ValueError("AI 생성 실패: 사용 가능한 모든 모델에서 응답을 받지 못했습니다.")
        
    raw_text = response.text.replace("```json", "").replace("```", "").strip()
    match = re.search(r'\[.*\]', raw_text, re.DOTALL)
    slides_data = json.loads(match.group()) if match else json.loads(raw_text)

    # 폰트 다운로드 세팅
    font_path = "CustomFont.otf"
    if not os.path.exists(font_path):
        font_url = "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/Korean/NotoSansCJKkr-Bold.otf"
        with open(font_path, "wb") as f: 
            f.write(requests.get(font_url).content)

    width, height = 1080, 1350
    # 3개 국어 계층적 폰트 크기 설정
    font_en = ImageFont.truetype(font_path, 110)
    font_ko = ImageFont.truetype(font_path, 45)
    font_ja = ImageFont.truetype(font_path, 35)
    
    image_paths = []
    
    for idx, slide in enumerate(slides_data):
        keyword = slide.get("search_keyword", "news")
        
        # [하이브리드 시스템] 1장은 Pexels, 2~5장은 SerpApi 사용
        if idx == 0:
            print(f"📸 1장 표지: Pexels에서 감성 이미지 검색 중 ({keyword})...")
            bg_img = fetch_pexels_image(f"aesthetic abstract {keyword}", PEXELS_KEY)
        else:
            print(f"🔍 {idx+1}장 본문: SerpApi에서 실사 이미지 검색 중 ({keyword})...")
            bg_img = fetch_serpapi_image(keyword, SERPAPI_KEY)
            
        # 이미지 없으면 대체 배경 생성
        if bg_img:
            bg_img = bg_img.resize((width, height), Image.Resampling.LANCZOS)
            bg_img = ImageEnhance.Brightness(bg_img).enhance(0.4) 
            c_main, c_sub, out = "#FFFFFF", "#E5E7EB", "#000000"
        else:
            bg_img = Image.new("RGB", (width, height), color="#1E293B")
            c_main, c_sub, out = "#F8FAFC", "#94A3B8", "#0F172A"
            
        draw = ImageDraw.Draw(bg_img)
        
        # 1장은 여백을 넓게(테두리 없음), 2~5장은 테두리를 쳐서 디자인 구분
        if idx > 0:
            draw.rectangle([60, 60, width-60, height-60], outline=c_main, width=4)
            
        # 다국어 3단 레이아웃 배치
        draw_smart_text_with_outline(draw, (width//2, height//2 - 250), slide.get("main_en", ""), font_en, c_main, out, max_width=width-200)
        draw_smart_text_with_outline(draw, (width//2, height//2 + 100), slide.get("sub_ko", ""), font_ko, c_sub, out, max_width=width-240)
        draw_smart_text_with_outline(draw, (width//2, height//2 + 300), slide.get("sub_ja", ""), font_ja, "#9CA3AF", out, max_width=width-240)
        
        # 페이지 번호 (표지 제외)
        if idx > 0:
            draw.text((width//2, height - 120), f"{idx+1} / 5", fill=c_sub, font=font_ja, anchor="mm")
            
        filename = f"slide_{idx+1}.png"
        bg_img.save(filename)
        image_paths.append(filename)
    
    return image_paths

# ==========================================
# 6. 완성본 이메일 자동 발송
# ==========================================
def send_email(topic, image_paths):
    if not all([EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECEIVER]):
        print("⚠️ 이메일 환경변수가 누락되었습니다.")
        return
        
    msg = MIMEMultipart()
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER
    msg['Subject'] = f"📢 [다국어 커스텀] 오늘의 AI 뉴스 카드뉴스: {topic}"
    msg.attach(MIMEText("안녕하세요.\n\n표지는 Pexels로 후킹하게, 본문은 SerpApi 실사로 구성된 영·한·일 3개 국어 카드뉴스입니다.", 'plain'))
    
    for path in image_paths:
        with open(path, 'rb') as f:
            msg.attach(MIMEImage(f.read(), name=os.path.basename(path)))
            
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
        server.quit()
        print("✅ 3개 국어 카드뉴스 이메일 발송 완료!")
    except Exception as e:
        print(f"❌ 이메일 발송 실패: {e}")

if __name__ == "__main__":
    today_topic = get_today_news_topic()
    print(f"📰 오늘의 뉴스: {today_topic}")
    images = create_card_news(today_topic)
    send_email(today_topic, images)