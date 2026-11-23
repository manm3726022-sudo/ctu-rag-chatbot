'''Cổng duy nhất TV4 dùng để lấy evidence. Chọn mock hoặc retriever thật của TV3 theo RETRIEVER trong .env.
TV4 không truy vấn Qdrant trực tiếp (Pipeline mục 6.1).'''
from core import config

if config.RETRIEVER == 'real':
    # retriever.py do TV3 cung cấp (runbook §9.2)
    from backend.services.retriever import RetrievalError, retrieve  # noqa: F401
else:
    from backend.services.retriever_mock import retrieve  # noqa: F401

    class RetrievalError(Exception):
        '''Chỉ để backend/main.py bắt lỗi giống nhau ở cả hai chế độ (mock không bao giờ ném).'''


MODE = config.RETRIEVER


def warmup():
    '''Nạp model local trước để câu hỏi đầu tiên không chậm (chỉ khi dùng retriever thật).'''
    if MODE != 'real':
        return
    from core.embedding import encode

    encode(['khởi động'])
    if config.RERANK_ENABLED:
        from backend.services.reranker import _reranker

        _reranker()


def health() -> dict:
    if MODE != 'real':
        return {'retriever': 'mock'}
    try:
        from backend.services.retriever import stats

        return {
            'retriever': 'real',
            'qdrant': 'ok',
            'rerank_enabled': config.RERANK_ENABLED,
            **stats(),
        }
    except Exception as e:  # noqa: BLE001 (health check không được làm sập API)
        return {'retriever': 'real', 'qdrant': 'down', 'error': type(e).__name__}
