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

# DANH SÁCH SẢN PHẨM / VẬT TƯ CẦN SOI CHI TIẾT
PRODUCT_KEYWORDS = [
    "nội soi", "nội soi tiêu hóa", "nội soi khí phế quản", "Bàn mổ", 
    "đèn mổ", "hệ thống khí y tế", "vận chuyển mẫu", "ERCP"
]

def fetch_ycbg_list_today():
    """Lấy toàn bộ Yêu cầu báo giá (YCBG/RQ) đăng tải trong 2 ngày gần nhất"""
    url = "https://muasamcong.mof.gov.vn/o/egp-portal-contractor-selection-v2/services/smart/search"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    tz_vn = zoneinfo.ZoneInfo("Asia/Ho_Chi_Minh")
    today_vn = datetime.now(tz_vn)
    
    # Lấy rộng từ ngày hôm trước đến hôm nay để tránh lệch múi giờ
    from_date = (today_vn - timedelta(days=1)).strftime("%Y-%m-%d")
    to_date = today_vn.strftime("%Y-%m-%d")
    
    all_items = []
    
    # Duyệt 3 trang đầu tiên (mỗi trang 50 gói = 150 gói gần nhất)
    for page in range(3):
        payload = {
            "page": page,
            "size": 50,
            "type": "YCBG", # Tìm kiếm chuyên biệt Yêu cầu báo giá (RQ)
            "keySearch": "",
            "publishDateFrom": f"{from_date}T00:00:00Z",
            "publishDateTo": f"{to_date}T23:59:59Z"
        }

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            if response.status_code == 200:
                data = response.json().get("result", {}).get("data", [])
                if not data:
                    break
                all_items.extend(data)
            time.sleep(1)
        except Exception as e:
            print(f"Lỗi khi lấy trang {page} YCBG: {e}")
            break

    return all_items

def fetch_ycbg_detail_items(notify_no, item_id):
    """
    Gọi API chi tiết của từng YCBG để lấy danh mục vật tư / hàng hóa bên trong
    """
    url = "https://muasamcong.mof.gov.vn/o/egp-portal-contractor-selection-v2/services/ycbg/detail"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    payload = {
        "id": item_id,
        "notifyNo": notify_no
    }
    
    try:
        res = requests.post(url, json=payload, headers=headers, timeout=15)
        if res.status_code == 200:
            # Trả về danh sách chi tiết mặt hàng
            return res.json().get("result", {})
    except Exception:
        pass
    return {}

def deep_analyze_with_gemini(ycbg_full_data, keywords):
    """Gửi toàn bộ thông tin YCBG kèm danh mục chi tiết cho Gemini phân tích"""
    if not ycbg_full_data:
        return "<p>Hôm nay không tìm thấy Yêu cầu báo giá mới nào.</p>"

    client = genai.Client(api_key=GEMINI_API_KEY)
    
    prompt = f"""
    Bạn là Trợ lý CNTT chuyên nghiệp. Dưới đây là danh sách các Yêu cầu báo giá (RQ) kèm thông tin danh mục hàng hóa chi tiết lấy từ muasamcong.mof.gov.vn:
    {ycbg_full_data}

    NHIỆM VỤ:
    1. Soi kỹ Tiêu đề và DANH MỤC HÀNG HÓA CHI TIẾT bên trong từng gói.
    2. Lọc ra các YCBG có chứa bất kỳ sản phẩm/vật tư nào khớp với từ khóa: {keywords}.
    3. Trình bày dạng BẢNG HTML chuyên nghiệp gửi Email gồm các cột:
       - Mã YCBG (ví dụ: RQ2600095388)
       - Tên Yêu cầu báo giá
       - Mặt hàng phát hiện trong danh mục chi tiết
       - Đơn vị yêu cầu
       - Hạn nộp báo giá
       - Link xem chi tiết trực tiếp: 
         `<a href="https://muasamcong.mof.gov.vn/web/guest/contractor-selection?type=es-ycbg&stepCode=request-quote-step-1&notifyNo=[MÃ_RQ]">Xem chi tiết</a>`

    4. Nếu không có gói nào chứa mặt hàng phù hợp, trả về: "Không có Yêu cầu báo giá nào chứa sản phẩm thuộc danh mục theo dõi trong ngày."
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
    msg.attach(MIMEText(html_content, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        print("-> Đã gửi thành công email báo cáo YCBG chi tiết!")
    except Exception as e:
        print(f"[Lỗi gửi email] {e}")

if __name__ == "__main__":
    print("=== BẮT ĐẦU QUÉT CHI TIẾT YÊU CẦU BÁO GIÁ (YCBG / RQ) ===")
    raw_list = fetch_ycbg_list_today()
    print(f"-> Thu thập được {len(raw_list)} YCBG tổng quan. Đang bóc tách danh mục chi tiết từng gói...")
    
    enriched_data = []
    for item in raw_list:
        notify_no = item.get("notifyNo")
        item_id = item.get("id")
        
        # Lấy thêm thông tin chi tiết danh mục sản phẩm của gói thầu
        detail_info = fetch_ycbg_detail_items(notify_no, item_id)
        
        enriched_data.append({
            "overview": item,
            "items_detail": detail_info
        })
        time.sleep(0.5)

    print("-> Đang nhờ Gemini phân tích toàn bộ dữ liệu chi tiết...")
    email_body = deep_analyze_with_gemini(enriched_data, PRODUCT_KEYWORDS)
    
    tz_vn = zoneinfo.ZoneInfo("Asia/Ho_Chi_Minh")
    subject = f"[YCBG RQ CHI TIẾT] Báo cáo Yêu cầu báo giá ngày {datetime.now(tz_vn).strftime('%d/%m/%Y')}"
    
    send_email(subject, email_body)
    print("=== HOÀN THÀNH ===")
