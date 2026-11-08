import os
import time
import smtplib
import requests
from datetime import datetime, timedelta
import zoneinfo
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from google import genai

# ================= 1. CẤU HÌNH BIẾN BẢO MẬT & DANH MỤC =================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD")
RECEIVER_EMAIL = SENDER_EMAIL

# BỔ SUNG ĐẦY ĐỦ TỪ KHÓA BẮT CÁC GÓI ỐNG SOI, OPTIC, NỘI SOI
KEYWORDS = [
    "nội soi", "nội soi tiêu hóa", "nội soi khí phế quản", "Bàn mổ", 
    "đèn mổ", "hệ thống khí y tế", "vận chuyển mẫu", "ERCP"
]

TZ_VN = zoneinfo.ZoneInfo("Asia/Ho_Chi_Minh")
NOW_VN = datetime.now(TZ_VN)

# Lấy từ ngày hôm qua đến hôm nay (định dạng YYYY-MM-DD chuẩn cho API Mua Sắm Công)
FROM_DATE_STR = (NOW_VN - timedelta(days=1)).strftime("%Y-%m-%d")
TO_DATE_STR = NOW_VN.strftime("%Y-%m-%d")
TODAY_STR = NOW_VN.strftime("%d/%m/%Y")


# ================= 2. THU THẬP DỮ LIỆU CHÍNH XÁC =================
def fetch_ycbg_by_keywords(keywords):
    url = "https://muasamcong.mof.gov.vn/o/egp-portal-contractor-selection-v2/services/smart/search"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    unique_items = {}

    for kw in keywords:
        for page in range(3):
            payload = {
                "page": page,
                "size": 50,
                "type": "YCBG",
                "keySearch": kw,
                "publishDateFrom": f"{FROM_DATE_STR} 00:00:00",
                "publishDateTo": f"{TO_DATE_STR} 23:59:59"
            }
            try:
                res = requests.post(url, json=payload, headers=headers, timeout=30)
                if res.status_code == 200:
                    data = res.json().get("result", {}).get("data", [])
                    if not data:
                        break
                    for item in data:
                        code = item.get("notifyNo") or item.get("code") or item.get("id")
                        if code and code not in unique_items:
                            unique_items[code] = item
                time.sleep(0.3)
            except Exception as e:
                print(f"[Lỗi YCBG] Từ khóa '{kw}', trang {page}: {e}")
                break

    return list(unique_items.values())

def fetch_tbmt_by_keywords(keywords):
    url = "https://muasamcong.mof.gov.vn/o/egp-portal-contractor-selection-v2/services/popular-keyword/get-list"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    unique_items = {}

    for kw in keywords:
        for page in range(3):
            payload = {
                "page": page,
                "size": 50,
                "type": "TBMT",
                "keySearch": kw,
                "publishDateFrom": f"{FROM_DATE_STR} 00:00:00",
                "publishDateTo": f"{TO_DATE_STR} 23:59:59"
            }
            try:
                res = requests.post(url, json=payload, headers=headers, timeout=30)
                if res.status_code == 200:
                    data = res.json().get("result", {}).get("data", [])
                    if not data:
                        break
                    for item in data:
                        code = item.get("bidNo") or item.get("notifyNo") or item.get("id")
                        if code and code not in unique_items:
                            unique_items[code] = item
                time.sleep(0.3)
            except Exception as e:
                print(f"[Lỗi TBMT] Từ khóa '{kw}', trang {page}: {e}")
                break

    return list(unique_items.values())


# ================= 3. ĐỊNH DẠNG VỚI GEMINI =================
def analyze_data_with_gemini(ycbg_data, tbmt_data, keywords):
    total_count = len(ycbg_data) + len(tbmt_data)
    if total_count == 0:
        return f"<p>Hệ thống đã quét từ 00:00 đến 23:59:59 ngày {TODAY_STR} và không ghi nhận Thông báo mời thầu hoặc Yêu cầu báo giá mới nào chứa từ khóa {keywords}.</p>"

    client = genai.Client(api_key=GEMINI_API_KEY)
    
    prompt = f"""
    Bạn là một Trợ lý CNTT & Chuyên gia Phân tích Đấu thầu.
    Dưới đây là dữ liệu Thông báo mời thầu (TBMT) và Yêu cầu báo giá (YCBG) thu thập được từ muasamcong.mof.gov.vn ngày {TODAY_STR}:

    === DANH SÁCH YÊU CẦU BÁO GIÁ (YCBG) ===
    {ycbg_data}

    === DANH SÁCH THÔNG BÁO MỜI THẦU (TBMT) ===
    {tbmt_data}

    NHIỆM VỤ:
    1. Trình bày toàn bộ danh sách gói thầu/YCBG trên thành BẢNG HTML đẹp mắt để gửi Email.
    2. Các cột trong bảng gồm:
       - Loại (YCBG hoặc TBMT)
       - Mã YCBG / Mã TBMT (Ví dụ: RQ2600095386-00, RQ2600095388-00)
       - Tên gói thầu / Yêu cầu báo giá
       - Chủ đầu tư / Bên mời chào giá
       - Ngày đăng tải
       - Link xem chi tiết trực tiếp:
         + Đối với YCBG: `<a href="https://muasamcong.mof.gov.vn/web/guest/contractor-selection?type=es-ycbg&stepCode=request-quote-step-1&notifyNo=[MÃ_RQ]">Xem chi tiết</a>`
         + Đối với TBMT: `<a href="https://muasamcong.mof.gov.vn/vi/web/guest/initiator?tbmtNo=[MÃ_TBMT]">Xem chi tiết</a>`
    """

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )
    return response.text


# ================= 4. GỬI EMAIL THÔNG BÁO =================
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


# ================= 5. LUỒNG CHẠY CHÍNH =================
if __name__ == "__main__":
    print(f"=== BẮT ĐẦU QUÉT THẦU THIẾT BỊ Y TẾ NGÀY {TODAY_STR} ===")
    
    print("-> Đang quét Yêu cầu báo giá (YCBG)...")
    ycbg_items = fetch_ycbg_by_keywords(KEYWORDS)
    print(f"   + Tìm thấy {len(ycbg_items)} YCBG phù hợp.")
    
    print("-> Đang quét Thông báo mời thầu (TBMT)...")
    tbmt_items = fetch_tbmt_by_keywords(KEYWORDS)
    print(f"   + Tìm thấy {len(tbmt_items)} TBMT phù hợp.")
    
    print("-> Đang tổng hợp báo cáo bằng Gemini...")
    email_body = analyze_data_with_gemini(ycbg_items, tbmt_items, KEYWORDS)
    
    subject = f"[TBMT & YCBG Y TẾ] Báo cáo ngày {TODAY_STR}"
    send_email(subject, email_body)
    print("=== HOÀN THÀNH ===")
