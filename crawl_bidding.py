import os
import time
import smtplib
import requests
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ================= 1. CẤU HÌNH TỪ KHÓA & MÔI TRƯỜNG =================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "")
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD", "")
RECEIVER_EMAIL = SENDER_EMAIL

KEYWORDS = [
    "nội soi", "nội soi tiêu hóa", "nội soi khí phế quản", 
    "Bàn mổ", "đèn mổ", "hệ thống khí y tế", "vận chuyển mẫu", "ERCP"
]

# Chuẩn hóa giờ Việt Nam (UTC+7) không phụ thuộc thư viện bên ngoài
TZ_VN = timezone(timedelta(hours=7))
NOW_VN = datetime.now(TZ_VN)
TODAY_STR = NOW_VN.strftime("%d/%m/%Y")


# ================= 2. HÀM QUÉT API MUA SẮM CÔNG =================
def fetch_bidding_api(search_type, keyword):
    if search_type == "YCBG":
        url = "https://muasamcong.mof.gov.vn/o/egp-portal-contractor-selection-v2/services/smart/search"
    else:
        url = "https://muasamcong.mof.gov.vn/o/egp-portal-contractor-selection-v2/services/popular-keyword/get-list"

    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json;charset=UTF-8",
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
            res = requests.post(url, json=payload, headers=headers, timeout=25)
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
            print(f"[CẢNH BÁO API] {search_type} | '{keyword}' | Page {page}: {e}")
            break

    return all_items


# ================= 3. THU THẬP & ĐỐI SOÁT DỮ LIỆU =================
def run_crawler():
    unique_matches = {}

    for kw in KEYWORDS:
        print(f"--> Đang gửi Request tìm từ khóa: '{kw}'...")
        
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
                    "matched_kw": kw
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
                    "matched_kw": kw
                }
                
        time.sleep(0.3)

    return list(unique_matches.values())


# ================= 4. TẠO HTML BÁO CÁO VÀ GỬI EMAIL =================
def generate_html_report(matched_items):
    if not matched_items:
        return f"""
        <div style="font-family: Arial, sans-serif; padding: 20px;">
            <h3 style="color: #d9534f;">BÁO CÁO QUÉT THẦU TỰ ĐỘNG - NGÀY {TODAY_STR}</h3>
            <p>Hệ thống đã truy vấn thành công tới máy chủ Mua Sắm Công nhưng không tìm thấy thông báo thầu/YCBG nào mới chứa danh mục từ khóa theo dõi.</p>
        </div>
        """

    html = f"""
    <div style="font-family: Arial, sans-serif; padding: 20px;">
        <h2 style="color: #0275d8;">BÁO CÁO GÓI THẦU & YCBG Y TẾ NGÀY {TODAY_STR}</h2>
        <p>Phát hiện <b>{len(matched_items)}</b> thông báo phù hợp danh mục từ khóa theo dõi:</p>
        <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%;">
            <tr style="background-color: #f2f2f2;">
                <th>STT</th>
                <th>Phân loại</th>
                <th>Mã gói</th>
                <th>Tên gói thầu / YCBG</th>
                <th>Bên mời chào giá</th>
                <th>Từ khóa khớp</th>
                <th>Chi tiết</th>
            </tr>
    """
    for idx, item in enumerate(matched_items, 1):
        if item['type'] == 'YCBG':
            link = f"https://muasamcong.mof.gov.vn/web/guest/contractor-selection?type=es-ycbg&stepCode=request-quote-step-1&notifyNo={item['code']}"
        else:
            link = f"https://muasamcong.mof.gov.vn/vi/web/guest/initiator?tbmtNo={item['code']}"

        html += f"""
            <tr>
                <td align="center">{idx}</td>
                <td align="center"><b>{item['type']}</b></td>
                <td>{item['code']}</td>
                <td>{item['title']}</td>
                <td>{item['investor']}</td>
                <td align="center"><span style="background-color: #ffffcc;">{item['matched_kw']}</span></td>
                <td align="center"><a href="{link}" target="_blank">Xem chi tiết</a></td>
            </tr>
        """
    html += "</table></div>"
    return html


def generate_email_body(matched_items):
    # Ưu tiên thử dùng Gemini SDK, nếu lỗi tự chuyển sang HTML thuần
    if GEMINI_API_KEY:
        try:
            from google import genai
            client = genai.Client(api_key=GEMINI_API_KEY)
            prompt = f"Tạo bảng HTML đẹp báo cáo danh sách gói thầu sau ngày {TODAY_STR}: {matched_items}"
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            return response.text
        except Exception as e:
            print(f"[CẢNH BÁO GEMINI] {e}, chuyển sang HTML mặc định.")
    
    return generate_html_report(matched_items)


def send_email(subject, html_content):
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        print("[LỖI] Thiếu SENDER_EMAIL hoặc SENDER_PASSWORD!")
        return

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
        print(f"[LỖI EMAIL] Không thể gửi: {e}")


# ================= 5. CHƯƠNG TRÌNH CHÍNH =================
if __name__ == "__main__":
    print(f"==================================================")
    print(f"   BẮT ĐẦU CRAWL DỮ LIỆU THẦU DAILY - {TODAY_STR}")
    print(f"==================================================")
    
    results = run_crawler()
    print(f"--> [TỔNG KẾT] Phát hiện: {len(results)} gói thầu/YCBG khớp từ khóa.")
    
    email_body = generate_email_body(results)
    subject = f"[TBMT & YCBG Y TẾ] Báo cáo ngày {TODAY_STR}"
    send_email(subject, email_body)
    
    print(f"==================================================")
    print(f"   HOÀN THÀNH TIẾN TRÌNH QUÉT THẦU TỰ ĐỘNG")
    print(f"==================================================")
