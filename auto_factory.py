import os
import json
import smtplib
import requests
import random  # 무작위 이미지 추출을 위해 추가
import time
import xml.etree.ElementTree as ET
from io import BytesIO
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

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
# 2. 오늘의 뉴스 자동 수집 로직 (캐시 브레이커)
# ==========================================
def get_today_news_topic():
    try:
        current_timestamp = int(time.time())
        url = f"https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko&t={current_timestamp}"
        
        response = requests.get(url, timeout=10)
        root = ET.fromstring(response.content)
        top_news_title = root.find('.//item/title').text
        
        if " - " in top_news_title:
            top_news_title = top_news_title.split(" - ")[0]
        return top_news_title
    except Exception as e:
        print(f"⚠️ 뉴스 수집 실패 (대체 주제 사용): {e}")
        return "오늘의 주요 시사 상식 및 트렌드 요약"

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
# 4. 카드뉴스 메인 제작 로직 (Perfect Randomization)
# ==========================================
def create_card_news(user_topic):
    # 🚨 [해결책 1] AI가 절대 똑같은 문장을 반복하지 않도록 무작위 시드 속성을 프롬프트에 주입
    random_seed = random.randint(1, 99999)
    prompt = f"""
주제: '{user_topic}'
작성 기준 일련번호: #{random_seed} (매번 완전히 새로운 시각과 문장으로 창작할 것)

위 주제를 기반으로 인스타그램 카드뉴스 5장 세트 기획을 독창적으로 작성해줘. 
또한 이 뉴스의 톤앤매너에 어울리는 화풍 스타일 키워드 1개(예: 'cyberpunk', 'watercolor', 'flat vector', 'isometric 3d', 'pop art' 중 택1)와 포인트 색상 1개(HEX 코드 예: '#EAB308')를 무작위성을 살려 아주 개성 있게 선정해줘.

출력은 오직 아래 키를 가진 JSON 배열만 출력해.
- slide_num: 슬라이드 번호
- title: 슬라이드 제목 (기존과 다른 신선한 문구로 작성)
- subtitle: 슬라이드 부제목 (첫 장에만 필요)
- description: 슬라이드 내용 설명
- keyword: 슬라이드에 어울리는 구체적인 사물/행동 영단어 (1단어)
- chosen_style: 선정한 화풍 스타일 영문 키워드 (전체 슬라이드 동일)
- point_color: 선정한 포인트 컬러 HEX 코드 (전체 슬라이드 동일)
"""
    
    print("🤖 AI가 새로운 내용과 스타일에 맞춰 실시간 기획 창작 중...")
    
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
    global_style = first_slide.get("chosen_style", "flat,vector").strip()
    global_color = first_slide.get("point_color", "#0284C7").strip()
    
    print(f"🎨 [오늘의 커스텀 테마] 화풍: {global_style} | 색상: {global_color}")
    
    for idx, slide in enumerate(slides_data):
        final_img = Image.new("RGB", (width, height), color="#FFFFFF")
        draw = ImageDraw.Draw(final_img)
        
        # 🚨 [해결책 2] 이미지 사이트가 똑같은 사진만 뱉지 못하도록 매 슬라이드마다 무작위 숫자를 쿼리에 조합
        clean_style = global_style.replace(" ", "")
        object_keyword = slide.get("keyword", "object").strip().replace(" ", "")
        random_image_breaker = random.randint(1, 1000)
        
        # 주소 뒤에 /?sig=숫자 형태로 고유 코드를 붙여 무조건 다른 사진이 매칭되게 차단
        img_url = f"https://loremflickr.com/1080/650/{clean_style},{object_keyword}?sig={random_image_breaker}"
        
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            img_data = requests.get(img_url, headers=headers, timeout=10).content
            top_img = Image.open(BytesIO(img_data))
            top_img = top_img.resize((width, 650), Image.Resampling.LANCZOS)
            final_img.paste(top_img, (0, 0))
        except Exception as e:
            print(f"⚠️ 이미지 매칭 실패 ➔ 컬러 프레임 대체: {e}")
            draw.rectangle([0, 0, width, 650], fill=global_color)
            draw.rectangle([30, 30, width - 30, 620], outline="#FFFFFF", width=4)
            
        # 1. 우측 상단 페이지 번호
        badge_w, badge_h = 110, 50
        badge_x1, badge_y1 = width - 210, 60
        draw.rounded_rectangle([badge_x1, badge_y1, badge_x1 + badge_w, badge_y1 + badge_h], radius=25, fill="#7E8B9B")
        draw.text((badge_x1 + badge_w//2, badge_y1 + badge_h//2), f"{idx+1}/{len(slides_data)}", fill="#FFFFFF", font=logo_font, anchor="mm")
        
        # 2. 좌측 중단 아이콘 배지 (그날의 테마 컬러 분배)
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
        style_info_tag = f"DAILY AUTO FACTORY  |  THEME: {global_style.upper()}"
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
    msg['Subject'] = f"📢 [실시간 갱신] 오늘의 AI 뉴스 카드뉴스: {topic}"
    msg.attach(MIMEText(f"안녕하세요.\n\n매번 누를 때마다 완전히 새롭게 생성되는 다이내믹 카드뉴스입니다.", 'plain'))
    
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

# ==========================================
# 6. 메인 실행 블록
# ==========================================
if __name__ == "__main__":
    today_topic = get_today_news_topic()
    print(f"📰 오늘 선택된 뉴스 주제: {today_topic}")
    images = create_card_news(today_topic)
    send_email(today_topic, images)