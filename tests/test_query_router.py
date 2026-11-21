import pytest

from backend.services.query_router import route
from tests.fakes import catalog

CAT = catalog()


def r(q):
    return route(q, CAT)


def test_chuan_hoa_khoang_trang_va_unicode():
    assert r('  Điều   kiện\u00a0tốt  nghiệp  ').question == 'Điều kiện tốt nghiệp'


@pytest.mark.parametrize('q', [
    'Theo QĐ 3266 thì sao?', 'QĐ3266 quy định gì', 'Quyết định số 3266 nói gì', '3266/QĐ-ĐHCT quy định gì',
    'QĐ học vụ 3266 có hiệu lực không',
])
def test_nhan_dien_van_ban_theo_nhieu_cach_viet(q):
    assert r(q).document_ids == ('qd3266',)


def test_thong_tu_va_nhieu_van_ban():
    assert r('Thông tư 40/2026/TT-BGDĐT').document_ids == ('tt40',)
    assert r('TT40 và QĐ 4932').document_ids == ('tt40', 'qd4932')


def test_so_hieu_khong_co_trong_kho_bi_bo_qua():
    assert r('Theo QĐ 6175 và QĐ 3873 thì sao?').document_ids == ()


def test_nam_hoc_khong_bi_nham_thanh_so_hieu():
    assert r('Năm 2025 và 2026 có thay đổi gì?').document_ids == ()


def test_dieu_va_phu_luc():
    x = r('Điều 18 khoản 2 điểm a, và Điều 25')
    assert x.articles == ('Điều 18', 'Điều 25') and x.article == 'Điều 18'
    assert r('Điều 180 là gì').articles == ('Điều 180',)
    assert r('Mức ở V.b là bao nhiêu và III.c?').appendix_items == ('V.b', 'III.c')
    assert r('Theo Phụ lục V quy định gì').appendix_items == ('V',)


@pytest.mark.parametrize('q, key', [
    ('HK1 năm học 2024–2025', 20241),
    ('học kỳ 2 năm 2025–2026', 20252),
    ('từ HK I năm học 2026-2027', 20261),
    ('học kỳ hè năm học 2025/2026', 20253),
    ('học kỳ 1 năm học 2026', 20261),
])
def test_hoc_ky(q, key):
    assert r(q).term_key == key


@pytest.mark.parametrize('q', [
    'HK1 2025',  # thiếu năm học đầy đủ
    'học kỳ 1 và học kỳ 2 năm 2025–2026',  # hai học kỳ: mơ hồ
    'năm học 2025–2027 học kỳ 1',  # khoảng năm không liên tiếp
    'học kỳ đầu hay học kỳ sau',
])
def test_khong_doan_khi_mo_ho(q):
    assert r(q).term_key is None


def test_cau_hoi_ve_hieu_luc():
    assert r('QĐ 3266 có hiệu lực từ kỳ nào?').about_validity
    assert r('HK1 năm học 2024–2025 có nằm trong kỳ áp dụng của QĐ 3266 không?').about_validity
    assert not r('Học kỳ 2 năm 2025–2026 rèn luyện cho mấy điểm?').about_validity


def test_khoa_tuyen_sinh():
    assert r('Sinh viên khóa 47 bị cảnh báo khi nào?').cohort == 47
    assert r('Sinh viên bị cảnh báo khi nào?').cohort is None


def test_thong_nhat_ki_thanh_ky():
    assert r('Mỗi kì được đăng ký tối đa bao nhiêu tín chỉ?').question == 'Mỗi kỳ được đăng ký tối đa bao nhiêu tín chỉ?'
    assert r('Kì này').question == 'Kỳ này'
    assert r('học kì 2 năm học 2025–2026').term_key == 20252
    assert r('thi kỳ').question == 'thi kỳ'  # không đụng chữ khác
