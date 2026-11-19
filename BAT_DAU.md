# Bàn giao dữ liệu nguồn và metadata cho CTU RAG Chatbot

Trần Hải Đăng phụ trách TV1 – Nguồn và quy định. Gói chứa mọi tệp của bản GitHub nhóm gửi (main, 021955b), phần bổ sung của TV1 và hai tài liệu Word trong thư mục ban_giao/. Giải nén vào một thư mục mới.

## Chạy kiểm tra

Từ thư mục chứa BAT_DAU.md, mở PowerShell. Dùng Python 3.11 hoặc 3.12. Các lệnh dưới đây chạy phần TV1 và bộ kiểm thử TV4 bằng môi trường riêng.

```powershell
python -m venv .venv
$py = ".\.venv\Scripts\python.exe"
& $py -m pip install -r requirements-tv1.txt
& $py -m scripts.register_corpus --check-only
& $py -m scripts.register_corpus --db demo_dang.db
& $py -m scripts.register_corpus --db demo_dang.db
& $py -m scripts.review_sources
& $py -m pytest -q
```

Gói đã kèm SQLite ở data/registry/registry.db. Các lệnh trên tạo demo_dang.db riêng. Để tái hiện từ đầu, chạy hai lần với cùng một đường dẫn mới, ví dụ `python -m scripts.register_corpus --db demo_registry.db`. Lần đầu ghi 5, lần sau ghi 0. Xem danh mục bằng truy vấn bên dưới trong trình đọc SQLite.

```sql
SELECT document_id, version,
       json_extract(record_json, '$.document_number') AS so_hieu,
       json_extract(record_json, '$.effective_from_term') AS tu_hoc_ky
FROM corpus_current ORDER BY document_id;
```

## Các tệp dùng trong nhóm

| Tệp | Dùng để |
|---|---|
| docs/corpus/documents.json | Tra số hiệu, ngày, phạm vi, quan hệ, danh sách file gốc, hash SHA-256. Năm mã văn bản, sáu tệp. |
| data/registry/registry.db | Registry SQLite đã nạp, bảng corpus_versions và view corpus_current. Manifest nằm ngoài thư mục registry để quy tắc gitignore hiện có không bỏ sót. |
| core/corpus_metadata.py và docs/schemas/ | Mô hình Pydantic 2 và JSON Schema xuất sẵn cho DocumentRecord, ChunkRecord, EvidenceChunk, ChatResponse. |
| data/raw/ | 5 nguồn chính. QĐ 3266 là Word ảnh. Bản PDF gốc QĐ 5976 lấy theo URL trong manifest. |
| data/ocr/ | Văn bản OCR thô theo thứ tự ảnh hoặc trang, gồm 21 tệp QĐ 3266 và 7 tệp QĐ 5976. Bản Word tóm tắt nằm riêng trong reference_only. |
| tests/fixtures/corpus_chunks.jsonl | 24 đoạn ngắn để kiểm tra ánh xạ số hiệu, trang và nguồn. Chuẩn hóa câu hoặc trải cột bảng thành câu khi cần. Một dòng là một JSON. |
| data/structured_rules/qd4932_rubric.csv | 47 dòng quy tắc. points mang nghĩa theo rule (mức, điểm ban đầu, mỗi lần hoặc mỗi đợt). criterion_cap và group_cap là hai trần khác nhau. Các lựa chọn cùng tiêu chí dùng chung trần, không cộng các mức thay thế. |
| eval/gold_corpus.csv và .jsonl | Hai cách đọc cùng 100 câu. CSV mở bằng Excel, JSONL dùng để chấm. Không đưa kho câu hỏi vào truy xuất. |
| docs/critical/source_review.md | Các điều khoản cần đọc cùng nhau, khác biệt thuật ngữ, ngày tháng, lỗi OCR và cách xử lý. |
| docs/test-log/tv1-integration.txt | Kết quả chạy kiểm tra cục bộ, có ghi mốc repo và phiên bản môi trường. |

## Kết nối với ingestion và retrieval

1. TV2 đọc manifest và nhận biết docx_scan khác DOCX văn bản. source_kind=summary chỉ hỗ trợ soạn từ khóa và câu hỏi. Với nguồn scan, giữ thứ tự ảnh hoặc trang. Nối hai trang khi một điều kiện hoặc dòng bảng bị ngắt.
2. Lưu mỗi đoạn kèm document_id, sha256, chunk_id, section và page_start/page_end. Dùng section có tiền tố Quyết định, Quy định, Quy chế hoặc Phụ lục để phân biệt các Điều 2 trùng số. Chunk mẫu có UUID v5 tạo từ định danh nguồn, vị trí và nội dung. Chỉ chuyển review_status sang checked khi đã kiểm nội dung.
3. TV3 khi lập chỉ mục chép từ DocumentRecord các trường document_number, title, source_url, status, effective_date, effective_from_term, effective_until_term_exclusive, applicability sang payload cùng ChunkRecord. Với điều kiện riêng ở từng khoản, gắn applies_from_cohort/applies_to_cohort. Ví dụ Điều 18.2.c QĐ 3266 có applies_from_cohort=47. Khóa và học kỳ là hai chiều độc lập. Không điền giá trị đoán khi thiếu dữ kiện.
4. Chỉ dùng phiên bản đã lập chỉ mục và được phép truy xuất. Trường status của registry đang là registered. Chuyển sang indexed sau khi TV3 đối soát xong các point, và hủy kích hoạt phiên bản cũ trong cùng quy trình xuất bản. Khi phân xử câu lịch sử, chọn kỳ bắt đầu ≤ kỳ hỏi và kỳ hỏi < kỳ kết thúc nếu có. Nếu HD 2427 thiếu mốc hiệu lực thì đánh dấu cần kiểm khi câu hỏi phụ thuộc thời điểm. Ngày ban hành và ngày hiệu lực có ý nghĩa khác nhau.
5. TV3 có thể gọi core.corpus_evidence.to_evidence(doc, chunk, position, score) cho mỗi đoạn đã xếp hạng. Hàm trả backend.schemas.EvidenceChunk, đặt source_id = S1, S2… theo lượt và ánh xạ content → text. TV4 dựng ChatResponse.citations từ metadata nguồn. Bộ gold ghi action; khi so kết quả API, dùng need_clarification cho clarify, abstain cho thiếu nguồn và kiểm risk_flag kèm nội dung cho refer. Với nguồn docx_scan hiển thị “ảnh”, với PDF hiển thị “trang PDF”. Chọn clarify khi thiếu thông tin của người hỏi, abstain khi kho thiếu bằng chứng, refer khi cần đơn vị có thẩm quyền giải quyết.
6. Khi đo thử, tách câu validation và test trước khi chỉnh tham số. Với câu cần nhiều nguồn, kiểm cả độ phủ toàn bộ nguồn bắt buộc. Bộ gold là đáp án đối chiếu. Chưa có kết quả chạy ứng dụng hoàn chỉnh hoặc xác nhận của người đánh giá thứ hai.

## Ghép vào GitHub

Chép các file theo đường dẫn tương ứng trên nhánh mới. Giữ dữ liệu thô, OCR, database và kết quả chạy riêng ở máy nhóm theo .gitignore hiện hành. Các file có thể review gồm core/corpus_metadata.py, scripts/register_corpus.py, docs/corpus/, docs/schemas/, data/structured_rules/, tests/ và eval/gold_corpus.*. File docs/test-log/tv1-integration.txt chỉ mô tả kiểm thử tổng hợp, không chứa log truy vấn cá nhân. Giữ nguyên README.md nhóm. Kho GitHub chưa được cập nhật trong lần bàn giao này.

## File cần mở trước khi trình bày

Mục tiêu và kết quả nằm trong ban_giao/Bao_cao_Hai_Dang_CTU_RAG.docx. Sổ tay Windows nằm kế bên. Phiếu review cụ thể nằm ở docs/critical/review_TV2_TV4.md. Nhật ký corpus.txt là kết quả lần bàn giao trước. Các mục mã nguồn và dữ liệu đề nghị đưa lên nhánh TV1 được liệt kê tại docs/corpus/tep_ban_giao.txt. Dữ liệu thô, OCR, SQLite và bản Word được trao đổi riêng qua ZIP.
