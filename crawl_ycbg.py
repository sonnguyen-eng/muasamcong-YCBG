import os
import time
import json
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# 1. CẤU HÌNH BIẾN MÔI TRƯỜNG & DANH SÁCH 19 TỪ KHÓA Y TẾ
RAW_GEMINI_KEYS = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_API_KEYS = [k.strip() for k in RAW_GEMINI_KEYS.split(",") if k.strip()]
current_key_index = 0

SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "").strip()
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD", "").strip()
RECEIVER_EMAIL = os.environ.get("RECEIVER_EMAIL", "").strip() or SENDER_EMAIL

LAST_RUN_ENV = os.environ.get("LAST_RUN_TIMESTAMP", "").strip()

KEYWORDS = [
    "nội soi", "Bàn mổ", "đèn mổ", "hệ thống khí y tế", "vận chuyển mẫu", 
    "ERCP", "Monitor theo dõi bệnh nhân", "Máy hấp tiệt trùng", "Nhiệt độ thấp", 
    "máy gây mê", "Bơm tiêm điện", "máy truyền dịch", "bàn khám sản", 
    "Monitor sản khoa", "máy hấp ướt", "giường ICU", "giường cấp cứu", 
    "Bồn oxy lỏng", "Oxy trung tâm"
]

# 2. DANH SÁCH 14 TỈNH / THÀNH PHỐ MỤC TIÊU
TARGET_LOCATIONS = [
    "Thành phố Đà Nẵng", "Tỉnh Quảng Ngãi", "Tỉnh Đắc Lắc", "Tỉnh Đắk Lắk", "Tỉnh Gia Lai", 
    "Tỉnh Khánh Hòa", "Tỉnh Lâm Đồng", "Thành phố Hồ Chí Minh", "Thành phố Đồng Nai", 
    "Tỉnh Tây Ninh", "Tỉnh Đồng Tháp", "Tỉnh Vĩnh Long", "Tỉnh An Giang", 
    "Thành phố Cần Thơ", "Tỉnh Cà Mau"
]

TZ_VN = timezone(timedelta(hours=7))
NOW_VN = datetime.now(TZ_VN)
TODAY_STR = NOW_VN.strftime("%H:%M %d/%m/%Y")

# Tính toán mốc START_TIME dựa trên lịch chạy tự động trước đó
if LAST_RUN_ENV:
    try:
        START_TIME = datetime.fromisoformat(LAST_RUN_ENV.replace("Z", "+00:00")).astimezone(TZ_VN)
    except Exception:
        START_TIME = NOW_VN - timedelta(hours=24)
else:
    START_TIME = NOW_VN - timedelta(hours=24)

BASE_DOMAIN = "muasamcong.mof.gov.vn"
PRIMARY_MODEL = "gemini-3.8-flash"

# 3. KHỞI TẠO CHROME HEADLESS
def init_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    return driver

# 4. LỌC THỜI GIAN ĐĂNG TRONG KHOẢNG [START_TIME -> NOW_VN]
def is_published_in_time_window(item):
    pub_date_str = item.get("publicDate") or item.get("originalPublicDate") or ""
    if not pub_date_str:
        return True
    
    try:
        clean_date_str = pub_date_str.split(".")[0].replace("Z", "")
        dt_obj = datetime.strptime(clean_date_str, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc).astimezone(TZ_VN)
        return START_TIME <= dt_obj <= NOW_VN
    except Exception:
        return True

# 5. ĐỊNH DẠNG HẠN NỘP BÁO GIÁ DỄ ĐỌC
def format_date_str(date_str):
    if not date_str:
        return "Chưa xác định"
    try:
        clean_str = date_str.split(".")[0].replace("Z", "")
        dt_obj = datetime.strptime(clean_str, "%Y-%m-%dT%H:%M:%S")
        return dt_obj.strftime("%H:%M %d/%m/%Y")
    except Exception:
        return str(date_str)

# 6. KIỂM TRA & CHUẨN HÓA ĐỊA PHƯƠNG
def check_location(item, raw_str):
    found_locs = []
    investor = str(item.get("investorName") or item.get("procuringEntityName") or "").lower()
    title = str(item.get("name") or item.get("pname") or "").lower()
    search_text = f"{investor} {title} {raw_str}"

    locations_arr = item.get("locations", [])
    if isinstance(locations_arr, list):
        for loc in locations_arr:
            if isinstance(loc, dict):
                prov_name = loc.get("provName", "")
                dist_name = loc.get("districtName", "")
                search_text += f" {prov_name} {dist_name}".lower()

    if "đắk lắk" in search_text or "đắc lắc" in search_text or "tây nguyên" in search_text or "buôn ma thuột" in search_text:
        found_locs.append("Tỉnh Đắk Lắk")

    for target in TARGET_LOCATIONS:
        clean_kw = target.replace("Thành phố ", "").replace("Tỉnh ", "").lower()
        if clean_kw in search_text:
            if clean_kw == "đồng nai":
                found_locs.append("Thành phố Đồng Nai")
            elif clean_kw not in ["đắk lắk", "đắc lắc"]:
                found_locs.append(target)

    return list(set(found_locs))

# 7. DEEP-SCAN LẤY CHI TIẾT DANH MỤC HÀNG HÓA YCBG
def get_yccg_form_values(driver, yc_id):
    js_get_yccg = """
    var callback = arguments[arguments.length - 1];
    var ycId = arguments[0];
    
    fetch('/o/egp-portal-contractor-selection-v2/services/get-request-quote', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/plain, */*'
        },
        body: JSON.stringify({
            id: ycId
        })
    })
    .then(response => response.json())
    .then(data => callback(data))
    .catch(err => callback({ error: err.toString() }));
    """
    try:
        res = driver.execute_async_script(js_get_yccg, yc_id)
        if isinstance(res, dict):
            return json.dumps(res, ensure_ascii=False).lower()
    except Exception:
        pass
    return ""

# 8. TẠO URL CHI TIẾT YCBG CHUẨN V2
def build_yccg_detail_url(item, code, yc_id, bid_form):
    url = (
        f"https://{BASE_DOMAIN}/web/guest/contractor-selection?"
        f"p_p_id=egpportalcontractorselectionv2_WAR_egpportalcontractorselectionv2"
        f"&p_p_lifecycle=0&p_p_state=normal&p_p_mode=view"
        f"&_egpportalcontractorselectionv2_WAR_egpportalcontractorselectionv2_render=detail-v2"
        f"&type=es-ycbg"
        f"&stepCode=request-quote-step-1"
        f"&id={yc_id}"
        f"&notifyNo={code}"
        f"&step=es-ycbg"
        f"&bidForm={bid_form or 'VATTU_ALL'}"
    )
    return url

# 9. TRÍCH XUẤT DỮ LIỆU YCBG THEO KHUNG THỜI GIAN
def fetch_yccg_today(driver):
    print(f"-> Kết nối Session Mua Sắm Công YCBG (Khung quét: {START_TIME.strftime('%H:%M %d/%m/%Y')} -> {TODAY_STR})...")
    driver.get(f"https://{BASE_DOMAIN}/web/guest/contractor-selection?render=index")
    time.sleep(10)

    js_get_token = """
    let token = '';
    let entries = window.performance.getEntriesByType('resource');
    for (let e of entries) {
        if (e.name && e.name.includes('token=')) {
            let match = e.name.match(/token=([^&]+)/);
            if (match) {
                token = match[1];
                break;
            }
        }
    }
    return token;
    """
    token_val = driver.execute_script(js_get_token)
    if token_val:
        print(f"-> Token YCBG trích xuất từ Session: {token_val[:20]}...")

    unique_matches = {}

    js_fetch_search_yccg = """
    var callback = arguments[arguments.length - 1];
    var kw = arguments[0];
    var token = arguments[1];
    
    let url = '/o/egp-portal-contractor-selection-v2/services/smart/search';
    if (token) {
        url += '?token=' + token;
    }
    
    fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/plain, */*'
        },
        body: JSON.stringify([{
            pageSize: 50,
            pageNumber: "0",
            query: [{
                index: "es-contractor-selection",
                keyWord: kw,
                matchType: "all-1",
                matchFields: ["notifyNo", "name"],
                filters: [
                    { fieldName: "type", searchType: "in", fieldValues: ["es-ycbg"] }
                ]
            }]
        }])
    })
    .then(response => response.json())
    .then(data => callback(data))
    .catch(err => callback({ error: err.toString() }));
    """

    search_queries = KEYWORDS + ["thiết bị y tế", "y tế", "bệnh viện", "báo giá", "vật tư y tế"]

    for kw in search_queries:
        print(f"-> Truy vấn YCBG cho từ khóa: '{kw}'...")
        try:
            res = driver.execute_async_script(js_fetch_search_yccg, kw, token_val)
            data_list = []
            
            if isinstance(res, list) and len(res) > 0:
                first_item = res[0]
                if isinstance(first_item, dict):
                    data_list = first_item.get("page", {}).get("content", [])
            elif isinstance(res, dict):
                data_list = res.get("page", {}).get("content", [])

            if not isinstance(data_list, list):
                data_list = []

            matched_in_kw = 0
            for item in data_list:
                if not isinstance(item, dict):
                    continue

                if not is_published_in_time_window(item):
                    continue

                code = str(item.get("notifyNo") or item.get("requestQuoteNo") or "")
                yc_id = str(item.get("id") or "")
                bid_form = str(item.get("bidForm") or "VATTU_ALL")

                title = str(item.get("name") or item.get("pname") or "")
                investor = str(item.get("investorName") or "")
                bid_close_date = format_date_str(item.get("bidCloseDate"))

                detail_url = build_yccg_detail_url(item, code, yc_id, bid_form)
                raw_str = json.dumps(item, ensure_ascii=False).lower()

                if yc_id:
                    yccg_detail_str = get_yccg_form_values(driver, yc_id)
                    if yccg_detail_str:
                        raw_str += " " + yccg_detail_str

                matched_kws = [k for k in KEYWORDS if k.lower() in raw_str]
                if matched_kws:
                    matched_province = check_location(item, raw_str)
                    if matched_province:
                        matched_in_kw += 1
                        if code and code not in unique_matches:
                            location_detail = "Tiêu đề" if any(k.lower() in f"{code} {title}".lower() for k in matched_kws) else "Chi tiết Hàng hóa Báo giá"
                            unique_matches[code] = {
                                "code": code,
                                "yc_id": yc_id,
                                "title": title,
                                "investor": investor,
                                "bid_close_date": bid_close_date,
                                "province": ", ".join(matched_province),
                                "matched_kw": ", ".join(matched_kws),
                                "location": location_detail,
                                "detail_url": detail_url,
                                "snippet": raw_str[:1200]
                            }
            print(f"    + Server trả về {len(data_list)} YCBG -> Khớp khung thời gian, địa phương & từ khóa: {matched_in_kw} thông báo.")
            time.sleep(0.5)
        except Exception as e:
            print(f"[CẢNH BÁO FETCH YCBG] Từ khóa '{kw}': {e}")
            continue

    return list(unique_matches.values())

# 10. PHÂN TÍCH YCBG VỚI GEMINI AI (gemini-3.8-flash HOẶC TỰ ĐỔI API KEY NẾU HẾT QUOTA)
def analyze_with_gemini(candidates):
    global current_key_index, GEMINI_API_KEYS
    if not candidates or not GEMINI_API_KEYS:
        return candidates

    while True:
        try:
            from google import genai
            from google.genai import types
            
            key = GEMINI_API_KEYS[current_key_index]
            client = genai.Client(api_key=key)
            
            prompt = f"""
Bạn là chuyên gia phân tích dữ liệu Báo giá Trang thiết bị Y tế.
Dưới đây là danh sách các Yêu cầu báo giá (YCBG) phát hành từ {START_TIME.strftime('%H:%M %d/%m/%Y')} đến {TODAY_STR} đã lọc theo địa phương và 19 từ khóa y tế.

Yêu cầu:
1. Giữ nguyên toàn bộ danh sách đầu vào.
2. Viết 1 câu tóm tắt ngắn gọn danh mục hàng hóa chính cần báo giá.
3. Trả về đúng mảng JSON chứa các object đầy đủ thuộc tính và thêm "reason".

Danh sách:
{json.dumps(candidates, ensure_ascii=False, indent=2)}
Chỉ trả về chuỗi JSON thuần túy (không kèm markdown).
"""
            response = client.models.generate_content(
                model=PRIMARY_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type="application/json")
            )
            
            if response and response.text:
                content = response.text.strip()
                return json.loads(content)

        except Exception as e:
            error_msg = str(e)
            print(f"[CẢNH BÁO AI GOOGLE-GENAI] {error_msg}")
            if any(k in error_msg.lower() for k in ["429", "resource_exhausted", "quota"]):
                if current_key_index + 1 < len(GEMINI_API_KEYS):
                    current_key_index += 1
                    print(f"🔄 Đã đổi sang Gemini API Key thứ [{current_key_index + 1}/{len(GEMINI_API_KEYS)}]")
                    continue
            break
    
    return candidates

# 11. GỬI EMAIL BÁO CÁO YCBG
def send_email_report(matched_list):
    if not RECEIVER_EMAIL:
        print("[LỖI CẤU HÌNH] Chưa khai báo email nhận.")
        return

    receiver_list = [e.strip() for e in RECEIVER_EMAIL.replace("\n", "").split(",") if e.strip()]
    if not receiver_list:
        print("[LỖI CẤU HÌNH] Danh sách email nhận không hợp lệ.")
        return

    email_subject = f"[YCCG TBYT - Địa bàn phụ trách] Báo cáo Yêu cầu báo giá ({START_TIME.strftime('%H:%M %d/%m')} - {TODAY_STR})"

    if not matched_list:
        html_body = f"""
        <div style="font-family: Arial, sans-serif; padding: 20px;">
            <h3 style="color: #d9534f;">BÁO CÁO YÊU CẦU BÁO GIÁ (YCCG)</h3>
            <p>Hệ thống đã quét dữ liệu từ <b>{START_TIME.strftime('%H:%M %d/%m/%Y')}</b> đến <b>{TODAY_STR}</b> nhưng chưa phát hiện Yêu cầu báo giá mới khớp 19 từ khóa y tế tại 14 địa phương theo dõi.</p>
        </div>
        """
    else:
        rows = ""
        for idx, item in enumerate(matched_list, 1):
            code = item.get("code", "")
            title = item.get("title", "")
            investor = item.get("investor", "")
            bid_close_date = item.get("bid_close_date", "Chưa xác định")
            province = item.get("province", "Theo dõi")
            location = item.get("location", "Chi tiết Hàng hóa Báo giá")
            reason = item.get("reason") or "Khớp từ khóa theo dõi y tế trong danh mục Báo giá"
            matched_kw = item.get("matched_kw", "")
            detail_url = item.get("detail_url") or f"https://{BASE_DOMAIN}/web/guest/contractor-selection?render=index"
            
            rows += f"""
            <tr>
                <td align="center">{idx}</td>
                <td><b>{code}</b></td>
                <td>{title}</td>
                <td align="center"><span style="color: #d9534f; font-weight: bold;">{bid_close_date}</span></td>
                <td>{investor}</td>
                <td align="center"><b><span style="color: #0275d8;">{province}</span></b></td>
                <td align="center"><span style="background-color: #ffffcc; padding: 3px 6px; border-radius: 3px;">{matched_kw}</span></td>
                <td align="center"><i>{location}</i></td>
                <td><small style="color: #333;">{reason}</small></td>
                <td align="center"><a href="{detail_url}" target="_blank" style="color: #0275d8; font-weight: bold;">Xem ngay</a></td>
            </tr>
            """
            
        html_body = f"""
        <div style="font-family: Arial, sans-serif; padding: 20px;">
            <h2 style="color: #0275d8;">BÁO CÁO YÊU CẦU BÁO GIÁ (YCCG)</h2>
            <p>Khung thời gian quét: từ <b>{START_TIME.strftime('%H:%M %d/%m/%Y')}</b> đến <b>{TODAY_STR}</b></p>
            <p>Đã lọc phát hiện <b>{len(matched_list)}</b> Yêu cầu báo giá Y tế thuộc địa bàn phụ trách:</p>
            <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%; border-color: #ddd;">
                <tr style="background-color: #e6f2ff;">
                    <th align="center">STT</th>
                    <th>Mã YCCG</th>
                    <th>Nội Dung Yêu Cầu Báo Giá</th>
                    <th align="center">Hạn Nộp Báo Giá</th>
                    <th>Đơn Vị Yêu Cầu</th>
                    <th align="center">Tỉnh / TP</th>
                    <th align="center">Từ Khóa Khớp</th>
                    <th align="center">Vị Trí Khớp</th>
                    <th>Phân Tích Chi Tiết</th>
                    <th align="center">Chi Tiết</th>
                </tr>
                {rows}
            </table>
        </div>
        """

    if SENDER_EMAIL and SENDER_PASSWORD:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = email_subject
        msg["From"] = SENDER_EMAIL
        msg["To"] = ", ".join(receiver_list)
        msg.attach(MIMEText(html_body, "html"))
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
                server.login(SENDER_EMAIL, SENDER_PASSWORD)
                server.sendmail(SENDER_EMAIL, receiver_list, msg.as_string())
            print(f"[SUCCESS] Đã gửi báo cáo YCBG thành công tới các email: {', '.join(receiver_list)}!")
        except Exception as e:
            print(f"[LỖI GỬI EMAIL SMTP] {e}")

def main():
    print(f"=== CRAWL & DEEP-SCAN YCBG (Khung quét: {START_TIME.strftime('%H:%M %d/%m/%Y')} -> {TODAY_STR}) ===")
    driver = init_driver()
    try:
        matched_list = fetch_yccg_today(driver)
        final_matches = analyze_with_gemini(matched_list)
        send_email_report(final_matches)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
