'''Kiểm tra tương thích với thư viện qdrant-client THẬT (chế độ local trong bộ nhớ, không cần Docker):
cú pháp prefetch + bộ lọc + RRF, scroll và count. Nếu test này lỗi trên máy bạn thì lỗi nằm ở phiên bản
qdrant-client chứ không phải logic retriever (các test với bản giả đã kiểm logic).'''
import pytest

pytest.importorskip('qdrant_client')

from qdrant_client import QdrantClient, models  # noqa: E402

from backend.services import reranker, retriever  # noqa: E402
from core import config, embedding  # noqa: E402
from tests import fakes  # noqa: E402


@pytest.fixture
def local(monkeypatch):
    monkeypatch.setattr(embedding, 'get_model', lambda: fakes.FakeModel())
    monkeypatch.setattr(reranker, '_reranker', lambda: fakes.FakeReranker())
    monkeypatch.setattr(reranker, 'count_tokens', lambda text: len(text.split()))
    client = QdrantClient(':memory:')
    client.create_collection(
        collection_name=config.COLLECTION,
        vectors_config={'dense': models.VectorParams(size=fakes.DIM, distance=models.Distance.COSINE)},
        sparse_vectors_config={'sparse': models.SparseVectorParams()},
    )
    client.upsert(
        collection_name=config.COLLECTION,
        points=[
            models.PointStruct(
                id=i,
                payload=p.payload,
                vector={'dense': p.dense, 'sparse': models.SparseVector(indices=p.sparse['indices'], values=p.sparse['values'])},
            )
            for i, p in enumerate(fakes.build_points(), start=1)
        ],
        wait=True,
    )
    retriever.set_client(client)
    yield client
    retriever.set_client(None)


def test_hybrid_rrf_loc_va_chon_dung_nguon(local):
    res = retriever.search('Mỗi học kỳ đăng ký tối đa bao nhiêu tín chỉ?', None, catalog=fakes.catalog())
    texts = [c.payload['content'] for c in res.selected]
    assert any('20 tín chỉ' in t for t in texts) and not any('bản cũ' in t for t in texts)
    assert all(c.payload['review_status'] == 'checked' for c in res.selected)  # mặc định chỉ dùng đoạn đã duyệt


def test_ghim_dieu_va_stats_tren_qdrant_that(local):
    res = retriever.search('Điều 14 quy định thế nào?', {'require_checked': False}, catalog=fakes.catalog())
    assert any(c.pinned for c in res.fused)
    s = retriever.stats()
    assert s['points'] == 7 and s['checked'] == 4
