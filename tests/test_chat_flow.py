'''Luồng /chat: thử lại có nhắc khi thiếu trích dẫn, và nhật ký ghi đủ để chẩn đoán (không gọi Groq thật).'''
from types import SimpleNamespace as NS

from backend import main
from backend.schemas import ChatRequest, EvidenceChunk
from backend.services import generator

EV = [EvidenceChunk(source_id='S1', chunk_id='c1', document_id='d', doc_title='Quy định thử', doc_number='1/QĐ-T',
                    section='Điều 14', page_start=8, page_end=8, text='Sinh viên được đăng ký tối đa 20 TC/HK.')]


def setup(monkeypatch, drafts, evidence=EV):
    calls, logs = [], []
    monkeypatch.setattr(main.retrieval, 'retrieve',
                        lambda q: NS(routed=NS(term_key=None, document_ids=('qd3266',), articles=(), about_validity=False),
                                     evidence=evidence, n_candidates=3, top_score=0.9))

    def fake(question, evidence_text):
        calls.append(evidence_text)
        return drafts.pop(0)

    monkeypatch.setattr(main.generator, 'generate_answer', fake)
    monkeypatch.setattr(main, '_log', lambda **kw: logs.append(kw))
    return calls, logs


def test_thieu_nhan_thi_sinh_lai_co_kem_loi_nhac(monkeypatch):
    calls, _ = setup(monkeypatch, [generator.AnswerDraft('Tối đa 20 tín chỉ.'), generator.AnswerDraft('Tối đa 20 tín chỉ [S1].')])
    out = main.chat(ChatRequest(question='Tối đa bao nhiêu tín chỉ?'))
    assert len(calls) == 2 and main.RETRY_NOTE not in calls[0] and main.RETRY_NOTE in calls[1]
    assert out.abstain is False and out.citations[0].source_id == 'S1' and out.risk_flag is None


def test_van_thieu_nhan_sau_khi_thu_lai_thi_tu_choi(monkeypatch):
    calls, logs = setup(monkeypatch, [generator.AnswerDraft('Tối đa 20.'), generator.AnswerDraft('Tối đa 20.')])
    out = main.chat(ChatRequest(question='Tối đa bao nhiêu tín chỉ?'))
    assert len(calls) == 2 and out.abstain is True and out.answer == main.ABSTAIN_MSG and 'no_citation' in out.risk_flag
    assert logs[-1]['draft'] == 'Tối đa 20.' and logs[-1]['abstain'] is True  # nhật ký giữ lời mô hình thô để chẩn đoán


def test_mo_hinh_tu_choi_khong_giai_thich_van_hien_cau_mac_dinh(monkeypatch):
    calls, logs = setup(monkeypatch, [generator.AnswerDraft('', abstain=True)])
    out = main.chat(ChatRequest(question='Tối đa bao nhiêu tín chỉ?'))
    assert len(calls) == 1 and out.abstain and out.answer == main.ABSTAIN_MSG  # tag ABSTAIN thì không sinh lại
    assert logs[-1]['routed']['docs'] == ['qd3266']


def test_khong_bang_chung_cung_duoc_ghi_nhat_ky(monkeypatch):
    calls, logs = setup(monkeypatch, [], evidence=[])
    out = main.chat(ChatRequest(question='abc'))
    assert out.abstain and not calls and logs[-1]['flags'] == ['no_evidence']
