import os
import smtplib
import requests
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from google import genai

# Nạp thông tin bảo mật từ cấu hình GitHub Environment
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD")
RECEIVER_EMAIL = SENDER_EMAIL  # Gửi về chính email của bạn

# DANH SÁCH TỪ KHÓA CẦN LỌC (Thay đổi/Thêm bớt tùy theo nhu cầu công việc)
KEYWORDS = ["Nội soi", "nội soi tiêu hóa", "Nội soi khí phế quản", "Bàn mổ", "Đèn mổ", "ERCP"]

def fetch_muasamcong_data():
    """Gọi API công khai của muasamcong.mof.gov.vn để lấy danh sách TBMT trong ngày"""
    url = "https://muasamcong.mof.gov.vn/api/egp/bidding/services/app/tbmt/search"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    today_str = datetime.now().strftime("%Y-%m-%d")
    payload = {
        "page": 0,
        "size": 100,
        "searchType": "TBMT",  # Thông báo mời thầu / Mời chào giá
        "publishDateFrom": f"{today_str}T00:00:00Z",
        "publishDateTo": f"{today_str}T23:59:59Z"
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        if response.status_code == 200:
            return response.json().get("result", {}).get("data", [])
        return []
    except Exception as e:
        print(f"Lỗi khi gửi yêu cầu tới Mua Sắm Công: {e}")
        return []

def filter_and_summarize_with_gemini(raw_data, keywords):
    """Sử dụng SDK google-genai để phân tích dữ liệu và trích xuất thông tin khớp từ khóa"""
    if not raw_data:
        return "<p>Hôm nay không có thông báo mời thầu/mời chào giá mới nào được đăng tải trên hệ thống.</p>"

    client = genai.Client(api_key=GEMINI_API_KEY)
    
    prompt = f"""
    Bạn là một Trợ lý CNTT chuyên nghiệp. Dưới đây là danh sách dữ liệu thông báo mời thầu/mời chào giá thô lấy từ trang muasamcong.mof.gov.vn trong ngày hôm nay:
    {raw_data}

    Nhiệm vụ của bạn:
    1. Tìm và lọc ra tất cả các gói thầu hoặc thông báo mời chào giá liên quan đến các từ khóa sau: {', '.join(keywords)}.
    2. Định dạng lại nội dung dưới dạng bảng HTML gọn gàng, chuyên nghiệp để gửi qua Email.
    3. Các cột thông tin bắt buộc bao gồm: 
       - Mã TBMT
       - Tên gói thầu / Nội dung chào giá
       - Bên mời thầu / Chủ đầu tư
       - Giá gói thầu / Dự toán (nếu có)
       - Thời điểm đóng thầu
       - Đường dẫn xem chi tiết (Tạo link truy cập dạng: https://muasamcong.mof.gov.vn/vi/web/guest/initiator?tbmtNo=<Mã TBMT>)
    4. Nếu không tìm thấy gói thầu nào phù hợp với các từ khóa trên, hãy trả về câu thông báo: "Không có gói thầu/chào giá nào phù hợp với danh mục từ khóa theo dõi trong ngày hôm nay."
    """

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )
    return response.text

def send_email(subject, html_content):
    """Gửi email kết quả thông qua SMTP Gmail"""
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
        print("Đã gửi email báo cáo thành công!")
    except Exception as e:
        print(f"Lỗi trong quá trình gửi email: {e}")

if __name__ == "__main__":
    print("Bắt đầu quét dữ liệu...")
    raw_bids = fetch_muasamcong_data()
    print(f"Đã thu thập {len(raw_bids)} bản ghi thô. Đang xử lý qua Gemini...")
    email_body = filter_and_summarize_with_gemini(raw_bids, KEYWORDS)
    
    subject = f"[BÁO CÁO THẦU CNTT] Thông báo mời chào giá ngày {datetime.now().strftime('%d/%m/%Y')}"
    send_email(subject, email_body)
