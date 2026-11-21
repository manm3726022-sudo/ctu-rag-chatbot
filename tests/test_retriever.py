'''Retriever với Qdrant/BGE-M3/Reranker giả: kiểm bộ lọc, ghim, khử trùng, hợp đồng với TV4.'''
import pytest

from backend.services import reranker, retriever
from core import config, corpus_catalog, embedding
from tests import fakes


@pytest.fixture(autouse=True)
def fake_stack(monkeypatch):
    monkeypatch.setattr(embedding, 'get_model', lambda: fakes.FakeModel())
    monkeypatch.setattr(reranker, '_reranker', lambda: fakes.FakeReranker())
    monkeypatch.setattr(reranker, 'count_tokens', lambda text: len(text.split()))
    monkeypatch.setattr(corpus_catalog, 'load_catalog', lambda path=None: fakes.catalog())
    client = fakes.FakeQdrant(fakes.build_points())
    retriever.set_client(client)
    yield client
    retriever.set_client(None)


def run(question, **filters):
    return retriever.search(question, filters or None, catalog=fakes.catalog())


def sections(res):
    return [(c.payload['document_id'], c.payload['section'], c.payload['review_status']) for c in res.selected]


def test_chi_dung_doan_checked_theo_mac_dinh(monkeypatch):
    monkeypatch.setattr(config, 'RETRIEVE_REQUIRE_CHECKED', True)
    res = run('Cảnh báo học vụ khi nợ đọng vượt quá bao nhiêu tín chỉ?')
    assert res.selected and all(s[2] == 'checked' for s in sections(res))


def test_che_do_danh_gia_gom_ca_doan_pending():
    res = run('Cảnh báo học vụ khi nợ đọng vượt quá bao nhiêu tín chỉ?', require_checked=False)
    assert ('qd3266', 'Quy định > Chương IV > Điều 18', 'pending') in sections(res)


def test_khong_bao_gio_tra_phien_ban_cu_sha256_khac():
    res = run('Mỗi học kỳ đăng ký tối đa bao nhiêu tín chỉ?', require_checked=False)
    texts = [c.payload['content'] for c in res.fused]
    assert any('20 tín chỉ' in t for t in texts)
    assert not any('bản cũ' in t for t in texts)


def test_loc_theo_hoc_ky_loai_van_ban_chua_hieu_luc():
    # QĐ 4932 chỉ hiệu lực từ HK1 2026–2027: hỏi HK2 2025–2026 thì không được dùng nó
    res = run('Xếp loại rèn luyện học kỳ 2 năm 2025–2026 gồm những loại nào?', require_checked=False)
    assert res.routed.term_key == 20252
    assert all(c.payload['document_id'] != 'qd4932' for c in res.fused)


def test_neu_dich_danh_van_ban_chua_hieu_luc_thi_khong_co_evidence():
    res = run('Theo QĐ 4932, học kỳ 2 năm 2025–2026 xếp loại rèn luyện thế nào?')
    assert res.reason == 'no_valid_document' and res.selected == []
    out = retriever.retrieve('Theo QĐ 4932, học kỳ 2 năm 2025–2026 xếp loại rèn luyện thế nào?')
    assert out.evidence == [] and out.routed.term_key == 20252  # TV4 sẽ báo no_valid_document_for_term


def test_cau_hoi_ve_hieu_luc_khong_loc_cung_theo_ky():
    # CTU-075: HK1 2024–2025 đứng trước hiệu lực của QĐ 3266 nhưng vẫn phải truy được QĐ 3266
    res = run('HK1 năm học 2024–2025 có nằm trong kỳ áp dụng của QĐ 3266 không?', require_checked=False)
    assert res.routed.about_validity and res.routed.term_key == 20241
    assert res.selected and all(c.payload['document_id'] == 'qd3266' for c in res.selected)


def test_nhac_van_ban_thi_gioi_han_trong_van_ban_do():
    res = run('Theo QĐ 4932, kết quả rèn luyện xếp thành mấy loại?', require_checked=False)
    assert res.routed.document_ids == ('qd4932',)
    assert {c.payload['document_id'] for c in res.fused} == {'qd4932'}


def test_ghim_dieu_duoc_nhac_dich_danh():
    # câu hỏi gần như không có từ trùng với nội dung, nhưng nêu "Điều 14" nên đoạn đó vẫn phải có mặt
    res = run('Điều 14 quy định thế nào?')
    assert ('qd3266', 'Quy định > Chương III > Điều 14', 'checked') in sections(res)
    assert any(c.pinned for c in res.fused)


def test_ghim_phu_luc_va_khu_trung_ban_pending_cung_muc():
    res = run('Mức điểm ở V.b là bao nhiêu?', require_checked=False)
    vb = [c for c in res.fused if 'V.b' in c.payload['section']]
    assert len(vb) == 1 and vb[0].payload['review_status'] == 'checked'  # giữ bản đã duyệt


def test_hai_doan_cung_muc_khac_noi_dung_khong_bi_coi_la_trung():
    a = retriever.Candidate('1', {'document_id': 'd', 'section': 'Quy định > Điều 7', 'page_start': 5, 'page_end': 5,
                                  'content': 'khoản một nói về đăng ký học phần', 'review_status': 'pending'})
    b = retriever.Candidate('2', {'document_id': 'd', 'section': 'Quy định > Điều 7', 'page_start': 5, 'page_end': 6,
                                  'content': 'khoản năm nói về xử lý học vụ và thôi học', 'review_status': 'pending'})
    assert len(retriever.dedupe([a, b])) == 2


def test_evidence_dung_hop_dong_tv4():
    out = retriever.retrieve('Mỗi học kỳ đăng ký tối đa bao nhiêu tín chỉ?')
    assert out.evidence and out.n_candidates >= 1
    first = out.evidence[0]
    assert [e.source_id for e in out.evidence] == [f'S{i}' for i in range(1, len(out.evidence) + 1)]
    assert first.doc_number == 'qd3266/TEST' and first.page_start == 8 and first.text.startswith('Mỗi học kỳ')
    assert first.article == 'Điều 14' and first.source_url.endswith('qd3266.pdf')
    assert out.top_score == out.evidence[0].score > 0


def test_khong_co_ket_qua_thi_tra_rong(fake_stack):
    fake_stack.points = []
    out = retriever.retrieve('Câu hỏi bất kỳ')
    assert out.evidence == [] and out.top_score == 0.0 and out.n_candidates == 0


def test_cau_hoi_rong():
    res = run('   ')
    assert res.reason == 'empty_question'


def test_loi_qdrant_thanh_retrieval_error(fake_stack):
    def boom(**kwargs):
        raise ConnectionError('Qdrant down')

    fake_stack.query_points = boom
    with pytest.raises(retriever.RetrievalError):
        run('Mỗi học kỳ đăng ký tối đa bao nhiêu tín chỉ?')


def test_stats_dem_checked_va_pending():
    s = retriever.stats()
    assert s['points'] == 7 and s['checked'] == 4 and s['pending'] == 3
