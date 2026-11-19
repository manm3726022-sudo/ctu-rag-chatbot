# Đối chiếu nguồn và quy tắc xử lý

Ngày đối chiếu 18/11/2026. Trang là vị trí vật lý tính từ 1. Với Word QĐ 3266, “ảnh” là thứ tự ảnh từ đầu tệp. Bản gốc có thể đánh số lại khi sang phần quy định hoặc phụ lục.

| Vấn đề | Bằng chứng | Cách xử lý trong chatbot |
|---|---|---|
| QĐ 4932 và QĐ 3266 điều chỉnh hai việc khác nhau | Điều 2 của quyết định ban hành ở trang 1 của 4932 và ảnh 2 của 3266 | Liên kết thay thế tương ứng tới 6175 và 1813. Giữ cả 4932 và 3266 khi hỏi hệ quả học vụ liên quan rèn luyện. |
| Ngày ban hành khác ngày có hiệu lực | QĐ 3266 ảnh 1–2, QĐ 4932 trang 1, TT40 trang 1 và 17 | Dùng kỳ hiệu lực đối với hai QĐ. Với TT40 dùng 15/5/2026 cho ban hành, 30/6/2026 cho hiệu lực. Đánh giá đang dở trước mốc này xem Điều 31. |
| Hai ngày ghi cho cùng một Thông tư | QĐ 4932 tr. 1–2 ghi 12/5. TT40 tr. 1 và Cổng thông tin Chính phủ ghi 15/5 | Giữ chính văn từng nguồn. Tra cứu theo số hiệu và chú thích sai khác khi câu hỏi về ngày. |
| Hệ quả của mức rèn luyện thấp | QĐ 3266, Điều 25 khoản 4–6, ảnh 16. QĐ 4932, Điều 6, tr. 4 | Trích hai quy định, giữ nguyên “yếu, kém”. Câu hỏi về hồ sơ cá nhân hoặc việc quy đổi “Kém” sang “Yếu” cần đơn vị có thẩm quyền giải thích. |
| Trật tự nhóm I và II khác nhau | TT40 Điều 17 khoản 1–2, tr. 7–8. Phụ lục QĐ 4932 tr. 5 và 7 | Ghép theo nội dung. Chấp hành pháp luật = khoản 1 của Bộ, nhóm II của trường. Học tập = khoản 2 của Bộ, nhóm I của trường. |
| Điểm mỗi lần và trần tiêu chí | QĐ 4932, phụ lục V.b, tr. 10 | Phải có xác nhận đơn vị tổ chức. Một đợt đủ điều kiện = 3. Năm đợt vẫn tối đa 12 ở V.b. Trần toàn nhóm V là 20. |
| Bảng rèn luyện xuống trang | QĐ 4932, phụ lục I.a, IV.a, V.a | Nối trang 5–6 cho mức A2, 8–9 cho điều kiện vi phạm pháp luật và 9–10 cho tổ trưởng/tổ phó. Kiểm tra cả cột ghi chú. Khoảng chứng chỉ ở ranh giới có thể trùng trong nguyên bản, cần xác minh nếu dẫn đến hai kết quả. |
| Word ảnh và Word tóm tắt khác nhau | QĐ 3266 có 21 ảnh; Word QĐ 5976 có 3 bảng và các cặp hỏi đáp biên soạn | Kiểm tra OCR trên ảnh khi có con số hoặc phủ định. Chọn PDF QĐ 5976 làm nguồn trích. Ví dụ câu FAQ 1 mở đầu tuyệt đối trong khi Điều 4 khoản 5 của bản gốc có ngoại lệ về đồ uống có cồn (tr. 3). |
| Giới hạn đối tượng | TT40 Điều 2 tr. 1–2, QĐ 4932 Điều 1 tr. 2, QĐ 3266 Điều 18 tại ảnh 10 | Giữ ngoại lệ về đối tượng của TT40 và điều kiện khóa 47 khi trích ngưỡng cảnh báo theo tín chỉ. |
| Nguồn còn thiếu trong bộ đóng gói | Các quan hệ trỏ tới QĐ 6175, 1813, 3873 | Có thể nêu quan hệ được ghi trong văn bản hiện có. Câu hỏi cần nội dung chi tiết của bản chưa nạp phải trả về thiếu nguồn. |

## Đối chiếu bổ sung ngày 19/11/2026

Xem [phiếu đối chiếu TV2 và TV4](review_TV2_TV4.md) và log tv1-integration.txt. Đã có kiểm thử backend qua TestClient với bằng chứng thật và câu trả lời mẫu.

## Kiểm tra tiếp theo tại buổi tích hợp

Có thể kiểm ngay ảnh 8 của QĐ 3266 (trang in 6, tối đa 20 TC), ảnh 10 (trang in 8, nợ đọng vượt 24 TC đối với khóa 47 trở về sau), ảnh 16 (trang in 14, nguyên văn “yếu, kém”), ảnh 19 (trang in 17, ĐTBCTL từ 2,00). Bản OCR thô có lỗi nhận dạng, ví dụ bảng Điều 5 hình ảnh 4 có thể đọc nhầm ký tự số và công thức Điều 24 ở ảnh 15 bị mất bố cục. Xem ảnh trước khi duyệt các đoạn mới.

Khi TV4 có kết quả thật, chọn câu về V.b, câu về ngưỡng học vụ, câu lịch sử và câu cần nhiều nguồn. Với từng mệnh đề, mở bằng chứng qua document_id, sha256 và trang. Kiểm tra phạm vi, số và đơn vị, điều kiện, ngoại lệ. Nếu có evidence_id lạ, bỏ citation và yêu cầu xử lý lại. Chỉ ghi nhận review chéo sau khi có câu trả lời thật và người review xác nhận.
