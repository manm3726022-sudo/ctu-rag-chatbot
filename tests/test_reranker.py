from backend.services import reranker
from backend.services.reranker import Candidate, rerank, select_evidence
from tests.fakes import FakeReranker

count = lambda text: len(text.split())  # noqa: E731


def cand(pid, doc, text, score=0.0):
    return Candidate(pid, {'document_id': doc, 'document_number': f'{doc}/T', 'section': 'Điều 1', 'content': text}, score)


def ranked(items):
    out = []
    for pid, doc, text, s in items:
        c = cand(pid, doc, text)
        c.rerank_score = s
        out.append(c)
    return sorted(out, key=lambda c: -c.rerank_score)


def test_rerank_sap_giam_dan_va_gan_diem():
    cands = [cand('1', 'a', 'học phí là gì'), cand('2', 'a', 'tối đa 20 tín chỉ mỗi học kỳ')]
    out = rerank('tối đa bao nhiêu tín chỉ mỗi học kỳ', cands, model=FakeReranker())
    assert [c.point_id for c in out] == ['2', '1'] and out[0].rerank_score > out[1].rerank_score


def test_rerank_rong_va_gioi_han_20_cap(monkeypatch):
    assert rerank('q', [], model=FakeReranker()) == []
    monkeypatch.setattr(reranker.config, 'RETRIEVE_LIMIT', 3)
    out = rerank('q', [cand(str(i), 'a', 'x') for i in range(10)], model=FakeReranker())
    assert len(out) == 3


def test_rerank_xu_ly_diem_la_so_don():
    class One:
        def compute_score(self, pairs, **kw):
            return 0.7

    out = rerank('q', [cand('1', 'a', 'x')], model=One())
    assert out[0].rerank_score == 0.7


def test_gioi_han_so_doan():
    r = ranked([(str(i), 'a', 'một hai ba', 1 - i / 10) for i in range(8)])
    assert len(select_evidence(r, max_chunks=3, max_tokens=1000, diversity_ratio=0.5, counter=count)) == 3


def test_gioi_han_token_nhung_luon_giu_doan_dau():
    r = ranked([('1', 'a', 'x ' * 50, 0.9), ('2', 'a', 'y ' * 50, 0.8), ('3', 'a', 'z ' * 10, 0.7)])
    out = select_evidence(r, max_chunks=6, max_tokens=60, diversity_ratio=0.5, counter=count)
    assert [c.point_id for c in out] == ['1', '3']  # đoạn 2 (50 từ) làm vượt 60 nên bị bỏ, đoạn 3 vừa
    big = ranked([('1', 'a', 'x ' * 500, 0.9)])
    assert len(select_evidence(big, max_tokens=10, counter=count)) == 1


def test_da_dang_van_ban_cho_cau_hoi_lien_van_ban():
    r = ranked([('1', 'a', 'x', 0.9), ('2', 'a', 'x', 0.85), ('3', 'a', 'x', 0.8), ('4', 'b', 'x', 0.5)])
    out = select_evidence(r, max_chunks=3, max_tokens=100, diversity_ratio=0.5, counter=count)
    assert {c.payload['document_id'] for c in out} == {'a', 'b'}  # văn bản b đủ gần điểm cao nhất
    assert [c.point_id for c in out] == ['1', '2', '4'] or [c.point_id for c in out] == ['1', '4', '2']


def test_van_ban_diem_qua_thap_khong_duoc_ep_vao():
    r = ranked([('1', 'a', 'x', 0.9), ('2', 'a', 'x', 0.8), ('3', 'b', 'x', 0.1)])
    out = select_evidence(r, max_chunks=2, max_tokens=100, diversity_ratio=0.5, counter=count)
    assert {c.point_id for c in out} == {'1', '2'}


def test_ket_qua_theo_thu_hang_giam_dan():
    r = ranked([('1', 'a', 'x', 0.9), ('2', 'b', 'x', 0.8), ('3', 'a', 'x', 0.7)])
    out = select_evidence(r, max_chunks=3, max_tokens=100, counter=count)
    assert [c.final_score for c in out] == sorted((c.final_score for c in out), reverse=True)


def test_rong():
    assert select_evidence([]) == []
