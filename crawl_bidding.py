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

# Danh sách từ khóa chính xác của anh
KEYWORDS = [
    "nội soi", "nội soi tiêu hóa", "nội soi khí phế quản", 
    "Bàn mổ", "đèn mổ", "hệ thống khí y tế", "vận chuyển mẫu", "ERCP"
]

TZ_VN = zoneinfo.ZoneInfo("Asia/Ho_Chi_Minh")
NOW_VN = datetime.now(TZ_VN)
TODAY_STR = NOW_VN.strftime("%d/%m/%Y")


# ================= 2. GIẢ LẬP HEADER ĐỂ TRÁNH BỊ SERVER CHẶN =================
def get_browser_headers():
    return {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        "Content-Type": "application/json;charset=UTF-8",
        "Origin": "https://muasamcong.mof.gov.vn",
        "Referer": "https://muasamcong.mof.gov.vn/web/guest/contractor-selection",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }


# ================= 3. HÀM QUÉT DỮ LIỆU TỪ MUA SẮM CÔNG =================
def fetch_api_data(search_type, keyword=""):
    """
    Hàm gọi API thông minh có giả lập Trình duyệt để vượt rào cản Security
    """
    if search_type == "YCBG":
        url = "https://muasamcong.mof.gov.vn/o/egp-portal-contractor-selection-v2/services/smart/search"
    else:
        url = "https://muasamcong.mof.gov.vn/o/egp-portal-contractor-selection-v2/services/popular-keyword/get-list"

    headers = get_browser_headers()
    collected_items = []

    # Quét 4 trang đầu tiên cho từ khóa
    for page in range(4):
        payload = {
            "page": page,
            "size": 50,
            "type": search_type,
            "keySearch": keyword
        }
        
        try:
            res = requests.post(url, json=payload, headers=headers, timeout=30)
            if res.status_code == 200:
                result_json = res.json()
                
                # Trích xuất linh hoạt cấu trúc dữ liệu trả về từ server
                items = []
                if isinstance(result_json.get("result"), dict):
                    items = result_json.get("result", {}).get("data", [])
                elif isinstance(result_json.get("result"), list):
                    items = result_json.get("result", [])

                if not items:
                    break
                    
                collected_items.extend(items)
            else:
                print(f"[CẢNH BÁO] API {search_type} trả về HTTP Status: {res.status_code}")
                
            time.sleep(0.4)
        except Exception as e:
            print(f"[LỖI KẾT NỐI] {search_type} | Từ khóa '{keyword}' | Trang {page}: {e}")
            break

    return collected_items


# ================= 4. TỔNG HỢP VÀ ĐỐI SOÁT TỪ KHÓA =================
def run_bidding_crawler():
    unique_matches = {}

    for kw in KEYWORDS:
        print(f"--> Đang gửi Request tìm từ khóa: '{kw}'...")
        
        # 1. Quét YCBG
        ycbg_raw = fetch_api_data("YCBG", kw)
        print(f"    + YCBG nhận được: {len(ycbg_raw)} bản ghi từ máy chủ.")
        
        for item in ycbg_raw:
            code = item.get("notifyNo") or item.get("code") or item.get("id")
            title = item.get("bidName") or item.get("name") or item.get("title") or ""
            investor = item.get("procuringEntityName") or item.get("investorName") or ""
            
            if code and code not in unique_matches:
                unique_matches[code] = {
                    "type": "YCBG",
                    "code": code,
                    "title": title,
                    "investor": investor,
                    "matched_kw": kw,
                    "raw": item
                }

        # 2. Quét TBMT
        tbmt_raw = fetch_api_data("TBMT", kw)
        print(f"    + TBMT nhận được: {len(tbmt_raw)} bản ghi từ máy chủ.")
        
        for item in tbmt_raw:
            code = item.get("bidNo") or item.get("notifyNo") or item.get("id")
            title = item.get("bidName") or item.get("name") or item.get("title") or ""
            investor = item.get("procuringEntityName") or item.get("investorName") or ""
            
            if code and code not in unique_matches:
                unique_matches[code] = {
                    "type": "TBMT",
                    "code": code,
                    "title": title,
                    "investor": investor,
                    "matched_kw": kw,
                    "raw": item
                }

    return list(unique_matches.values())


# ================= 5. TẠO EMAIL BÁO CÁO VỚI GEMINI =================
def build_email_content(matched_items):
    if not matched_items:
        return f"""
        <div style="font-family: Arial, sans-serif; padding: 20px; line-height: 1.6;">
            <h3 style="color: #d9534f;">BÁO CÁO QUÉT THẦU TỰ ĐỘNG - NGÀY {TODAY_STR}</h3>
            <p>Hệ thống đã truy vấn thành công tới máy chủ Mua Sắm Công nhưng không ghi nhận thông báo thầu/YCBG mới nào chứa các từ khóa sau:</p>
            <ul>
                {"".join([f"<li><b>{kw}</b></li>" for kw in KEYWORDS])}
            </ul>
        </div>
        """

    client = genai.Client(api_key=GEMINI_API_KEY)
    
    prompt = f"""
    Bạn là Trợ lý CNTT. Dưới đây là danh sách các Yêu cầu báo giá (YCBG) và Thông báo mời thầu (TBMT) thu thập được từ muasamcong.mof.gov.vn ngày {TODAY_STR}:
    {matched_items}

    NHIỆM VỤ:
    1. Tạo một email báo cáo chuyên nghiệp có BẢNG HTML đẹp mắt.
    2. Các cột gồm:
       - STT
       - Phân loại (TBMT hoặc YCBG)
       - Mã số gói (Ví dụ: RQ2600095388-00)
       - Tên gói thầu / Yêu cầu báo giá
       - Chủ đầu tư / Bên mời chào giá
       - Từ khóa phát hiện
       - Link xem chi tiết:
         + YCBG: `<a href="https://muasamcong.mof.gov.vn/web/guest/contractor-selection?type=es-ycbg&stepCode=request-quote-step-1&notifyNo=[MÃ_SỐ]">Xem chi tiết</a>`
         + TBMT: `<a href="https://muasamcong.mof.gov.vn/vi/web/guest/initiator?tbmtNo=[MÃ_SỐ]">Xem chi tiết</a>`
    3. Thêm tổng số lượng thông báo tìm thấy ở đầu bảng.
    """

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )
    return response.text


# ================= 6. HÀM GỬI EMAIL SMTP =================
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
        print(f"[EMAIL] Đã gửi báo cáo thành công tới {RECEIVER_EMAIL}!")
    except Exception as e:
        print(f"[LỖI EMAIL] Không thể gửi email: {e}")


# ================= 7. TIẾN TRÌNH CHÍNH =================
if __name__ == "__main__":
    print(f"==================================================")
    print(f"   BẮT ĐẦU CRAWL DỮ LIỆU THẦU DAILY - {TODAY_STR}")
    print(f"==================================================")
    
    matched_data = run_bidding_crawler()
    print(f"--> [TỔNG KẾT] Phát hiện tổng cộng: {len(matched_data)} gói thầu/YCBG khớp từ khóa.")
    
    print("--> Đang tạo giao diện báo cáo Email...")
    html_report = build_email_content(matched_data)
    
    subject = f"[THÔNG BÁO THẦU] Báo cáo ngày {TODAY_STR}"
    send_email(subject, html_report)
    print(f"==================================================")
