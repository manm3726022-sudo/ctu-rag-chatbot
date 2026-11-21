import pytest

from backend.services.verify_rules import needs_verification


@pytest.mark.parametrize('q', [
    'Rèn luyện loại kém thì sao?',
    'Điểm rèn luyện thấp bị xếp Yếu có sao không?',
    'Cứ hai kỳ bị Yếu là hệ thống sẽ tự động ra quyết định đình chỉ em phải không?',  # CTU-085, thiếu "rèn luyện"
    'Em xếp loại kém ở học kỳ này thì bị gì?',
])
def test_can_xac_minh(q):
    assert needs_verification(q)


def test_khong_can_xac_minh():
    assert not needs_verification('Mỗi học kỳ đăng ký tối đa bao nhiêu tín chỉ?')
    assert not needs_verification('Có mấy mức xếp loại học lực?')


def test_chu_yeu_khong_bi_bat_nham():
    assert not needs_verification('Quy định này chủ yếu áp dụng cho ai?')
