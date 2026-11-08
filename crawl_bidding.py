import os
import time
import smtplib
import requests
from datetime import datetime
import zoneinfo
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from google import genai

# ================= 1. CẤU HÌNH HỆ THỐNG & TỪ KHÓA =================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD")
RECEIVER_EMAIL = SENDER_EMAIL

KEYWORDS = [
    "nội soi", "nội soi tiêu hóa", "nội soi khí phế quản", 
    "Bàn mổ", "đèn mổ", "hệ thống khí y tế", "vận chuyển mẫu", "ERCP"
]

TZ_VN = zoneinfo.ZoneInfo("Asia/Ho_Chi_Minh")
NOW_VN = datetime.now(TZ_VN)
TODAY_STR = NOW_VN.strftime("%d/%m/%Y")


# ================= 2. QUÉT TRỰC TIẾP API YCBG & TBMT =================
def fetch_ycbg_portal(keyword):
    """
    Truy vấn Yêu cầu báo giá từ API Mua Sắm Công theo chuẩn Payload mới nhất
    """
    url = "https://muasamcong.mof.gov.vn/o/egp-portal-contractor-selection-v2/services/smart/search"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*"
    }
    
    # Không chặn publishDate ở Payload API để tránh server Mua Sắm Công trả về rỗng []
    payload = {
        "page": 0,
        "size": 50,
        "type": "YCBG",
        "keySearch": keyword
    }

    try:
        res = requests.post(url, json=payload, headers=headers, timeout=30)
        if res.status_code == 200:
            return res.json().get("result", {}).get("data", [])
    except Exception as e:
        print(f"[ERROR YCBG] Lỗi kết nối khi tìm từ khóa '{keyword}': {e}")
    return []

def fetch_tbmt_portal(keyword):
    """
    Truy vấn Thông báo mời thầu từ API Popular Keyword
    """
    url = "https://muasamcong.mof.gov.vn/o/egp-portal-contractor-selection-v2/services/popular-keyword/get-list"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    payload = {
        "page": 0,
        "size": 50,
        "type": "TBMT",
        "keySearch": keyword
    }

    try:
        res = requests.post(url, json=payload, headers=headers, timeout=30)
        if res.status_code == 200:
            return res.json().get("result", {}).get("data", [])
    except Exception as e:
        print(f"[ERROR TBMT] Lỗi kết nối khi tìm từ khóa '{keyword}': {e}")
    return []


# ================= 3. THU THẬP & LỌC DỮ LIỆU TẠI CHỖ =================
def collect_all_bidding_data(keywords):
    unique_items = {}

    for kw in keywords:
        print(f"[DEBUG] -> Đang truy vấn từ khóa: '{kw}'...")
        
        # 1. Quét YCBG
        ycbg_items = fetch_ycbg_portal(kw)
        print(f"         + API YCBG trả về: {len(ycbg_items)} bản ghi.")
        for item in ycbg_items:
            code = item.get("notifyNo") or item.get("code") or item.get("id")
            if code and code not in unique_items:
                unique_items[code] = {"type": "YCBG", "data": item, "kw_match": kw}
        
        # 2. Quét TBMT
        tbmt_items = fetch_tbmt_portal(kw)
        print(f"         + API TBMT trả về: {len(tbmt_items)} bản ghi.")
        for item in tbmt_items:
            code = item.get("bidNo") or item.get("notifyNo") or item.get("id")
            if code and code not in unique_items:
                unique_items[code] = {"type": "TBMT", "data": item, "kw_match": kw}
                
        time.sleep(0.5)

    return list(unique_items.values())


# ================= 4. GEMINI TỔNG HỢP NỘI DUNG EMAIL =================
def generate_email_body_with_gemini(items, keywords):
    if not items:
        return f"""
        <div style="font-family: Arial, sans-serif; padding: 20px;">
            <h3 style="color: #d9534f;">BÁO CÁO QUÉT THẦU NGÀY {TODAY_STR}</h3>
            <p>Hệ thống đã kết nối máy chủ Mua Sắm Công nhưng không tìm thấy thông báo thầu/YCBG nào khớp từ khóa: <b>{', '.join(keywords)}</b>.</p>
        </div>
        """

    client = genai.Client(api_key=GEMINI_API_KEY)
    
    prompt = f"""
    Bạn là Trợ lý CNTT. Dưới đây là danh sách các Yêu cầu báo giá (YCBG) và Thông báo mời thầu (TBMT) thu thập được từ muasamcong.mof.gov.vn khớp với danh mục từ khóa {keywords}:
    {items}

    NHIỆM VỤ:
    1. Trình bày danh sách trên dưới dạng BẢNG HTML chuyên nghiệp để gửi email.
    2. Các cột thông tin trong bảng bao gồm:
       - Phân loại (TBMT hoặc YCBG)
       - Mã số gói thầu (Ví dụ: RQ2600095388-00)
       - Tên gói thầu / Yêu cầu báo giá
       - Chủ đầu tư / Bên mời chào giá
       - Ngày đăng tải
       - Đường dẫn xem chi tiết:
         + Nếu loại là YCBG: `<a href="https://muasamcong.mof.gov.vn/web/guest/contractor-selection?type=es-ycbg&stepCode=request-quote-step-1&notifyNo=[MÃ_SỐ]">Xem chi tiết</a>`
         + Nếu loại là TBMT: `<a href="https://muasamcong.mof.gov.vn/vi/web/guest/initiator?tbmtNo=[MÃ_SỐ]">Xem chi tiết</a>`
    3. Thêm phần thống kê tổng số lượng gói thầu tìm thấy ở đầu Email.
    """

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )
    return response.text


# ================= 5. GỬI EMAIL THÔNG BÁO =================
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
        print(f"[SUCCESS] Đã gửi email báo cáo thành công tới {RECEIVER_EMAIL}!")
    except Exception as e:
        print(f"[ERROR] Không thể gửi email: {e}")


# ================= 6. HÀM CHẠY CHÍNH =================
if __name__ == "__main__":
    print(f"==================================================")
    print(f"   BẮT ĐẦU TIẾN TRÌNH QUÉT THẦU NGÀY {TODAY_STR}")
    print(f"==================================================")
    
    results = collect_all_bidding_data(KEYWORDS)
    print(f"[SUMMARY] Tổng số gói thầu/YCBG thu thập được: {len(results)}")
    
    print("[INFO] Đang tổng hợp báo cáo bằng Gemini...")
    email_body = generate_email_body_with_gemini(results, KEYWORDS)
    
    subject = f"[TBMT & YCBG Y TẾ] Báo cáo danh mục ngày {TODAY_STR}"
    send_email(subject, email_body)
    print(f"==================================================")
