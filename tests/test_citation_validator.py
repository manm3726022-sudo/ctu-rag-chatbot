'''T12'''
from backend.schemas import EvidenceChunk
from backend.services.citation_validator import validate


def ev(n=1, text='Mỗi học kỳ không quá 18 tín chỉ.'):
    return EvidenceChunk(source_id=f'S{n}', chunk_id=f'c{n}', document_id='d', doc_title='Tên', doc_number='1/QĐ',
                         article='Điều 5', section='Chương II > Điều 5', page_start=3, page_end=3, text=text)


def test_citation_hop_le_lay_metadata_tu_evidence():
    _clean, cites, flags = validate('Không quá 18 tín chỉ [S1].', [ev()])
    assert cites[0].document == 'Tên (1/QĐ)' and cites[0].page == 3 and flags == []


def test_citation_bia_bi_go():
    clean, cites, flags = validate('Theo quy định [S9] và [S1].', [ev()])
    assert '[S9]' not in clean and 'invalid_citation_removed' in flags and len(cites) == 1


def test_khong_citation_nao():
    _, cites, flags = validate('Câu trả lời không dẫn nguồn.', [ev()])
    assert cites == [] and 'no_citation' in flags


def test_con_so_la_bi_gan_co():
    _, _, flags = validate('Tối đa 24 tín chỉ [S1].', [ev()])
    assert 'unsupported_number' in flags


def test_chap_nhan_nhan_gop_va_dang_khac():
    evs = [ev(1), ev(2, 'Học phí mỗi tín chỉ là 500 nghìn đồng.')]
    for answer in ['Không quá 18 tín chỉ [S1, S2].', 'Không quá 18 tín chỉ [S1][S2].', 'Không quá 18 tín chỉ 【S1】【S2】.',
                   'Không quá 18 tín chỉ [S 1] [S 2].', 'Không quá 18 tín chỉ (S1) (S2).', 'Không quá 18 tín chỉ [S1 và S2].']:
        clean, cites, flags = validate(answer, evs)
        assert [c.source_id for c in cites] == ['S1', 'S2'] and 'no_citation' not in flags, answer
        assert '[S1][S2]' in clean.replace(' ', '') or '[S1]' in clean


def test_nhan_gop_co_ma_khong_ton_tai_van_bi_go():
    clean, cites, flags = validate('Quy định [S1, S9].', [ev()])
    assert [c.source_id for c in cites] == ['S1'] and 'invalid_citation_removed' in flags and '[S9]' not in clean
