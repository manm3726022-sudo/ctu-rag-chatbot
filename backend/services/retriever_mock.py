'''Bộ truy xuất GIẢ để TV4 phát triển API/UI khi chưa có retriever của TV3.

Cùng giao diện với runbook §9.2: retrieve(question) -> Retrieval(routed, evidence, n_candidates, top_score).
Nội dung dưới đây là DỮ LIỆU GIẢ, không phải trích từ quy chế thật. Không dùng để đánh giá chất lượng.
Thay bằng TV2/TV3 chunk mẫu khi có (đặt RETRIEVER=real trong .env).'''
import unicodedata
from dataclasses import dataclass

from backend.schemas import EvidenceChunk


@dataclass
class Routed:
    question: str
    doc_number: str | None = None
    article: str | None = None
    term_key: int | None = None


@dataclass
class Retrieval:
    routed: Routed
    evidence: list
    n_candidates: int
    top_score: float


_FAKE = [
    {'chunk_id': 'mock-a-1', 'document_id': 'doc_mock_a', 'doc_title': 'Quy định học vụ (MẪU GIẢ)',
         'doc_number': '0001/QĐ-MOCK', 'article': 'Điều 3', 'section': 'Chương I > Điều 3', 'page_start': 2,
         'keywords': ('tín chỉ', 'đăng ký', 'học kỳ'),
         'text': '[DỮ LIỆU GIẢ] Mỗi học kỳ chính, sinh viên đăng ký tối thiểu 10 tín chỉ và tối đa 20 tín chỉ, '
              'trừ học kỳ cuối khóa.'},
    {'chunk_id': 'mock-a-2', 'document_id': 'doc_mock_a', 'doc_title': 'Quy định học vụ (MẪU GIẢ)',
         'doc_number': '0001/QĐ-MOCK', 'article': 'Điều 7', 'section': 'Chương II > Điều 7', 'page_start': 5,
         'keywords': ('cảnh báo', 'học vụ', 'điểm trung bình'),
         'text': '[DỮ LIỆU GIẢ] Sinh viên bị cảnh báo học vụ khi điểm trung bình học kỳ dưới 0,8 đối với '
              'học kỳ đầu khóa hoặc dưới 1,0 đối với các học kỳ tiếp theo.'},
    {'chunk_id': 'mock-b-1', 'document_id': 'doc_mock_b', 'doc_title': 'Quy chế rèn luyện (MẪU GIẢ)',
         'doc_number': '0002/QĐ-MOCK', 'article': 'Điều 4', 'section': 'Điều 4', 'page_start': 3,
         'keywords': ('rèn luyện', 'xếp loại', 'yếu', 'kém'),
         'text': '[DỮ LIỆU GIẢ] Kết quả rèn luyện được xếp thành năm loại: Xuất sắc, Tốt, Khá, Trung bình, Yếu.'},
]


def retrieve(question: str, filters: dict | None = None) -> Retrieval:
    q = ' '.join(unicodedata.normalize('NFC', question).split())
    low = q.lower()
    hits = [p for p in _FAKE if any(k in low for k in p['keywords'])]
    evidence = []
    for i, p in enumerate(hits, start=1):
        fields = {k: v for k, v in p.items() if k != 'keywords'}
        evidence.append(EvidenceChunk(source_id=f'S{i}', score=0.9 - 0.1 * i, **fields))
    return Retrieval(Routed(q), evidence, len(hits), evidence[0].score if evidence else 0.0)
