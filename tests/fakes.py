'''Bản giả của Qdrant, BGE-M3 và BGE-Reranker để test retriever mà không cần Docker hay tải model.

FakeQdrant hiểu đúng các thứ retriever dùng: Filter(must=[FieldCondition(MatchAny|MatchValue)]),
query_points(prefetch=[dense, sparse] + FusionQuery RRF), scroll, count.'''
import math
import re
import zlib
from types import SimpleNamespace

from qdrant_client import models

from core.corpus_catalog import CatalogDoc

DIM = 32
SHA_A, SHA_A_OLD, SHA_B, SHA_C = 'a' * 64, 'z' * 64, 'b' * 64, 'c' * 64


def words(text):
    return re.findall(r'\w+', text.lower())


class FakeModel:
    '''BGE-M3 giả: dense = túi từ băm 32 chiều (chuẩn hóa), sparse = trọng số theo từ.'''

    def encode(self, texts, **kwargs):
        assert kwargs['return_dense'] and kwargs['return_sparse']
        dense, lexical = [], []
        for text in texts:
            vec = [0.0] * DIM
            weights = {}
            for w in words(text):
                vec[zlib.crc32(w.encode()) % DIM] += 1.0
                tid = str(zlib.crc32(w.encode()) % 5000)
                weights[tid] = weights.get(tid, 0.0) + 0.1
            norm = math.sqrt(sum(x * x for x in vec)) or 1.0
            dense.append([x / norm for x in vec])
            lexical.append(weights)
        return {'dense_vecs': dense, 'lexical_weights': lexical}


class FakeReranker:
    '''Điểm = độ chồng lấn từ giữa câu hỏi và đoạn, trong [0, 1].'''

    def compute_score(self, pairs, **kwargs):
        assert kwargs['normalize'] is True
        out = []
        for q, p in pairs:
            wq, wp = set(words(q)), set(words(p))
            out.append(len(wq & wp) / (len(wq) or 1))
        return out


def _match(payload, cond):
    value = payload.get(cond.key)
    m = cond.match
    if hasattr(m, 'any'):
        return value in m.any
    return value == m.value


def _passes(payload, flt):
    return flt is None or all(_match(payload, c) for c in flt.must)


class FakeQdrant:
    def __init__(self, points):
        self.points = points  # list[SimpleNamespace(id, payload, dense, sparse)]
        self.calls = []

    @staticmethod
    def _dense(a, b):
        return sum(x * y for x, y in zip(a, b, strict=True))

    @staticmethod
    def _sparse(q, p):
        table = dict(zip(p['indices'], p['values'], strict=True))
        return sum(v * table.get(i, 0.0) for i, v in zip(q.indices, q.values, strict=True))

    def query_points(self, collection_name, prefetch, query, limit, with_payload=True):
        assert isinstance(query, models.FusionQuery) and query.fusion == models.Fusion.RRF
        self.calls.append(('query_points', len(prefetch)))
        lists = []
        for pf in prefetch:
            scored = []
            for pt in self.points:
                if not _passes(pt.payload, pf.filter):
                    continue
                if pf.using == 'dense':
                    scored.append((self._dense(pf.query, pt.dense), pt))
                else:
                    scored.append((self._sparse(pf.query, pt.sparse), pt))
            scored.sort(key=lambda x: -x[0])
            lists.append([pt for s, pt in scored[: pf.limit] if s > 0])
        fused = {}
        for lst in lists:
            for rank, pt in enumerate(lst, start=1):
                fused[pt.id] = fused.get(pt.id, 0.0) + 1.0 / (60 + rank)
        by_id = {pt.id: pt for pt in self.points}
        top = sorted(fused.items(), key=lambda kv: -kv[1])[:limit]
        pts = [SimpleNamespace(id=i, payload=by_id[i].payload, score=s) for i, s in top]
        return SimpleNamespace(points=pts)

    def scroll(self, collection_name, scroll_filter=None, limit=10, offset=None, with_payload=True, with_vectors=False):
        start = offset or 0
        matching = [p for p in self.points if _passes(p.payload, scroll_filter)]
        page = matching[start : start + limit]
        nxt = start + limit if start + limit < len(matching) else None
        return [SimpleNamespace(id=p.id, payload=p.payload) for p in page], nxt

    def count(self, collection_name, count_filter=None, exact=True):
        return SimpleNamespace(count=sum(1 for p in self.points if _passes(p.payload, count_filter)))


def payload(doc_id, sha, section, pages, content, status='checked', number=None, title=None):
    return {
        'chunk_id': f'{doc_id}-{section}-{pages[0]}-{status}',
        'document_id': doc_id,
        'sha256': sha,
        'section': section,
        'page_start': pages[0],
        'page_end': pages[1],
        'content': content,
        'review_status': status,
        'status': 'indexed',
        'title': title or f'Văn bản {doc_id}',
        'document_number': number or f'{doc_id}/TEST',
        'source_url': f'https://example.org/{doc_id}.pdf',
    }


def build_points(model=None):
    model = model or FakeModel()
    rows = [
        payload('qd3266', SHA_A, 'Quy định > Chương III > Điều 14', (8, 8),
                'Mỗi học kỳ sinh viên được đăng ký tối đa 20 tín chỉ.'),
        payload('qd3266', SHA_A, 'Quy định > Chương IV > Điều 18', (10, 10),
                'Cảnh báo học vụ khi số tín chỉ nợ đọng vượt quá 24 tín chỉ đối với khóa 47.', status='pending'),
        payload('qd3266', SHA_A_OLD, 'Quy định > Chương III > Điều 14', (8, 8),
                'Mỗi học kỳ sinh viên được đăng ký tối đa 18 tín chỉ (bản cũ).'),
        payload('qd4932', SHA_B, 'Phụ lục V.b', (10, 10),
                'Hoạt động chung có xác nhận: 3 điểm mỗi đợt. Trần tiêu chí 12 điểm. Trần nhóm V: 20 điểm.'),
        payload('qd4932', SHA_B, 'Phụ lục > V.b', (10, 10),
                'V.b Tham gia hoạt động chung 3 điểm trần tiêu chí 12 trần nhóm V 20 có xác nhận đơn vị tổ chức',
                status='pending'),
        payload('qd4932', SHA_B, 'Quy chế > Điều 6', (4, 4),
                'Kết quả rèn luyện được xếp thành năm loại: Xuất sắc, Tốt, Khá, Trung bình, Yếu.'),
        payload('tt40', SHA_C, 'Thông tư > Điều 17', (7, 8),
                'Nội dung đánh giá kết quả rèn luyện của sinh viên gồm ý thức học tập và chấp hành pháp luật.',
                status='pending'),
    ]
    points = []
    for i, pl in enumerate(rows):
        enc = model.encode([f"{pl['title']}\n{pl['section']}\n{pl['content']}"], return_dense=True, return_sparse=True)
        lex = enc['lexical_weights'][0]
        points.append(SimpleNamespace(
            id=f'pt{i}', payload=pl, dense=enc['dense_vecs'][0],
            sparse={'indices': [int(t) for t in lex], 'values': list(lex.values())},
        ))
    return points


def catalog():
    return (
        CatalogDoc('qd3266', '3266/QĐ-ĐHCT', 'Quy định học vụ', 'registered', 'qd', '3266', 20242, None, None, (SHA_A,)),
        CatalogDoc('qd4932', '4932/QĐ-ĐHCT', 'Quy chế rèn luyện', 'registered', 'qd', '4932', 20261, None, None, (SHA_B,)),
        CatalogDoc('tt40', '40/2026/TT-BGDĐT', 'Công tác sinh viên', 'registered', 'tt', '40',
                   None, None, '2026-06-30', (SHA_C,)),
    )
