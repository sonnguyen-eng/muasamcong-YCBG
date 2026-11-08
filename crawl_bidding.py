import os
import time
import smtplib
import requests
from datetime import datetime, timedelta
import zoneinfo
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from google import genai

# ================= 1. CẤU HÌNH CHÍNH XÁC DANH MỤC TỪ KHÓA =================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD")
RECEIVER_EMAIL = SENDER_EMAIL

# Danh sách từ khóa chuẩn của anh
KEYWORDS = [
    "nội soi", "nội soi tiêu hóa", "nội soi khí phế quản", 
    "Bàn mổ", "đèn mổ", "hệ thống khí y tế", "vận chuyển mẫu", "ERCP"
]

TZ_VN = zoneinfo.ZoneInfo("Asia/Ho_Chi_Minh")
NOW_VN = datetime.now(TZ_VN)
TODAY_STR = NOW_VN.strftime("%d/%m/%Y")

# Khung ngày truy vấn (lấy cả hôm nay và hôm qua để tránh trôi gói thầu)
DATE_FROM = (NOW_VN - timedelta(days=1)).strftime("%Y-%m-%d")
DATE_TO = NOW_VN.strftime("%Y-%m-%d")


# ================= 2. TRUY VẤN CHÍNH XÁC THEO TỪ KHÓA =================
def fetch_ycbg_by_keyword(kw):
    """Truy vấn YCBG theo từ khóa chính xác trên API Smart Search"""
    url = "https://muasamcong.mof.gov.vn/o/egp-portal-contractor-selection-v2/services/smart/search"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    results = []
    for page in range(3): # Quét 3 trang đầu cho mỗi từ khóa
        payload = {
            "page": page,
            "size": 50,
            "type": "YCBG",
            "keySearch": kw,
            "publishDateFrom": f"{DATE_FROM}T00:00:00Z",
            "publishDateTo": f"{DATE_TO}T23:59:59Z"
        }
        try:
            res = requests.post(url, json=payload, headers=headers, timeout=30)
            if res.status_code == 200:
                data = res.json().get("result", {}).get("data", [])
                if not data:
                    break
                results.extend(data)
            time.sleep(0.3)
        except Exception as e:
            print(f"[Lỗi API YCBG] Từ khóa '{kw}', trang {page}: {e}")
            break

    return results

def fetch_tbmt_by_keyword(kw):
    """Truy vấn TBMT theo từ khóa chính xác"""
    url = "https://muasamcong.mof.gov.vn/o/egp-portal-contractor-selection-v2/services/popular-keyword/get-list"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    results = []
    for page in range(3):
        payload = {
            "page": page,
            "size": 50,
            "type": "TBMT",
            "keySearch": kw,
            "publishDateFrom": f"{DATE_FROM}T00:00:00Z",
            "publishDateTo": f"{DATE_TO}T23:59:59Z"
        }
        try:
            res = requests.post(url, json=payload, headers=headers, timeout=30)
            if res.status_code == 200:
                data = res.json().get("result", {}).get("data", [])
                if not data:
                    break
                results.extend(data)
            time.sleep(0.3)
        except Exception as e:
            print(f"[Lỗi API TBMT] Từ khóa '{kw}', trang {page}: {e}")
            break

    return results


# ================= 3. THU THẬP & KHỬ TRÙNG LẶP =================
def collect_all_data(keywords):
    unique_items = {}

    for kw in keywords:
        print(f"-> Đang quét từ khóa: '{kw}'...")
        
        # 1. Quét YCBG
        ycbg_items = fetch_ycbg_by_keyword(kw)
        for item in ycbg_items:
            code = item.get("notifyNo") or item.get("code") or item.get("id")
            if code and code not in unique_items:
                unique_items[code] = {"type": "YCBG", "data": item}
        
        # 2. Quét TBMT
        tbmt_items = fetch_tbmt_by_keyword(kw)
        for item in tbmt_items:
            code = item.get("bidNo") or item.get("notifyNo") or item.get("id")
            if code and code not in unique_items:
                unique_items[code] = {"type": "TBMT", "data": item}

    return list(unique_items.values())


# ================= 4. ĐỊNH DẠNG VỚI GEMINI =================
def analyze_with_gemini(items, keywords):
    if not items:
        return f"<p>Hệ thống đã quét từ 00:00 đến 23:59:59 ngày {TODAY_STR} và không ghi nhận Thông báo mời thầu hoặc Yêu cầu báo giá mới nào chứa các từ khóa {keywords}.</p>"

    client = genai.Client(api_key=GEMINI_API_KEY)
    
    prompt = f"""
    Bạn là Trợ lý CNTT & Chuyên gia Phân tích Đấu thầu.
    Dưới đây là danh sách toàn bộ các Yêu cầu báo giá (YCBG) và Thông báo mời thầu (TBMT) vừa tìm thấy trên muasamcong.mof.gov.vn khớp với danh mục từ khóa {keywords}:
    {items}

    NHIỆM VỤ:
    1. Trình bày toàn bộ danh sách gói thầu/YCBG thành BẢNG HTML đẹp mắt để gửi Email.
    2. Các cột trong bảng gồm:
       - Loại (YCBG hoặc TBMT)
       - Mã số (Ví dụ: RQ2600095388-00)
       - Tên gói thầu / Yêu cầu báo giá
       - Chủ đầu tư / Bên mời chào giá
       - Ngày đăng tải
       - Link xem chi tiết trực tiếp:
         + Nếu là YCBG: `<a href="https://muasamcong.mof.gov.vn/web/guest/contractor-selection?type=es-ycbg&stepCode=request-quote-step-1&notifyNo=[MÃ_SỐ]">Xem chi tiết</a>`
         + Nếu là TBMT: `<a href="https://muasamcong.mof.gov.vn/vi/web/guest/initiator?tbmtNo=[MÃ_SỐ]">Xem chi tiết</a>`
    """

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )
    return response.text


# ================= 5. GỬI EMAIL & MAIN =================
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
        print(f"[{TODAY_STR}] -> Đã gửi email báo cáo thành công!")
    except Exception as e:
        print(f"[Lỗi gửi email] {e}")

if __name__ == "__main__":
    print(f"=== BẮT ĐẦU QUÉT THẦU THIẾT BỊ Y TẾ - NGÀY {TODAY_STR} ===")
    
    matched_items = collect_all_data(KEYWORDS)
    print(f"-> Tổng số thông báo tìm thấy: {len(matched_items)} gói.")
    
    print("-> Đang tổng hợp báo cáo qua Gemini...")
    email_body = analyze_with_gemini(matched_items, KEYWORDS)
    
    subject = f"[TBMT & YCBG Y TẾ] Báo cáo ngày {TODAY_STR}"
    send_email(subject, email_body)
    print("=== HOÀN THÀNH ===")
