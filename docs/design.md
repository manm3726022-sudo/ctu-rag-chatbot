# Quyết định thiết kế (cập nhật 20/11/2026)

Tài liệu này ghi các quyết định liên thành viên để không ai phải đoán. Pipeline là kế hoạch gốc; Sổ tay D1–D7
là các quyết định đã chốt ở TV4. Mục D8 trở đi bổ sung khi tích hợp phần truy xuất (TV3).

| Mã | Quyết định | Lý do ngắn |
|---|---|---|
| D1–D7 | Như Sổ tay (ngân sách token Groq, thẻ `[ABSTAIN]`/`[CLARIFY]`, sinh lại tối đa 1 lần, hiệu lực theo học kỳ, ...) | Đã triển khai ở TV4 |
| D8 | **Ngưỡng từ chối theo điểm reranker để trống** (`RERANK_ABSTAIN_THRESHOLD=`) | Bộ gold chỉ có 2 câu hoàn toàn ngoài kho (CTU-094, 095). 6/8 câu `abstain` còn lại có văn bản liên quan nhưng thiếu dữ liệu cá nhân nên điểm reranker vẫn cao; việc từ chối do prompt/LLM đảm nhiệm. Chỉ hiệu chỉnh khi TV1 bổ sung đủ câu ngoài kho |
| D9 | **Văn bản "đang hoạt động" lấy từ manifest** `documents.json` (status ≠ archived, sha256 = tệp nguồn chính), không lấy từ payload Qdrant | Payload luôn ghi `status="indexed"` và ingest không xóa điểm cũ. Retriever lọc theo `document_id` + `sha256` nên phiên bản cũ không bao giờ lọt vào evidence |
| D10 | **Lọc hiệu lực theo học kỳ bằng số nguyên** (`2024-HK2` → 20242). Lọc cứng, trừ câu hỏi về chính hiệu lực/thay thế (`hiệu lực`, `áp dụng từ`, `kỳ áp dụng`, `thay thế`, `ban hành`). Văn bản chỉ có ngày hiệu lực (TT 40, QĐ 5976) hoặc không có mốc (HD 2427) được giữ lại | Câu như CTU-075 ("HK1 2024–2025 có thuộc kỳ áp dụng của QĐ 3266 không?") phải truy được chính QĐ 3266. Chưa có quy ước đổi học kỳ sang ngày nên không đoán |
| D11 | Nêu đích danh văn bản (QĐ/TT/HD + số, hoặc số hiệu riêng ≥ 4 chữ số) thì **chỉ tìm trong văn bản đó**; nếu văn bản đó không còn hiệu lực ở học kỳ được hỏi thì trả **rỗng** để TV4 báo `no_valid_document_for_term` | Tránh trả lời bằng văn bản khác như thể nó là văn bản được hỏi |
| D12 | **Chỉ dùng đoạn `checked` làm bằng chứng** theo mặc định (`RETRIEVE_REQUIRE_CHECKED=true`); chế độ đánh giá/thử nghiệm đặt `false` | Đúng hợp đồng TV1/TV2. Hiện 47/217 đoạn `checked`; 170 đoạn `pending` chờ duyệt |
| D13 | **Sổ duyệt đoạn** `data/review/approved_chunks.csv` + `scripts/review_chunks.py` | Nếu không có sổ, mỗi lần ingest lại mọi đoạn tự động quay về `pending`. `chunk_id` sinh từ nội dung nên sửa chữ thì tự mất trạng thái đã duyệt |
| D14 | Câu hỏi nêu "Điều N" hoặc "Phụ lục V.b" → **ghim** tối đa 8 đoạn có mục đó vào tập ứng viên trước khi rerank | Pipeline B5: câu hỏi theo số điều phải tìm đúng nguồn; BM25/dense không đảm bảo điều này |
| D15 | **Khử trùng**: hai đoạn cùng văn bản, chồng trang, và (nội dung ≥ 85% từ trùng, hoặc một `checked` + một `pending` cùng mục) → giữ bản `checked`. Hai đoạn cùng mục, cùng trạng thái, khác nội dung KHÔNG bị coi là trùng | QĐ 4932 phụ lục được nạp hai lần (hàng rubric đã duyệt + đoạn tự động) |
| D16 | **Chọn evidence theo token** (`EVIDENCE_MAX_TOKENS`) và theo đa dạng văn bản (`EVIDENCE_DIVERSITY_RATIO`) | Quota Groq tính theo token/phút; câu liên văn bản (21% bộ gold) cần đủ nguồn |
| D17 | **Một nguồn duy nhất cho sparse**: `core/embedding.sparse_from_lexical` được cả `ingestion/index.py` và retriever dùng | Lệch giữa hai phía làm hybrid search sai mà không báo lỗi; có test giữ đồng bộ |
| D18 | **Chấm truy xuất theo `document_id` + khoảng trang chồng lấn**, không theo sha256/section | Gold ghi sha bản Word và section đến khoản; Qdrant lưu sha bản PDF và section đến Điều. Kết quả là cận trên. Giả định "ảnh N" của Word = "trang N" của PDF cần kiểm một mẫu (smoke test in ra trang của từng đoạn) |
| D19 | **Chia gold cố định**: `CTU-005, 010, 015, ...` là test (20%), còn lại validation. Chỉnh tham số chỉ trên validation | Pipeline §8.2 |
| D20 | **Archive** = đặt `status: archived` trong manifest rồi `python -m scripts.prune_index --apply` | Thay cho `--archive` trong Pipeline §5.1; không cần sửa ingest |
| D21 | Quy tắc "cần xác minh" Yếu/Kém mở rộng sang diễn đạt tắt ("bị Yếu", "loại kém") ở `backend/services/verify_rules.py` | CTU-085 trước đây bị bỏ lọt |
| D22 | Lỗi Qdrant/model ở retriever → `RetrievalError` → API trả 503 | Trước đây là lỗi 500 không rõ nguyên nhân |

## Hạn chế đã biết (chưa xử lý, cần người quyết định)

- **Khóa tuyển sinh**: `applies_from_cohort/applies_to_cohort` luôn trống (parser không điền). Router đọc được "khóa 47" nhưng chưa lọc. Cần TV1/TV2 điền cho các khoản có điều kiện (ví dụ Điều 18.2.c QĐ 3266 từ khóa 47).
- **Hiệu lực theo ngày** (TT 40, QĐ 5976) chưa so sánh với học kỳ vì chưa có quy ước ngày bắt đầu/kết thúc học kỳ.
- **Citation.page** chỉ hiển thị trang đầu của đoạn nhiều trang (5 nguồn gold nằm trên nhiều trang).
- **Validator con số** vẫn bỏ lọt câu sai nghĩa nhưng số có trong nguồn (CTU-056: "mỗi đợt được 12 điểm"); cần đối chiếu người khi chấm.
- **OCR**: QĐ 3266 và QĐ 5976 là bản scan; Điều 5 (số 8 đọc thành "§") và công thức Điều 24 có lỗi nhận dạng đã được TV1 ghi nhận. Đoạn chứa các chỗ này không được duyệt `ok` cho đến khi sửa.
- **docker-compose.yml** dùng `qdrant/qdrant:latest`. Nên ghim đúng phiên bản đang chạy (xem `curl http://localhost:6333` trường `version`) để cả nhóm dùng cùng một bản.
- **Python**: Pipeline ghi 3.11, TV1 chạy 3.12.14, TV4 chạy 3.11.9. Code không dùng tính năng riêng của phiên bản nào; chọn một bản thống nhất cho demo.
