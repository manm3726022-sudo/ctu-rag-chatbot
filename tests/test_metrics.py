from types import SimpleNamespace

from eval import run_retrieval_eval as ev
from eval.metrics import aggregate, case_metrics, first_hit_rank, hits, overlaps, split_of

SRC = [{'document_id': 'qd3266', 'page_start': 8, 'page_end': 8}]


def chunk(doc, a, b=None):
    return {'document_id': doc, 'page_start': a, 'page_end': b or a}


def test_chong_lan_trang():
    assert overlaps(5, 6, 6, 9) and not overlaps(5, 6, 7, 9)


def test_hits_can_cung_van_ban_va_chong_trang():
    assert hits(chunk('qd3266', 7, 8), SRC[0])
    assert not hits(chunk('qd3266', 9, 9), SRC[0])
    assert not hits(chunk('qd4932', 8), SRC[0])


def test_thu_hang_va_case_metrics():
    chunks = [chunk('qd4932', 1), chunk('qd3266', 8), chunk('qd3266', 20)]
    assert first_hit_rank(chunks, SRC) == 2
    m = case_metrics(chunks, SRC, k=5)
    assert m['hit'] == 1.0 and m['full'] == 1.0 and m['rr'] == 0.5 and abs(m['precision'] - 1 / 3) < 1e-9
    assert case_metrics(chunks[:1], SRC, k=5)['hit'] == 0.0
    assert case_metrics([], SRC)['rr'] == 0.0


def test_cau_nhieu_nguon_do_do_phu():
    sources = SRC + [{'document_id': 'qd4932', 'page_start': 10, 'page_end': 10}]
    m = case_metrics([chunk('qd3266', 8)], sources)
    assert m['hit'] == 1.0 and m['coverage'] == 0.5 and m['full'] == 0.0
    both = case_metrics([chunk('qd3266', 8), chunk('qd4932', 10)], sources)
    assert both['full'] == 1.0


def test_k_cat_top():
    chunks = [chunk('x', 1)] * 5 + [chunk('qd3266', 8)]
    assert case_metrics(chunks, SRC, k=5)['hit'] == 0.0
    assert case_metrics(chunks, SRC, k=6)['hit'] == 1.0


def test_aggregate():
    a = aggregate([{'hit': 1.0, 'coverage': 1.0, 'full': 1.0, 'precision': 1.0, 'rr': 1.0},
                   {'hit': 0.0, 'coverage': 0.0, 'full': 0.0, 'precision': 0.0, 'rr': 0.0}])
    assert a['n'] == 2 and a['hit'] == 0.5 and a['mrr'] == 0.5
    assert aggregate([])['n'] == 0


def test_chia_validation_test_co_dinh():
    assert split_of('CTU-005') == 'test' and split_of('CTU-010') == 'test' and split_of('CTU-009') == 'validation'
    assert split_of('CTU-100') == 'test'


def test_select_cases_chi_lay_cau_answer_co_nguon():
    gold = [
        {'case_id': 'CTU-001', 'action': 'answer', 'sources': SRC},
        {'case_id': 'CTU-002', 'action': 'abstain', 'sources': []},
        {'case_id': 'CTU-005', 'action': 'answer', 'sources': SRC},
        {'case_id': 'CTU-003', 'action': 'answer', 'sources': []},
    ]
    assert [g['case_id'] for g in ev.select_cases(gold, 'validation')] == ['CTU-001']
    assert [g['case_id'] for g in ev.select_cases(gold, 'test')] == ['CTU-005']
    assert len(ev.select_cases(gold, 'all')) == 2


def test_evaluate_voi_search_gia():
    def fake_search(question, filters):
        good = SimpleNamespace(payload=chunk('qd3266', 8), final_score=0.9)
        bad = SimpleNamespace(payload=chunk('qd4932', 1), final_score=0.1)
        return SimpleNamespace(fused=[bad, good], ranked=[good, bad], selected=[good], reason=None)

    cases = [{'case_id': 'CTU-001', 'category': 'hoc_vu', 'question': 'q', 'sources': SRC}]
    rep = ev.evaluate(cases, fake_search, k=5, filters={'require_checked': False})
    assert rep['overall']['fused']['mrr'] == 0.5 and rep['overall']['ranked']['mrr'] == 1.0
    assert rep['overall']['evidence']['hit'] == 1.0 and rep['cases'][0]['evidence_hit'] == 1.0
    assert rep['by_category']['evidence']['hoc_vu']['n'] == 1


def test_tom_tat_diem_top1_cua_cau_tim_dung():
    cases = [
        {'evidence_hit': 1.0, 'reason': '', 'top_score': 0.99},
        {'evidence_hit': 1.0, 'reason': '', 'top_score': 0.40},
        {'evidence_hit': 1.0, 'reason': '', 'top_score': 0.80},
        {'evidence_hit': 0.0, 'reason': '', 'top_score': 0.03},  # trượt: không tính vào mức thấp nhất
        {'evidence_hit': 1.0, 'reason': 'no_candidates', 'top_score': 0.0},
    ]
    ss = ev.score_summary(cases)
    assert ss['n'] == 3 and ss['min'] == 0.40 and ss['median'] == 0.80
    assert ev.score_summary([]) == {'n': 0}


def test_evaluate_ghi_top_score():
    def fake_search(question, filters):
        good = SimpleNamespace(payload=chunk('qd3266', 8), final_score=0.95)
        return SimpleNamespace(fused=[good], ranked=[good], selected=[good], reason=None)

    rep = ev.evaluate([{'case_id': 'CTU-001', 'category': 'hoc_vu', 'question': 'q', 'sources': SRC}], fake_search)
    assert rep['cases'][0]['top_score'] == 0.95 and rep['top_score_found']['min'] == 0.95
