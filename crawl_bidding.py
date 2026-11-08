import os
import time
import smtplib
import requests
from datetime import datetime
import zoneinfo
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from google import genai

# ================= 1. CẤU HÌNH BIẾN & TỪ KHÓA =================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD")
RECEIVER_EMAIL = SENDER_EMAIL

# DANH SÁCH TỪ KHÓA TÌM KIẾM (ĐÃ BỎ "ỐNG SOI")
KEYWORDS = [
    "nội soi", "nội soi tiêu hóa", "nội soi khí phế quản", "Bàn mổ", 
    "đèn mổ", "hệ thống khí y tế", "vận chuyển mẫu", "ERCP"
]

TZ_VN = zoneinfo.ZoneInfo("Asia/Ho_Chi_Minh")
NOW_VN = datetime.now(TZ_VN)
TODAY_STR = NOW_VN.strftime("%d/%m/%Y")


# ================= 2. QUÉT DIỆN RỘNG TẤT CẢ GÓI TRONG NGÀY =================
def fetch_all_ycbg_today():
    """Lấy danh sách YCBG đăng tải gần nhất"""
    url = "https://muasamcong.mof.gov.vn/o/egp-portal-contractor-selection-v2/services/smart/search"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    all_items = []
    # Duyệt 5 trang đầu tiên (250 gói mới nhất)
    for page in range(5):
        payload = {
            "page": page,
            "size": 50,
            "type": "YCBG",
            "keySearch": ""
        }
        try:
            res = requests.post(url, json=payload, headers=headers, timeout=30)
            if res.status_code == 200:
                data = res.json().get("result", {}).get("data", [])
                if not data:
                    break
                all_items.extend(data)
            time.sleep(0.3)
        except Exception as e:
            print(f"[Lỗi API YCBG] Trang {page}: {e}")
            break

    return all_items

def fetch_all_tbmt_today():
    """Lấy danh sách TBMT đăng tải gần nhất"""
    url = "https://muasamcong.mof.gov.vn/o/egp-portal-contractor-selection-v2/services/popular-keyword/get-list"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    all_items = []
    for page in range(5):
        payload = {
            "page": page,
            "size": 50,
            "type": "TBMT",
            "keySearch": ""
        }
        try:
            res = requests.post(url, json=payload, headers=headers, timeout=30)
            if res.status_code == 200:
                data = res.json().get("result", {}).get("data", [])
                if not data:
                    break
                all_items.extend(data)
            time.sleep(0.3)
        except Exception as e:
            print(f"[Lỗi API TBMT] Trang {page}: {e}")
            break

    return all_items


# ================= 3. BỘ LỌC TỰ ĐỘNG BẰNG PYTHON =================
def filter_matching_items(ycbg_list, tbmt_list, keywords):
    matched_results = []
    seen_codes = set()

    def is_keyword_in_text(text, kw_list):
        if not text:
            return False
        text_lower = str(text).lower()
        return any(kw.lower() in text_lower for kw in kw_list)

    # 1. Lọc YCBG
    for item in ycbg_list:
        code = item.get("notifyNo") or item.get("code") or item.get("id")
        title = item.get("bidName") or item.get("name") or item.get("title") or ""
        investor = item.get("procuringEntityName") or item.get("investorName") or ""
        
        full_text = f"{code} {title} {investor}"
        
        if is_keyword_in_text(full_text, keywords):
            if code not in seen_codes:
                seen_codes.add(code)
                matched_results.append({"type": "YCBG", "data": item})

    # 2. Lọc TBMT
    for item in tbmt_list:
        code = item.get("bidNo") or item.get("notifyNo") or item.get("id")
        title = item.get("bidName") or item.get("name") or item.get("title") or ""
        investor = item.get("procuringEntityName") or item.get("investorName") or ""
        
        full_text = f"{code} {title} {investor}"
        
        if is_keyword_in_text(full_text, keywords):
            if code not in seen_codes:
                seen_codes.add(code)
                matched_results.append({"type": "TBMT", "data": item})

    return matched_results


# ================= 4. PHÂN TÍCH & ĐỊNH DẠNG VỚI GEMINI =================
def analyze_with_gemini(matched_items, keywords):
    if not matched_items:
        return f"<p>Hệ thống đã quét trong ngày {TODAY_STR} và không ghi nhận Thông báo mời thầu hoặc Yêu cầu báo giá mới nào chứa từ khóa {keywords}.</p>"

    client = genai.Client(api_key=GEMINI_API_KEY)
    
    prompt = f"""
    Bạn là Trợ lý CNTT & Chuyên gia Phân tích Đấu thầu.
    Dưới đây là danh sách các Yêu cầu báo giá (YCBG) và Thông báo mời thầu (TBMT) đã được lọc khớp từ khóa {keywords} trong ngày {TODAY_STR}:
    {matched_items}

    NHIỆM VỤ:
    1. Trình bày toàn bộ danh sách gói thầu/YCBG trên thành BẢNG HTML đẹp mắt để gửi Email.
    2. Các cột trong bảng gồm:
       - Loại (YCBG hoặc TBMT)
       - Mã số (Ví dụ: RQ2600095388-00)
       - Tên gói thầu / Yêu cầu báo giá
       - Chủ đầu tư / Bên mời chào giá
       - Ngày đăng tải
       - Link xem chi tiết trực tiếp:
         + Đối với YCBG: `<a href="https://muasamcong.mof.gov.vn/web/guest/contractor-selection?type=es-ycbg&stepCode=request-quote-step-1&notifyNo=[MÃ_SỐ]">Xem chi tiết</a>`
         + Đối với TBMT: `<a href="https://muasamcong.mof.gov.vn/vi/web/guest/initiator?tbmtNo=[MÃ_SỐ]">Xem chi tiết</a>`
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
        print(f"[{TODAY_STR}] -> Đã gửi thành công email báo cáo!")
    except Exception as e:
        print(f"[Lỗi gửi email] {e}")

if __name__ == "__main__":
    print(f"=== BẮT ĐẦU TÌM KIẾM DỮ LIỆU THẦU Y TẾ NGÀY {TODAY_STR} ===")
    
    print("-> Đang lấy danh sách YCBG thô...")
    raw_ycbg = fetch_all_ycbg_today()
    print(f"   + Lấy được {len(raw_ycbg)} YCBG.")
    
    print("-> Đang lấy danh sách TBMT thô...")
    raw_tbmt = fetch_all_tbmt_today()
    print(f"   + Lấy được {len(raw_tbmt)} TBMT.")
    
    print("-> Đang tiến hành lọc tại chỗ theo từ khóa...")
    matched = filter_matching_items(raw_ycbg, raw_tbmt, KEYWORDS)
    print(f"   + Phát hiện {len(matched)} gói khớp từ khóa.")
    
    print("-> Đang định dạng báo cáo với Gemini...")
    email_body = analyze_with_gemini(matched, KEYWORDS)
    
    subject = f"[TBMT & YCBG Y TẾ] Báo cáo ngày {TODAY_STR}"
    send_email(subject, email_body)
    print("=== HOÀN THÀNH ===")
