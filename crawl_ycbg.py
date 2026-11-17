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
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager

# ==============================================================================
# 1. CẤU HÌNH BIẾN MÔI TRƯỜNG & BỘ TỪ KHÓA LỌC CHÍNH XÁC Y TẾ / PACS / DỰ ÁN BV
# ==============================================================================
RAW_GEMINI_KEYS = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_API_KEYS = [k.strip() for k in RAW_GEMINI_KEYS.split(",") if k.strip()]
current_key_index = 0

SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "").strip()
SENDER_PASSWORD = os.environ.get("SENDER_PASSWORD", "").strip()
RECEIVER_EMAIL = os.environ.get("RECEIVER_EMAIL", "").strip() or SENDER_EMAIL

LAST_RUN_ENV = os.environ.get("LAST_RUN_TIMESTAMP", "").strip()
EVENT_NAME_ENV = os.environ.get("GITHUB_EVENT_NAME", "").strip()

# Nhóm 1: Từ khóa thiết bị y tế & giải pháp PACS đặc thù (khớp trực tiếp)
SPECIFIC_DEVICE_KEYWORDS = [
    # Nội soi - Phẫu thuật - Laser
    "nội soi", "ống soi", "optic nội soi", "ercp", "robot phẫu thuật",
    "tán sỏi laser", "máy tán sỏi",
    # Phòng mổ - Gây mê - Hồi sức - Giường
    "bàn mổ", "đèn mổ", "máy gây mê", "monitor theo dõi bệnh nhân",
    "máy theo dõi bệnh nhân", "bơm tiêm điện", "máy truyền dịch",
    "giường icu", "giường cấp cứu", "giường đa năng", "giường bệnh",
    "hồi sức cấp cứu", "hồi sức sơ sinh", "máy thở", "máy phá rung tim",
    # Khí y tế - Vận chuyển - Tiệt trùng
    "hệ thống khí y tế", "bồn oxy lỏng", "oxy trung tâm", "vận chuyển mẫu",
    "máy hấp tiệt trùng", "nhiệt độ thấp", "máy hấp ướt",
    # Sản khoa - Chẩn đoán hình ảnh - PACS - Chuyên khoa
    "bàn khám sản", "monitor sản khoa", "c-arm", "c arm", "x-quang",
    "máy siêu âm", "siêu âm màu", "siêu âm chẩn đoán", "thận nhân tạo",
    "máy chạy thận", "hdf online",
    "pacs", "ris/pacs", "ris - pacs", "lưu trữ và truyền tải hình ảnh",
    # Gói mua sắm / chào giá thiết bị y tế tổng thể
    "thiết bị y tế chuyên môn", "thiết bị y tế chuyên dùng",
    "thiết bị y tế cấp thiết", "mua sắm thiết bị chuyên môn",
    "mua sắm thiết bị y tế", "mua thiết bị y tế",
    "cung cấp, lắp đặt thiết bị y tế", "cung cấp lắp đặt thiết bị y tế",
    "trang thiết bị y tế"
]

# Nhóm 2: Từ khóa có điều kiện (CHỈ khớp khi đi kèm đơn vị/công trình ngành Y tế)
CONDITIONAL_KEYWORDS = [
    "thẩm định giá", "chẩn đoán hình ảnh", "phục hồi chức năng"
]

# Thực thể / Công trình thuộc ngành Y tế
MEDICAL_ENTITY_TERMS = [
    "bệnh viện", "trung tâm y tế", "viện tim", "ngành y tế", "sở y tế",
    "đại học y khoa", "đại học y dược", "khối khám bệnh", "khối bệnh nhiệt đới",
    "khoa khám bệnh", "khu khám bệnh", "khu hồi sức", "trung tâm sơ sinh",
    "trung tâm y khoa", "trạm y tế", "y tế khu vực"
]

# Hành động YCBG tổng cho dự án xây mới / cải tạo nâng cấp công trình BV
HOSPITAL_PROJECT_ACTIONS = [
    "xây dựng mới", "nâng cấp", "cải tạo, sửa chữa", "cải tạo sửa chữa",
    "dự án đầu tư", "xây dựng khối", "xây dựng khu",
    "cung cấp, lắp đặt thiết bị", "cung cấp lắp đặt thiết bị",
    "mua sắm thiết bị", "trang bị thiết bị"
]

# Từ khóa loại trừ các dự án ngoài ngành y tế hoặc kiểm xạ/khám sức khỏe định kỳ
EXCLUDE_NON_MEDICAL_PATTERNS = [
    "thẩm định giá đất", "thi hành bản án", "tuần tra, kiểm tra rừng",
    "dây chuyền kiểm định phương tiện", "cầu đi bộ", "tái định cư",
    "công viên", "nhà văn hóa", "trường tiểu học", "trường thcs", "trường thpt",
    "cao đẳng kỹ thuật", "trụ sở văn phòng", "hệ thống chiếu sáng",
    "mở rộng, nâng cấp tuyến đường", "kiểm định máy x-quang",
    "kiểm xạ an toàn", "liều kế cá nhân", "khám sức khỏe định kỳ"
]

# Cụm từ nhận diện gói thuần THUÊ dịch vụ phần mềm (không phải mua đứt/đầu tư PACS)
RENTAL_SOFTWARE_TERMS = [
    "thuê dịch vụ sử dụng phần mềm", "thuê dịch vụ phần mềm",
    "thuê hệ thống phần mềm", "thuê phần mềm", "cung cấp dịch vụ phần mềm"
]

BROAD_QUERIES = [
    "thiết bị y tế", "trang thiết bị y tế", "bệnh viện",
    "trung tâm y tế", "ngành y tế", "ban quản lý dự án",
    "xây dựng mới", "nâng cấp", "mua sắm"
]

# ==============================================================================
# 2. DANH SÁCH 14 TỈNH / THÀNH PHỐ MỤC TIÊU PHỤ TRÁCH
# ==============================================================================
LOCATION_ALIASES = {
    "Thành phố Đà Nẵng": ["đà nẵng", "quảng nam", "tam kỳ", "hội an", "việt - hàn đà nẵng"],
    "Tỉnh Quảng Ngãi": ["quảng ngãi", "kon tum"],
    "Tỉnh Đắk Lắk": ["đắk lắk", "đắc lắc", "tây nguyên", "buôn ma thuột", "phú yên", "tuy hòa"],
    "Tỉnh Gia Lai": ["gia lai", "pleiku", "bình định", "quy nhơn"],
    "Tỉnh Khánh Hòa": ["khánh hòa", "nha trang", "ninh thuận", "phan rang"],
    "Tỉnh Lâm Đồng": ["lâm đồng", "đà lạt", "bảo lộc", "đắk nông", "bình thuận", "phan thiết"],
    "Thành phố Hồ Chí Minh": [
        "hồ chí minh", "tp.hcm", "tphcm", "tp hcm", "sài gòn", "thủ đức",
        "bình dương", "bà rịa", "vũng tàu", "phú mỹ", "nhi đồng", "bình dân",
        "viện tim", "nhân ái", "đại học y dược", "ung bướu", "gò vấp",
        "bệnh nhiệt đới", "phạm ngọc thạch", "chấn thương", "lê văn thịnh",
        "thuận an", "tân uyên"
    ],
    "Thành phố Đồng Nai": ["đồng nai", "biên hòa", "long khánh", "bình phước", "đồng xoài", "long thành"],
    "Tỉnh Tây Ninh": ["tây ninh", "long an", "tân an", "thủ thừa", "tân hưng"],
    "Tỉnh Đồng Tháp": ["đồng tháp", "cao lãnh", "sa đéc", "tiền giang", "mỹ tho", "quân y 120"],
    "Tỉnh Vĩnh Long": ["vĩnh long", "bến tre", "trà vinh", "nguyễn đình chiểu"],
    "Tỉnh An Giang": ["an giang", "long xuyên", "châu đốc", "kiên giang", "rạch giá", "phú quốc", "ung bướu kiên giang"],
    "Thành phố Cần Thơ": ["cần thơ", "hậu giang", "sóc trăng", "thốt nốt"],
    "Tỉnh Cà Mau": ["cà mau", "bạc liêu"]
}

TZ_VN = timezone(timedelta(hours=7))
NOW_VN = datetime.now(TZ_VN)
TODAY_STR = NOW_VN.strftime("%H:%M %d/%m/%Y")

if LAST_RUN_ENV:
    try:
        parsed_last_run = datetime.fromisoformat(LAST_RUN_ENV.replace("Z", "+00:00")).astimezone(TZ_VN)
        START_TIME = parsed_last_run - timedelta(minutes=15)
    except Exception:
        START_TIME = NOW_VN - timedelta(hours=24)
else:
    START_TIME = NOW_VN - timedelta(hours=24)

BASE_DOMAIN = "muasamcong.mof.gov.vn"
PRIMARY_MODEL = "gemini-2.5-flash"
FALLBACK_MODEL = "gemini-2.5-flash-lite"

SERVER_MAX_PAGE_SIZE = 50
SPECIFIC_MAX_RECORDS = 150
BROAD_MAX_RECORDS = 500

# ==============================================================================
# 3. KHỞI TẠO CHROME HEADLESS
# ==============================================================================
def init_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

# ==============================================================================
# 4. LỌC THỜI GIAN ĐĂNG & ĐỊNH DẠNG HẠN NỘP BÁO GIÁ
# ==============================================================================
def is_published_in_time_window(item):
    pub_date_str = item.get("publicDate") or item.get("originalPublicDate") or ""
    if not pub_date_str:
        return True
    try:
        clean_date_str = pub_date_str.split(".")[0].replace("Z", "")
        dt_obj = datetime.strptime(clean_date_str, "%Y-%m-%dT%H:%M:%S").replace(tzinfo=TZ_VN)
        return START_TIME <= dt_obj <= NOW_VN
    except Exception:
        return True

def format_bid_close_date(item):
    close_date_str = (
        item.get("bidCloseDate")
        or item.get("receptionDateTo")
        or item.get("closeDate")
        or item.get("expireDate")
        or ""
    )
    if not close_date_str:
        return "Chưa xác định"
    try:
        clean_str = str(close_date_str).split(".")[0].replace("Z", "")
        dt_obj = datetime.strptime(clean_str, "%Y-%m-%dT%H:%M:%S")
        return dt_obj.strftime("%H:%M %d/%m/%Y")
    except Exception:
        return str(close_date_str)

# ==============================================================================
# 5. KIỂM TRA & CHUẨN HÓA ĐỊA PHƯƠNG TRONG 14 TỈNH / THÀNH PHỐ MỤC TIÊU
# ==============================================================================
def check_location(item, raw_str):
    found_locs = []
    investor = str(item.get("investorName") or item.get("procuringEntityName") or "").lower()
    title = str(item.get("bidName") or item.get("name") or "").lower()
    search_text = f"{investor} {title} {raw_str}".lower()

    locations_arr = item.get("locations", [])
    if isinstance(locations_arr, list):
        for loc in locations_arr:
            if isinstance(loc, dict):
                prov_name = loc.get("provName", "")
                dist_name = loc.get("districtName", "")
                search_text += f" {prov_name} {dist_name}".lower()

    for canonical_name, aliases in LOCATION_ALIASES.items():
        if any(alias in search_text for alias in aliases):
            found_locs.append(canonical_name)

    return list(set(found_locs))

# ==============================================================================
# 6. BÓC TÁCH SÂU CHI TIẾT YCBG (API GET-REQUEST-QUOTE + FALLBACK VIEW-PRICE-REQ)
# ==============================================================================
def get_yccg_detail_values(driver, req_id, req_type, token_val):
    """
    Gọi API chính xác /services/get-request-quote (cho es-ycbg) để bóc tách:
    - Bảng danh mục hàng hóa chi tiết trong formValue (category, description, qty, unit)
    - Tên file đính kèm (otherFileName / briefFileName)
    """
    js_get_detail = """
    var callback = arguments[arguments.length - 1];
    var reqId = arguments[0];
    var reqType = arguments[1];
    var token = arguments[2];

    let endpoint = (reqType === 'es-price-req')
        ? '/o/egp-portal-contractor-selection-v2/services/expose/lcnt/bid-po-bidp-price-req-view/view-price-req'
        : '/o/egp-portal-contractor-selection-v2/services/get-request-quote';

    if (token) {
        endpoint += '?token=' + token;
    }

    fetch(endpoint, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/plain, */*'
        },
        body: JSON.stringify({ id: reqId })
    })
    .then(response => response.json())
    .then(data => callback(data))
    .catch(err => callback({ error: err.toString() }));
    """
    extracted_items = []
    attached_files = []
    detail_raw_lower = ""

    try:
        res = driver.execute_async_script(js_get_detail, req_id, req_type, token_val)
        if isinstance(res, dict) and not res.get("error"):
            detail_raw_lower = json.dumps(res, ensure_ascii=False).lower()
            rq_obj = res.get("bidoRequestQuote") or res.get("bidPoBidpPriceReqView") or res

            if isinstance(rq_obj, dict):
                for f_key in ["otherFileName", "briefFileName", "decisionFileName"]:
                    f_val = rq_obj.get(f_key)
                    if f_val:
                        attached_files.append(str(f_val))

                form_val_raw = rq_obj.get("formValue")
                if isinstance(form_val_raw, str) and form_val_raw.strip():
                    try:
                        form_json = json.loads(form_val_raw)
                        forms_dict = form_json.get("forms", {})
                        if isinstance(forms_dict, dict):
                            for _, f_data in forms_dict.items():
                                table_rows = f_data.get("Table", []) if isinstance(f_data, dict) else []
                                for row in table_rows:
                                    if isinstance(row, dict):
                                        cat = str(row.get("category") or "").strip()
                                        desc = str(row.get("description") or "").strip()
                                        qty = row.get("qty") or ""
                                        unit = str(row.get("unit") or "").strip()
                                        if cat:
                                            item_line = f"{cat}"
                                            if qty != "":
                                                item_line += f" (SL: {qty} {unit})".strip()
                                            if desc and desc.lower() != cat.lower():
                                                item_line += f" - {desc[:120]}"
                                            extracted_items.append(item_line)
                    except Exception:
                        pass
    except Exception:
        pass

    return extracted_items, attached_files, detail_raw_lower

# ==============================================================================
# 7. TRÍCH XUẤT & LÀM MỚI RECAPTCHA TOKEN TỪ SESSION TRÌNH DUYỆT
# ==============================================================================
def get_latest_token_from_perf(driver):
    js_get_token = """
    let token = '';
    let entries = window.performance.getEntriesByType('resource');
    for (let i = entries.length - 1; i >= 0; i--) {
        let e = entries[i];
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
    return driver.execute_script(js_get_token) or ""

def refresh_session_token(driver, kw_hint="y tế"):
    driver.execute_script("window.performance.clearResourceTimings();")
    try:
        inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='text'], input[placeholder*='tìm'], input[placeholder*='Tìm'], input[placeholder*='từ khóa']")
        for inp in inputs:
            if inp.is_displayed():
                inp.click()
                inp.send_keys(Keys.CONTROL, "a")
                inp.send_keys(Keys.BACKSPACE)
                inp.send_keys(kw_hint)
                inp.send_keys(Keys.RETURN)
                time.sleep(5)
                new_tok = get_latest_token_from_perf(driver)
                if new_tok:
                    return new_tok
                break
    except Exception:
        pass

    driver.get(f"https://{BASE_DOMAIN}/web/guest/contractor-selection?render=index")
    time.sleep(8)
    return get_latest_token_from_perf(driver)

# ==============================================================================
# 8. BỘ LỌC 2 LỚP: LOẠI BỎ YCBG NGOÀI Y TẾ & BẮT YCBG TỔNG DỰ ÁN XÂY MỚI/NÂNG CẤP BV
# ==============================================================================
def evaluate_ycbg_medical_relevance(title, investor, extracted_items, attached_files, raw_str):
    """
    Đánh giá độ liên quan thực sự đến TBYT, mua sắm/đầu tư PACS hoặc YCBG tổng cho Dự án xây mới/nâng cấp BV:
    - Bắt trọn YCBG thiết bị lẻ + mua đứt PACS + YCBG tổng cho dự án xây mới/cải tạo nâng cấp bệnh viện.
    - Loại bỏ tuyệt đối YCBG ngoài ngành y tế (trường học, giao thông, công viên, UBND xã...)
      và các YCBG thuần THUÊ dịch vụ phần mềm.
    """
    title_lower = title.lower()
    investor_lower = investor.lower()
    items_lower = " ".join(extracted_items).lower()
    files_lower = " ".join(attached_files).lower()
    core_text = f"{title_lower} {investor_lower} {items_lower} {files_lower}"

    # 1. Chốt chặn loại trừ các dự án ngoài ngành y tế hoặc kiểm xạ/khám sức khỏe định kỳ
    if any(excl in core_text for excl in EXCLUDE_NON_MEDICAL_PATTERNS):
        return False, False, []

    if any(infra in title_lower for infra in ["cầu đi bộ", "tuyến đường", "khu tái định cư", "hệ thống chiếu sáng", "trụ sở", "nhà văn hóa", "công viên"]):
        return False, False, []

    # 2. Loại bỏ gói thuần THUÊ dịch vụ phần mềm (không phải mua đứt/đầu tư PACS)
    is_software_rental = any(r in core_text for r in RENTAL_SOFTWARE_TERMS)
    is_purchase_action = any(p in core_text for p in ["mua sắm", "mua ", "đầu tư", "cung cấp", "lắp đặt", "trang bị"])
    if is_software_rental and not is_purchase_action:
        return False, False, []

    # Nếu chỉ là phần mềm bệnh án điện tử / HIS đơn thuần mà không có PACS hoặc TBYT thì bỏ qua
    if ("bệnh án điện tử" in core_text or "phần mềm quản lý bệnh viện" in core_text) and not any(
        p in core_text for p in ["pacs", "ris/pacs", "ris - pacs", "lưu trữ và truyền tải hình ảnh", "thiết bị y tế"]
    ):
        return False, False, []

    # 3. Kiểm tra thực thể y tế (Bệnh viện, TTYT, Sở Y tế, hoặc Ban QLDA đầu tư công trình Bệnh viện)
    has_medical_entity = any(ent in f"{title_lower} {investor_lower}" for ent in MEDICAL_ENTITY_TERMS)

    # 4. Kiểm tra từ khóa thiết bị y tế & PACS đặc thù trên tiêu đề + bảng danh mục hàng hóa
    search_scope = f"{title_lower} {items_lower}" if items_lower.strip() else raw_str
    matched_specific = [k for k in SPECIFIC_DEVICE_KEYWORDS if k in search_scope]

    # 5. Kiểm tra từ khóa có điều kiện (CHỈ tính khi thuộc thực thể y tế và xuất hiện trong tiêu đề/danh mục)
    matched_cond = []
    if has_medical_entity:
        for ck in CONDITIONAL_KEYWORDS:
            if ck in title_lower or ck in items_lower:
                matched_cond.append(ck)

    # 6. Nhận diện YCBG Tổng thuộc Dự án Xây mới / Cải tạo nâng cấp Công trình Bệnh viện
    is_hospital_proj_ycbg = False
    hospital_proj_label = ""
    if has_medical_entity:
        matched_actions = [act for act in HOSPITAL_PROJECT_ACTIONS if act in title_lower]
        # Nếu tiêu đề thuộc công trình BV có hành động đầu tư/xây mới/nâng cấp/cung cấp lắp đặt thiết bị
        if matched_actions:
            is_hospital_proj_ycbg = True
            hospital_proj_label = f"YCBG Dự án công trình BV ({', '.join(matched_actions[:2])})"

    all_matched_tags = list(dict.fromkeys(matched_specific + matched_cond))
    if is_hospital_proj_ycbg and hospital_proj_label not in all_matched_tags:
        all_matched_tags.append(hospital_proj_label)

    is_relevant = bool(all_matched_tags)
    return is_relevant, is_hospital_proj_ycbg, all_matched_tags

# ==============================================================================
# 9. TRÍCH XUẤT THÔNG TIN YCBG THEO KHUNG THỜI GIAN PHÂN TẦNG (150 - 500)
# ==============================================================================
def fetch_yccg_today(driver):
    print(f"-> Chế độ chạy: {EVENT_NAME_ENV or 'local'} | Mốc lịch sử gốc: {LAST_RUN_ENV or 'Mặc định 24h'}")
    print(f"-> Mở Session Mua Sắm Công YCBG (Khung quét có đệm: {START_TIME.strftime('%H:%M %d/%m/%Y')} -> {TODAY_STR})...")
    driver.get(f"https://{BASE_DOMAIN}/web/guest/contractor-selection?render=index")
    time.sleep(9)

    token_val = get_latest_token_from_perf(driver)
    if not token_val:
        token_val = refresh_session_token(driver, "y tế")

    if token_val:
        print(f"-> Token bảo mật trích xuất từ Session: {token_val[:20]}...")
    else:
        print(f"-> [CẢNH BÁO SESSION] Chưa trích xuất được token (Page Title: '{driver.title}').")

    unique_matches = {}
    scanned_codes = set()
    api_calls_since_refresh = 0

    from_date_str = START_TIME.strftime("%Y-%m-%dT%H:%M:%S.000")
    to_date_str = NOW_VN.strftime("%Y-%m-%dT%H:%M:%S.999")

    js_fetch_search = """
    var callback = arguments[arguments.length - 1];
    var kw = arguments[0];
    var pageNum = arguments[1];
    var pageSize = arguments[2];
    var token = arguments[3];
    var fromDate = arguments[4];
    var toDate = arguments[5];

    let url = '/o/egp-portal-contractor-selection-v2/services/smart/search';
    if (token) {
        url += '?token=' + token;
    }

    const payloadObj = [{
        pageSize: pageSize,
        pageNumber: String(pageNum),
        query: [{
            index: "es-contractor-selection",
            keyWord: kw,
            matchType: "all-1",
            matchFields: ["notifyNo", "bidName", "name"],
            filters: [
                { fieldName: "type", searchType: "in", fieldValues: ["es-ycbg", "es-price-req"] },
                { fieldName: "publicDate", searchType: "range", from: fromDate, to: toDate }
            ]
        }]
    }];

    fetch(url, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/plain, */*'
        },
        body: JSON.stringify(payloadObj)
    })
    .then(async response => {
        const rawText = await response.text();
        try {
            callback({
                status: response.status,
                body: JSON.parse(rawText)
            });
        } catch (e) {
            callback({
                status: response.status,
                rawText: rawText.substring(0, 300)
            });
        }
    })
    .catch(err => callback({ error: err.toString() }));
    """

    query_plan = []
    for kw in SPECIFIC_DEVICE_KEYWORDS:
        query_plan.append((kw, SPECIFIC_MAX_RECORDS))
    for kw in BROAD_QUERIES:
        query_plan.append((kw, BROAD_MAX_RECORDS))

    for kw, max_records in query_plan:
        if api_calls_since_refresh >= 12:
            new_tok = refresh_session_token(driver, kw)
            if new_tok:
                token_val = new_tok
            api_calls_since_refresh = 0

        print(f"-> Truy vấn API Smart Search YCBG cho: '{kw}' (Mục tiêu tối đa {max_records} bản ghi)...")
        matched_in_kw = 0
        province_in_kw = 0
        fetched_in_kw = 0
        total_elements = None
        page_num = 0
        retried_token_for_kw = False

        while fetched_in_kw < max_records:
            current_page_size = min(SERVER_MAX_PAGE_SIZE, max_records - fetched_in_kw)
            try:
                raw_res = driver.execute_async_script(
                    js_fetch_search,
                    kw,
                    page_num,
                    current_page_size,
                    token_val,
                    from_date_str,
                    to_date_str
                )
                api_calls_since_refresh += 1

                res = raw_res.get("body") if isinstance(raw_res, dict) else raw_res
                data_list = []

                if isinstance(res, list) and len(res) > 0:
                    first_item = res[0]
                    if isinstance(first_item, dict):
                        page_obj = first_item.get("page", {})
                        data_list = page_obj.get("content", [])
                        if total_elements is None:
                            total_elements = page_obj.get("totalElements")
                elif isinstance(res, dict):
                    page_obj = res.get("page", {})
                    data_list = page_obj.get("content", [])
                    if total_elements is None:
                        total_elements = page_obj.get("totalElements")

                if (not isinstance(data_list, list) or not data_list) and page_num == 0 and total_elements is None and not retried_token_for_kw:
                    retried_token_for_kw = True
                    new_tok = refresh_session_token(driver, kw)
                    if new_tok and new_tok != token_val:
                        token_val = new_tok
                        api_calls_since_refresh = 0
                        continue

                if not isinstance(data_list, list) or not data_list:
                    break

                fetched_in_kw += len(data_list)

                for item in data_list:
                    if not isinstance(item, dict):
                        continue

                    if not is_published_in_time_window(item):
                        continue

                    code = str(item.get("notifyNo") or item.get("notifyNoStand") or item.get("bidNo") or item.get("id") or "")
                    if not code or code in unique_matches or code in scanned_codes:
                        continue

                    scanned_codes.add(code)

                    req_id = str(item.get("id") or "")
                    req_type = str(item.get("type") or "es-ycbg")
                    bid_name_raw = item.get("bidName")
                    if isinstance(bid_name_raw, list) and len(bid_name_raw) > 0:
                        title = str(bid_name_raw[0]).replace("\n", " ").strip()
                    else:
                        title = str(bid_name_raw or item.get("name") or "").replace("\n", " ").strip()

                    investor = str(item.get("investorName") or item.get("procuringEntityName") or "").strip()
                    bid_close_date_str = format_bid_close_date(item)

                    if req_id:
                        step_code = "price-req-step-1" if req_type == "es-price-req" else "request-quote-step-1"
                        detail_url = (
                            f"https://{BASE_DOMAIN}/web/guest/contractor-selection?"
                            f"p_p_id=egpportalcontractorselectionv2_WAR_egpportalcontractorselectionv2"
                            f"&p_p_lifecycle=0&p_p_state=normal&p_p_mode=view"
                            f"&_egpportalcontractorselectionv2_WAR_egpportalcontractorselectionv2_render=detail-v2"
                            f"&type={req_type}&stepCode={step_code}&id={req_id}&notifyNo={code}"
                        )
                    else:
                        detail_url = f"https://{BASE_DOMAIN}/web/guest/contractor-selection?render=index"

                    raw_str = json.dumps(item, ensure_ascii=False).lower()

                    matched_province = check_location(item, raw_str)
                    if not matched_province:
                        continue

                    province_in_kw += 1

                    extracted_items = []
                    attached_files = []
                    if req_id:
                        extracted_items, attached_files, detail_str = get_yccg_detail_values(
                            driver, req_id, req_type, token_val
                        )
                        if detail_str:
                            raw_str += " " + detail_str

                    is_relevant, is_hospital_proj_ycbg, kw_tags = evaluate_ycbg_medical_relevance(
                        title, investor, extracted_items, attached_files, raw_str
                    )

                    if is_relevant:
                        matched_in_kw += 1
                        final_kw_str = ", ".join(kw_tags)

                        if "thẩm định giá" in title.lower():
                            stage_label = "Tiền dự án (Thẩm định giá)"
                        elif is_hospital_proj_ycbg:
                            stage_label = "YCBG Tổng (Dự án Xây mới / Nâng cấp BV)"
                        else:
                            stage_label = "Mời báo giá (YCBG)"

                        # Tự động gắn Note nếu là YCBG tổng dự án BV hoặc danh mục nằm trong file PDF/Excel đính kèm
                        auto_note = ""
                        if is_hospital_proj_ycbg and not extracted_items:
                            auto_note = "YCBG tổng công trình BV (danh mục chi tiết trong file đính kèm) - Tải hồ sơ để chào cấu hình sớm"
                        elif is_hospital_proj_ycbg:
                            auto_note = "YCBG tổng dự án xây mới/nâng cấp BV - Theo dõi sát để chào thầu"
                        elif not extracted_items and attached_files:
                            auto_note = f"Danh mục hàng hóa đính kèm file: {', '.join(attached_files[:2])}"

                        header_text = f"{code} {title}".lower()
                        location_detail = (
                            "Tiêu đề"
                            if (any(k.lower() in header_text for k in kw_tags) or is_hospital_proj_ycbg)
                            else "Biểu mẫu Mời chào giá"
                        )

                        snippet_parts = []
                        if extracted_items:
                            snippet_parts.append("Danh mục hàng hóa: " + " ; ".join(extracted_items[:15]))
                        if attached_files:
                            snippet_parts.append("File đính kèm: " + ", ".join(attached_files))
                        snippet_text = " | ".join(snippet_parts) if snippet_parts else raw_str[:1200]

                        unique_matches[code] = {
                            "code": code,
                            "stage": stage_label,
                            "title": title,
                            "investor": investor,
                            "province": ", ".join(matched_province),
                            "bid_close_date": bid_close_date_str,
                            "matched_kw": final_kw_str,
                            "location": location_detail,
                            "auto_note": auto_note,
                            "quote_items": extracted_items[:25],
                            "attached_files": attached_files,
                            "detail_url": detail_url,
                            "snippet": snippet_text[:1500]
                        }

                if len(data_list) < current_page_size:
                    break
                if isinstance(total_elements, int) and fetched_in_kw >= total_elements:
                    break

                page_num += 1
                time.sleep(0.35)
            except Exception as e:
                print(f"[CẢNH BÁO FETCH API] Từ khóa '{kw}' (Trang {page_num}): {e}")
                break

        total_label = f"/{total_elements}" if isinstance(total_elements, int) else ""
        print(f"    + Đã tải {fetched_in_kw}{total_label} YCBG (thuộc 14 tỉnh: {province_in_kw}) -> Khớp TBYT / PACS / Dự án BV: {matched_in_kw} gói.")
        time.sleep(0.35)

    print(f"=== TỔNG KẾT QUÉT YCBG 14 TỈNH/TP: {len(unique_matches)} GÓI SẠCH KHỚP TIÊU CHÍ ===")
    return list(unique_matches.values())

# ==============================================================================
# 10. PHÂN TÍCH VỚI GEMINI AI (HẬU KIỂM + PHÂN LOẠI GIAI ĐOẠN & NHÓM BU)
# ==============================================================================
def analyze_batch_with_gemini(batch_items):
    global current_key_index, GEMINI_API_KEYS
    from google import genai
    from google.genai import types

    models_to_try = [
        PRIMARY_MODEL,
        FALLBACK_MODEL,
        "gemini-2.5-pro",
        "gemini-2.0-flash"
    ]

    prompt = f"""
Bạn là chuyên gia thẩm định dữ liệu Yêu cầu báo giá (YCBG) Trang thiết bị Y tế, Hệ thống PACS và Dự án đầu tư xây dựng Bệnh viện.
Dưới đây là danh sách các YCBG phát hành từ {START_TIME.strftime('%H:%M %d/%m/%Y')} đến {TODAY_STR} tại 14 tỉnh/thành phố phụ trách.

Yêu cầu BẮT BUỘC:
1. Giữ nguyên toàn bộ thuộc tính gốc của từng phần tử trong danh sách đầu vào.
2. Thêm trường boolean "is_medical_relevant":
   - Đặt true NẾU YCBG này liên quan đến mua sắm/sửa chữa Trang thiết bị y tế, vật tư y tế, MUA SẮM/ĐẦU TƯ hệ thống PACS (RIS/PACS), hoặc YCBG tổng cho dự án xây mới/cải tạo nâng cấp Bệnh viện / Trung tâm y tế / Cơ sở khám chữa bệnh.
   - Đặt false nếu đây là YCBG ngoài ngành y tế (trường học, giao thông, công viên, UBND xã, công an, điện lực, di tích) hoặc chỉ là thuê dịch vụ phần mềm hành chính/EMR không có mua sắm PACS/TBYT.
3. Viết tóm tắt ngắn gọn, rõ ràng danh mục thiết bị / hệ thống PACS / quy mô gói chào giá công trình bệnh viện vào trường "reason" (nếu có số lượng hàng hóa trong "quote_items" hoặc tên file đính kèm trong "attached_files", hãy nêu rõ).
4. Giữ nguyên hoặc chuẩn hóa trường "stage":
   - "YCBG Tổng (Dự án Xây mới / Nâng cấp BV)" nếu là báo giá tổng cho công trình bệnh viện xây mới/cải tạo nâng cấp.
   - "Tiền dự án (Thẩm định giá)" nếu là mời thẩm định giá thiết bị y tế.
   - "Mời báo giá (YCBG)" cho các gói mời báo giá thiết bị/vật tư/PACS thông thường.
5. Thêm trường "bu_group": phân loại vào 1 trong các nhóm [Dự án Xây mới / Nâng cấp BV, Nội soi - Tiêu hóa, Phòng mổ - Gây mê, Hồi sức - Giường bệnh, Tiệt trùng, Khí y tế, Chẩn đoán hình ảnh, Vật tư & Khác].
6. Trả về đúng mảng JSON thuần túy (không kèm markdown).

Danh sách:
{json.dumps(batch_items, ensure_ascii=False, indent=2)}
"""

    retry_delays = [8, 15, 25]

    for model_name in models_to_try:
        key_idx = current_key_index
        while key_idx < len(GEMINI_API_KEYS):
            key = GEMINI_API_KEYS[key_idx]
            client = genai.Client(api_key=key)

            for attempt in range(len(retry_delays)):
                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=prompt,
                        config=types.GenerateContentConfig(response_mime_type="application/json")
                    )
                    if response and response.text:
                        current_key_index = key_idx
                        parsed = json.loads(response.text.strip())
                        if isinstance(parsed, list):
                            return [x for x in parsed if x.get("is_medical_relevant", True) is not False]
                except Exception as e:
                    error_msg = str(e)
                    print(f"[CẢNH BÁO AI GOOGLE-GENAI ({model_name})] {error_msg}")

                    if "404" in error_msg or "not_found" in error_msg.lower():
                        key_idx = len(GEMINI_API_KEYS)
                        break

                    if any(k in error_msg.lower() for k in ["429", "resource_exhausted", "quota"]):
                        key_idx += 1
                        if key_idx < len(GEMINI_API_KEYS):
                            print(f"🔄 Đã đổi sang Gemini API Key thứ [{key_idx + 1}/{len(GEMINI_API_KEYS)}]")
                        break

                    if "503" in error_msg or "unavailable" in error_msg.lower():
                        if attempt < len(retry_delays) - 1:
                            wait_sec = retry_delays[attempt]
                            print(f"⏳ Model {model_name} đang quá tải (503), thử lại lần {attempt + 2} sau {wait_sec}s...")
                            time.sleep(wait_sec)
                            continue
                        key_idx = len(GEMINI_API_KEYS)
                        break

                    key_idx = len(GEMINI_API_KEYS)
                    break

    return batch_items

def analyze_with_gemini(candidates):
    if not candidates or not GEMINI_API_KEYS:
        return candidates

    batch_size = 15
    analyzed_results = []
    for i in range(0, len(candidates), batch_size):
        batch = candidates[i:i + batch_size]
        print(f"   Đang phân tích & thẩm định AI lô {i // batch_size + 1} ({len(batch)} YCBG)...")
        analyzed_batch = analyze_batch_with_gemini(batch)
        if isinstance(analyzed_batch, list):
            analyzed_results.extend(analyzed_batch)
        else:
            analyzed_results.extend(batch)
        time.sleep(1)
    return analyzed_results

# ==============================================================================
# 11. GỬI EMAIL BÁO CÁO
# ==============================================================================
def send_email_report(matched_list):
    if not RECEIVER_EMAIL:
        print("[LỖI CẤU HÌNH] Chưa khai báo email nhận.")
        return

    receiver_list = [e.strip() for e in RECEIVER_EMAIL.replace("\n", "").split(",") if e.strip()]
    if not receiver_list:
        print("[LỖI CẤU HÌNH] Danh sách email nhận không hợp lệ.")
        return

    matched_list_sorted = sorted(matched_list, key=lambda x: x.get("province", ""))
    email_subject = f"[YCBG TBYT & Dự Án BV - Địa bàn phụ trách] Phát hiện {len(matched_list_sorted)} gói chào giá ({START_TIME.strftime('%H:%M %d/%m')} - {TODAY_STR})"

    if not matched_list_sorted:
        html_body = f"""
        <div style="font-family: Arial, sans-serif; padding: 20px;">
            <h3 style="color: #d9534f;">BÁO CÁO YÊU CẦU BÁO GIÁ (YCBG)</h3>
            <p>Hệ thống đã quét dữ liệu từ <b>{START_TIME.strftime('%H:%M %d/%m/%Y')}</b> đến <b>{TODAY_STR}</b> nhưng chưa phát hiện gói chào giá mới khớp tiêu chí tại 14 địa phương theo dõi.</p>
        </div>
        """
    else:
        rows = ""
        for idx, item in enumerate(matched_list_sorted, 1):
            code = item.get("code", "")
            stage = item.get("stage", "Mời báo giá (YCBG)")
            title = item.get("title", "")
            investor = item.get("investor", "")
            province = item.get("province", "Theo dõi")
            bid_close_date = item.get("bid_close_date", "Chưa xác định")
            location = item.get("location", "Biểu mẫu Mời chào giá")
            auto_note = item.get("auto_note", "")
            quote_items = item.get("quote_items", [])
            reason = item.get("reason") or (" ; ".join(quote_items[:5]) if quote_items else "Khớp tiêu chí theo dõi y tế")
            if auto_note and auto_note not in reason:
                reason += f"<br><b style='color:#d9534f;'>Note: {auto_note}</b>"
            matched_kw = item.get("matched_kw", "")
            detail_url = item.get("detail_url") or f"https://{BASE_DOMAIN}/web/guest/contractor-selection?render=index"

            code_block = f"<b>{code}</b><br><span style='font-size:11px; color:#2e7d32; font-weight:bold;'>[{stage}]</span>"

            rows += f"""
            <tr>
                <td align="center">{idx}</td>
                <td>{code_block}</td>
                <td><b>{title}</b></td>
                <td>{investor}</td>
                <td align="center"><b><span style="color: #d9534f;">{province}</span></b></td>
                <td align="center"><b style="color: #2e7d32;">{bid_close_date}</b></td>
                <td align="center"><span style="background-color: #ffffcc; padding: 3px 6px; border-radius: 3px;">{matched_kw}</span></td>
                <td align="center"><i>{location}</i></td>
                <td><small style="color: #333;">{reason}</small></td>
                <td align="center"><a href="{detail_url}" target="_blank" style="color: #0275d8; font-weight: bold;">Xem ngay</a></td>
            </tr>
            """

        html_body = f"""
        <div style="font-family: Arial, sans-serif; padding: 20px;">
            <h2 style="color: #0275d8;">BÁO CÁO YÊU CẦU BÁO GIÁ (YCBG)</h2>
            <p>Khung thời gian quét: từ <b>{START_TIME.strftime('%H:%M %d/%m/%Y')}</b> đến <b>{TODAY_STR}</b></p>
            <p>Đã lọc phát hiện <b>{len(matched_list_sorted)}</b> gói chào giá (TBYT, PACS & Dự án xây mới/nâng cấp BV) thuộc địa bàn phụ trách:</p>
            <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; width: 100%; border-color: #ddd;">
                <tr style="background-color: #f2f8ff;">
                    <th align="center">STT</th>
                    <th>Mã YCBG / Giai Đoạn</th>
                    <th>Nội Dung Yêu Cầu</th>
                    <th>Đơn Vị Yêu Cầu</th>
                    <th align="center">Tỉnh / TP</th>
                    <th align="center">Hạn Nộp Báo Giá</th>
                    <th align="center">Tiêu Chí Khớp</th>
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
            print(f"[SUCCESS] Đã gửi báo cáo YCBG ({len(matched_list_sorted)} gói) tới: {', '.join(receiver_list)}!")
        except Exception as e:
            print(f"[LỖI GỬI EMAIL SMTP] {e}")

def main():
    print(f"=== CRAWL & DEEP-SCAN YCBG 14 TỈNH/TP (Khung quét: {START_TIME.strftime('%H:%M %d/%m/%Y')} -> {TODAY_STR}) ===")
    driver = init_driver()
    try:
        matched_list = fetch_yccg_today(driver)
        final_matches = analyze_with_gemini(matched_list)
        with open("latest_results.json", "w", encoding="utf-8") as f:
            json.dump(final_matches, f, ensure_ascii=False, indent=2)
        send_email_report(final_matches)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()
