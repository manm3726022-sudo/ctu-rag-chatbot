# Phiếu đối chiếu của TV1 ngày 19/11/2026

Người phụ trách theo phân công: Trần Hải Đăng. Kết quả dưới đây là đối chiếu trên bộ bàn giao và kiểm thử kỹ thuật ở commit 021955b. Khi có luồng truy xuất và phản hồi sinh tự động trên dữ liệu thật, nhóm đánh giá lần nữa và ghi kết quả từng ca vào bộ gold.

## Hỗ trợ TV2 kiểm OCR

Các số “ảnh” là vị trí từ đầu file Word QĐ 3266; trang in của phần Quy định bắt đầu lại từ 1.

| Ảnh / trang in | Vị trí | Kết quả đối chiếu với ảnh gốc | Xử lý |
|---|---|---|---|
| 4 / 2 | Điều 5, bảng thời gian | Dòng CTĐT 4 năm có mức tối đa 8 năm. OCR ghi “4 năm § năm”. Hai dòng sau tương ứng 4,5 → 9 và 5 → 10 năm. | Giữ đủ hai cột. Dùng ảnh làm căn cứ cho con số 8. |
| 8 / 6 | Điều 14 khoản 1 | Cả ảnh và OCR đều ghi tối đa 20 TC/HK. | Dùng để kiểm mẫu CTU-009. |
| 10 / 8 | Điều 18 khoản 2 điểm c | Ảnh và OCR đều có ngưỡng “vượt quá 24 TC”. Điều kiện áp dụng từ khóa 47 trở về sau nằm ở đầu điểm c. | Giữ cả phần dẫn khi tách đoạn; đúng 24 chưa vượt 24. |
| 15 / 13 | Điều 24 khoản 2 | Công thức trong OCR xuất hiện chuỗi “ĐTBCHK = mm —”. | Khoanh vùng cần chép công thức từ ảnh và kiểm độc lập trước khi dùng. |
| 16 / 14 | Điều 25 khoản 4–6 | OCR còn cụm “yếu, kém” như ảnh. Các hậu quả khác nhau theo số kỳ và lần lặp. | Giữ nguyên thuật ngữ và điều kiện. Ca cá nhân cần xác minh. |
| 19 / 17 | Điều 32 khoản 1 điểm a | Ngưỡng 2,00 trên thang 4 đọc được. Cùng khoản còn có yêu cầu học phần, tín chỉ và chuẩn đầu ra. | Khi hỏi điều kiện tốt nghiệp phải tra đủ khoản và các điểm liên quan. |

## Review nguồn và citation của TV4

| Ca kiểm | Đã thử | Kết quả hoặc giới hạn |
|---|---|---|
| CTU-009 | Chuyển đoạn học vụ thành EvidenceChunk, đưa câu mẫu vào validate | S1 dẫn QĐ 3266, Điều 14 khoản 1, ảnh 8. Mốc 20 TC khớp ảnh gốc. |
| CTU-056 | Chuyển đoạn V.b đã duyệt, gọi validate và thử POST /chat | Tên văn bản, mục, trang 10 và URL lấy từ bằng chứng. Câu mẫu trả 12 điểm. Endpoint chạy thật trong TestClient; đầu vào retrieval và câu do mô hình sinh được thay bằng dữ liệu kiểm soát. |
| Dẫn S9 khi chỉ có S1, đưa 99 điểm vào phản hồi | Gọi validator với đoạn V.b | Gỡ S9 và có hai cờ invalid_citation_removed, unsupported_number. |
| Câu sai nghĩa nhưng số có trong đoạn | Đưa “Mỗi đợt được 12 điểm [S1].” thay cho 3 điểm mỗi đợt | Validator có thể trả cờ rỗng: số 12 có trong nguồn nhưng là trần. Khi chấm phải so nghĩa, đơn vị và điều kiện. |
| Câu cần chuyển xác minh | Kiểm hàm needs_verification với nguyên văn CTU-085 | Câu chỉ nói “bị Yếu” nên thiếu từ khóa “rèn luyện”. Bộ gold kỳ vọng refer, còn bộ dò từ khóa hiện tại trả False. Cần rà cả diễn đạt tắt trong đợt tích hợp. |
| Dòng bảng qua hai trang | Đọc schema và bộ dựng citation | EvidenceChunk giữ page_start và page_end. Citation.page hiện chỉ hiển thị trang đầu. Khi đối chiếu hàng qua trang, TV1 tra cả hai trang trong bản ghi nguồn. |

Lệnh chạy lại: python -m scripts.review_sources và python -m pytest -q. File docs/test-log/tv1-integration.txt ghi đầu ra. API mặc định của TV4 dùng retriever mock riêng. Điểm 12 ở ca CTU-056 được kiểm với câu mẫu cố định và phụ lục; chưa có kết quả đo độ chính xác hỏi đáp tự động của mô hình.
