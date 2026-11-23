# TV3 – Truy xuất: cách chạy và hợp đồng

Phạm vi: B5 (hybrid search), B6 (reranker, chọn evidence), đánh giá truy xuất (B10), và các công cụ phụ trợ
(smoke test, dọn index, duyệt đoạn). Việc lập chỉ mục (B4) do TV2 làm trong `ingestion/index.py`.

## Hợp đồng với TV4

`backend/services/retrieval.py` chọn bộ truy xuất theo `RETRIEVER` trong `.env`. Với `real`, nó import:

| Tên | Ở đâu | Vai trò |
|---|---|---|
| `retrieve(question, filters=None) -> Retrieval` | `backend/services/retriever.py` | `Retrieval(routed, evidence, n_candidates, top_score, timings_ms)` |
| `RetrievalError` | `backend/services/retriever.py` | Lỗi Qdrant/model → API trả 503 |
| `stats()` | `backend/services/retriever.py` | `/health`: số điểm tổng/checked/pending |
| `encode(list[str])` | `core/embedding.py` | warmup |
| `_reranker()` | `backend/services/reranker.py` | warmup khi `RERANK_ENABLED=true` |

`evidence` là `list[EvidenceChunk]` đã gán `S1, S2, ...`; `top_score` là điểm xếp hạng cao nhất;
`routed.term_key` là học kỳ nhận diện được (20241 = HK1 năm học 2024–2025) hoặc `None`.
`filters` (tùy chọn): `require_checked` (bool), `document_ids` (list), `term_key` (int).

## Luồng một câu hỏi

1. `query_router.route`: chuẩn hóa NFC; nhận diện văn bản nêu đích danh, "Điều N", "Phụ lục V.b", học kỳ + năm học, khóa, câu hỏi về hiệu lực.
2. `corpus_catalog.valid_documents`: văn bản còn dùng được (manifest) theo học kỳ (nếu có).
3. Bộ lọc Qdrant: `document_id` ∈ văn bản hợp lệ, `sha256` ∈ tệp nguồn chính, `status = indexed`, và `review_status = checked` nếu `RETRIEVE_REQUIRE_CHECKED`.
4. BGE-M3 mã hóa câu hỏi → 2 prefetch (dense top 20, sparse top 20) → RRF → tối đa 10 ứng viên.
5. Ghim tối đa 4 đoạn theo "Điều N"/"Phụ lục" (nếu có) → khử trùng → tối đa 10 ứng viên.
6. Nếu `RERANK_ENABLED=true`, BGE-Reranker chấm cặp (câu hỏi, đoạn); nếu không, giữ thứ tự RRF. Sau đó chọn ≤ `EVIDENCE_MAX_CHUNKS` đoạn trong `EVIDENCE_MAX_TOKENS` token.
7. Payload → `EvidenceChunk` (tên văn bản, mục, trang lấy từ metadata).

Mặc định `RERANK_ENABLED=false`: hệ thống bỏ qua cross-encoder và dùng thứ tự RRF, tránh độ trễ
cao trên CPU. Bật `RERANK_ENABLED=true` để ưu tiên chất lượng xếp hạng; giới hạn tối đa 10 ứng viên
và 512 token mỗi cặp. Ngân sách evidence mặc định là 2.000 token. So sánh validation trước/sau,
đặc biệt độ phủ câu hỏi cần nhiều văn bản. `timings_ms` và `scripts.debug_chat --no-llm` tách
thời gian embedding, Qdrant, quét đoạn ghim, rerank và chọn evidence.

## Chạy trên máy của bạn (thứ tự khuyến nghị)

```text
docker compose up -d qdrant
python -m scripts.ingest --document qd4932 --document tt40 --document hd2427     # chưa cần OCR
python -m scripts.smoke_retrieval        # phải ĐẠT: 1.024 chiều, cosine ~1 với vector đã lưu, in ví dụ truy xuất
python -m scripts.ingest                 # nạp nốt QĐ 3266 và QĐ 5976 (cần Tesseract vie+eng)
python -m scripts.smoke_retrieval "Điều 14 quy định gì?"   # kiểm tra trang: Điều 14 QĐ 3266 phải ở trang 8
python -m eval.run_retrieval_eval        # validation, gồm pending; mục tiêu Recall@5 ≥ 90%
```

Nếu `smoke_retrieval` bước 3 báo cosine thấp: model/tham số khác nhau giữa lúc nạp và lúc truy vấn
(kiểm `EMBED_MODEL`, `USE_FP16`). Nếu bước 1 báo thiếu vector `dense`/`sparse`: collection cũ từ 16/11 sai schema;
xóa collection (`curl -X DELETE http://localhost:6333/collections/ctu_knowledge`) rồi nạp lại.

## Kiểm thử

| File | Kiểm gì | Cần Docker/model? |
|---|---|---|
| `tests/test_query_router.py` | số hiệu, Điều, phụ lục, học kỳ, hiệu lực, khóa | không |
| `tests/test_corpus_catalog.py` | manifest thật, nguồn chính, hiệu lực theo kỳ | không |
| `tests/test_reranker.py` | rerank, giới hạn token/đoạn, đa dạng văn bản | không |
| `tests/test_retriever.py` | bộ lọc, phiên bản cũ, ghim, khử trùng, hợp đồng TV4 (Qdrant/BGE giả trong `tests/fakes.py`) | không |
| `tests/test_retriever_qdrant_local.py` | cú pháp prefetch+RRF với `qdrant-client` thật (chế độ bộ nhớ) | không (cần `qdrant-client`) |
| `tests/test_embedding.py` | sparse query = sparse ingestion | không |
| `tests/test_metrics.py` | chỉ số, chia validation/test, vòng đánh giá | không |
| `tests/test_approvals.py` | sổ duyệt, xuất/ghi nhận duyệt, tìm điểm mồ côi | không |
| `tests/test_verify_rules.py` | quy tắc Yếu/Kém | không |
