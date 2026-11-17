from backend.services.retriever_mock import retrieve


def test_mock_tra_evidence_dung_schema():
    r = retrieve('Mỗi học kỳ đăng ký tối đa bao nhiêu tín chỉ?')
    assert r.evidence and r.evidence[0].source_id == 'S1' and r.evidence[0].page_start
    assert r.top_score == r.evidence[0].score


def test_mock_cau_hoi_ngoai_kho_khong_co_evidence():
    assert retrieve('Học phí ngành Y năm 2027?').evidence == []
