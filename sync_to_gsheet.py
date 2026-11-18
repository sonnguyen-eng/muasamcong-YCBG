import os
import json
from datetime import datetime, timezone, timedelta
import gspread
from google.oauth2.service_account import Credentials

GSHEET_ID = os.environ.get("GSHEET_ID", "").strip()
GCP_SERVICE_ACCOUNT_JSON = os.environ.get("GCP_SERVICE_ACCOUNT_JSON", "").strip()
RESULTS_FILE = "latest_results.json"

TZ_VN = timezone(timedelta(hours=7))
SYNC_TIME_STR = datetime.now(TZ_VN).strftime("%H:%M %d/%m/%Y")

HEADERS = [
    "Ngày Đồng Bộ",
    "Mã YCBG",
    "Giai Đoạn",
    "Nhóm BU",
    "Nội Dung Yêu Cầu",
    "Đơn Vị Yêu Cầu",
    "Tỉnh / TP",
    "Hạn Nộp Báo Giá",
    "Tiêu Chí Khớp",
    "Phân Tích & Ghi Chú",
    "Link Chi Tiết"
]

def main():
    if not os.path.exists(RESULTS_FILE):
        print("Không tìm thấy file latest_results.json, bỏ qua bước đồng bộ.")
        return

    with open(RESULTS_FILE, "r", encoding="utf-8") as f:
        try:
            records = json.load(f)
        except Exception as e:
            print(f"Lỗi đọc JSON kết quả: {e}")
            return

    if not records:
        print("Không có gói YCBG mới nào trong lượt quét này.")
        return

    if not GSHEET_ID or not GCP_SERVICE_ACCOUNT_JSON:
        print("[LỖI CẤU HÌNH] Thiếu GSHEET_ID hoặc GCP_SERVICE_ACCOUNT_JSON.")
        return

    creds_dict = json.loads(GCP_SERVICE_ACCOUNT_JSON)
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    gc = gspread.authorize(creds)
    sh = gc.open_by_key(GSHEET_ID)
    ws = sh.sheet1

    existing_values = ws.get_all_values()
    if not existing_values:
        ws.append_row(HEADERS, value_input_option="USER_ENTERED")
        existing_codes = set()
    else:
        existing_codes = set()
        for row in existing_values[1:]:
            if len(row) > 1 and row[1].strip():
                existing_codes.add(row[1].strip())

    new_rows = []
    for item in records:
        code = str(item.get("code", "")).strip()
        if not code or code in existing_codes:
            continue
        existing_codes.add(code)

        stage = item.get("stage", "Mời báo giá (YCBG)")
        bu_group = item.get("bu_group", "Đa chuyên khoa / TBYT tổng hợp")
        title = item.get("title", "")
        investor = item.get("investor", "")
        province = item.get("province", "")
        bid_close_date = item.get("bid_close_date", "")
        matched_kw = item.get("matched_kw", "")
        reason = item.get("reason", "")
        auto_note = item.get("auto_note", "")
        full_note = f"{reason} | Note: {auto_note}" if (auto_note and auto_note not in reason) else (reason or auto_note)
        detail_url = item.get("detail_url", "")

        new_rows.append([
            SYNC_TIME_STR,
            code,
            stage,
            bu_group,
            title,
            investor,
            province,
            bid_close_date,
            matched_kw,
            full_note,
            detail_url
        ])

    if new_rows:
        ws.append_rows(new_rows, value_input_option="USER_ENTERED")
        print(f"[SUCCESS] Đã ghi thêm {len(new_rows)} gói YCBG mới vào Google Sheets.")
    else:
        print("Tất cả gói YCBG quét được đều đã tồn tại trên Google Sheets (0 dòng trùng).")

if __name__ == "__main__":
    main()
