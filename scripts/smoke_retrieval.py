'''T2 (phần TV3): kiểm BGE-M3 + Qdrant + reranker trên máy bạn.  Chạy: python -m scripts.smoke_retrieval ["câu hỏi"]

Không tốn quota Groq. Lần đầu chạy sẽ tải trọng số BGE-M3 và reranker (vài GB). Các bước:
  1. Qdrant sống, collection có đủ vector "dense" (1.024 chiều, cosine) và "sparse"; đếm điểm checked/pending.
  2. Tải BGE-M3, mã hóa một câu: dense 1.024 chiều, sparse có phần tử.
  3. Nhất quán với ingestion: mã hóa lại đúng văn bản của một điểm đã lưu thì cosine với vector đã lưu ~1.
  4. Chạy vài câu hỏi qua retriever (gồm cả đoạn pending) và in kết quả để mắt người kiểm tra.'''
import sys
import time

from core import config

DEFAULT_QUESTIONS = [
    'Mỗi học kỳ được đăng ký tối đa bao nhiêu tín chỉ?',
    'Tham gia 5 đợt đủ điều kiện V.b thì điểm riêng tiêu chí là bao nhiêu?',
    'QĐ 3266 có hiệu lực từ kỳ nào?',
]
failures = []


def check(ok: bool, message: str) -> None:
    print(('  [ĐẠT] ' if ok else '  [LỖI] ') + message)
    if not ok:
        failures.append(message)


def cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na, nb = sum(x * x for x in a) ** 0.5, sum(y * y for y in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def main() -> int:
    from backend.services import retriever
    from core import embedding
    from core.tokens import count_tokens

    print(f'Qdrant {config.QDRANT_URL} | collection {config.COLLECTION} | model {config.EMBED_MODEL}')
    print('\n== 1. Qdrant')
    client = retriever.get_client()
    try:
        info = client.get_collection(config.COLLECTION)
    except Exception as exc:  # noqa: BLE001
        print(f'  [LỖI] Không đọc được collection: {type(exc).__name__}: {exc}')
        print('  Gợi ý: docker compose up -d qdrant, rồi python -m scripts.ingest')
        return 1
    vectors = info.config.params.vectors
    dense = vectors.get('dense') if isinstance(vectors, dict) else None
    sparse = (info.config.params.sparse_vectors or {}).get('sparse')
    expected_dim = 768 if config.EMBED_BACKEND == 'mgte' else 1024
    check(dense is not None and dense.size == expected_dim,
          f'vector dense {expected_dim} chiều (thực tế: {getattr(dense, "size", None)})')
    check(sparse is not None, 'có vector sparse')
    st = retriever.stats()
    print(f"  điểm: {st['points']} (checked {st['checked']}, pending {st['pending']}); "
          f"RETRIEVE_REQUIRE_CHECKED={st['require_checked']}")
    check(st['points'] > 0, 'collection có dữ liệu (nếu 0: chạy python -m scripts.ingest)')
    if st['points'] == 0:
        return 1

    print('\n== 2. BGE-M3')
    t0 = time.time()
    enc = embedding.encode(['Mỗi học kỳ đăng ký tối đa bao nhiêu tín chỉ?'])[0]
    print(f'  tải + mã hóa: {time.time() - t0:.1f}s')
    check(len(enc.dense) == expected_dim, f'dense có {len(enc.dense)} chiều')
    check(len(enc.indices) > 0 and len(enc.indices) == len(enc.values), f'sparse có {len(enc.indices)} phần tử')

    print('\n== 3. Nhất quán với ingestion')
    points, _ = client.scroll(config.COLLECTION, limit=1, with_payload=True, with_vectors=['dense'])
    p = points[0]
    text = f"{p.payload['title']}\n{p.payload['section']}\n{p.payload['content']}"
    again = embedding.encode([text], max_length=8192)[0]
    cos = cosine(again.dense, p.vector['dense'])
    check(cos > 0.98, f'cosine(vector tính lại, vector đã lưu) = {cos:.4f} (cần > 0.98; thấp hơn nghĩa là '
                      'khác model/tham số giữa ingestion và truy vấn)')

    print('\n== 4. Truy xuất thử (gồm cả đoạn pending)')
    questions = sys.argv[1:] or DEFAULT_QUESTIONS
    for q in questions:
        t0 = time.time()
        res = retriever.search(q, {'require_checked': False})
        r = res.routed
        print(f'\n  Hỏi: {q}')
        print(f'  router: văn bản={list(r.document_ids)} điều={list(r.articles)} phụ lục={list(r.appendix_items)} '
              f'kỳ={r.term_key} hiệu lực={r.about_validity}  ({time.time() - t0:.1f}s)')
        if res.reason:
            print(f'  -> không có evidence: {res.reason}')
            continue
        total = 0
        for i, c in enumerate(res.selected, start=1):
            pl = c.payload
            tokens = count_tokens(pl['content'])
            total += tokens
            where = f"{pl['document_number']} | {pl['section']} | tr.{pl['page_start']}-{pl['page_end']}"
            print(f"  S{i} {c.final_score:.3f} {where} | {pl['review_status']} | {tokens} token")
            print(f"      {pl['content'][:110]!r}")
        print(f'  tổng token evidence: {total} (EVIDENCE_MAX_TOKENS={config.EVIDENCE_MAX_TOKENS})')
        check(bool(res.selected), 'có ít nhất một đoạn evidence')

    print('\nKẾT QUẢ:', 'ĐẠT' if not failures else f'{len(failures)} lỗi')
    return 1 if failures else 0


if __name__ == '__main__':
    raise SystemExit(main())
