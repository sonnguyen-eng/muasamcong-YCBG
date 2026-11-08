import os
import time
import smtplib
import requests
from datetime import datetime, timedelta
import zoneinfo
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from google import genai

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD")
RECEIVER_EMAIL = SENDER_EMAIL

# Danh sách TỪ KHÓA SẢN PHẨM / THIẾT BỊ cần tìm trong DANH MỤC CHI TIẾT
# (Cấu hình các sản phẩm bạn quan tâm ở đây, ví dụ: ống soi, camera, phần mềm, máy tính...)
PRODUCT_KEYWORDS = [
    "nội soi", "nội soi tiêu hóa", "nội soi khí phế quản", "Bàn mổ", 
    "đèn mổ", "hệ thống khí y tế", "vận chuyển mẫu", "ERCP"
]

def fetch_all_ycbg_today():
    """Lấy danh sách tất cả YCBG phát hành trong ngày (Không lọc tiêu đề để tránh bỏ sót)"""
    url = "https://muasamcong.mof.gov.vn/o/egp-portal-contractor-selection-v2/services/smart/search"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    tz_vn = zoneinfo.ZoneInfo("Asia/Ho_Chi_Minh")
    today_vn = datetime.now(tz_vn)
    today_str = today_vn.strftime("%Y-%m-%d")
    
    payload = {
        "page": 0,
        "size": 150,  # Lấy diện rộng tối đa 150 gói/ngày
        "type": "YCBG",
        "keySearch": "", # Để trống từ khóa để lấy tất cả gói trong ngày
        "publishDateFrom": f"{today_str}T00:00:00Z",
        "publishDateTo": f"{today_str}T23:59:59Z"
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=60)
        if response.status_code == 200:
            return response.json().get("result", {}).get("data", [])
        return []
    except Exception as e:
        print(f"[Lỗi YCBG] Không thể kết nối API: {e}")
        return []

def deep_analyze_with_gemini(raw_data, product_keywords):
    """Gửi toàn bộ danh mục dữ liệu chi tiết cho Gemini để 'soi' từng mặt hàng sản phẩm"""
    if not raw_data:
        return "<p>Hôm nay không có Yêu cầu báo giá mới nào được đăng tải.</p>"

    client = genai.Client(api_key=GEMINI_API_KEY)
    
    prompt = f"""
    Bạn là một Trợ lý CNTT & Chuyên gia phân tích dữ liệu mua sắm công.
    Dưới đây là danh sách dữ liệu Yêu cầu báo giá (YCBG) thô thu thập trong ngày từ muasamcong.mof.gov.vn:
    {raw_data}

    NHIỆM VỤ CỦA BẠN:
    1. Đọc và phân tích CHI TIẾT từng gói/thông báo (bao gồm danh mục hàng hóa, danh sách vật tư, mô tả chi tiết nếu có trong dữ liệu thô).
    2. Lọc ra tất cả các gói YCBG có chứa các sản phẩm/thiết bị thuộc danh sách từ khóa sau: {product_keywords}. 
       *LƯU Ý QUAN TRỌNG:* Kiểm tra sâu vào danh mục mặt hàng chi tiết. Ngay cả khi Tiêu đề gói không chứa từ khóa, nhưng bên trong DANH MỤC HÀNG HÓA/VẬT TƯ có chứa sản phẩm phù hợp thì VẪN PHẢI LỌC RA.
    
    3. Trình bày kết quả dưới dạng BẢNG HTML chuyên nghiệp gửi Email:
       - Mã YCBG / Mã số
       - Tên Yêu cầu báo giá (Tiêu đề)
       - Sản phẩm/Thiết bị phát hiện (Chỉ rõ tìm thấy sản phẩm nào trong danh mục chi tiết)
       - Đơn vị yêu cầu báo giá
       - Hạn nộp báo giá
       - Link xem chi tiết: Tạo đường dẫn dạng `<a href="https://muasamcong.mof.gov.vn/vi/web/guest/initiator?tbmtNo=[MÃ_SỐ]">Xem chi tiết</a>`

    4. Nếu sau khi soi toàn bộ danh mục chi tiết mà KHÔNG có sản phẩm nào phù hợp, hãy trả về thông báo: "Hôm nay không có Yêu cầu báo giá nào chứa sản phẩm/thiết bị thuộc danh mục theo dõi."
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

    part = MIMEText(html_content, "html")
    msg.attach(part)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        print("-> Đã gửi Email báo cáo YCBG chi tiết thành công!")
    except Exception as e:
        print(f"[Lỗi gửi Email] {e}")

if __name__ == "__main__":
    print("=== BẮT ĐẦU SOÁT CHI TIẾT DANH MỤC YÊU CẦU BÁO GIÁ (YCBG) ===")
    raw_ycbg = fetch_all_ycbg_today()
    print(f"-> Đã thu thập {len(raw_ycbg)} gói YCBG trong ngày. Đang chuyển cho Gemini phân tích danh mục...")
    
    email_body = deep_analyze_with_gemini(raw_ycbg, PRODUCT_KEYWORDS)
    
    tz_vn = zoneinfo.ZoneInfo("Asia/Ho_Chi_Minh")
    today_str = datetime.now(tz_vn).strftime('%d/%m/%Y')
    subject = f"[YCBG CHI TIẾT] Báo cáo sản phẩm danh mục ngày {today_str}"
    
    send_email(subject, email_body)
    print("=== HOÀN THÀNH ===")
