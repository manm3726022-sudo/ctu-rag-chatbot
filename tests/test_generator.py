from types import SimpleNamespace as NS

from backend.schemas import EvidenceChunk
from backend.services import generator


def fake_resp(text, reason='stop'):
    return NS(choices=[NS(message=NS(content=text), finish_reason=reason)], usage=None, model='fake')


def test_the_abstain_va_clarify(monkeypatch):
    monkeypatch.setattr(generator.groq_client, 'chat', lambda m, e: fake_resp('[ABSTAIN]\nChưa đủ căn cứ.'))
    d = generator.generate_answer('hỏi', '[S1] nội dung')
    assert d.abstain and not d.clarify and d.text == 'Chưa đủ căn cứ.'
    monkeypatch.setattr(generator.groq_client, 'chat', lambda m, e: fake_resp('[CLARIFY]\nBạn học khóa nào?'))
    assert generator.generate_answer('hỏi', '[S1] nội dung').clarify


def test_finish_reason_length_duoc_giu_lai(monkeypatch):
    monkeypatch.setattr(generator.groq_client, 'chat', lambda m, e: fake_resp('Dở dang', 'length'))
    assert generator.generate_answer('hỏi', '[S1] nội dung').finish_reason == 'length'


def test_prompt_dua_evidence_va_cau_hoi(monkeypatch):
    seen = {}

    def fake_chat(messages, est):
        seen['m'], seen['est'] = messages, est
        return fake_resp('OK [S1]')

    monkeypatch.setattr(generator.groq_client, 'chat', fake_chat)
    generator.generate_answer('Câu hỏi X', '[S1] Bằng chứng Y')
    user = seen['m'][1]['content']
    assert 'Câu hỏi X' in user and 'Bằng chứng Y' in user and seen['m'][0]['role'] == 'system'
    assert seen['est'] > generator.config.GROQ_MAX_OUTPUT_TOKENS


def test_format_evidence():
    e = EvidenceChunk(source_id='S1', chunk_id='c', document_id='d', doc_title='T', doc_number='1/QĐ',
                      section='Điều 5', page_start=3, text='nội dung')
    assert generator.format_evidence([e]) == '[S1] (1/QĐ, Điều 5, tr. 3)\nnội dung'
