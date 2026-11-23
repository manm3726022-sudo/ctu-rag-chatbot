'''Truy xuất lai cho kho CTU (Pipeline B5–B6):
  câu hỏi -> router -> văn bản còn dùng được (manifest) -> BGE-M3 dense+sparse -> Qdrant RRF
  -> (ghim "Điều N"/"Phụ lục") -> khử trùng -> (reranker tùy chọn) -> chọn evidence theo token.

Hợp đồng với TV4 (backend/services/retrieval.py):
  retrieve(question, filters=None) -> Retrieval(routed, evidence, n_candidates, top_score)
  - evidence: list[EvidenceChunk] đã gán source_id S1, S2, ... theo thứ hạng
  - top_score: điểm xếp hạng cao nhất (ngưỡng chỉ áp dụng khi reranker bật)
  - routed.term_key: học kỳ nhận diện được (None nếu không có)
filters (tùy chọn, cho đánh giá/thử nghiệm): require_checked, document_ids, term_key.

Cố ý không import FlagEmbedding/QdrantClient ở cấp module (chỉ import khi dùng) để test và /health nhẹ.'''
import re
import time
from dataclasses import dataclass, field

from qdrant_client import models

from backend.schemas import EvidenceChunk
from backend.services import reranker
from backend.services.query_router import Routed, route
from backend.services.reranker import Candidate
from core import config, corpus_catalog, embedding


class RetrievalError(Exception):
    '''Không truy cập được Qdrant/model; API trả 503 thay vì lỗi 500.'''


@dataclass
class Retrieval:
    routed: Routed
    evidence: list
    n_candidates: int
    top_score: float
    timings_ms: dict = field(default_factory=dict)


@dataclass
class SearchResult:
    routed: Routed
    fused: list  # ứng viên sau RRF + ghim + khử trùng, theo thứ tự RRF
    ranked: list  # sau reranker, giảm dần
    selected: list  # đoạn được chọn làm evidence
    reason: str = None  # 'empty_question' | 'no_valid_document' | 'no_candidates' | None
    timings_ms: dict = field(default_factory=dict)


# ---------------------------------------------------------------- client Qdrant
_client = None


def get_client():
    global _client
    if _client is None:
        from qdrant_client import QdrantClient

        _client = QdrantClient(url=config.QDRANT_URL, timeout=30)
    return _client


def set_client(client):
    '''Dùng trong test (QdrantClient(":memory:") hoặc bản giả).'''
    global _client
    _client = client


def __getattr__(name):  # PEP 562: giữ tương thích "from ...retriever import client"
    if name == 'client':
        return get_client()
    raise AttributeError(f'module {__name__!r} has no attribute {name!r}')


# ---------------------------------------------------------------- bộ lọc
def build_filter(docs, require_checked: bool):
    must = [
        models.FieldCondition(
            key='document_id', match=models.MatchAny(any=[d.document_id for d in docs])
        ),
        models.FieldCondition(
            key='sha256',
            match=models.MatchAny(any=sorted({s for d in docs for s in d.active_sha256})),
        ),
        models.FieldCondition(key='status', match=models.MatchValue(value='indexed')),
    ]
    if require_checked:
        must.append(
            models.FieldCondition(key='review_status', match=models.MatchValue(value='checked'))
        )
    return models.Filter(must=must)


def _documents(routed: Routed, catalog, filters: dict) -> list:
    '''Tập văn bản được phép tìm. Nêu đích danh văn bản mà văn bản đó không còn hiệu lực ở học kỳ
    được hỏi thì trả rỗng (TV4 sẽ báo no_valid_document_for_term thay vì trả lời bằng văn bản khác).'''
    if 'term_key' in filters:
        term = filters['term_key']
    else:
        term = None if routed.about_validity else routed.term_key
    docs = corpus_catalog.valid_documents(term, catalog)
    wanted = set(filters.get('document_ids') or routed.document_ids)
    return [d for d in docs if d.document_id in wanted] if wanted else docs


# ---------------------------------------------------------------- truy vấn Qdrant
def _hybrid(client, enc, flt) -> list:
    prefetch = [
        models.Prefetch(query=enc.dense, using='dense', filter=flt, limit=config.RETRIEVE_PREFETCH)
    ]
    if enc.indices:
        prefetch.append(
            models.Prefetch(
                query=models.SparseVector(indices=enc.indices, values=enc.values),
                using='sparse',
                filter=flt,
                limit=config.RETRIEVE_PREFETCH,
            )
        )
    res = client.query_points(
        collection_name=config.COLLECTION,
        prefetch=prefetch,
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        limit=config.RETRIEVE_LIMIT,
        with_payload=True,
    )
    return [Candidate(str(p.id), dict(p.payload or {}), float(p.score)) for p in res.points]


def _norm_section(section: str) -> str:
    return re.sub(r'\s*>\s*', ' ', section or '').strip()


def section_matches(section: str, articles, appendix_items) -> bool:
    '''Mục "Quy định > Chương II > Điều 14" khớp "Điều 14"; "Phụ lục V.b" / "Phụ lục > V.b" khớp "V.b".'''
    s = _norm_section(section)
    for article in articles:
        if re.search(rf'(?<!\d){re.escape(article)}(?!\d)', s):
            return True
    for item in appendix_items:
        if '.' in item:
            pattern = rf'Phụ lục {re.escape(item)}(?!\w)'
        else:  # nhóm "V" khớp V.a, V.b, ... nhưng không khớp "VI"
            pattern = rf'Phụ lục {re.escape(item)}(?:\.[a-z])?(?!\w)'
        if re.search(pattern, s, re.IGNORECASE):
            return True
    return False


def _pinned(client, flt, routed: Routed) -> list:
    '''Câu hỏi nêu số điều/phụ lục: lấy thẳng các đoạn có mục đó (kho chỉ vài trăm điểm).'''
    if not (routed.articles or routed.appendix_items):
        return []
    found, offset = [], None
    while True:
        points, offset = client.scroll(
            collection_name=config.COLLECTION,
            scroll_filter=flt,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for p in points:
            payload = dict(p.payload or {})
            if section_matches(payload.get('section', ''), routed.articles, routed.appendix_items):
                found.append(Candidate(str(p.id), payload, 0.0, pinned=True))
        if offset is None:
            break
    found.sort(key=lambda c: (c.payload.get('document_id', ''), c.payload.get('page_start') or 0))
    return found[: config.RETRIEVE_MAX_PINNED]


# ---------------------------------------------------------------- khử trùng
def _span(c: Candidate):
    start = c.payload.get('page_start') or 0
    return start, c.payload.get('page_end') or start


def _words(text: str) -> set:
    return set(re.findall(r'\w+', (text or '').lower()))


def _is_duplicate(a: Candidate, b: Candidate) -> bool:
    '''Cùng văn bản, chồng trang, và (nội dung gần như trùng HOẶC một bản checked + một bản pending
    cùng mục). Hai đoạn cùng mục nhưng cùng trạng thái và khác nội dung KHÔNG bị coi là trùng
    (một Điều dài được cắt thành nhiều đoạn).'''
    pa, pb = a.payload, b.payload
    if pa.get('document_id') != pb.get('document_id'):
        return False
    (sa, ea), (sb, eb) = _span(a), _span(b)
    if sa > eb or sb > ea:
        return False
    wa, wb = _words(pa.get('content')), _words(pb.get('content'))
    if wa and wb and len(wa & wb) / len(wa | wb) >= 0.85:
        return True
    return pa.get('review_status') != pb.get('review_status') and _norm_section(
        pa.get('section')
    ).lower() == _norm_section(pb.get('section')).lower()


def _checked(c: Candidate) -> int:
    return 1 if c.payload.get('review_status') == 'checked' else 0


def dedupe(cands: list) -> list:
    kept = []
    for c in cands:
        for i, k in enumerate(kept):
            if _is_duplicate(k, c):
                if _checked(c) > _checked(k):
                    kept[i] = c  # ưu tiên bản đã duyệt
                break
        else:
            kept.append(c)
    return kept


def _merge(fused: list, pins: list) -> list:
    seen, merged = set(), []
    for c in [*pins, *fused]:
        if c.point_id not in seen:
            seen.add(c.point_id)
            merged.append(c)
    return dedupe(merged)[: config.RETRIEVE_LIMIT]


# ---------------------------------------------------------------- API chính
def search(question: str, filters: dict = None, catalog=None) -> SearchResult:
    started = time.perf_counter()
    filters = filters or {}
    require_checked = filters.get('require_checked', config.RETRIEVE_REQUIRE_CHECKED)
    catalog = corpus_catalog.load_catalog() if catalog is None else catalog
    routed = route(question, catalog)
    if not routed.question:
        return SearchResult(
            routed, [], [], [], 'empty_question',
            {'retrieval_total_ms': round((time.perf_counter() - started) * 1000, 1)},
        )
    docs = _documents(routed, catalog, filters)
    if not docs:
        return SearchResult(
            routed, [], [], [], 'no_valid_document',
            {'retrieval_total_ms': round((time.perf_counter() - started) * 1000, 1)},
        )
    flt = build_filter(docs, require_checked)
    try:
        client = get_client()
        stage_started = time.perf_counter()
        enc = embedding.encode([routed.question])[0]
        timings_ms = {
            'embedding_ms': round((time.perf_counter() - stage_started) * 1000, 1)
        }
        stage_started = time.perf_counter()
        fused = _hybrid(client, enc, flt)
        timings_ms['qdrant_hybrid_ms'] = round(
            (time.perf_counter() - stage_started) * 1000, 1
        )
        stage_started = time.perf_counter()
        pins = _pinned(client, flt, routed)
        timings_ms['pin_scan_ms'] = round((time.perf_counter() - stage_started) * 1000, 1)
    except Exception as exc:  # noqa: BLE001 (Qdrant/model lỗi -> báo 503 qua RetrievalError)
        raise RetrievalError(f'{type(exc).__name__}: {exc}') from exc
    cands = _merge(fused, pins)
    if not cands:
        timings_ms['retrieval_total_ms'] = round(
            (time.perf_counter() - started) * 1000, 1
        )
        return SearchResult(routed, [], [], [], 'no_candidates', timings_ms)
    try:
        if config.RERANK_ENABLED:
            stage_started = time.perf_counter()
            ranked = reranker.rerank(routed.question, cands)
            timings_ms['rerank_ms'] = round(
                (time.perf_counter() - stage_started) * 1000, 1
            )
            diversity_ratio = None
        else:
            ranked = sorted(
                cands,
                key=lambda candidate: (candidate.pinned, candidate.score),
                reverse=True,
            )
            timings_ms['rerank_ms'] = 0.0
            diversity_ratio = 0.0 if any(candidate.pinned for candidate in ranked) else None
        stage_started = time.perf_counter()
        selected = reranker.select_evidence(ranked, diversity_ratio=diversity_ratio)
        timings_ms['evidence_selection_ms'] = round(
            (time.perf_counter() - stage_started) * 1000, 1
        )
    except Exception as exc:  # noqa: BLE001 (reranker lỗi/hết RAM -> 503 thay vì 500)
        raise RetrievalError(f'{type(exc).__name__}: {exc}') from exc
    timings_ms['retrieval_total_ms'] = round((time.perf_counter() - started) * 1000, 1)
    return SearchResult(routed, cands, ranked, selected, timings_ms=timings_ms)


def _article(section) -> str:
    m = re.search(r'Điều \d+', section or '')
    return m[0] if m else None


def to_evidence(selected: list) -> list:
    '''Payload Qdrant -> EvidenceChunk của TV4. Tên văn bản, mục, trang lấy từ payload (metadata),
    không lấy từ lời LLM. Dựng trực tiếp (không qua core.corpus_evidence.to_evidence) vì hàm đó
    từ chối đoạn pending, còn chế độ đánh giá cần dùng cả đoạn pending.'''
    out = []
    for i, c in enumerate(selected, start=1):
        p = c.payload
        out.append(
            EvidenceChunk(
                source_id=f'S{i}',
                chunk_id=str(p.get('chunk_id') or c.point_id),
                document_id=p['document_id'],
                doc_title=p.get('title') or p['document_id'],
                doc_number=p.get('document_number'),
                article=_article(p.get('section')),
                section=p.get('section'),
                page_start=p.get('page_start'),
                page_end=p.get('page_end'),
                source_url=p.get('source_url'),
                text=p['content'],
                score=c.final_score,
            )
        )
    return out


def retrieve(question: str, filters: dict = None) -> Retrieval:
    res = search(question, filters)
    evidence = to_evidence(res.selected)
    top = max((candidate.final_score for candidate in res.selected), default=0.0)
    return Retrieval(res.routed, evidence, len(res.fused), top, res.timings_ms)


def stats() -> dict:
    '''Số điểm trong collection (dùng cho /health và smoke test).'''
    try:
        client = get_client()
        total = client.count(collection_name=config.COLLECTION, exact=True).count
        checked = client.count(
            collection_name=config.COLLECTION,
            count_filter=models.Filter(
                must=[models.FieldCondition(key='review_status', match=models.MatchValue(value='checked'))]
            ),
            exact=True,
        ).count
    except Exception as exc:  # noqa: BLE001
        raise RetrievalError(f'{type(exc).__name__}: {exc}') from exc
    return {
        'points': total,
        'checked': checked,
        'pending': total - checked,
        'require_checked': config.RETRIEVE_REQUIRE_CHECKED,
    }
