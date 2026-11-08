import os
import time
import smtplib
from datetime import datetime
import zoneinfo
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from playwright.sync_api import sync_playwright
from google import genai

# ================= 1. CẤU HÌNH BIẾN & TỪ KHÓA =================
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


# ================= 2. QUÉT TRUY CẬP TRỰC TIẾP BẰNG PLAYWRIGHT =================
def fetch_data_with_playwright():
    matched_results = []
    
    with sync_playwright() as p:
        print("-> Đang khởi chạy Trình duyệt Chromium...")
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = context.new_page()

        # Intercept mạng: Tự động bắt các API JSON trả về từ Mua Sắm Công
        def handle_response(response):
            if "services/" in response.url and response.status == 200:
                try:
                    res_json = response.json()
                    data_list = []
                    if isinstance(res_json.get("result"), dict):
                        data_list = res_json.get("result", {}).get("data", [])
                    elif isinstance(res_json.get("result"), list):
                        data_list = res_json.get("result", [])
                    
                    for item in data_list:
                        code = item.get("notifyNo") or item.get("bidNo") or item.get("code") or item.get("id")
                        title = item.get("bidName") or item.get("name") or item.get("title") or ""
                        investor = item.get("procuringEntityName") or item.get("investorName") or ""
                        
                        full_text = f"{code} {title} {investor}".lower()
                        for kw in KEYWORDS:
                            if kw.lower() in full_text:
                                matched_results.append({
                                    "code": code,
                                    "title": title,
                                    "investor": investor,
                                    "matched_kw": kw,
                                    "raw": item
                                })
                                break
                except Exception:
                    pass

        page.on("response", handle_response)

        print("-> Mở trang chủ Mua Sắm Công V2...")
        try:
            page.goto("https://muasamcong.mof.gov.vn/web/guest/contractor-selection", timeout=60000)
            page.wait_for_timeout(4000)
        except Exception as e:
            print(f"Lỗi tải trang: {e}")

        # Tự động gõ từ khóa và Enter
        for kw in KEYWORDS:
            try:
                print(f"-> Đang quét từ khóa: '{kw}'...")
                search_input = page.locator("input[placeholder*='Tìm kiếm']").first
                if search_input.is_visible():
                    search_input.fill(kw)
                    search_input.press("Enter")
                    page.wait_for_timeout(3500)
            except Exception as e:
                print(f"Lỗi khi tương tác với từ khóa '{kw}': {e}")

        browser.close()

    # Loại bỏ bản ghi trùng lặp theo Mã gói
    unique_items = {}
    for item in matched_results:
        code = item["code"]
        if code and code not in unique_items:
            unique_items[code] = item

    return list(unique_items.values())


# ================= 3. ĐỊNH DẠNG GEMINI & GỬI EMAIL =================
def build_report_and_send(items):
    if not items:
        email_body = f"""
        <div style="font-family: Arial, sans-serif; padding: 20px; line-height: 1.6;">
            <h3 style="color: #d9534f;">BÁO CÁO QUÉT THẦU NGÀY {TODAY_STR}</h3>
            <p>Trình duyệt đã kết nối Mua Sắm Công nhưng không phát hiện thông báo thầu/YCBG nào chứa các từ khóa theo dõi trong ngày.</p>
        </div>
        """
    else:
        client = genai.Client(api_key=GEMINI_API_KEY)
        prompt = f"""
        Bạn là Trợ lý CNTT. Dưới đây là danh sách các Yêu cầu báo giá (YCBG) và Thông báo mời thầu (TBMT) thu thập thực tế từ muasamcong.mof.gov.vn ngày {TODAY_STR}:
        {items}

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
        3. Thêm tổng số lượng thông báo tìm thấy ở đầu Email.
        """
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )
        email_body = response.text

    # Gửi Email
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[TBMT & YCBG Y TẾ] Báo cáo ngày {TODAY_STR}"
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL
    msg.attach(MIMEText(email_body, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        print("-> Đã gửi thành công email báo cáo thầu!")
    except Exception as e:
        print(f"[Lỗi gửi email] {e}")


if __name__ == "__main__":
    print(f"=== BẮT ĐẦU CRAWL PLAYWRIGHT MUA SẮM CÔNG - {TODAY_STR} ===")
    results = fetch_data_with_playwright()
    print(f"-> Tổng kết thu thập được: {len(results)} gói thầu thực tế.")
    build_report_and_send(results)
    print("=== HOÀN THÀNH ===")
