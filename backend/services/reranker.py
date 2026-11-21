'''Xếp hạng lại bằng BGE-Reranker và chọn evidence theo ngân sách token (Pipeline B6).

- FlagEmbedding được import muộn; _reranker() tải model một lần.
- Điểm reranker (normalize=True) nằm trong [0, 1] nhưng KHÔNG phải xác suất đúng; chỉ dùng để xếp hạng.
- select_evidence chọn theo token chứ không chỉ theo số đoạn, vì quota Groq Free tính theo token/phút.'''
from dataclasses import dataclass, field
from functools import lru_cache

from core import config
from core.tokens import count_tokens


@dataclass
class Candidate:
    point_id: str
    payload: dict
    score: float = 0.0  # điểm RRF của Qdrant
    pinned: bool = False  # được ghim vì câu hỏi nêu "Điều N" / "Phụ lục ..."
    rerank_score: float = None
    extra: dict = field(default_factory=dict)

    @property
    def final_score(self) -> float:
        return self.score if self.rerank_score is None else self.rerank_score


@lru_cache(maxsize=1)
def _reranker():
    from FlagEmbedding import FlagReranker

    return FlagReranker(config.RERANK_MODEL, use_fp16=config.USE_FP16)


def passage(c: Candidate) -> str:
    p = c.payload
    head = ' · '.join(x for x in [p.get('document_number'), p.get('section')] if x)
    return f"{head}\n{p.get('content', '')}".strip()


def rerank(question: str, candidates: list, model=None) -> list:
    '''Chấm tối đa RETRIEVE_LIMIT cặp (câu hỏi, đoạn); trả danh sách giảm dần theo rerank_score.'''
    cands = list(candidates)[: max(1, config.RETRIEVE_LIMIT)]
    if not cands:
        return []
    model = model or _reranker()
    scores = model.compute_score(
        [[question, passage(c)] for c in cands],
        batch_size=config.RERANK_BATCH_SIZE,
        max_length=config.RERANK_MAX_LENGTH,
        normalize=True,
    )
    if isinstance(scores, (int, float)):
        scores = [scores]
    for c, s in zip(cands, scores, strict=True):
        c.rerank_score = float(s)
    # sort ổn định: cùng điểm thì giữ thứ tự RRF/ghim ban đầu
    return sorted(cands, key=lambda c: c.rerank_score, reverse=True)


def select_evidence(ranked, max_chunks=None, max_tokens=None, diversity_ratio=None, counter=None) -> list:
    '''Chọn tối đa max_chunks đoạn và không vượt max_tokens (đoạn đầu luôn được giữ).

    Lượt 1: lấy đoạn tốt nhất của MỖI văn bản nếu điểm >= diversity_ratio * điểm cao nhất
            (câu hỏi liên văn bản cần đủ nguồn).
    Lượt 2: lấp đầy phần còn lại theo thứ hạng. Kết quả sắp giảm dần theo điểm để gán S1, S2, ...'''
    if not ranked:
        return []
    max_chunks = config.EVIDENCE_MAX_CHUNKS if max_chunks is None else max_chunks
    max_tokens = config.EVIDENCE_MAX_TOKENS if max_tokens is None else max_tokens
    ratio = config.EVIDENCE_DIVERSITY_RATIO if diversity_ratio is None else diversity_ratio
    counter = counter or count_tokens
    top = ranked[0].final_score
    cost = {c.point_id: counter(c.payload.get('content', '')) for c in ranked}
    chosen, used, docs = [], 0, set()

    def take(c):
        nonlocal used
        chosen.append(c)
        used += cost[c.point_id]

    def fits(c):
        return not chosen or used + cost[c.point_id] <= max_tokens

    for c in ranked:
        if len(chosen) >= max_chunks:
            break
        doc = c.payload.get('document_id')
        if doc in docs or (chosen and c.final_score < ratio * top):
            continue
        if fits(c):
            take(c)
            docs.add(doc)
    ids = {c.point_id for c in chosen}
    for c in ranked:
        if len(chosen) >= max_chunks:
            break
        if c.point_id not in ids and fits(c):
            take(c)
            ids.add(c.point_id)
    order = {c.point_id: i for i, c in enumerate(ranked)}
    return sorted(chosen, key=lambda c: order[c.point_id])
