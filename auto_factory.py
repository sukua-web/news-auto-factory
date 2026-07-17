import os
import json
import smtplib
import requests
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

# Client 객체 생성
client = genai.Client(api_key=GEMINI_API_KEY)

# ==========================================
# 2. 오늘의 뉴스 자동 수집 로직
# ==========================================
def get_today_news_topic():
    try:
        url = "https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko"
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
# 4. 카드뉴스 메인 제작 로직 (Dynamic Style System)
# ==========================================
def create_card_news(user_topic):
    # [스타일 가변화 프롬프트] 뉴스 분위기에 맞는 디자인 스타일과 포인트 색상 코드를 직접 생성하게 합니다.
    prompt = f"""
주제: '{user_topic}'
인스타그램 카드뉴스 5장 세트 기획을 작성해줘.

추가로, 이 뉴스의 성격(경제, IT, 사회, 힐링 등)을 분석해서 가장 잘 어울리는 화풍 스타일(예: 'watercolor', 'cyberpunk', 'retro flat vector', 'isometric 3d', 'minimal pencil sketch' 중 택 1)과, 포인트 컬러 1개(HEX 코드 형태, 예: '#0284C7')를 선정해줘.

출력은 오직 아래 키를 가진 JSON 배열만 출력해.
- slide_num: 슬라이드 번호
- title: 슬라이드 제목
- subtitle: 슬라이드 부제목 (첫 장에만 필요)
- description: 슬라이드 내용 설명
- keyword: 슬라이드에 어울리는 구체적인 사물/행동 영단어 (1단어)
- chosen_style: 선정한 화풍 스타일 영문 키워드 (전체 슬라이드 동일하게 적용)
- point_color: 선정한 포인트 컬러 HEX 코드 (전체 슬라이드 동일하게 적용)
"""
    
    print("🤖 AI 기획 및 오늘에 맞는 스타일 분석 중...")
    
    models_to_try = [
        'gemini-2.0-flash',
        'gemini-2.0-flash-lite',
        'gemini-3.1-flash-lite',
        'gemini-3.5-flash'
    ]
    
    response = None
    last_error = None
    
    for model_name in models_to_try:
        try:
            print(f"👉 {model_name} 모델로 생성 시도 중...")
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                )
            )
            print(f"✅ {model_name} 모델 호출 성공!")
            break
        except Exception as e:
            print(f"⚠️ {model_name} 호출 실패 (다음 모델로 넘어갑니다): {e}")
            last_error = e
            continue
            
    if response is None:
        print("\n❌ 준비된 모든 무료 모델 호출에 실패했습니다.")
        raise last_error
    
    slides_data = json.loads(response.text)
    if isinstance(slides_data, dict) and "slides" in slides_data:
        slides_data = slides_data["slides"]

    # 폰트 로드
    font_path = "CustomFont.otf"
    if not os.path.exists(font_path):
        print("📥 폰트 다운로드 중...")
        font_url = "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/Korean/NotoSansCJKkr-Bold.otf"
        with open(font_path, "wb") as f: 
            f.write(requests.get(font_url).content)

    width, height = 1080, 1350
    title_font = ImageFont.truetype(font_path, 64)
    desc_font = ImageFont.truetype(font_path, 36)
    logo_font = ImageFont.truetype(font_path, 24)
    
    image_paths = []
    
    # 첫 장에서 결정된 공통 스타일 정보 가져오기 (기본값 설정)
    first_slide = slides_data[0]
    global_style = first_slide.get("chosen_style", "minimal,flat,vector").strip()
    global_color = first_slide.get("point_color", "#0284C7").strip()
    
    print(f"🎨 [오늘의 매칭 스타일] 화풍: {global_style} | 포인트 컬러: {global_color}")
    print("🎨 스타일리시 다이내믹 카드뉴스 렌더링 시작...")
    
    for idx, slide in enumerate(slides_data):
        final_img = Image.new("RGB", (width, height), color="#FFFFFF")
        draw = ImageDraw.Draw(final_img)
        
        # AI가 뽑아준 스타일과 사물 키워드를 믹스해서 이미지 다운로드
        object_keyword = slide.get("keyword", "object").strip()
        combined_keyword = f"{global_style},{object_keyword}"
        img_url = f"https://loremflickr.com/1080/650/{combined_keyword}"
        
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            img_data = requests.get(img_url, headers=headers, timeout=10).content
            top_img = Image.open(BytesIO(img_data))
            top_img = top_img.resize((width, 650), Image.Resampling.LANCZOS)
            final_img.paste(top_img, (0, 0))
        except Exception as e:
            print(f"⚠️ {idx+1}번 이미지 다운로드 실패, 연한 그레이 대체: {e}")
            draw.rectangle([0, 0, width, 650], fill="#F1F5F9")
            
        # 1. 우측 상단 페이지 번호 캡슐 버튼
        badge_w, badge_h = 110, 50
        badge_x1, badge_y1 = width - 210, 60
        draw.rounded_rectangle(
            [badge_x1, badge_y1, badge_x1 + badge_w, badge_y1 + badge_h],
            radius=25,
            fill="#7E8B9B"
        )
        draw.text((badge_x1 + badge_w//2, badge_y1 + badge_h//2), f"{idx+1}/{len(slides_data)}", fill="#FFFFFF", font=logo_font, anchor="mm")
        
        # 2. 좌측 중단 아이콘 배지 (AI가 정한 그날의 테마 포인트 컬러 적용!)
        icon_box_x, icon_box_y = 100, 720
        draw.rounded_rectangle(
            [icon_box_x, icon_box_y, icon_box_x + 100, icon_box_y + 100],
            radius=20,
            fill="#E2F2FE"
        )
        # 아이콘 안의 점들에 테마 컬러 반영
        draw.rectangle([icon_box_x + 30, icon_box_y + 30, icon_box_x + 44, icon_box_y + 44], fill=global_color)
        draw.rectangle([icon_box_x + 56, icon_box_y + 30, icon_box_x + 70, icon_box_y + 44], fill=global_color)
        draw.rectangle([icon_box_x + 30, icon_box_y + 56, icon_box_x + 44, icon_box_y + 70], fill=global_color)
        draw.rectangle([icon_box_x + 56, icon_box_y + 56, icon_box_x + 70, icon_box_y + 70], fill=global_color)
        
        # 3. 좌측 정렬 텍스트 렌더링
        title_text = f"{idx+1}. {slide.get('title', '')}" if idx > 0 else slide.get('title', '')
        title_y_end = draw_left_wrapped_text(
            draw, str(title_text), title_font, "#0F2942", 
            start_x=100, start_y=860, 
            max_width=880
        )
        
        desc_text = str(slide.get("description", ""))
        draw_left_wrapped_text(
            draw, desc_text, desc_font, "#475569", 
            start_x=100, start_y=title_y_end + 35, 
            max_width=880, line_spacing=14
        )
        
        # 4. 하단 미니 로고 및 그날의 스타일 정보 노출 (디자인 디테일)
        style_info_tag = f"DAILY AUTO FACTORY  |  STYLE: {global_style.upper()}"
        draw.text((100, 1250), style_info_tag, fill="#94A3B8", font=logo_font, anchor="la")
        
        filename = f"slide_{idx+1}.png"
        final_img.save(filename)
        image_paths.append(filename)
    
    print("✅ 스타일리시 다이내믹 카드뉴스 이미지 렌더링 완료!")
    return image_paths

# ==========================================
# 5. 생성된 이미지를 이메일로 발송
# ==========================================
def send_email(topic, image_paths):
    if not all([EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECEIVER]):
        print("⚠️ 이메일 환경변수가 누락되어 메일을 발송하지 않습니다.")
        return

    print("📧 이메일 발송 준비 중...")
    msg = MIMEMultipart()
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER
    msg['Subject'] = f"📢 [자동 발송] 오늘의 AI 뉴스 카드뉴스: {topic}"
    msg.attach(MIMEText(f"안녕하세요.\n\nAI가 오늘의 뉴스 분위기에 맞추어 커스텀 디자인한 카드뉴스 5장을 첨부합니다.\n인스타그램에 바로 업로드해보세요!", 'plain'))
    
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
    print("🎉 모든 자동화 프로세스 종료!")