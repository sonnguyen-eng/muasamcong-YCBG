import os
import time
import smtplib
import requests
from datetime import datetime
import zoneinfo
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from google import genai

# ================= CẤU HÌNH BIẾN & TỪ KHÓA =================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD")
RECEIVER_EMAIL = SENDER_EMAIL

KEYWORDS = [
    "nội soi", "nội soi tiêu hóa", "nội soi khí phế quản", "Bàn mổ", 
    "đèn mổ", "hệ thống khí y tế", "vận chuyển mẫu", "ERCP"
]

TZ_VN = zoneinfo.ZoneInfo("Asia/Ho_Chi_Minh")
NOW_VN = datetime.now(TZ_VN)
TODAY_STR = NOW_VN.strftime("%d/%m/%Y") # Định dạng DD/MM/YYYY để so sánh
TODAY_ISO = NOW_VN.strftime("%Y-%m-%d")

def fetch_ycbg_data(keyword):
    """Gọi API Smart Search với từ khóa cụ thể"""
    url = "https://muasamcong.mof.gov.vn/o/egp-portal-contractor-selection-v2/services/smart/search"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*"
    }
    
    payload = {
        "page": 0,
        "size": 100,
        "type": "YCBG",
        "keySearch": keyword
    }

    try:
        res = requests.post(url, json=payload, headers=headers, timeout=30)
        if res.status_code == 200:
            return res.json().get("result", {}).get("data", [])
    except Exception as e:
        print(f"[Lỗi API YCBG] Từ khóa '{keyword}': {e}")
    return []

def fetch_tbmt_data(keyword):
    """Gọi API Popular Keyword cho TBMT"""
    url = "https://muasamcong.mof.gov.vn/o/egp-portal-contractor-selection-v2/services/popular-keyword/get-list"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    payload = {
        "page": 0,
        "size": 100,
        "type": "TBMT",
        "keySearch": keyword
    }

    try:
        res = requests.post(url, json=payload, headers=headers, timeout=30)
        if res.status_code == 200:
            return res.json().get("result", {}).get("data", [])
    except Exception as e:
        print(f"[Lỗi API TBMT] Từ khóa '{keyword}': {e}")
    return []

def collect_and_filter_today():
    all_matched_items = {}

    for kw in KEYWORDS:
        print(f"-> Đang truy vấn từ khóa: '{kw}'...")
        # 1. Quét YCBG
        ycbg_list = fetch_ycbg_data(kw)
        for item in ycbg_list:
            # Lấy ngày đăng tải từ dữ liệu trả về (hỗ trợ cả dạng string và timestamp)
            pub_date = str(item.get("createDate") or item.get("publishDate") or item.get("publicDate") or "")
            code = item.get("notifyNo") or item.get("code") or item.get("id")
            
            # Lọc các gói đăng trong ngày hôm nay hoặc chưa lọc ngày cứng ở API để không sót
            if code and code not in all_matched_items:
                all_matched_items[code] = {
                    "type": "YCBG",
                    "data": item
                }
        
        # 2. Quét TBMT
        tbmt_list = fetch_tbmt_data(kw)
        for item in tbmt_list:
            code = item.get("bidNo") or item.get("notifyNo") or item.get("id")
            if code and code not in all_matched_items:
                all_matched_items[code] = {
                    "type": "TBMT",
                    "data": item
                }
                
        time.sleep(0.3)

    return list(all_matched_items.values())

def analyze_with_gemini(items, keywords):
    if not items:
        return f"<p>Hệ thống đã quét trong ngày {TODAY_STR} và không ghi nhận Thông báo mời thầu hoặc Yêu cầu báo giá mới nào chứa các từ khóa {keywords}.</p>"

    client = genai.Client(api_key=GEMINI_API_KEY)
    
    prompt = f"""
    Bạn là Trợ lý CNTT & Chuyên gia Phân tích Đấu thầu.
    Dưới đây là danh sách toàn bộ các Yêu cầu báo giá (YCBG) và Thông báo mời thầu (TBMT) vừa thu thập từ muasamcong.mof.gov.vn:
    {items}

    NHIỆM VỤ:
    1. Kiểm tra kỹ dữ liệu và LỌC RA các thông báo đăng tải trong ngày hôm nay ({TODAY_STR} hoặc {TODAY_ISO}) có chứa từ khóa: {keywords}.
    2. Trình bày kết quả thành BẢNG HTML đẹp mắt để gửi Email gồm các cột:
       - Loại (YCBG hoặc TBMT)
       - Mã số (Ví dụ: RQ2600095388-00)
       - Tên gói thầu / Yêu cầu báo giá
       - Bên mời chào giá / Chủ đầu tư
       - Ngày đăng tải
       - Link xem chi tiết:
         + Nếu là YCBG: `<a href="https://muasamcong.mof.gov.vn/web/guest/contractor-selection?type=es-ycbg&stepCode=request-quote-step-1&notifyNo=[MÃ_SỐ]">Xem chi tiết</a>`
         + Nếu là TBMT: `<a href="https://muasamcong.mof.gov.vn/vi/web/guest/initiator?tbmtNo=[MÃ_SỐ]">Xem chi tiết</a>`
    """

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )
    return response.text

def send_email(subject, html_content):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL
    msg.attach(MIMEText(html_content, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        print(f"[{TODAY_STR}] -> Đã gửi thành công email báo cáo!")
    except Exception as e:
        print(f"[Lỗi gửi email] {e}")

if __name__ == "__main__":
    print(f"=== BẮT ĐẦU QUÉT THẦU VỚI BỘ LỌC CHUẨN XÁC - NGÀY {TODAY_STR} ===")
    matched_items = collect_and_filter_today()
    print(f"-> Thu thập được tổng cộng {len(matched_items)} bản ghi liên quan từ API.")
    
    print("-> Đang đưa dữ liệu cho Gemini phân tích & tổng hợp...")
    email_body = analyze_with_gemini(matched_items, KEYWORDS)
    
    subject = f"[TBMT & YCBG Y TẾ] Báo cáo ngày {TODAY_STR}"
    send_email(subject, email_body)
    print("=== HOÀN THÀNH ===")
