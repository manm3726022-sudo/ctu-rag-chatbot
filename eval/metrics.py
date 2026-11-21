'''Chỉ số truy xuất tính bằng Python thuần (Pipeline B10): không gọi LLM, không tốn quota.

Quy tắc "trúng": một đoạn truy xuất TRÚNG một nguồn kỳ vọng khi cùng document_id và khoảng trang
chồng lấn. Không so sha256 (gold ghi bản Word, Qdrant lưu bản PDF của QĐ 3266) và không so chuỗi
section (gold ghi đến khoản "Đ14.1", đoạn chỉ ghi đến Điều). Hạn chế: đoạn cùng trang nhưng khác Điều
cũng bị tính trúng, nên kết quả là cận trên so với việc so đến từng khoản.'''


def overlaps(a_start, a_end, b_start, b_end) -> bool:
    return a_start <= b_end and b_start <= a_end


def hits(chunk: dict, source: dict) -> bool:
    '''chunk: payload (hoặc dict có document_id, page_start, page_end); source: một mục của gold.'''
    if chunk.get('document_id') != source['document_id']:
        return False
    start = chunk.get('page_start') or 0
    end = chunk.get('page_end') or start
    return overlaps(start, end, source['page_start'], source['page_end'])


def first_hit_rank(chunks: list, sources: list):
    '''Thứ hạng (từ 1) của đoạn đầu tiên trúng bất kỳ nguồn nào; None nếu không có.'''
    for rank, chunk in enumerate(chunks, start=1):
        if any(hits(chunk, s) for s in sources):
            return rank
    return None


def case_metrics(chunks: list, sources: list, k: int = 5) -> dict:
    '''Chỉ số một câu hỏi trên top-k đoạn.
    hit: có ít nhất một nguồn kỳ vọng được tìm thấy (đây là "Recall@k" theo Pipeline).
    coverage: tỷ lệ nguồn kỳ vọng được tìm thấy; full: tìm đủ mọi nguồn (câu nhiều văn bản).
    precision: tỷ lệ đoạn trong top-k trúng ít nhất một nguồn. rr: nghịch đảo thứ hạng trúng đầu tiên.'''
    top = chunks[:k]
    found = sum(1 for s in sources if any(hits(c, s) for c in top))
    rank = first_hit_rank(chunks, sources)
    return {
        'hit': 1.0 if found else 0.0,
        'coverage': found / len(sources) if sources else 0.0,
        'full': 1.0 if sources and found == len(sources) else 0.0,
        'precision': (sum(1 for c in top if any(hits(c, s) for s in sources)) / len(top)) if top else 0.0,
        'rr': (1.0 / rank) if rank else 0.0,
    }


def aggregate(rows: list) -> dict:
    '''Trung bình từng chỉ số trên nhiều câu hỏi.'''
    if not rows:
        return {'n': 0, 'hit': 0.0, 'coverage': 0.0, 'full': 0.0, 'precision': 0.0, 'mrr': 0.0}
    n = len(rows)
    return {
        'n': n,
        'hit': sum(r['hit'] for r in rows) / n,
        'coverage': sum(r['coverage'] for r in rows) / n,
        'full': sum(r['full'] for r in rows) / n,
        'precision': sum(r['precision'] for r in rows) / n,
        'mrr': sum(r['rr'] for r in rows) / n,
    }


def split_of(case_id: str, test_every: int = 5) -> str:
    '''Chia cố định, không ngẫu nhiên: CTU-005, 010, 015... vào tập test (20%), còn lại là validation.
    Chỉnh tham số (chunking, RRF, reranker, ngưỡng) chỉ trên validation; tập test chỉ chạy lúc nghiệm thu.'''
    number = int(case_id.rsplit('-', 1)[-1])
    return 'test' if number % test_every == 0 else 'validation'
