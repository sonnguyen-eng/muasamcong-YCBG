import os
import time
import smtplib
import requests
from datetime import datetime, timedelta
import zoneinfo
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from google import genai

# ================= 1. CẤU HÌNH HỆ THỐNG & TỪ KHÓA =================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD")
RECEIVER_EMAIL = SENDER_EMAIL

# Danh sách từ khóa theo đúng yêu cầu của anh
KEYWORDS = [
    "nội soi", "nội soi tiêu hóa", "nội soi khí phế quản", 
    "Bàn mổ", "đèn mổ", "hệ thống khí y tế", "vận chuyển mẫu", "ERCP"
]

TZ_VN = zoneinfo.ZoneInfo("Asia/Ho_Chi_Minh")
NOW_VN = datetime.now(TZ_VN)
TODAY_STR = NOW_VN.strftime("%d/%m/%Y")


# ================= 2. HÀM GỌI API MUA SẮM CÔNG CHUẨN =================
def search_muasamcong(keyword, search_type="YCBG"):
    """
    Gửi request chuẩn tới API Mua Sắm Công
    search_type: "YCBG" (Yêu cầu báo giá) hoặc "TBMT" (Thông báo mời thầu)
    """
    if search_type == "YCBG":
        url = "https://muasamcong.mof.gov.vn/o/egp-portal-contractor-selection-v2/services/smart/search"
    else:
        url = "https://muasamcong.mof.gov.vn/o/egp-portal-contractor-selection-v2/services/popular-keyword/get-list"

    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*"
    }
    
    matched_items = []
    
    # Quét 3 trang đầu tiên cho mỗi từ khóa
    for page in range(3):
        payload = {
            "page": page,
            "size": 50,
            "type": search_type,
            "keySearch": keyword.strip()
        }
        try:
            res = requests.post(url, json=payload, headers=headers, timeout=30)
            if res.status_code == 200:
                res_data = res.json()
                # Trích xuất danh sách dữ liệu từ response
                items = res_data.get("result", {}).get("data", [])
                if not items and isinstance(res_data.get("result"), list):
                    items = res_data.get("result", [])
                
                if not items:
                    break
                matched_items.extend(items)
            time.sleep(0.3)
        except Exception as e:
            print(f"[LỖI API] Từ khóa '{keyword}', loại {search_type}, trang {page}: {e}")
            break

    return matched_items


# ================= 3. THU THẬP & KHỬ TRÙNG LẶP =================
def collect_all_data():
    unique_results = {}

    for kw in KEYWORDS:
        print(f"-> Đang tìm kiếm từ khóa: '{kw}'...")
        
        # 1. Tìm trong YCBG
        ycbg_items = search_muasamcong(kw, "YCBG")
        print(f"   + YCBG tìm thấy: {len(ycbg_items)} bản ghi.")
        for item in ycbg_items:
            code = item.get("notifyNo") or item.get("code") or item.get("id")
            if code and code not in unique_results:
                unique_results[code] = {
                    "type": "YCBG",
                    "code": code,
                    "title": item.get("bidName") or item.get("name") or item.get("title") or "",
                    "investor": item.get("procuringEntityName") or item.get("investorName") or "",
                    "date": item.get("createDate") or item.get("publishDate") or item.get("publicDate") or TODAY_STR,
                    "matched_kw": kw,
                    "raw": item
                }

        # 2. Tìm trong TBMT
        tbmt_items = search_muasamcong(kw, "TBMT")
        print(f"   + TBMT tìm thấy: {len(tbmt_items)} bản ghi.")
        for item in tbmt_items:
            code = item.get("bidNo") or item.get("notifyNo") or item.get("id")
            if code and code not in unique_results:
                unique_results[code] = {
                    "type": "TBMT",
                    "code": code,
                    "title": item.get("bidName") or item.get("name") or item.get("title") or "",
                    "investor": item.get("procuringEntityName") or item.get("investorName") or "",
                    "date": item.get("createDate") or item.get("publishDate") or item.get("publicDate") or TODAY_STR,
                    "matched_kw": kw,
                    "raw": item
                }
                
        time.sleep(0.5)

    return list(unique_results.values())


# ================= 4. GEMINI TỔNG HỢP NỘI DUNG EMAIL =================
def generate_email_with_gemini(matched_items):
    if not matched_items:
        return f"""
        <div style="font-family: Arial, sans-serif; padding: 20px;">
            <h3 style="color: #d9534f;">BÁO CÁO QUÉT THẦU NGÀY {TODAY_STR}</h3>
            <p>Hệ thống đã kết nối máy chủ Mua Sắm Công nhưng không tìm thấy thông báo thầu/YCBG nào khớp danh mục từ khóa theo dõi.</p>
        </div>
        """

    client = genai.Client(api_key=GEMINI_API_KEY)
    
    prompt = f"""
    Bạn là Trợ lý CNTT chuyên nghiệp. Dưới đây là danh sách các Yêu cầu báo giá (YCBG) và Thông báo mời thầu (TBMT) thu thập được từ muasamcong.mof.gov.vn trong ngày {TODAY_STR}:
    {matched_items}

    NHIỆM VỤ:
    1. Trình bày danh sách trên dưới dạng BẢNG HTML chuyên nghiệp gửi email.
    2. Các cột trong bảng bao gồm:
       - Phân loại (TBMT hoặc YCBG)
       - Mã số gói thầu / YCBG (Ví dụ: RQ2600095388-00)
       - Tên gói thầu / Yêu cầu báo giá
       - Chủ đầu tư / Bên mời chào giá
       - Từ khóa khớp
       - Link xem chi tiết trực tiếp:
         + Đối với YCBG: `<a href="https://muasamcong.mof.gov.vn/web/guest/contractor-selection?type=es-ycbg&stepCode=request-quote-step-1&notifyNo=[MÃ_SỐ]">Xem chi tiết</a>`
         + Đối với TBMT: `<a href="https://muasamcong.mof.gov.vn/vi/web/guest/initiator?tbmtNo=[MÃ_SỐ]">Xem chi tiết</a>`
    3. Bổ sung phần thống kê tổng số lượng gói thầu tìm thấy ở đầu Email.
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


# ================= 6. CHƯƠNG TRÌNH CHÍNH =================
if __name__ == "__main__":
    print(f"==================================================")
    print(f"   BẮT ĐẦU QUÉT DỮ LIỆU MUA SẮM CÔNG - NGÀY {TODAY_STR}")
    print(f"==================================================")
    
    results = collect_all_data()
    print(f"[KẾT QUẢ] Tổng số gói thầu/YCBG thu thập được: {len(results)}")
    
    print("[INFO] Đang nhờ Gemini tổng hợp báo cáo Email...")
    email_body = generate_email_with_gemini(results)
    
    subject = f"[TBMT & YCBG Y TẾ] Báo cáo ngày {TODAY_STR}"
    send_email(subject, email_body)
    
    print(f"==================================================")
    print(f"   HOÀN THÀNH TIẾN TRÌNH QUÉT THẦU TỰ ĐỘNG")
    print(f"==================================================")
