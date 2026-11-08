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


# ================= 2. QUÉT TRỰC TIẾP API MUA SẮM CÔNG V2 =================
def fetch_bidding_api(search_type, keyword):
    """
    Hàm kết nối API Mua Sắm Công với Header giả lập và Mã hóa UTF-8 chuẩn
    """
    if search_type == "YCBG":
        url = "https://muasamcong.mof.gov.vn/o/egp-portal-contractor-selection-v2/services/smart/search"
    else:
        url = "https://muasamcong.mof.gov.vn/o/egp-portal-contractor-selection-v2/services/popular-keyword/get-list"

    headers = {
        "Host": "muasamcong.mof.gov.vn",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
        "Content-Type": "application/json;charset=UTF-8",
        "Origin": "https://muasamcong.mof.gov.vn",
        "Referer": "https://muasamcong.mof.gov.vn/web/guest/contractor-selection",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }

    all_items = []
    for page in range(3):
        payload = {
            "page": page,
            "size": 50,
            "type": search_type,
            "keySearch": str(keyword).strip()
        }
        try:
            res = requests.post(url, json=payload, headers=headers, timeout=30)
            if res.status_code == 200:
                res_json = res.json()
                items = []
                if isinstance(res_json.get("result"), dict):
                    items = res_json.get("result", {}).get("data", [])
                elif isinstance(res_json.get("result"), list):
                    items = res_json.get("result", [])
                
                if not items:
                    break
                all_items.extend(items)
            time.sleep(0.3)
        except Exception as e:
            print(f"[LỖI API] Loại {search_type} | Từ khóa '{keyword}' | Trang {page}: {e}")
            break

    return all_items


# ================= 3. THU THẬP & ĐỐI SOÁT TỪ KHÓA =================
def run_crawler():
    unique_matches = {}

    for kw in KEYWORDS:
        print(f"--> Đang gửi Request API tìm từ khóa: '{kw}'...")
        
        # 1. Quét YCBG
        ycbg_list = fetch_bidding_api("YCBG", kw)
        print(f"    + YCBG tìm thấy: {len(ycbg_list)} bản ghi.")
        for item in ycbg_list:
            code = item.get("notifyNo") or item.get("code") or item.get("id")
            if code and code not in unique_matches:
                unique_matches[code] = {
                    "type": "YCBG",
                    "code": code,
                    "title": item.get("bidName") or item.get("name") or item.get("title") or "",
                    "investor": item.get("procuringEntityName") or item.get("investorName") or "",
                    "matched_kw": kw,
                    "raw": item
                }

        # 2. Quét TBMT
        tbmt_list = fetch_bidding_api("TBMT", kw)
        print(f"    + TBMT tìm thấy: {len(tbmt_list)} bản ghi.")
        for item in tbmt_list:
            code = item.get("bidNo") or item.get("notifyNo") or item.get("id")
            if code and code not in unique_matches:
                unique_matches[code] = {
                    "type": "TBMT",
                    "code": code,
                    "title": item.get("bidName") or item.get("name") or item.get("title") or "",
                    "investor": item.get("procuringEntityName") or item.get("investorName") or "",
                    "matched_kw": kw,
                    "raw": item
                }
                
        time.sleep(0.3)

    return list(unique_matches.values())


# ================= 4. GEMINI TỔNG HỢP NỘI DUNG EMAIL =================
def generate_email_with_gemini(matched_items):
    if not matched_items:
        return f"""
        <div style="font-family: Arial, sans-serif; padding: 20px; line-height: 1.6;">
            <h3 style="color: #d9534f;">BÁO CÁO QUÉT THẦU TỰ ĐỘNG - NGÀY {TODAY_STR}</h3>
            <p>Hệ thống đã truy vấn máy chủ Mua Sắm Công nhưng không phát hiện thông báo thầu/YCBG nào mới chứa từ khóa theo dõi.</p>
        </div>
        """

    client = genai.Client(api_key=GEMINI_API_KEY)
    
    prompt = f"""
    Bạn là Trợ lý CNTT chuyên nghiệp. Dưới đây là danh sách các Yêu cầu báo giá (YCBG) và Thông báo mời thầu (TBMT) thu thập được từ muasamcong.mof.gov.vn trong ngày {TODAY_STR}:
    {matched_items}

    NHIỆM VỤ:
    1. Trình bày danh sách trên dưới dạng BẢNG HTML đẹp mắt gửi email.
    2. Các cột trong bảng gồm:
       - STT
       - Phân loại (TBMT hoặc YCBG)
       - Mã số gói thầu / YCBG (Ví dụ: RQ2600095388-00)
       - Tên gói thầu / Yêu cầu báo giá
       - Chủ đầu tư / Bên mời chào giá
       - Từ khóa phát hiện
       - Link xem chi tiết trực tiếp:
         + Đối với YCBG: `<a href="https://muasamcong.mof.gov.vn/web/guest/contractor-selection?type=es-ycbg&stepCode=request-quote-step-1&notifyNo=[MÃ_SỐ]">Xem chi tiết</a>`
         + Đối với TBMT: `<a href="https://muasamcong.mof.gov.vn/vi/web/guest/initiator?tbmtNo=[MÃ_SỐ]">Xem chi tiết</a>`
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
        print(f"[GỬI EMAIL] Đã gửi báo cáo thành công tới {RECEIVER_EMAIL}!")
    except Exception as e:
        print(f"[LỖI GỬI EMAIL] {e}")


# ================= 6. TIẾN TRÌNH CHÍNH =================
if __name__ == "__main__":
    print(f"==================================================")
    print(f"   BẮT ĐẦU CRAWL DỮ LIỆU THẦU DAILY - {TODAY_STR}")
    print(f"==================================================")
    
    results = run_crawler()
    print(f"--> [TỔNG KẾT] Phát hiện tổng cộng: {len(results)} gói thầu/YCBG khớp từ khóa.")
    
    print("--> Đang nhờ Gemini tổng hợp báo cáo Email...")
    email_body = generate_email_with_gemini(results)
    
    subject = f"[TBMT & YCBG Y TẾ] Báo cáo ngày {TODAY_STR}"
    send_email(subject, email_body)
    
    print(f"==================================================")
    print(f"   HOÀN THÀNH TIẾN TRÌNH QUÉT THẦU TỰ ĐỘNG")
    print(f"==================================================")
