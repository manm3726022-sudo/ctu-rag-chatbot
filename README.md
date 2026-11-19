# CTU RAG Chatbot

Chatbot tiếng Việt tư vấn **quy chế học vụ và thông tin liên quan của Đại học Cần Thơ (CTU)**, xây dựng theo kỹ thuật **RAG**: hệ thống tìm bằng chứng trong kho tài liệu do người quản lý cung cấp, rồi mới nhờ mô hình ngôn ngữ (GroqCloud Free API) tổng hợp câu trả lời kèm nguồn trích dẫn. Dự án **không huấn luyện** LLM để ghi nhớ quy chế, nhằm giảm nguy cơ bịa thông tin (hallucination).

## Phạm vi MVP

- Một giao diện chatbot (Streamlit) dành cho sinh viên; hiển thị câu trả lời và nguồn trích dẫn.
- Không có trang Admin. Người quản lý đặt file vào `data/raw/` và chạy script nạp tài liệu.
- Định dạng đầu vào: PDF có text, PDF scan (OCR), DOCX, TXT, HTML.
- Một collection Qdrant chung cho mọi tài liệu; tìm trên toàn bộ tài liệu đang hoạt động.
- LLM: GroqCloud Free API. Không dùng API trả phí, không chạy LLM local.
- Ngoài phạm vi: fine-tuning LLM, trang quản trị riêng, đăng nhập/phân quyền sinh viên, hosting trả phí.

## Kiến trúc

```text
Nạp tài liệu (offline):
  data/raw -> ingestion (trích xuất / OCR -> parse -> chunk) -> BGE-M3 (dense + sparse) -> Qdrant

Hỏi đáp (online):
  Streamlit -> FastAPI -> BGE-M3 -> Qdrant hybrid search + RRF -> BGE-Reranker
            -> GroqCloud (gpt-oss) -> kiểm tra trích dẫn -> Streamlit
```

| Thành phần | Công nghệ |
|---|---|
| Ngôn ngữ | Python 3.11 |
| PDF / OCR | pypdf; OCRmyPDF + Tesseract (`vie+eng`) |
| DOCX / HTML | python-docx; BeautifulSoup4 |
| Embedding | `BAAI/bge-m3` (dense + sparse), chạy local |
| Reranker | `BAAI/bge-reranker-v2-m3`, chạy local |
| Vector DB | Qdrant (Docker Compose) |
| LLM | GroqCloud Free API: `openai/gpt-oss-120b`, dự phòng `openai/gpt-oss-20b` |
| Backend / UI | FastAPI + Pydantic / Streamlit |
| Registry | SQLite |
| Kiểm thử | pytest, Ruff |

## Yêu cầu hệ thống

- Ubuntu, hoặc Windows với WSL2 + Ubuntu (khuyến nghị cho Windows).
- Python 3.11, Git, Docker Engine + Docker Compose.
- Tesseract kèm dữ liệu tiếng Việt, Ghostscript, qpdf (cho OCR).
- RAM tối thiểu 8 GB; ước lượng vài GB ổ đĩa cho model cache và Qdrant. Không cần GPU.
- Tài khoản Groq (Free Plan) để lấy API key. **Không** thêm phương thức thanh toán.

## Cấu trúc thư mục

```text
ctu-rag-chatbot/
├── app/            # Streamlit UI và client gọi FastAPI
├── backend/        # FastAPI, schemas, prompts, services (retriever, reranker, generator, ...)
├── core/           # cấu hình, embedding, đếm token (dùng chung)
├── ingestion/      # nạp tài liệu: registry, extract, OCR, parser, chunker, index Qdrant
├── scripts/        # smoke_test, validate_rubric, verify_extraction, ...
├── data/           # raw/ ocr/ processed/ structured_rules/ registry/   (không commit file lớn)
├── eval/           # bộ câu hỏi chuẩn và script đánh giá
├── tests/          # unit, integration, retrieval
├── docs/           # runbook.md, design.md, test-log/
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── README.md
```

## Nạp dữ liệu nguồn

Lệnh nạp đọc `docs/corpus/documents.json`, kiểm SHA-256 của tệp có sẵn trong `data/raw/` và tải tệp còn thiếu từ URL nguồn. QĐ 3266 dùng bản PDF scan chính thức được khai báo ở `ingestion_source`. Bản Word ảnh của TV1 vẫn có định danh và vị trí riêng cho bộ kiểm thử bàn giao. Cài Tesseract trên `PATH` với dữ liệu ngôn ngữ `vie` và `eng` để xử lý bản scan.

```text
python -m pip install -r requirements.txt
python -m scripts.ingest --prepare-only
docker compose up -d qdrant
python -m scripts.ingest
```

Dùng `--document tt40` để chạy một văn bản. Có thể lặp `--document` để chọn nhiều văn bản. `--prepare-only` tạo các tệp `*.pages.jsonl`, `*.tables.jsonl` và `*.chunks.jsonl` trong `data/processed/` để soát kết quả. Đoạn trích tự động mang `review_status=pending`. Các hàng từ bảng QĐ 4932 đã đối chiếu được gắn `checked` theo đúng SHA-256 và vị trí trang.

Lệnh nạp mặc định tạo vector BGE-M3 `dense` và `sparse` và ghi vào `QDRANT_COLLECTION`. Chạy lại cùng dữ liệu sẽ ghi đè điểm có cùng ID. TV3 cần lọc `status=indexed` và `review_status=checked` khi cung cấp bằng chứng đã duyệt, đồng thời quản lý việc hủy kích hoạt phiên bản cũ. Với nguồn HTML hoặc TXT, khai báo `pages: 1` cho tài liệu một trang logic. Với DOCX văn bản, chỉ dùng số trang theo ngắt trang rõ ràng trong tệp.

## Quy ước làm việc

- `main` luôn chạy được; **không commit trực tiếp**. Mỗi việc một Issue, một branch, một Pull Request.
- Tên branch: `feat/<module>-<việc>`, `fix/<module>-<lỗi>`, `docs/<chủ-đề>`.
- Commit dùng tiền tố `feat:`, `fix:`, `docs:`, `test:`, `refactor:`.
- Pull Request: một mục tiêu nhỏ, nêu cách kiểm tra, liên kết Issue, tối thiểu một reviewer.
- Mỗi người viết test cho module mình phụ trách và review ít nhất một Pull Request của người khác.
- **Không commit:** `.env`, khoá API, mật khẩu, PDF/file nguồn lớn, kết quả OCR, model weights/cache, Qdrant volume, `.venv/`, log.

## Lưu ý

- **Quota Groq Free** có hạn chế theo phút và theo ngày, tính theo từng model và có thể thay đổi. Kiểm tra trang Limits trong Groq Console trước mỗi buổi demo; khi hết quota thì dừng gọi và thông báo người dùng.
- Chỉ câu hỏi và các đoạn bằng chứng cần thiết được gửi tới Groq; không gửi dữ liệu cá nhân.
- Chatbot trích dẫn nguồn theo metadata của tài liệu, từ chối hoặc hỏi lại khi thiếu bằng chứng. Câu trả lời chỉ mang tính tham khảo, sinh viên cần đối chiếu với văn bản gốc.
- Hạn chế đã biết của MVP: mỗi câu hỏi được truy xuất độc lập, lịch sử hội thoại chỉ nằm trong phiên làm việc của trình duyệt.
