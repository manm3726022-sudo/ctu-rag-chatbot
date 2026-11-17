'''Cổng duy nhất TV4 dùng để lấy evidence. Chọn mock hoặc retriever thật của TV3 theo RETRIEVER trong .env.
TV4 không truy vấn Qdrant trực tiếp (Pipeline mục 6.1).'''
from core import config

if config.RETRIEVER == 'real':
    # retriever.py do TV3 cung cấp (runbook §9.2)
    from backend.services.retriever import retrieve
else:
    from backend.services.retriever_mock import retrieve  # noqa: F401

MODE = config.RETRIEVER


def warmup():
    '''Nạp model local trước để câu hỏi đầu tiên không chậm (chỉ khi dùng retriever thật).'''
    if MODE != 'real':
        return
    from core.embedding import encode

    from backend.services.reranker import _reranker

    encode(['khởi động'])
    _reranker()


def health() -> dict:
    if MODE != 'real':
        return {'retriever': 'mock'}
    try:
        from backend.services.retriever import client

        n = client.count(config.COLLECTION, exact=False).count
        return {'retriever': 'real', 'qdrant': 'ok', 'points': n}
    except Exception as e:  # noqa: BLE001 (health check không được làm sập API)
        return {'retriever': 'real', 'qdrant': 'down', 'error': type(e).__name__}
