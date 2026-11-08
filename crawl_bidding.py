import os
import time
import smtplib
import requests
from datetime import datetime
import zoneinfo
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from google import genai

# ================= 1. CẤU HÌNH BIẾN & DANH MỤC TỪ KHÓA =================
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


# ================= 2. QUÉT TRUY VẤN DỮ LIỆU TỪ MUA SẮM CÔNG =================
def fetch_portal_data(search_type):
    """
    Lấy danh sách dữ liệu mới nhất từ Mua Sắm Công (dành cho cả YCBG và TBMT)
    """
    url = "https://muasamcong.mof.gov.vn/o/egp-portal-contractor-selection-v2/services/smart/search"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*"
    }
    
    all_data = []
    # Duyệt 6 trang đầu tiên (300 thông báo gần nhất)
    for page in range(6):
        payload = {
            "page": page,
            "size": 50,
            "type": search_type,
            "keySearch": "" # Không chặn từ khóa ở server để lấy toàn bộ dữ liệu thô
        }
        try:
            res = requests.post(url, json=payload, headers=headers, timeout=30)
            if res.status_code == 200:
                items = res.json().get("result", {}).get("data", [])
                if not items:
                    break
                all_data.extend(items)
            time.sleep(0.3)
        except Exception as e:
            print(f"[LỖI API] Loại {search_type}, Trang {page}: {e}")
            break

    return all_data


# ================= 3. BỘ LỌC TỪ KHÓA BẰNG PYTHON (BẮT 100% TỪ KHÓA) =================
def filter_items_by_keywords(items, keywords, item_type):
    matched_results = []
    
    for item in items:
        # Gom toàn bộ nội dung chữ của thông báo (Tiêu đề, Mã, Tên bên mời thầu)
        code = str(item.get("notifyNo") or item.get("bidNo") or item.get("code") or item.get("id") or "")
        title = str(item.get("bidName") or item.get("name") or item.get("title") or "")
        investor = str(item.get("procuringEntityName") or item.get("investorName") or "")
        
        full_text = f"{code} {title} {investor}".lower()
        
        # Kiểm tra xem có chứa bất kỳ từ khóa nào trong danh sách không
        for kw in keywords:
            if kw.lower() in full_text:
                matched_results.append({
                    "type": item_type,
                    "code": code,
                    "title": title,
                    "investor": investor,
                    "matched_kw": kw,
                    "raw": item
                })
                break # Đã khớp 1 từ khóa thì chuyển sang gói tiếp theo (tránh lặp)
                
    return matched_results


# ================= 4. GEMINI ĐỊNH DẠNG BÁO CÁO EMAIL =================
def generate_email_with_gemini(matched_items, keywords):
    if not matched_items:
        return f"""
        <div style="font-family: Arial, sans-serif; padding: 20px;">
            <h3 style="color: #d9534f;">BÁO CÁO QUÉT THẦU NGÀY {TODAY_STR}</h3>
            <p>Hệ thống đã kết nối máy chủ Mua Sắm Công nhưng không tìm thấy thông báo thầu/YCBG nào khớp từ khóa: <b>{', '.join(keywords)}</b>.</p>
        </div>
        """

    client = genai.Client(api_key=GEMINI_API_KEY)
    
    prompt = f"""
    Bạn là Trợ lý CNTT. Dưới đây là danh sách các Yêu cầu báo giá (YCBG) và Thông báo mời thầu (TBMT) đã được lọc khớp chính xác từ khóa {keywords} trên muasamcong.mof.gov.vn trong ngày {TODAY_STR}:
    {matched_items}

    NHIỆM VỤ:
    1. Trình bày danh sách trên dưới dạng BẢNG HTML chuyên nghiệp gửi email.
    2. Các cột thông tin trong bảng bao gồm:
       - Phân loại (TBMT hoặc YCBG)
       - Mã số gói thầu / YCBG (Ví dụ: RQ2600095388-00)
       - Tên gói thầu / Yêu cầu báo giá
       - Chủ đầu tư / Bên mời chào giá
       - Từ khóa phát hiện
       - Đường dẫn xem chi tiết:
         + Nếu là YCBG: `<a href="https://muasamcong.mof.gov.vn/web/guest/contractor-selection?type=es-ycbg&stepCode=request-quote-step-1&notifyNo=[MÃ_SỐ]">Xem chi tiết</a>`
         + Nếu là TBMT: `<a href="https://muasamcong.mof.gov.vn/vi/web/guest/initiator?tbmtNo=[MÃ_SỐ]">Xem chi tiết</a>`
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
        print(f"[GỬI EMAIL] Thành công gửi báo cáo tới {RECEIVER_EMAIL}!")
    except Exception as e:
        print(f"[LỖI GỬI EMAIL] {e}")


# ================= 6. CHƯƠNG TRÌNH CHÍNH =================
if __name__ == "__main__":
    print(f"==================================================")
    print(f"   BẮT ĐẦU QUÉT DỮ LIỆU MUA SẮM CÔNG - NGÀY {TODAY_STR}")
    print(f"==================================================")
    
    # 1. Thu thập YCBG thô
    print("[1/4] Đang thu thập danh sách YCBG thô từ server...")
    raw_ycbg = fetch_portal_data("YCBG")
    print(f"      -> Thu thập được: {len(raw_ycbg)} YCBG.")
    
    # 2. Thu thập TBMT thô
    print("[2/4] Đang thu thập danh sách TBMT thô từ server...")
    raw_tbmt = fetch_portal_data("TBMT")
    print(f"      -> Thu thập được: {len(raw_tbmt)} TBMT.")
    
    # 3. Lọc tại chỗ bằng Python
    print("[3/4] Đang đối soát từ khóa bằng Python...")
    matched_ycbg = filter_items_by_keywords(raw_ycbg, KEYWORDS, "YCBG")
    matched_tbmt = filter_items_by_keywords(raw_tbmt, KEYWORDS, "TBMT")
    
    all_matched = matched_ycbg + matched_tbmt
    print(f"      -> TỔNG SỐ GÓI KHỚP TỪ KHÓA: {len(all_matched)} gói.")
    for m in all_matched:
        print(f"         + [{m['type']}] {m['code']} - {m['title']} (Khớp: '{m['matched_kw']}')")

    # 4. Tạo báo cáo & Gửi Email
    print("[4/4] Đang tổng hợp báo cáo và gửi Email...")
    email_body = generate_email_with_gemini(all_matched, KEYWORDS)
    
    subject = f"[TBMT & YCBG Y TẾ] Báo cáo ngày {TODAY_STR}"
    send_email(subject, email_body)
    
    print(f"==================================================")
    print(f"   HOÀN THÀNH TIẾN TRÌNH QUÉT THẦU TỰ ĐỘNG")
    print(f"==================================================")
