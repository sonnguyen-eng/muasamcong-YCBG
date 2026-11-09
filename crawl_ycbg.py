import os
import time
import smtplib
import requests
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ================= 1. CẤU HÌNH TỪ KHÓA & MÔI TRƯỜNG =================
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "").strip()
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD", "").strip()
RECEIVER_EMAIL = SENDER_EMAIL

KEYWORDS = [
    "nội soi", "nội soi tiêu hóa", "nội soi khí phế quản", 
    "Bàn mổ", "đèn mổ", "hệ thống khí y tế", "vận chuyển mẫu", "ERCP"
]
EXCLUDE_KEYWORD = "ống soi"

TZ_VN = timezone(timedelta(hours=7))
TODAY_STR = datetime.now(TZ_VN).strftime("%d/%m/%Y")


# ================= 2. QUÉT TRỰC TIẾP API YCBG (PAYLOAD F12 MẢNG) =================
def fetch_ycbg_api():
    url = "https://muasamcong.mof.gov.vn/o/egp-portal-contractor-selection-v2/services/smart/search"
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json;charset=UTF-8",
        "Origin": "https://muasamcong.mof.gov.vn",
        "Referer": "https://muasamcong.mof.gov.vn/web/guest/contractor-selection",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    }
    
    collected_items = []
    # Quét 4 trang đầu tiên (200 YCBG mới nhất)
    for page in range(4):
        payload = [
            {
                "pageSize": 50,
                "pageNumber": str(page),
                "query": [
                    {
                        "index": "es-ycbg",
                        "matchType": "all-1",
                        "matchFields": ["notifyNo", "bidName"]
                    },
                    {
                        "name": "type",
                        "searchType": "in",
                        "fieldValues": ["es-ycbg"]
                    }
                ]
            }
        ]
        try:
            res = requests.post(url, json=payload, headers=headers, timeout=25)
            if res.status_code == 200:
                data = res.json()
                items = []
                if isinstance(data, list) and len(data) > 0:
                    items = data[0].get("result", {}).get("data", [])
                elif isinstance(data, dict):
                    items = data.get("result", {}).get("data", [])

                if not items:
                    break
                collected_items.extend(items)
            time.sleep(0.3)
        except Exception as e:
            print(f"[CẢNH BÁO YCBG API] Trang {page}: {e}")
            break

    return collected_items


# ================= 3. ĐỐI SOÁT DỮ LIỆU & RENDER HTML =================
def main_ycbg():
    print(f"=== BẮT ĐẦU QUÉT YCBG - NGÀY {TODAY_STR} ===")
    raw_list = fetch_ycbg_api()
    print(f"-> Thu thập từ server: {len(raw_list)} YCBG.")
    
    unique_matches = {}
    for item in raw_list:
        code = str(item.get("notifyNo") or item.get("code") or item.get("id") or "")
        title = str(item.get("bidName") or item.get("name") or item.get("title") or "")
        investor = str(item.get("procuringEntityName") or item.get("investorName") or "")
        
        full_text = f"{code} {title} {investor}".lower()
        
        # Bỏ qua nếu có "ống soi"
        if EXCLUDE_KEYWORD.lower() in full_text:
            continue
            
        # Lọc theo danh mục từ khóa
        for kw in KEYWORDS:
            if kw.lower() in full_text:
                if code and code not in unique_matches:
                    unique_matches[code] = {
                        "code": code,
                        "title": title,
                        "investor": investor,
                        "matched_kw": kw
                    }
                break

    matched_list = list(unique_matches.values())
    print(f"-> Khớp từ khóa: {len(matched_list)} gói YCBG.")

    # Tạo nội dung Email
    if not matched_list:
        html_body = f"""
        <div style="font-family: Arial, sans-serif; padding: 20px;">
            <h3 style="color: #d9534f;">YÊU CẦU BÁO GIÁ (YCBG) NGÀY {TODAY_STR}</h3>
            <p>Hệ thống đã truy vấn thành công nhưng không có YCBG mới nào chứa các từ khóa theo dõi trong ngày.</p>
        </div>
        """
    else:
        html_body = f"""
        <div style="font-family: Arial, sans-serif; padding: 20px;">
            <h2 style="color: #0275d8;">BÁO CÁO YÊU CẦU BÁO GIÁ (YCBG) NGÀY {TODAY_STR}</h2>
            <p>Phát hiện <b>{len(matched_list)}</b> YCBG phù hợp danh mục theo dõi:</p>
            <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%;">
                <tr style="background-color: #e6f2ff;">
                    <th align="center">STT</th>
                    <th>Mã YCBG</th>
                    <th>Tên Yêu Cầu Báo Giá</th>
                    <th>Bên Mời Chào Giá</th>
                    <th align="center">Từ Khóa Khớp</th>
                    <th align="center">Chi Tiết</th>
                </tr>
        """
        for idx, item in enumerate(matched_list, 1):
            link = f"https://muasamcong.mof.gov.vn/web/guest/contractor-selection?type=es-ycbg&stepCode=request-quote-step-1&notifyNo={item['code']}"
            html_body += f"""
                <tr>
                    <td align="center">{idx}</td>
                    <td><b>{item['code']}</b></td>
                    <td>{item['title']}</td>
                    <td>{item['investor']}</td>
                    <td align="center"><span style="background-color: #ffffcc;">{item['matched_kw']}</span></td>
                    <td align="center"><a href="{link}" target="_blank">Xem ngay</a></td>
                </tr>
            """
        html_body += "</table></div>"

    # Gửi Email SMTP
    if SENDER_EMAIL and SENDER_PASSWORD:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[YCBG -Nội Soi] Báo cáo ngày {TODAY_STR}"
        msg["From"] = SENDER_EMAIL
        msg["To"] = RECEIVER_EMAIL
        msg.attach(MIMEText(html_body, "html"))
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(SENDER_EMAIL, SENDER_PASSWORD)
                server.sendmail(SENDER_EMAIL, RECEIVER_EMAIL, msg.as_string())
            print(f"[SUCCESS] Đã gửi báo cáo YCBG thành công tới {RECEIVER_EMAIL}!")
        except Exception as e:
            print(f"[LỖI GỬI EMAIL] {e}")
    else:
        print("[CẢNH BÁO] Thiếu SENDER_EMAIL hoặc SENDER_PASSWORD trong GitHub Secrets!")


if __name__ == "__main__":
    main_ycbg()
