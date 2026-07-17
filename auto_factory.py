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
# 3. 텍스트 자동 줄바꿈 및 프리미엄 렌더러
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

def draw_centered_wrapped_text(draw, text, font, fill_color, center_x, start_y, max_width, line_spacing=18):
    lines = wrap_text(text, font, max_width, draw)
    current_y = start_y
    for line in lines:
        # 가로 가운데 정렬('ma')로 텍스트 출력
        draw.text((center_x, current_y), line, fill=fill_color, font=font, anchor="ma", align="center")
        bbox = draw.textbbox((0, 0), line, font=font)
        h = bbox[3] - bbox[1]
        current_y += h + line_spacing
    return current_y

# ==========================================
# 4. 카드뉴스 메인 제작 로직 (Premium Redesign)
# ==========================================
def create_card_news(user_topic):
    prompt = f"주제: '{user_topic}'\n인스타그램 카드뉴스 5장 세트 기획을 작성해.\nslide_num, title, subtitle, description, keyword(영문1단어) 키를 가진 JSON 배열만 출력해."
    
    print("🤖 AI 기획 생성 중...")
    
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

    font_path = "CustomFont.otf"
    if not os.path.exists(font_path):
        print("📥 폰트 다운로드 중...")
        font_url = "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/Korean/NotoSansCJKkr-Bold.otf"
        with open(font_path, "wb") as f: 
            f.write(requests.get(font_url).content)

    width, height = 1080, 1350 # 인스타그램 추천 비율 (4:5)
    title_font = ImageFont.truetype(font_path, 68)
    subtitle_font = ImageFont.truetype(font_path, 40)
    desc_font = ImageFont.truetype(font_path, 32)
    
    image_paths = []
    
    print("🎨 프리미엄 매거진 스타일 카드뉴스 렌더링 중...")
    for idx, slide in enumerate(slides_data):
        keyword = slide.get("keyword", "news").strip()
        img_url = f"https://loremflickr.com/1080/1350/{keyword}"
        
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            img_data = requests.get(img_url, headers=headers, timeout=10).content
            bg = Image.open(BytesIO(img_data))
        except Exception as e:
            print(f"⚠️ {idx+1}번 슬라이드 이미지 다운로드 실패, 단색 배경 대체: {e}")
            bg = Image.new("RGB", (width, height), color="#0F172A")
            
        # 이미지 크기 강제 맞춤 및 밝기 조절 (배경이 살짝 살아나도록 0.55로 설정)
        bg = bg.resize((width, height), Image.Resampling.LANCZOS)
        bg_dark = ImageEnhance.Brightness(bg).enhance(0.55)
        
        # 반투명 레이어를 위한 RGBA 변환
        bg_rgba = bg_dark.convert("RGBA")
        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw_overlay = ImageDraw.Draw(overlay)
        
        # [디자인] 프리미엄 반투명 다크 슬레이트 카드 배치 (#0F172A 기반, 알파값 220)
        card_left, card_top, card_right, card_bottom = 100, 180, 980, 1220
        draw_overlay.rounded_rectangle(
            [card_left, card_top, card_right, card_bottom],
            radius=24,
            fill=(15, 23, 42, 220)
        )
        
        # [디자인] 카드 상단 골드 포인트 탑 바 데코레이션 (#F59E0B)
        draw_overlay.rounded_rectangle(
            [card_left, card_top, card_right, card_top + 15],
            radius=5,
            fill=(245, 158, 11, 255)
        )
        
        # 베이스 이미지와 반투명 레이어 믹스
        combined = Image.alpha_composite(bg_rgba, overlay)
        final_img = combined.convert("RGB")
        draw = ImageDraw.Draw(final_img)
        
        # [텍스트] 1. 최상단 분류 배지
        badge_text = "TODAY'S ISSUE" if idx == 0 else f"KEY POINT 0{idx}"
        badge_font = ImageFont.truetype(font_path, 30)
        draw.text((width // 2, card_top + 60), badge_text, fill="#F59E0B", font=badge_font, anchor="ma")
        
        # [텍스트] 2. 페이지 번호 (우측 하단 소형화)
        draw.text((card_right - 60, card_bottom - 70), f"{idx+1} / 5", fill="#64748B", font=desc_font, anchor="ra")
        
        # [텍스트] 3. 제목 렌더링 (동적으로 위치 확보)
        title_text = str(slide.get("title", ""))
        title_y_end = draw_centered_wrapped_text(
            draw, title_text, title_font, "#FFFFFF", 
            center_x=width // 2, start_y=card_top + 130, 
            max_width=760
        )
        
        # [텍스트] 4. 본문 내용 (커버와 알맹이 분리 설계)
        if idx == 0:
            # 첫 페이지 (표지): 세련된 정돈감 위주
            subtitle_text = str(slide.get("subtitle", ""))
            sub_y_end = draw_centered_wrapped_text(
                draw, subtitle_text, subtitle_font, "#94A3B8", 
                center_x=width // 2, start_y=title_y_end + 50, 
                max_width=760
            )
            
            desc_text = str(slide.get("description", ""))
            draw_centered_wrapped_text(
                draw, desc_text, desc_font, "#E2E8F0", 
                center_x=width // 2, start_y=sub_y_end + 60, 
                max_width=760
            )
        else:
            # 본문 페이지: 얇은 디자인 구분선 긋고 설명 배치
            draw.line([width // 2 - 80, title_y_end + 40, width // 2 + 80, title_y_end + 40], fill="#334155", width=2)
            
            desc_text = str(slide.get("description", ""))
            draw_centered_wrapped_text(
                draw, desc_text, desc_font, "#E2E8F0", 
                center_x=width // 2, start_y=title_y_end + 80, 
                max_width=760
            )
        
        filename = f"slide_{idx+1}.png"
        final_img.save(filename)
        image_paths.append(filename)
    
    print("✅ 프리미엄 카드뉴스 이미지 렌더링 완료!")
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
    msg.attach(MIMEText(f"안녕하세요.\n\nAI 공장이 오늘의 뉴스 [{topic}]를 기반으로 제작한 프리미엄 카드뉴스 5장을 첨부합니다.\n인스타그램에 바로 업로드해보세요!", 'plain'))
    
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