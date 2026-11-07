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

# DANH SÁCH TỪ KHÓA CẦN TÌM KIẾM
KEYWORDS = ["Nội soi", "nội soi tiêu hóa", "nội soi ERCP", "Nội soi khí phế quản", "bàn mổ", "đèn mổ", "máy hấp tiệt trùng"]

def fetch_ycbg_data(keyword):
    """
    Gọi API Smart Search của muasamcong.mof.gov.vn để lấy thông báo Yêu cầu báo giá / Mời chào giá theo từ khóa
    """
    url = "https://muasamcong.mof.gov.vn/o/egp-portal-contractor-selection-v2/services/smart/search"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*"
    }
    
    # Lấy dữ liệu trong ngày hôm nay
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    payload = {
        "page": 0,
        "size": 50,
        "type": "YCBG",  # Loại thông tin: YCBG (Yêu cầu báo giá / Mời chào giá). Bạn có thể đổi thành "TBMT" nếu muốn tìm Thông báo mời thầu.
        "keySearch": keyword,
        "publishDateFrom": f"{today_str}T00:00:00Z",
        "publishDateTo": f"{today_str}T23:59:59Z"
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        if response.status_code == 200:
            res_json = response.json()
            # Trả về danh sách kết quả từ cấu trúc response mới
            return res_json.get("result", {}).get("data", [])
        else:
            print(f"Lỗi API HTTP {response.status_code} khi tìm từ khóa: {keyword}")
            return []
    except Exception as e:
        print(f"Lỗi khi gửi yêu cầu tới Mua Sắm Công với từ khóa '{keyword}': {e}")
        return []

def collect_all_biddings(keywords):
    """Gửi request tìm kiếm lần lượt từng từ khóa và gộp dữ liệu (loại bỏ trùng lặp)"""
    all_items = {}
    
    for kw in keywords:
        print(f"Đang tìm kiếm thông báo với từ khóa: '{kw}'...")
        items = fetch_ycbg_data(kw)
        for item in items:
            # Dùng ID hoặc mã thông báo làm Key để loại bỏ các gói thầu bị trùng giữa các từ khóa
            item_id = item.get("id") or item.get("notifyNo") or item.get("code")
            if item_id and item_id not in all_items:
                all_items[item_id] = item

    return list(all_items.values())

def summarize_and_format_with_gemini(data, keywords):
    """Sử dụng SDK google-genai để tổng hợp và tạo giao diện HTML gửi Email"""
    if not data:
        return "<p>Hôm nay không có Thông báo mời chào giá / Yêu cầu báo giá mới nào phù hợp với các từ khóa theo dõi.</p>"

    client = genai.Client(api_key=GEMINI_API_KEY)
    
    prompt = f"""
    Bạn là một Trợ lý CNTT chuyên nghiệp. Dưới đây là danh sách các Thông báo yêu cầu báo giá / Mời chào giá vừa thu thập được từ muasamcong.mof.gov.vn theo các từ khóa {keywords}:
    {data}

    Nhiệm vụ của bạn:
    1. Trình bày nội dung trên thành một báo cáo dạng BẢNG HTML đẹp mắt, chuyên nghiệp để gửi qua Email.
    2. Các cột thông tin trong bảng cần bao gồm:
       - Mã TBMT / Mã YCBG
       - Tên gói thầu / Nội dung yêu cầu báo giá
       - Bên mời chào giá / Đơn vị yêu cầu
       - Giá dự toán / Giá gói thầu (nếu có, nếu không ghi 'Chưa cập nhật')
       - Thời điểm đóng thầu / Hạn nộp báo giá
       - Link xem chi tiết: Tạo đường dẫn trực tiếp dạng `<a href="https://muasamcong.mof.gov.vn/vi/web/guest/initiator?tbmtNo=[MÃ_SỐ]">Xem chi tiết</a>` (thay [MÃ_SỐ] bằng Mã số thông báo tương ứng).
    3. Thêm một lời chào ngắn ở đầu email và lời chúc làm việc hiệu quả ở cuối email.
    """

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )
    return response.text

def send_email(subject, html_content):
    """Gửi email thông qua SMTP Gmail"""
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
        print(f"Lỗi khi gửi email: {e}")

if __name__ == "__main__":
    print("Bắt đầu tiến trình quét Yêu cầu báo giá...")
    bidding_data = collect_all_biddings(KEYWORDS)
    print(f"Tổng số thông báo tìm thấy (không trùng lặp): {len(bidding_data)}")
    
    print("Đang xử lý nội dung báo cáo qua Gemini...")
    email_body = summarize_and_format_with_gemini(bidding_data, KEYWORDS)
    
    subject = f"[YÊU CẦU BÁO GIÁ - Nội soi] Báo cáo ngày {datetime.now().strftime('%d/%m/%Y')}"
    send_email(subject, email_body)
