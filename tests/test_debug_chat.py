from types import SimpleNamespace as NS

from backend.schemas import EvidenceChunk  # noqa: F401  (kiểm tra import schema)
from backend.services import generator
from backend.services.query_router import Routed
from backend.services.reranker import Candidate
from scripts import debug_chat


def cand(score=0.9):
    c = Candidate('p1', {'document_id': 'qd3266', 'chunk_id': 'c1', 'title': 'Quy định học vụ', 'document_number': '3266/QĐ-ĐHCT',
                         'section': 'Quy định > Điều 14', 'page_start': 8, 'page_end': 8, 'review_status': 'checked',
                         'content': 'Sinh viên được đăng ký học tối đa 20 TC/HK.', 'source_url': 'u'})
    c.rerank_score = score
    return c


def fake_search(selected):
    return lambda q, f: NS(routed=Routed(question=q), fused=list(selected), ranked=list(selected), selected=list(selected),
                           reason=None if selected else 'no_candidates')


def run(selected, draft=None, **kw):
    return debug_chat.diagnose('Tối đa bao nhiêu tín chỉ?', search=fake_search(selected),
                               generate=lambda q, e: draft, tokens=lambda t: len(t.split()), **kw)


def test_khong_bang_chung_khong_goi_llm():
    rep = run([], draft=None)
    assert 'KHÔNG có bằng chứng' in rep['verdict'] and 'draft' not in rep


def test_dung_truoc_llm_khi_no_llm():
    rep = run([cand()], draft=None, call_llm=False)
    assert 'Đã dừng' in rep['verdict'] and rep['evidence'][0]['source_id'] == 'S1' and rep['evidence'][0]['tokens'] == 10


def test_tra_loi_co_trich_dan():
    rep = run([cand()], generator.AnswerDraft('Tối đa 20 TC [S1].'))
    assert rep['verdict'].startswith('TRẢ LỜI CÓ TRÍCH DẪN') and rep['validation']['cited'] == ['S1']


def test_phan_biet_tu_choi_do_thieu_nhan_va_do_mo_hinh_abstain():
    thieu = run([cand()], generator.AnswerDraft('Tối đa 20 tín chỉ.'))
    assert 'KHÔNG có nhãn [S#]' in thieu['verdict']
    abstain_rong = run([cand()], generator.AnswerDraft('', abstain=True))
    assert '[ABSTAIN]' in abstain_rong['verdict'] and 'KHÔNG kèm lời giải thích' in abstain_rong['verdict']
    clarify = run([cand()], generator.AnswerDraft('Bạn học khóa nào?', clarify=True))
    assert 'HỎI LẠI' in clarify['verdict']
