'''T11: mô phỏng 429, timeout, model ID sai, hết quota. Không tốn quota.'''
import groq
import httpx
import pytest

from backend.services import groq_client as gc

REQ = httpx.Request('POST', 'https://api.groq.com/openai/v1/chat/completions')


def err(cls, status, headers=None):
    return cls('lỗi thử', response=httpx.Response(status, headers=headers or {}, request=REQ), body=None)


class FakeClient:
    def __init__(self, script):
        self.script, self.models = list(script), []
        self.chat = type('C', (), {})()
        self.chat.completions = self

    def create(self, **kw):
        self.models.append(kw['model'])
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def fake(monkeypatch):
    def make(script):
        fc = FakeClient(script)
        monkeypatch.setattr(gc, '_get', lambda: fc)
        monkeypatch.setattr(gc, 'limiter', gc.TpmLimiter(10 ** 9))
        return fc
    return make


def nosleep(s):
    return None


def test_429_ngan_thi_thu_lai_roi_thanh_cong(fake):
    fc = fake([err(groq.RateLimitError, 429, {'retry-after': '1'}), 'OK'])
    assert gc.chat([], 100, sleep=nosleep) == 'OK' and len(fc.models) == 2


def test_het_quota_ngay_thi_dung(fake):
    fake([err(groq.RateLimitError, 429, {'retry-after': '3600'})] * 2)
    with pytest.raises(gc.QuotaExhausted):
        gc.chat([], 100, sleep=nosleep)


def test_model_id_sai_chuyen_sang_model_du_phong(fake):
    fc = fake([err(groq.NotFoundError, 404), 'OK'])
    assert gc.chat([], 100, sleep=nosleep) == 'OK'
    assert fc.models[0] != fc.models[1]


def test_timeout_het_lan_thu_thi_bao_loi(fake):
    fake([groq.APITimeoutError(request=REQ)] * 4)
    with pytest.raises(gc.LLMUnavailable):
        gc.chat([], 100, sleep=nosleep)


def test_bo_gioi_han_tpm():
    lim = gc.TpmLimiter(1000)
    lim.record(800, now=0.0)
    assert lim.wait_time(400, now=10.0) == 50.0
    assert lim.wait_time(100, now=10.0) == 0.0

    lim.record(150, now=5.0)
    assert lim.wait_time(900, now=10.0) == 55.0
    assert lim.wait_time(900, now=60.0) == 5.0
    assert lim.wait_time(1100, now=65.0) == 0.0


def test_vuot_ngan_sach_qua_lau_thi_bao_het_quota(monkeypatch):
    lim = gc.TpmLimiter(1000)
    lim.record(1000, now=0.0)
    monkeypatch.setattr(gc.time, 'monotonic', lambda: 17.2)
    monkeypatch.setattr(gc, 'limiter', lim)
    with pytest.raises(gc.QuotaExhausted) as exc:
        gc.chat([], 500, sleep=nosleep)
    assert exc.value.retry_after == 43


def test_thieu_khoa_api_bao_loi_ro_rang(monkeypatch):
    monkeypatch.setattr(gc, '_client', None)
    monkeypatch.setattr(gc.config, 'GROQ_API_KEY', '')
    with pytest.raises(gc.LLMUnavailable):
        gc._get()
