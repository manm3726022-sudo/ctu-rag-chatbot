# CTU RAG Chatbot

Chatbot tiếng Việt tư vấn **quy chế học vụ và thông tin liên quan của Đại học Cần Thơ (CTU)**, xây dựng theo kỹ thuật **RAG**: hệ thống tìm bằng chứng trong kho tài liệu do người quản lý cung cấp, rồi mới nhờ mô hình ngôn ngữ (GroqCloud Free API) tổng hợp câu trả lời kèm nguồn trích dẫn. Dự án **không huấn luyện** LLM để ghi nhớ quy chế, nhằm giảm nguy cơ bịa thông tin (hallucination).

## Phạm vi MVP

- Một giao diện chatbot (Streamlit) dành cho sinh viên; hiển thị câu trả lời và nguồn trích dẫn.
- Không có trang Admin. Người quản lý khai báo tài liệu trong `docs/corpus/documents.json` (và đặt file vào `data/raw/`) rồi chạy script nạp.
- Định dạng đầu vào: PDF có text, PDF scan (OCR), DOCX, TXT, HTML.
- Một collection Qdrant chung cho mọi tài liệu; tìm trên toàn bộ tài liệu đang hoạt động.
- LLM: GroqCloud Free API. Không dùng API trả phí, không chạy LLM local.
- Ngoài phạm vi: fine-tuning LLM, trang quản trị riêng, đăng nhập/phân quyền sinh viên, hosting trả phí.

## Kiến trúc

```text
Nạp tài liệu (offline):
  documents.json + data/raw -> trích xuất / OCR -> parse -> chunk -> BGE-M3 (dense + sparse) -> Qdrant

Hỏi đáp (online):
  Streamlit -> FastAPI -> router (số hiệu, Điều, học kỳ) -> BGE-M3 -> Qdrant hybrid search + RRF
            -> BGE-Reranker -> chọn evidence theo token -> GroqCloud (gpt-oss)
            -> kiểm tra trích dẫn -> Streamlit
```

| Thành phần | Công nghệ |
|---|---|
| Ngôn ngữ | Python 3.11 hoặc 3.12 |
| PDF / OCR | pypdf, pypdfium2 (dựng ảnh trang) + Tesseract `vie+eng` (gọi bằng dòng lệnh) |
| DOCX / HTML | python-docx; BeautifulSoup4 |
| Embedding | `BAAI/bge-m3` (dense + sparse), chạy local |
| Reranker | `BAAI/bge-reranker-v2-m3`, chạy local |
| Vector DB | Qdrant (Docker Compose) |
| LLM | GroqCloud Free API: `openai/gpt-oss-120b`, dự phòng `openai/gpt-oss-20b` |
| Backend / UI | FastAPI + Pydantic / Streamlit |
| Danh mục văn bản | `docs/corpus/documents.json` (nguồn sự thật); SQLite registry chỉ lưu lịch sử phiên bản |
| Kiểm thử | pytest, Ruff |

## Yêu cầu hệ thống

- Ubuntu, hoặc Windows với WSL2 + Ubuntu (khuyến nghị cho Windows).
- Python 3.11 hoặc 3.12, Git, Docker Engine + Docker Compose.
- Tesseract kèm dữ liệu tiếng Việt và tiếng Anh (`tesseract --list-langs` phải có `vie` và `eng`). Ghostscript/qpdf chỉ cần nếu sau này dùng OCRmyPDF (code hiện tại không dùng).
- RAM: khuyến nghị 12 GB trở lên khi chạy API với `RETRIEVER=real` (nạp đồng thời BGE-M3 và reranker); tối thiểu 8 GB. Vài GB ổ đĩa cho model cache và Qdrant. Không cần GPU.
- Tài khoản Groq (Free Plan) để lấy API key. **Không** thêm phương thức thanh toán.

## Cấu trúc thư mục

```text
ctu-rag-chatbot/
├── app/            # Streamlit UI và client gọi FastAPI
├── backend/        # FastAPI, schemas, prompts, services (query_router, retriever, reranker, generator, ...)
├── core/           # cấu hình, embedding, danh mục văn bản, đếm token, metadata (dùng chung)
├── ingestion/      # nạp tài liệu: sources, extract (+OCR), chunking, rubric, index Qdrant, approvals
├── scripts/        # ingest, register_corpus, smoke_retrieval, prune_index, review_chunks, smoke_groq, ...
├── data/           # raw/ ocr/ processed/ structured_rules/ review/ registry/   (không commit file lớn)
├── eval/           # bộ câu hỏi chuẩn (gold) và đánh giá truy xuất (metrics.py, run_retrieval_eval.py)
├── tests/          # unit, integration, retrieval (có bản giả Qdrant/BGE để chạy không cần Docker)
├── docs/           # design.md, tv3-retrieval.md, tv4-llm-app.md, corpus/, schemas/, critical/, test-log/
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── README.md
```

## Cài đặt và chạy từ đầu (máy mới)

```text
git clone <repo> && cd ctu-rag-chatbot
python3 -m venv .venv && source .venv/bin/activate
python -m pip install torch --index-url https://download.pytorch.org/whl/cpu    # máy không có GPU
python -m pip install -r requirements.txt
cp .env.example .env            # điền GROQ_API_KEY; để RETRIEVER=mock cho tới khi đã nạp dữ liệu
docker compose up -d qdrant
```

### 1) Nạp dữ liệu nguồn

Lệnh nạp đọc `docs/corpus/documents.json`, kiểm SHA-256 của tệp có sẵn trong `data/raw/` và tải tệp còn thiếu từ URL nguồn. QĐ 3266 dùng bản PDF scan chính thức được khai báo ở `ingestion_source`. Bản Word ảnh của TV1 vẫn có định danh và vị trí riêng cho bộ kiểm thử bàn giao. Cài Tesseract trên `PATH` với dữ liệu ngôn ngữ `vie` và `eng` để xử lý bản scan.

```text
python -m scripts.ingest --prepare-only                  # xuất data/processed/*.jsonl để soát, chưa embedding
python -m scripts.ingest --document qd4932 --document tt40 --document hd2427   # 3 văn bản có lớp chữ, thường không cần OCR
python -m scripts.ingest                                 # toàn bộ (QĐ 3266 và QĐ 5976 cần OCR)
```

Đoạn trích tự động mang `review_status=pending`; các hàng bảng QĐ 4932 đã đối chiếu mang `checked`. Đoạn nào đã được người phụ trách duyệt (ghi trong `data/review/approved_chunks.csv`) sẽ được ghi `checked` mỗi lần nạp lại. Chạy lại cùng dữ liệu sẽ ghi đè điểm có cùng ID. Để archive một văn bản: đặt `"status": "archived"` trong `documents.json` rồi chạy `python -m scripts.prune_index --apply` để dọn điểm khỏi Qdrant (retriever đã tự bỏ qua chúng).

### 2) Kiểm tra BGE-M3 + Qdrant + reranker (T2, không tốn quota Groq)

```text
python -m scripts.smoke_retrieval
```

### 3) Chạy chatbot

```text
# trong .env: RETRIEVER=real
uvicorn backend.main:app --host 127.0.0.1 --port 8000      # cửa sổ 1 (lần đầu nạp model mất vài phút)
streamlit run app/main.py                                   # cửa sổ 2 -> http://localhost:8501
curl http://127.0.0.1:8000/health                           # xem số điểm checked/pending
```

Mặc định (`RETRIEVE_REQUIRE_CHECKED=true`) chatbot chỉ dùng đoạn đã duyệt làm bằng chứng. Khi chưa duyệt xong các đoạn `pending`, câu hỏi ngoài bảng rèn luyện QĐ 4932 sẽ bị từ chối; đặt `false` để thử nghiệm.

Đặt `RERANK_BACKEND=phoranker` để thử cross-encoder tiếng Việt trên collection hiện có. PhoRanker dùng PyVi để tách từ và chấm tối đa 256 token cho mỗi cặp câu hỏi–đoạn.

Đặt thêm `CHUNKING_MODE=phoranker` khi ingest vào collection mới để chia các đoạn dài theo ranh giới khoản hoặc câu. Giới hạn 200 token PhoRanker cho đoạn và tiêu đề chừa chỗ cho câu hỏi. Đoạn con giữ khoảng trang nguồn của đoạn gốc. Các đoạn dẫn xuất giữ trạng thái duyệt của nội dung gốc và các hàng rubric đã kiểm duyệt được dùng nguyên vẹn.

Để thử embedding mGTE, đặt `EMBED_BACKEND=mgte` và chọn `QDRANT_COLLECTION` mới, sau đó chạy lại `python -m scripts.ingest`. Collection này lưu dense 768 chiều cùng sparse của mGTE. Khi đổi backend, cập nhật hoặc bỏ các giá trị `EMBED_MODEL` và `RERANK_MODEL` đã ghi trong `.env`. Đặt `EVIDENCE_TOKENIZER_MODEL=BAAI/bge-m3` nếu cần giữ cùng cách chia đoạn và đếm ngân sách evidence khi so sánh hai embedder.

### 4) Kiểm thử và đánh giá

```text
python -m pytest -q                                   # unit + integration, không cần Docker/Groq
python -m ruff check .
python -m eval.run_retrieval_eval                     # Recall@5/MRR trên tập validation (gồm đoạn pending)
python -m eval.run_retrieval_eval --split test        # CHỈ chạy lúc nghiệm thu cuối
```

Hai file test của TV1 (`test_corpus_metadata.py`, `test_tv1_integration.py`) cần các tệp trong gói bàn giao (ZIP) nên tự bỏ qua khi thiếu.

### 5) Duyệt đoạn pending

```text
python -m scripts.ingest --prepare-only
python -m scripts.review_chunks export                # -> data/review/pending_review.csv
# người duyệt đối chiếu cột content với PDF gốc, điền decision = ok cho đoạn đúng
python -m scripts.review_chunks apply --file data/review/pending_review.csv --reviewer "Tên người duyệt"
git add data/review/approved_chunks.csv               # sổ duyệt PHẢI được commit
```

Chi tiết thiết kế: `docs/design.md`. Hướng dẫn riêng cho phần truy xuất: `docs/tv3-retrieval.md`. Phần LLM và ứng dụng: `docs/tv4-llm-app.md`.

## Quy ước làm việc

- `main` luôn chạy được; **không commit trực tiếp**. Mỗi việc một Issue, một branch, một Pull Request.
- Tên branch: `feat/<module>-<việc>`, `fix/<module>-<lỗi>`, `docs/<chủ-đề>`.
- Commit dùng tiền tố `feat:`, `fix:`, `docs:`, `test:`, `refactor:`.
- Pull Request: một mục tiêu nhỏ, nêu cách kiểm tra, liên kết Issue, tối thiểu một reviewer.
- Mỗi người viết test cho module mình phụ trách và review ít nhất một Pull Request của người khác.
- **Không commit:** `.env`, khoá API, mật khẩu, PDF/file nguồn lớn, kết quả OCR, model weights/cache, Qdrant volume, `.venv/`, log, `registry.db`, `eval/results/`.

## Lưu ý

- **Quota Groq Free** có hạn chế theo phút và theo ngày, tính theo từng model và có thể thay đổi. Kiểm tra trang Limits trong Groq Console trước mỗi buổi demo; khi hết quota thì dừng gọi và thông báo người dùng. Với cấu hình mặc định, hai câu hỏi liên tiếp trong vòng ~35 giây có thể nhận lỗi tạm thời "quá tải" (xem `.env.example`, mục EVIDENCE_MAX_TOKENS).
- Chỉ câu hỏi và các đoạn bằng chứng cần thiết được gửi tới Groq; không gửi dữ liệu cá nhân.
- Chatbot trích dẫn nguồn theo metadata của tài liệu, từ chối hoặc hỏi lại khi thiếu bằng chứng. Câu trả lời chỉ mang tính tham khảo, sinh viên cần đối chiếu với văn bản gốc.
- Hạn chế đã biết của MVP: mỗi câu hỏi được truy xuất độc lập, lịch sử hội thoại chỉ nằm trong phiên làm việc của trình duyệt; chưa lọc theo khóa tuyển sinh (payload chưa có dữ liệu); trích dẫn hiển thị trang đầu của đoạn nhiều trang.
