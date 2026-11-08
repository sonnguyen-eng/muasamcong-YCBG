import os
import time
import smtplib
import requests
from datetime import datetime
import zoneinfo
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from google import genai

# ================= 1. CẤU HÌNH BIẾN BẢO MẬT & DANH MỤC =================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD")
RECEIVER_EMAIL = SENDER_EMAIL  # Gửi về chính email của bạn

# DANH SÁCH TỪ KHÓA SẢN PHẨM / THIẾT BỊ / MÃ GÓI CẦN SOI CHI TIẾT
PRODUCT_KEYWORDS = [
    "nội soi", "nội soi tiêu hóa", "nội soi khí phế quản", "Bàn mổ", 
    "đèn mổ", "hệ thống khí y tế", "vận chuyển mẫu", "ERCP"
]

# Lấy ngày hiện tại theo Múi giờ Việt Nam (Asia/Ho_Chi_Minh)
TZ_VN = zoneinfo.ZoneInfo("Asia/Ho_Chi_Minh")
NOW_VN = datetime.now(TZ_VN)

# Chốt khung thời gian cố định: Từ 00:00:00 đến 23:59:59 của NGÀY HÔM NAY
DATE_FROM = NOW_VN.strftime("%Y-%m-%dT00:00:00Z")
DATE_TO = NOW_VN.strftime("%Y-%m-%dT23:59:59Z")
TODAY_STR = NOW_VN.strftime("%d/%m/%Y")


# ================= 2. TRUY VẤN DỮ LIỆU TỪ MUA SẮM CÔNG =================
def fetch_ycbg_today():
    """Lấy danh sách Yêu cầu báo giá (YCBG/RQ) phát hành trong ngày từ 00:00 đến 23:59:59"""
    url = "https://muasamcong.mof.gov.vn/o/egp-portal-contractor-selection-v2/services/smart/search"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    all_items = []
    # Quét 3 trang đầu (tối đa 150 gói YCBG mới nhất trong ngày)
    for page in range(3):
        payload = {
            "page": page,
            "size": 50,
            "type": "YCBG",
            "keySearch": "",
            "publishDateFrom": DATE_FROM,
            "publishDateTo": DATE_TO
        }
        try:
            res = requests.post(url, json=payload, headers=headers, timeout=30)
            if res.status_code == 200:
                data = res.json().get("result", {}).get("data", [])
                if not data:
                    break
                all_items.extend(data)
            time.sleep(0.5)
        except Exception as e:
            print(f"[Lỗi API YCBG] Trang {page}: {e}")
            break
            
    return all_items

def fetch_tbmt_today():
    """Lấy danh sách Thông báo mời thầu (TBMT) phát hành trong ngày từ 00:00 đến 23:59:59"""
    url = "https://muasamcong.mof.gov.vn/o/egp-portal-contractor-selection-v2/services/popular-keyword/get-list"
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    all_items = []
    for page in range(3):
        payload = {
            "page": page,
            "size": 50,
            "type": "TBMT",
            "keySearch": "",
            "publishDateFrom": DATE_FROM,
            "publishDateTo": DATE_TO
        }
        try:
            res = requests.post(url, json=payload, headers=headers, timeout=30)
            if res.status_code == 200:
                data = res.json().get("result", {}).get("data", [])
                if not data:
                    break
                all_items.extend(data)
            time.sleep(0.5)
        except Exception as e:
            print(f"[Lỗi API TBMT] Trang {page}: {e}")
            break
            
    return all_items


# ================= 3. SOI DANH MỤC HÀNG HÓA & PHÂN TÍCH GEMINI =================
def analyze_data_with_gemini(ycbg_data, tbmt_data, keywords):
    """Gửi toàn bộ dữ liệu gói thầu/chào giá trong ngày để Gemini phân tích chi tiết"""
    total_count = len(ycbg_data) + len(tbmt_data)
    if total_count == 0:
        return f"<p>Hệ thống đã quét từ 00:00 đến 23:59:59 ngày {TODAY_STR} và không ghi nhận Thông báo mời thầu hoặc Yêu cầu báo giá mới nào được đăng tải trên Mua Sắm Công.</p>"

    client = genai.Client(api_key=GEMINI_API_KEY)
    
    prompt = f"""
    Bạn là một Trợ lý CNTT & Chuyên gia phân tích dữ liệu Đấu thầu.
    Dưới đây là toàn bộ dữ liệu Thông báo mời thầu (TBMT) và Yêu cầu báo giá (YCBG/RQ) đăng tải trong ngày {TODAY_STR} (từ 00:00:00 đến 23:59:59) trên muasamcong.mof.gov.vn:

    === DANH SÁCH YÊU CẦU BÁO GIÁ (YCBG) ===
    {ycbg_data}

    === DANH SÁCH THÔNG BÁO MỜI THẦU (TBMT) ===
    {tbmt_data}

    NHIỆM VỤ CỦA BẠN:
    1. Soi kỹ Tiêu đề, Mã gói và DANH MỤC HÀNG HÓA/CHI TIẾT MẶT HÀNG bên trong từng thông báo.
    2. Lọc ra các gói thầu/yêu cầu báo giá có chứa bất kỳ sản phẩm/vật tư nào thuộc danh mục từ khóa: {keywords}.
       *LƯU Ý quan trọng:* Kể cả khi tiêu đề viết chung chung (ví dụ: 'Mua sắm trang thiết bị năm 2026'), nhưng trong danh mục sản phẩm chi tiết có chứa các thiết bị/vật tư quan tâm thì VẪN LỌC RA.
    
    3. Định dạng kết quả thành BẢNG HTML chuyên nghiệp gửi Email bao gồm các cột:
       - Phân loại (TBMT hoặc YCBG)
       - Mã số (Mã TBMT hoặc Mã RQ)
       - Tên gói thầu / Yêu cầu báo giá
       - Mặt hàng/Sản phẩm phát hiện (Nêu rõ tên sản phẩm khớp từ khóa nằm trong danh mục)
       - Bên mời thầu / Đơn vị yêu cầu
       - Hạn nộp / Đóng thầu
       - Link trực tiếp: 
         + Nếu là YCBG: `<a href="https://muasamcong.mof.gov.vn/web/guest/contractor-selection?type=es-ycbg&stepCode=request-quote-step-1&notifyNo=[MÃ_SỐ]">Xem chi tiết</a>`
         + Nếu là TBMT: `<a href="https://muasamcong.mof.gov.vn/vi/web/guest/initiator?tbmtNo=[MÃ_SỐ]">Xem chi tiết</a>`

    4. Nếu không có gói nào chứa mặt hàng phù hợp, trả về thông báo: "Hệ thống đã quét {total_count} thông báo trong ngày {TODAY_STR}, nhưng không có gói thầu/chào giá nào chứa sản phẩm thuộc danh mục theo dõi."
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
        print(f"[{TODAY_STR}] -> Đã gửi thành công email báo cáo thầu daily!")
    except Exception as e:
        print(f"[Lỗi gửi email] {e}")


# ================= 5. LUỒNG CHẠY CHÍNH (MAIN) =================
if __name__ == "__main__":
    print(f"=== BẮT ĐẦU QUÉT DỮ LIỆU MUA SẮM CÔNG NGÀY {TODAY_STR} (00:00:00 - 23:59:59) ===")
    
    # 1. Thu thập dữ liệu YCBG
    print("-> Đang lấy dữ liệu Yêu cầu báo giá (YCBG/RQ)...")
    ycbg_items = fetch_ycbg_today()
    print(f"   + Đã lấy được {len(ycbg_items)} YCBG trong ngày.")
    
    # 2. Thu thập dữ liệu TBMT
    print("-> Đang lấy dữ liệu Thông báo mời thầu (TBMT)...")
    tbmt_items = fetch_tbmt_today()
    print(f"   + Đã lấy được {len(tbmt_items)} TBMT trong ngày.")
    
    # 3. Phân tích qua Gemini
    print("-> Đang chuyển toàn bộ dữ liệu ngày cho Gemini phân tích & bóc tách danh mục...")
    email_body = analyze_data_with_gemini(ycbg_items, tbmt_items, PRODUCT_KEYWORDS)
    
    # 4. Gửi email báo cáo
    subject = f"[BÁO CÁO THẦU DAILY] Ngày {TODAY_STR} (00:00 - 23:59)"
    send_email(subject, email_body)
    
    print("=== HOÀN THÀNH QUY TRÌNH HÀNG NGÀY ===")
