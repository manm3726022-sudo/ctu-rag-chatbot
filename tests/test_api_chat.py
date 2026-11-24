'''T13: mock retriever và generator, không nạp model, không gọi Groq.'''
from types import SimpleNamespace as NS

from fastapi.testclient import TestClient

from backend import main
from backend.schemas import EvidenceChunk
from backend.services import generator, groq_client

EV = [EvidenceChunk(source_id='S1', chunk_id='c1', document_id='d', doc_title='Quy định thử', doc_number='1/QĐ-T',
                    article='Điều 5', section='Điều 5', page_start=2, page_end=2,
                    text='Mỗi học kỳ không quá 18 tín chỉ.')]


def setup(monkeypatch, evidence=EV, draft=None, exc=None):
    monkeypatch.setattr(main.retrieval, 'retrieve',
                        lambda q: NS(routed=NS(term_key=None, question=q), evidence=evidence,
                                     n_candidates=1, top_score=0.9))

    def fake(q, e):
        if exc:
            raise exc
        return draft

    monkeypatch.setattr(main.generator, 'generate_answer', fake)
    monkeypatch.setattr(main, '_log', lambda **kw: None)
    return TestClient(main.app)


def test_citation_lay_tu_metadata(monkeypatch):
    c = setup(monkeypatch, draft=generator.AnswerDraft('Tối đa 18 tín chỉ [S1].'))
    r = c.post('/chat', json={'question': 'Tối đa bao nhiêu tín chỉ?'}).json()
    assert r['citations'][0]['document'] == 'Quy định thử (1/QĐ-T)' and r['citations'][0]['page'] == 2
    assert r['abstain'] is False


def test_khong_bang_chung_thi_tu_choi_va_khong_goi_llm(monkeypatch):
    c = setup(monkeypatch, evidence=[], exc=AssertionError('không được gọi LLM'))
    r = c.post('/chat', json={'question': 'abc'}).json()
    assert r['abstain'] is True and r['answer'] == main.ABSTAIN_MSG
    assert r['total_tokens'] == 0


def test_clarify(monkeypatch):
    c = setup(monkeypatch, draft=generator.AnswerDraft('Bạn học khóa nào?', clarify=True))
    r = c.post('/chat', json={'question': 'Điều kiện tốt nghiệp?'}).json()
    assert r['need_clarification'] is True
    assert r['risk_flag'] is None


def test_followup_context_is_used_for_retrieval_and_generation(monkeypatch):
    seen = {}
    c = setup(monkeypatch, draft=generator.AnswerDraft('Câu trả lời [S1].'))

    def fake_retrieve(question):
        seen['retrieval'] = question
        return NS(
            routed=NS(term_key=None, question=question),
            evidence=EV,
            n_candidates=1,
            top_score=0.9,
        )

    def fake_generate(question, evidence):
        seen['generation'] = question
        return generator.AnswerDraft('Câu trả lời [S1].')

    monkeypatch.setattr(main.retrieval, 'retrieve', fake_retrieve)
    monkeypatch.setattr(main.generator, 'generate_answer', fake_generate)
    r = c.post(
        '/chat',
        json={
            'question': 'Khóa 47',
            'history': [
                {'role': 'user', 'content': 'Điều kiện cảnh báo học vụ là gì?'},
                {
                    'role': 'assistant',
                    'content': 'Bạn thuộc khóa nào?',
                    'need_clarification': True,
                },
            ],
        },
    )

    assert r.status_code == 200
    assert 'Điều kiện cảnh báo học vụ là gì?' in seen['retrieval']
    assert 'Khóa 47' in seen['retrieval']
    assert seen['generation'] == seen['retrieval']


def test_confirmation_followup_that_clarifies_again_abstains_instead(monkeypatch):
    c = setup(
        monkeypatch,
        draft=generator.AnswerDraft('Bạn muốn biết điểm chữ nào?', clarify=True),
    )
    r = c.post(
        '/chat',
        json={
            'question': 'Đúng vậy',
            'history': [
                {
                    'role': 'user',
                    'content': '3.7 điểm trên thang điểm 4 có tương ứng với điểm A không?',
                },
                {
                    'role': 'assistant',
                    'content': 'Bạn muốn biết điểm 3.7 tương ứng với điểm chữ nào? Vui lòng xác nhận.',
                    'need_clarification': True,
                },
            ],
        },
    ).json()

    assert r['need_clarification'] is False
    assert r['abstain'] is True
    assert r['answer'] == main.ABSTAIN_MSG
    assert 'no_citation' not in (r['risk_flag'] or '')
    assert 'clarification_after_confirmation' in r['risk_flag']


def test_khong_co_citation_hop_le_thi_tu_choi(monkeypatch):
    c = setup(monkeypatch, draft=generator.AnswerDraft('Trả lời không nguồn.'))
    r = c.post('/chat', json={'question': 'hỏi'}).json()
    assert r['abstain'] is True and 'no_citation' in r['risk_flag']


def test_total_tokens_counts_citation_retry(monkeypatch):
    c = setup(monkeypatch)
    drafts = iter([
        generator.AnswerDraft('Trả lời không nguồn.', usage={'total_tokens': 120}),
        generator.AnswerDraft('Tối đa 18 tín chỉ [S1].', usage={'total_tokens': 150}),
    ])
    monkeypatch.setattr(generator, 'generate_answer', lambda q, e: next(drafts))

    response = c.post('/chat', json={'question': 'Tối đa bao nhiêu tín chỉ?'})

    assert response.status_code == 200
    assert response.json()['total_tokens'] == 270


def test_het_quota_tra_503(monkeypatch):
    c = setup(monkeypatch, exc=groq_client.QuotaExhausted('hết quota', retry_after=43))
    r = c.post('/chat', json={'question': 'hỏi'})
    assert r.status_code == 503 and r.headers.get('retry-after') == '43'


def test_dau_vao_khong_hop_le(monkeypatch):
    c = setup(monkeypatch)
    assert c.post('/chat', json={'question': ''}).status_code == 422
    assert c.post('/chat', json={'question': 'x' * 1001}).status_code == 422


def test_kem_yeu_gan_co_can_xac_minh(monkeypatch):
    c = setup(monkeypatch, draft=generator.AnswerDraft('Xếp loại Yếu [S1].'))
    r = c.post('/chat', json={'question': 'Rèn luyện loại kém thì sao?'}).json()
    assert 'needs_verification' in r['risk_flag']


def test_health_khong_lo_khoa():
    r = TestClient(main.app).get('/health').json()
    assert r['retriever'] == 'mock' and 'groq_key_set' in r
    assert all('gsk_' not in str(v) for v in r.values())
