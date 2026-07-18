import os
import json
import random
import re
import time
import smtplib
import requests
import xml.etree.ElementTree as ET
from io import BytesIO
from email.message import EmailMessage
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
# 2. 오늘의 뉴스 자동 수집 (최신 타임라인 고정 및 파라미터 쇄신)
# ==========================================
def get_today_news_topic():
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0',
        'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8'
    }
    try:
        # 캐시 버그가 발생하는 구식 &t= 파라미터를 제거하고 최신 KR 정식 배포 주소로 변경
        url = "https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko"
        response = requests.get(url, headers=headers, timeout=10)
        
        if "<rss" in response.text or "<?xml" in response.text:
            root = ET.fromstring(response.content)
            items = root.findall('.//item')
            if items:
                # 가장 첫 번째에 노출된 실시간 헤드라인 뉴스를 가져옵니다
                top_news_title = items[0].find('title').text
                return top_news_title.split(" - ")[0] if " - " in top_news_title else top_news_title
        raise ValueError("구글 RSS 파싱 실패 또는 데이터 무효")
    except Exception as e:
        print(f"⚠️ 구글 뉴스 수집 실패 ➔ 네이버 IT/과학 실시간 백업 가동: {e}")
        try:
            backup_url = "https://news.naver.com/rss/main/105.xml"
            response = requests.get(backup_url, headers=headers, timeout=10)
            root = ET.fromstring(response.content)
            return root.find('.//item/title').text
        except:
            return "AI 인공지능 기술과 글로벌 테크 트렌드 최신 동향 요약"

# ==========================================
# 3. 이미지 검색 (Pexels & SerpApi)
# ==========================================
def fetch_pexels_image(query, api_key):
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
# 5. 메인 카드뉴스 제작 로직
# ==========================================
def create_card_news(user_topic):
    prompt = f"""
주제: '{user_topic}'
위 뉴스 주제로 인스타그램 카드뉴스 5장 기획을 작성해줘. 
1장은 뉴스의 가장 핵심적이고 강렬한 헤드라인, 2~5장은 뉴스의 구체적인 내용을 담아줘.
출력은 오직 아래 키를 가진 JSON 배열만 출력해. 다른 설명문은 일절 포함하지 마.
- slide_num: 슬라이드 번호
- main_en: 아주 짧고 강렬한 영어 핵심 구절 (대제목 역할, 1~4단어)
- sub_ko: 한국어 서브 설명 문장
- sub_ja: 일본어 서브 번역 문장
- search_keyword: 이 슬라이드에 어울리는 구체적 이미지 검색용 영단어 1~2개
"""
    
    print("🤖 Gemini AI 다국어 카드뉴스 기획 중...")
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
        raise ValueError("AI 생성 실패: 모든 지정 모델이 응답하지 않습니다.")
        
    raw_text = response.text.replace("```json", "").replace("```", "").strip()
    match = re.search(r'\[.*\]', raw_text, re.DOTALL)
    slides_data = json.loads(match.group()) if match else json.loads(raw_text)

    font_path = "CustomFont.otf"
    if not os.path.exists(font_path):
        font_url = "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/Korean/NotoSansCJKkr-Bold.otf"
        with open(font_path, "wb") as f: 
            f.write(requests.get(font_url).content)

    width, height = 1080, 1350
    font_en = ImageFont.truetype(font_path, 110)
    font_ko = ImageFont.truetype(font_path, 45)
    font_ja = ImageFont.truetype(font_path, 35)
    
    image_paths = []
    
    for idx, slide in enumerate(slides_data):
        keyword = slide.get("search_keyword", "news")
        
        if idx == 0:
            print(f"📸 1장 표지 이미지 수집 중 ({keyword})...")
            bg_img = fetch_pexels_image(f"aesthetic abstract {keyword}", PEXELS_KEY)
        else:
            print(f"🔍 {idx+1}장 본문 이미지 수집 중 ({keyword})...")
            bg_img = fetch_serpapi_image(keyword, SERPAPI_KEY)
            
        if bg_img:
            bg_img = bg_img.resize((width, height), Image.Resampling.LANCZOS)
            bg_img = ImageEnhance.Brightness(bg_img).enhance(0.4) 
            c_main, c_sub, out = "#FFFFFF", "#E5E7EB", "#000000"
        else:
            bg_img = Image.new("RGB", (width, height), color="#1E293B")
            c_main, c_sub, out = "#F8FAFC", "#94A3B8", "#0F172A"
            
        draw = ImageDraw.Draw(bg_img)
        
        if idx > 0:
            draw.rectangle([60, 60, width-60, height-60], outline=c_main, width=4)
            
        draw_smart_text_with_outline(draw, (width//2, height//2 - 250), slide.get("main_en", ""), font_en, c_main, out, max_width=width-200)
        draw_smart_text_with_outline(draw, (width//2, height//2 + 100), slide.get("sub_ko", ""), font_ko, c_sub, out, max_width=width-240)
        draw_smart_text_with_outline(draw, (width//2, height//2 + 300), slide.get("sub_ja", ""), font_ja, "#9CA3AF", out, max_width=width-240)
        
        if idx > 0:
            draw.text((width//2, height - 120), f"{idx+1} / 5", fill=c_sub, font=font_ja, anchor="mm")
            
        filename = f"slide_{idx+1}.png"
        bg_img.save(filename)
        image_paths.append(filename)
    
    return image_paths

# ==========================================
# 6. 완성본 이메일 자동 발송 (EmailMessage 표준 엔진으로 전면 갱신)
# ==========================================
def send_email(topic, image_paths):
    if not all([EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECEIVER]):
        print("⚠️ 이메일 환경변수가 누락되어 전송을 건너뜁니다.")
        return
        
    msg = EmailMessage()
    msg['Subject'] = f"📢 [다국어 자동화] 오늘의 최신 뉴스 카드뉴스: {topic}"
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER
    
    # 기본 본문 설정
    msg.set_content("안녕하세요.\n\n요청하신 디자인 쇄신 버전(Pexels + SerpApi 하이브리드) 3개 국어 자동 생성 카드뉴스 파일 5장이 본 이메일에 정상 첨부되었습니다.\n\n- AI 뉴스 카드뉴스 공장")
    
    # 💥 누락 없는 완벽한 바이너리 파일 첨부 프로세스 고정
    for path in image_paths:
        if os.path.exists(path):
            with open(path, 'rb') as f:
                file_data = f.read()
                file_name = os.path.basename(path)
                msg.add_attachment(file_data, maintype='image', subtype='png', filename=file_name)
            
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)
        print("✅ 3개 국어 뉴스 카드(이미지 파일 첨부 포함) 이메일 발송을 완벽하게 성공했습니다!")
    except Exception as e:
        print(f"❌ 이메일 최종 발송 실패: {e}")

if __name__ == "__main__":
    today_topic = get_today_news_topic()
    print(f"📰 오늘의 실제 최신 뉴스 검색어: {today_topic}")
    images = create_card_news(today_topic)
    send_email(today_topic, images)