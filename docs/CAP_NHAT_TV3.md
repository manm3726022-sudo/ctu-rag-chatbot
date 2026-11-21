# Bản cập nhật TV3 – danh sách file và cách áp dụng (20/11/2026)

## Cách áp dụng

```text
git switch main && git pull
git switch -c feat/retrieval-tv3
# giải nén gói ZIP vào thư mục gốc repo (giữ nguyên đường dẫn; hỏi ghi đè thì chọn ghi đè)
python -m pip install -r requirements.txt
# MERGE các biến mới của .env.example vào .env của bạn (đừng chép đè .env): RETRIEVE_REQUIRE_CHECKED, RETRIEVE_MAX_PINNED,
#   EVIDENCE_DIVERSITY_RATIO, EMBED_QUERY_MAX_LENGTH, RERANK_MAX_LENGTH, RERANK_BATCH_SIZE, MANIFEST_PATH, APPROVED_CHUNKS_PATH
python -m pytest -q
git add -A && git commit -m "feat(retrieval): hybrid search, reranker, đánh giá, sổ duyệt đoạn" && git push -u origin feat/retrieval-tv3
```
.gitignore là bản đầy đủ mới: so sánh với bản cũ bằng `git diff` trước khi commit.

## File MỚI

| Đường dẫn | Vai trò |
|---|---|
| `core/embedding.py` | Mã hóa BGE-M3 (dense+sparse) phía truy vấn; `sparse_from_lexical` dùng chung với ingestion |
| `core/corpus_catalog.py` | Đọc manifest: văn bản còn dùng được, hiệu lực theo học kỳ, sha256 tệp nguồn chính |
| `backend/services/query_router.py` | Nhận diện số hiệu, Điều, Phụ lục, học kỳ, khóa, câu hỏi về hiệu lực |
| `backend/services/retriever.py` | Hybrid search + RRF, ghim Điều/Phụ lục, khử trùng, chuyển payload → EvidenceChunk |
| `backend/services/reranker.py` | BGE-Reranker và chọn evidence theo token + đa dạng văn bản |
| `backend/services/verify_rules.py` | Quy tắc "cần xác minh" Yếu/Kém (tách khỏi main.py, mở rộng cho CTU-085) |
| `ingestion/approvals.py` | Sổ duyệt đoạn: đọc/ghi CSV và áp dụng `checked` khi ingest |
| `eval/__init__.py`, `eval/metrics.py`, `eval/run_retrieval_eval.py` | Recall@k, Precision@k, MRR, độ phủ nguồn; chia validation/test cố định |
| `scripts/smoke_retrieval.py` | T2 phần BGE-M3 + Qdrant + reranker |
| `scripts/prune_index.py` | Dọn điểm mồ côi (văn bản archived, sha256 cũ) |
| `scripts/review_chunks.py` | Xuất đoạn pending để duyệt và ghi nhận kết quả duyệt |
| `data/review/approved_chunks.csv` | Sổ duyệt (hiện chỉ có dòng tiêu đề) – commit file này |
| `data/registry/README.md` | Giữ thư mục registry trong git (db bị bỏ qua) |
| `tests/fakes.py` + 9 file `tests/test_*.py` | Test cho toàn bộ phần mới (bản giả Qdrant/BGE, không cần Docker) |
| `docs/design.md`, `docs/tv3-retrieval.md`, `docs/CAP_NHAT_TV3.md` | Tài liệu quyết định, hướng dẫn chạy, danh sách này |

## File ĐÃ CÓ được sửa

| Đường dẫn | Sửa gì | Người sở hữu |
|---|---|---|
| `core/config.py` | Thêm `ROOT` và các biến TV3 (giữ nguyên toàn bộ biến cũ) | TV4 |
| `backend/services/retrieval.py` | Xuất `RetrievalError`; `/health` dùng `stats()` (thêm số checked/pending) | TV4 |
| `backend/main.py` | Bắt `RetrievalError` → 503; `needs_verification` chuyển sang `verify_rules.py` (vẫn import lại cùng tên) | TV4 |
| `ingestion/index.py` | Dùng `sparse_from_lexical` chung (kết quả giống hệt bản cũ) | TV2 |
| `scripts/ingest.py` | Thêm `--approved` và áp dụng sổ duyệt; hành vi mặc định không đổi | TV2 |
| `tests/conftest.py` | Giữ hai dòng cũ; thêm bỏ qua test cần ZIP của TV1 khi thiếu tệp; ghim cấu hình truy xuất | TV4 |
| `.env.example`, `.gitignore`, `requirements.txt`, `README.md` | Cập nhật khớp thực tế | chung |

Không sửa: `docker-compose.yml`, `docs/schemas/*`, `core/corpus_metadata.py`, `core/corpus_evidence.py`, `ingestion/chunking.py`, `extract.py`, `sources.py`, `rubric.py`, mọi file test cũ của TV1/TV2/TV4.

## Đã kiểm tra gì và CHƯA kiểm tra gì

Môi trường soạn thảo không có Qdrant, FlagEmbedding, Pydantic, FastAPI, pytest, ruff và không có mạng. Đã làm:
- Toàn bộ code biên dịch được; 88 test (của phần mới và các test thuần Python của TV4) chạy đạt trên bộ giả lập tối giản
  (Pydantic/pytest/qdrant_client giả, Qdrant và BGE giả trong `tests/fakes.py`); đã thử phá code có chủ đích (bỏ lọc sha256, khử trùng sai, bỏ giới hạn token) và test bắt được cả ba.
- Router chạy thử trên cả 100 câu gold; luồng đánh giá chạy thử trọn vẹn trên 24 đoạn fixture (chỉ kiểm chức năng, không phải chất lượng).
- Mô phỏng `backend.main.chat` với retriever giả: truy xuất rỗng, lỗi Qdrant → 503, cờ Yếu/Kém; `retrieval.health/warmup` ở chế độ real.

CHƯA kiểm tra (cần chạy trên máy bạn, theo `docs/tv3-retrieval.md`):
- Các lời gọi thật tới `FlagEmbedding` (`BGEM3FlagModel.encode`, `FlagReranker.compute_score`) và `qdrant-client` (`query_points` với prefetch + RRF). `tests/test_retriever_qdrant_local.py` và `scripts.smoke_retrieval` được viết để bắt lệch phiên bản ở đúng các điểm này.
- Chạy `pytest`, `ruff check` thật; hai file test của TV1 chỉ chạy khi có gói ZIP.
- Chất lượng truy xuất thật (Recall@5 ≥ 90%) và việc "ảnh N" của Word = "trang N" của PDF QĐ 3266.

## Việc còn lại KHÔNG thể làm bằng code
1. TV1/TV2 duyệt 170 đoạn `pending` (dùng `scripts/review_chunks.py`), đặc biệt các đoạn trùng nguồn trong gold; đoạn OCR sai chữ thì sửa trước khi duyệt.
2. TV1 bổ sung câu hỏi ngoài kho (nếu muốn hiệu chỉnh ngưỡng từ chối) và điền khóa tuyển sinh cho các khoản có điều kiện khóa.
3. Cả nhóm chọn một phiên bản Python và ghim tag Qdrant; TV4 đo token thật (T19) để chốt `EVIDENCE_MAX_TOKENS`.
