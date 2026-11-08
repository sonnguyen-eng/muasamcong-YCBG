import os
import time
import smtplib
import requests
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ================= 1. CẤU HÌNH TỪ KHÓA & MÔI TRƯỜNG =================
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "")
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD", "")
RECEIVER_EMAIL = SENDER_EMAIL

KEYWORDS = [
    "nội soi", "nội soi tiêu hóa", "nội soi khí phế quản", 
    "Bàn mổ", "đèn mổ", "hệ thống khí y tế", "vận chuyển mẫu", "ERCP"
]

TZ_VN = timezone(timedelta(hours=7))
NOW_VN = datetime.now(TZ_VN)
TODAY_STR = NOW_VN.strftime("%d/%m/%Y")


# ================= 2. THU THẬP DỮ LIỆU TỪ MUA SẮM CÔNG =================
def fetch_api(search_type, keyword):
    if search_type == "YCBG":
        url = "https://muasamcong.mof.gov.vn/o/egp-portal-contractor-selection-v2/services/smart/search"
    else:
        url = "https://muasamcong.mof.gov.vn/o/egp-portal-contractor-selection-v2/services/popular-keyword/get-list"

    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json;charset=UTF-8",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }

    results = []
    for page in range(3):
        payload = {
            "page": page,
            "size": 50,
            "type": search_type,
            "keySearch": str(keyword).strip()
        }
        try:
            res = requests.post(url, json=payload, headers=headers, timeout=20)
            if res.status_code == 200:
                data = res.json()
                items = []
                if isinstance(data.get("result"), dict):
                    items = data.get("result", {}).get("data", [])
                elif isinstance(data.get("result"), list):
                    items = data.get("result", [])

                if not items:
                    break
                results.extend(items)
            time.sleep(0.3)
        except Exception as e:
            print(f"[API WARN] {search_type} '{keyword}' p.{page}: {e}")
            break

    return results


def run_crawler():
    unique_items = {}

    for kw in KEYWORDS:
        print(f"-> Quét từ khóa: '{kw}'...")
        
        # Quét YCBG
        ycbg = fetch_api("YCBG", kw)
        for item in ycbg:
            code = item.get("notifyNo") or item.get("code") or item.get("id")
            if code and code not in unique_items:
                unique_items[code] = {
                    "type": "YCBG",
                    "code": code,
                    "title": item.get("bidName") or item.get("name") or item.get("title") or "",
                    "investor": item.get("procuringEntityName") or item.get("investorName") or "",
                    "matched_kw": kw
                }

        # Quét TBMT
        tbmt = fetch_api("TBMT", kw)
        for item in tbmt:
            code = item.get("bidNo") or item.get("notifyNo") or item.get("id")
            if code and code not in unique_items:
                unique_items[code] = {
                    "type": "TBMT",
                    "code": code,
                    "title": item.get("bidName") or item.get("name") or item.get("title") or "",
                    "investor": item.get("procuringEntityName") or item.get("investorName") or "",
                    "matched_kw": kw
                }

    return list(unique_items.values())


# ================= 3. RENDER EMAIL HTML & GỬI SMTP =================
def send_report_email(items):
    if not SENDER_EMAIL or not SENDER_PASSWORD:
        print("[ERROR] Chưa thiết lập SENDER_EMAIL hoặc SENDER_PASSWORD trong Secrets!")
        return

    if not items:
        html_body = f"""
        <div style="font-family: Arial, sans-serif; padding: 20px;">
            <h3 style="color: #d9534f;">BÁO CÁO QUÉT THẦU TỰ ĐỘNG - NGÀY {TODAY_STR}</h3>
            <p>Hệ thống đã truy vấn thành công tới máy chủ Mua Sắm Công nhưng không tìm thấy thông báo thầu/YCBG nào mới chứa danh mục từ khóa theo dõi.</p>
        </div>
        """
    else:
        html_body = f"""
        <div style="font-family: Arial, sans-serif; padding: 20px;">
            <h2 style="color: #0275d8;">BÁO CÁO GÓI THẦU & YCBG Y TẾ NGÀY {TODAY_STR}</h2>
            <p>Phát hiện <b>{len(items)}</b> thông báo phù hợp danh mục từ khóa theo dõi:</p>
            <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%;">
                <tr style="background-color: #f2f2f2;">
                    <th align="center">STT</th>
                    <th align="center">Phân loại</th>
                    <th>Mã gói</th>
                    <th>Tên gói thầu / YCBG</th>
                    <th>Bên mời chào giá</th>
                    <th align="center">Từ khóa khớp</th>
                    <th align="center">Chi tiết</th>
                </tr>
        """
        for idx, item in enumerate(items, 1):
            if item['type'] == 'YCBG':
                link = f"https://muasamcong.mof.gov.vn/web/guest/contractor-selection?type=es-ycbg&stepCode=request-quote-step-1&notifyNo={item['code']}"
            else:
                link = f"https://muasamcong.mof.gov.vn/vi/web/guest/initiator?tbmtNo={item['code']}"

            html_body += f"""
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
        html_body += "</table></div>"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"[TBMT & YCBG Y TẾ] Báo cáo ngày {TODAY_STR}"
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL
    msg.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
        print(f"[SUCCESS] Đã gửi báo cáo email thành công tới {RECEIVER_EMAIL}!")
    except Exception as e:
        print(f"[ERROR] Không thể gửi email: {e}")


# ================= 4. LUỒNG CHÍNH =================
if __name__ == "__main__":
    print(f"=== BẮT ĐẦU CRAWL MUA SẮM CÔNG - NGÀY {TODAY_STR} ===")
    data = run_crawler()
    print(f"-> Tìm thấy tổng cộng: {len(data)} gói thầu/YCBG.")
    send_report_email(data)
    print("=== HOÀN THÀNH tiến trình ===")
