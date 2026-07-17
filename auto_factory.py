import os
import json
import smtplib
import requests
import random
import time
import xml.etree.ElementTree as ET
from io import BytesIO
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from PIL import Image, ImageDraw, ImageFont

# [최신 규격] 구글 최신 라이브러리 임포트
from google import genai
from google.genai import types

# ==========================================
# 1. 환경 변수 설정 및 API 클라이언트 초기화
# ==========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.environ.get("EMAIL_RECEIVER")

if not GEMINI_API_KEY:
    print("⚠️ 에러: GEMINI_API_KEY가 설정되지 않았습니다.")

client = genai.Client(api_key=GEMINI_API_KEY)

# ==========================================
# 2. 오늘의 뉴스 자동 수집 로직 (강력 차단 우회 및 2중 백업)
# ==========================================
def get_today_news_topic():
    current_timestamp = int(time.time())
    
    # 🚨 [해결책 1] 구글 뉴스 서버가 봇으로 의심해 차단하지 않도록 실제 크롬 브라우저 정보(User-Agent)를 강력하게 심어줍니다.
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7'
    }
    
    # 1차 시도: 구글 뉴스 RSS
    try:
        url = f"https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko&t={current_timestamp}"
        response = requests.get(url, headers=headers, timeout=10)
        
        # 받아온 데이터가 올바른 XML 양식인지 안전하게 체크
        if response.text.strip().startswith("<?xml") or "<rss" in response.text:
            root = ET.fromstring(response.content)
            top_news_title = root.find('.//item/title').text
            if " - " in top_news_title:
                top_news_title = top_news_title.split(" - ")[0]
            print("✅ 1차 구글 뉴스 수집 성공!")
            return top_news_title
        else:
            raise ValueError("구글이 뉴스 대신 경고 웹페이지를 반환했습니다.")
            
    except Exception as e:
        print(f"⚠️ 1차 구글 뉴스 실패 ({e}) ➔ 2차 네이버 뉴스 백업 가동...")
        
        # 2차 시도: 구글이 막히면 자동으로 '네이버 실시간 뉴스 RSS' 채널로 우회하여 생뉴스를 가져옵니다.
        try:
            backup_url = f"https://news.naver.com/rss/main/105.xml?t={current_timestamp}" # IT/과학 속보
            # 혹은 전체 주요뉴스: https://news.naver.com/rss/main/100.xml (정치), 101.xml (경제)
            
            response = requests.get(backup_url, headers=headers, timeout=10)
            root = ET.fromstring(response.content)
            top_news_title = root.find('.//item/title').text
            print("✅ 2차 네이버 뉴스 백업 수집 성공!")
            return top_news_title
        except Exception as e2:
            print(f"⚠️ 2차 백업 뉴스도 실패: {e2}")
            return "오늘의 주요 시사 상식 및 융합 트렌드 요약"

# ==========================================
# 3. 좌측 정렬 텍스트 자동 줄바꿈 렌더러
# ==========================================
def wrap_text(text, font, max_width, draw):
    lines, current_line = [], ""
    for char in text:
        test_line = current_line + char
        bbox = draw.textbbox((0, 0), test_line, font=font)
        if (bbox[2] - bbox[0]) <= max_width:
            current_line = test_line
        else:
            if current_line: lines.append(current_line)
            current_line = char
    if current_line: lines.append(current_line)
    return lines

def draw_left_wrapped_text(draw, text, font, fill_color, start_x, start_y, max_width, line_spacing=18):
    lines = wrap_text(text, font, max_width, draw)
    current_y = start_y
    for line in lines:
        draw.text((start_x, current_y), line, fill=fill_color, font=font, anchor="la")
        bbox = draw.textbbox((0, 0), line, font=font)
        h = bbox[3] - bbox[1]
        current_y += h + line_spacing
    return current_y

# ==========================================
# 4. 카드뉴스 메인 제작 로직
# ==========================================
def create_card_news(user_topic):
    random_seed = random.randint(1, 99999)
    
    prompt = f"""
주제: '{user_topic}'
기획 일련번호: #{random_seed}

이 주제로 인스타그램 카드뉴스 5장 세트를 완전히 새롭고 신선한 문장으로 독창적으로 기획해줘.
추가로, 아래의 5가지 디자인 스타일 테마 중 이 뉴스 성격에 가장 잘 어울리는 딱 하나의 테마 영어 단어(theme)와 그에 맞는 포인트 색상 HEX 코드(color)를 골라줘.

[선택할 수 있는 테마 리스트]
1. 테크/미래 ➔ theme: "tech", color: "#3B82F6" (블루)
2. 비즈니스/경제 ➔ theme: "finance", color: "#0F172A" (다크 네이비)
3. 힐링/라이프 ➔ theme: "nature", color: "#10B981" (그린)
4. 트렌드/이슈 ➔ theme: "neon", color: "#A855F7" (퍼플)
5. 문화/예술 ➔ theme: "minimal", color: "#F59E0B" (오렌지)

출력은 오직 아래 키를 가진 JSON 배열만 출력해.
- slide_num: 슬라이드 번호
- title: 슬라이드 제목
- description: 슬라이드 내용 설명
- keyword: 슬라이드 내용과 매칭되는 구체적인 사물/오브젝트 영단어 1개 (예: 'phone', 'computer', 'leaf')
- chosen_theme: 위 리스트에서 선택한 테마 영어 단어 (5장 모두 동일)
- point_color: 위 리스트에서 선택한 테마의 color HEX 코드 (5장 모두 동일)
"""
    
    print("🤖 AI가 새로운 테마 색상과 내용 기획 중...")
    
    models_to_try = ['gemini-2.0-flash', 'gemini-2.0-flash-lite', 'gemini-3.1-flash-lite', 'gemini-3.5-flash']
    response = None
    last_error = None
    
    for model_name in models_to_try:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            break
        except Exception as e:
            last_error = e
            continue
            
    if response is None:
        raise last_error
    
    slides_data = json.loads(response.text)
    if isinstance(slides_data, dict) and "slides" in slides_data:
        slides_data = slides_data["slides"]

    font_path = "CustomFont.otf"
    if not os.path.exists(font_path):
        font_url = "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/Korean/NotoSansCJKkr-Bold.otf"
        with open(font_path, "wb") as f: 
            f.write(requests.get(font_url).content)

    width, height = 1080, 1350
    title_font = ImageFont.truetype(font_path, 64)
    desc_font = ImageFont.truetype(font_path, 36)
    logo_font = ImageFont.truetype(font_path, 24)
    
    image_paths = []
    
    first_slide = slides_data[0]
    global_theme = first_slide.get("chosen_theme", "minimal").strip()
    global_color = first_slide.get("point_color", "#3B82F6").strip()
    
    print(f"🎨 [선택된 테마] 종류: {global_theme} | 색상 코드: {global_color}")
    
    for idx, slide in enumerate(slides_data):
        final_img = Image.new("RGB", (width, height), color="#FFFFFF")
        draw = ImageDraw.Draw(final_img)
        
        object_keyword = slide.get("keyword", "object").strip()
        unique_time = int(time.time()) + idx
        
        # 무작위 잠금을 활성화한 고유 주소 매칭
        img_url = f"https://loremflickr.com/1080/650/{global_theme},{object_keyword}/all?lock={unique_time}"
        
        try:
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            img_data = requests.get(img_url, headers=headers, timeout=12).content
            top_img = Image.open(BytesIO(img_data))
            top_img = top_img.resize((width, 650), Image.Resampling.LANCZOS)
            final_img.paste(top_img, (0, 0))
        except Exception as e:
            print(f"⚠️ 이미지 다운로드 우회 처리 ➔ 컬러 디자인 대체: {e}")
            draw.rectangle([0, 0, width, 650], fill=global_color)
            draw.rectangle([30, 30, width - 30, 620], outline="#FFFFFF", width=4)
            
        # 1. 우측 상단 페이지 번호
        badge_w, badge_h = 110, 50
        badge_x1, badge_y1 = width - 210, 60
        draw.rounded_rectangle([badge_x1, badge_y1, badge_x1 + badge_w, badge_y1 + badge_h], radius=25, fill="#7E8B9B")
        draw.text((badge_x1 + badge_w//2, badge_y1 + badge_h//2), f"{idx+1}/{len(slides_data)}", fill="#FFFFFF", font=logo_font, anchor="mm")
        
        # 2. 좌측 중단 아이콘 배지 (그날의 테마 컬러 반영)
        icon_box_x, icon_box_y = 100, 720
        draw.rounded_rectangle([icon_box_x, icon_box_y, icon_box_x + 100, icon_box_y + 100], radius=20, fill="#E2F2FE")
        draw.rectangle([icon_box_x + 30, icon_box_y + 30, icon_box_x + 44, icon_box_y + 44], fill=global_color)
        draw.rectangle([icon_box_x + 56, icon_box_y + 30, icon_box_x + 70, icon_box_y + 44], fill=global_color)
        draw.rectangle([icon_box_x + 30, icon_box_y + 56, icon_box_x + 44, icon_box_y + 70], fill=global_color)
        draw.rectangle([icon_box_x + 56, icon_box_y + 56, icon_box_x + 70, icon_box_y + 70], fill=global_color)
        
        # 3. 텍스트 렌더링
        title_text = f"{idx+1}. {slide.get('title', '')}" if idx > 0 else slide.get('title', '')
        title_y_end = draw_left_wrapped_text(draw, str(title_text), title_font, "#0F2942", start_x=100, start_y=860, max_width=880)
        
        desc_text = str(slide.get("description", ""))
        draw_left_wrapped_text(draw, desc_text, desc_font, "#475569", start_x=100, start_y=title_y_end + 35, max_width=880, line_spacing=14)
        
        # 4. 하단 태그 디자인
        style_info_tag = f"DAILY AUTO FACTORY  |  THEME: {global_theme.upper()}"
        draw.text((100, 1250), style_info_tag, fill="#94A3B8", font=logo_font, anchor="la")
        
        filename = f"slide_{idx+1}.png"
        final_img.save(filename)
        image_paths.append(filename)
    
    return image_paths

# ==========================================
# 5. 생성된 이미지를 이메일로 발송
# ==========================================
def send_email(topic, image_paths):
    if not all([EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECEIVER]):
        return
    msg = MIMEMultipart()
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER
    msg['Subject'] = f"📢 [실시간 차단 우회] 오늘의 AI 뉴스 카드뉴스: {topic}"
    msg.attach(MIMEText(f"안녕하세요.\n\n수집 차단 현상을 완벽하게 뚫어낸 최신 실시간 카드뉴스입니다.", 'plain'))
    
    for path in image_paths:
        with open(path, 'rb') as f:
            msg.attach(MIMEImage(f.read(), name=os.path.basename(path)))
            
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
        server.quit()
        print("✅ 이메일 발송 완료!")
    except Exception as e:
        print(f"❌ 이메일 발송 실패: {e}")

if __name__ == "__main__":
    today_topic = get_today_news_topic()
    print(f"📰 오늘 선택된 뉴스 주제: {today_topic}")
    images = create_card_news(today_topic)
    send_email(today_topic, images)