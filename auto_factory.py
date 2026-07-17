import os
import json
import time
import smtplib
import requests
import xml.etree.ElementTree as ET
from io import BytesIO  # 이미지 처리를 위한 필수 모듈
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.image import MIMEImage
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
import google.generativeai as genai

# 1. 환경 변수 설정 (코랩 설정 혹은 서버 환경 변수에서 로드)
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
EMAIL_RECEIVER = os.environ.get("EMAIL_RECEIVER")

genai.configure(api_key=GEMINI_API_KEY)

# 2. 뉴스 수집
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
        print(f"뉴스 수집 실패: {e}")
        return "오늘의 주요 이슈 요약"

# 3. 텍스트 처리
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

def draw_text_outline(draw, position, text, font, text_color, outline_color, max_width):
    lines = wrap_text(text, font, max_width, draw)
    line_heights = [draw.textbbox((0, 0), line, font=font)[3] - draw.textbbox((0, 0), line, font=font)[1] for line in lines]
    current_y = position[1] - (sum(line_heights) + 20 * (len(lines) - 1)) // 2
    for line, h in zip(lines, line_heights):
        x, y = position[0], current_y + h // 2
        for dx in [-2, 0, 2]:
            for dy in [-2, 0, 2]:
                if dx != 0 or dy != 0:
                    draw.text((x + dx, y + dy), line, fill=outline_color, font=font, anchor="mm", align="center")
        draw.text((x, y), line, fill=text_color, font=font, anchor="mm", align="center")
        current_y += h + 20

# 4. 카드뉴스 제작
def create_card_news(user_topic):
    # 안정적인 모델로 지정
    model = genai.GenerativeModel('gemini-1.5-flash')
    prompt = f"주제: '{user_topic}'\n인스타그램 카드뉴스 5장 세트 기획을 작성해.\nslide_num, title, subtitle, description, keyword(영문1단어) 키를 가진 JSON 배열만 출력해."
    
    response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
    slides_data = json.loads(response.text)
    if isinstance(slides_data, dict) and "slides" in slides_data:
        slides_data = slides_data["slides"]

    font_path = "CustomFont.otf"
    if not os.path.exists(font_path):
        font_url = "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/Korean/NotoSansCJKkr-Bold.otf"
        with open(font_path, "wb") as f: f.write(requests.get(font_url).content)

    width, height = 1080, 1350
    title_font = ImageFont.truetype(font_path, 72)
    subtitle_font = ImageFont.truetype(font_path, 42)
    desc_font = ImageFont.truetype(font_path, 32)
    
    image_paths = []
    for idx, slide in enumerate(slides_data):
        keyword = slide.get("keyword", "news")
        img_url = f"https://loremflickr.com/1080/1350/{keyword}"
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            img_data = requests.get(img_url, headers=headers, timeout=10).content
            bg = Image.open(BytesIO(img_data))
        except:
            bg = Image.new("RGB", (width, height), color="#0F172A")
            
        bg_dark = ImageEnhance.Brightness(bg).enhance(0.2)
        draw = ImageDraw.Draw(bg_dark)
        
        draw.rectangle([60, 60, width - 60, height - 60], outline="#FFFFFF", width=3)
        draw.text((width - 120, 120), f"{idx+1} / 5", fill="#9CA3AF", font=desc_font, anchor="rt")
        
        title_color = "#FBBF24" if idx == 0 else "#FFFFFF"
        draw_text_outline(draw, (width // 2, height // 3), str(slide.get("title", "")), title_font, title_color, "#000000", width - 240)
        draw_text_outline(draw, (width // 2, height // 2 + 100), str(slide.get("subtitle", "")), subtitle_font, "#FFFFFF", "#000000", width - 240)
        draw_text_outline(draw, (width // 2, height - 180), str(slide.get("description", "")), desc_font, "#E5E7EB", "#000000", width - 240)
        
        filename = f"slide_{idx+1}.png"
        bg_dark.save(filename)
        image_paths.append(filename)
    
    return image_paths

# 5. 이메일 발송
def send_email(topic, image_paths):
    msg = MIMEMultipart()
    msg['From'] = EMAIL_SENDER
    msg['To'] = EMAIL_RECEIVER
    msg['Subject'] = f"📢 [자동 발송] AI 카드뉴스: {topic}"
    msg.attach(MIMEText(f"AI가 제작한 '{topic}' 카드뉴스입니다.", 'plain'))
    
    for path in image_paths:
        with open(path, 'rb') as f:
            msg.attach(MIMEImage(f.read(), name=os.path.basename(path)))
            
    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login(EMAIL_SENDER, EMAIL_PASSWORD)
    server.sendmail(EMAIL_SENDER, EMAIL_RECEIVER, msg.as_string())
    server.quit()
    print("📧 이메일 발송 완료!")

if __name__ == "__main__":
    today_topic = get_today_news_topic()
    print(f"주제: {today_topic}")
    images = create_card_news(today_topic)
    send_email(today_topic, images)
