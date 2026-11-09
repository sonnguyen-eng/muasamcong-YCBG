# BOT Tự Động Quét Yêu Cầu Báo Giá Y Tế (YCCG / YCBG) - Mua Sắm Công V2

Hệ thống tự động chạy hàng ngày (khung giờ 23h30 - 23h59) để thu thập, phân tích và gửi báo cáo các Yêu cầu báo giá (YCBG) lĩnh vực Trang thiết bị Y tế trên hệ thống `muasamcong.mof.gov.vn`.

## 📌 Tính năng chính
1. **Lọc thời gian nghiêm ngặt**: Chỉ lấy các YCCG phát hành từ 00h00 của ngày hiện tại đến thời điểm quét.
2. **Bộ 19 Từ khóa Y tế**: Lọc theo các từ khóa chuyên sâu (Nội soi, Bàn mổ, Máy gây mê, Bồn oxy lỏng...).
3. **Bộ 14 Địa phương mục tiêu**: Chuẩn hóa định danh tỉnh/thành phố (Tỉnh Đắk Lắk, Thành phố Đồng Nai...).
4. **Deep-Scan 2 Tầng**: Gọi ngầm API `/services/get-request-quote` để bóc tách toàn bộ danh mục hàng hóa bên trong từng YCBG.
5. **Trí tuệ nhân tạo Gemini**: Phân tích tóm tắt nội dung báo giá tự động.
6. **Báo cáo Email**: Tự động gửi kết quả dạng HTML chuyên nghiệp kèm link truy cập trực tiếp.

## ⚙️ Cấu hình GitHub Secrets
Cần thiết lập 4 biến trong **Settings -> Secrets and variables -> Actions**:
- `GEMINI_API_KEY`: API Key của Google Gemini AI.
- `SENDER_EMAIL`: Email Gmail dùng để gửi báo cáo.
- `SENDER_PASSWORD`: App Password (Mật khẩu ứng dụng 16 ký tự) của Gmail.
- `RECEIVER_EMAIL`: Email nhận báo cáo hàng ngày.
