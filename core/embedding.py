'''Mã hóa dense và sparse bằng cùng model cho truy vấn và ingestion.

Quy ước PHẢI giống hệt ingestion/index.py (đây là nguồn duy nhất cho phần sparse):
  - cùng model và use_fp16 (config.EMBED_MODEL, config.USE_FP16);
  - sparse = (token_id kiểu int sắp tăng dần, trọng số float), không dùng IDF.
FlagEmbedding được import muộn (lazy) nên test, /health và các script nhẹ không phải tải model.'''
from dataclasses import dataclass
from functools import lru_cache

from core import config


@dataclass(frozen=True)
class Encoded:
    dense: list
    indices: list
    values: list


def sparse_from_lexical(lexical) -> tuple[list, list]:
    '''lexical_weights của BGE-M3 ({"token_id": trọng số}) -> (indices, values) đã sắp xếp.'''
    pairs = sorted((int(token), float(weight)) for token, weight in lexical.items())
    return [i for i, _ in pairs], [w for _, w in pairs]


@lru_cache(maxsize=1)
def get_model():
    if config.EMBED_BACKEND == 'mgte':
        from core.mgte import MgteEmbedder

        return MgteEmbedder(config.EMBED_MODEL, use_fp16=config.USE_FP16)
    if config.EMBED_BACKEND != 'bge-m3':
        raise ValueError(f'Unknown EMBED_BACKEND: {config.EMBED_BACKEND}')

    from FlagEmbedding import BGEM3FlagModel

    return BGEM3FlagModel(config.EMBED_MODEL, use_fp16=config.USE_FP16)


def encode(texts, model=None, max_length=None) -> list:
    '''Mã hóa danh sách văn bản -> list[Encoded].'''
    texts = list(texts)
    if not texts:
        return []
    model = model or get_model()
    out = model.encode(
        texts,
        batch_size=min(len(texts), 16),
        max_length=max_length or config.EMBED_QUERY_MAX_LENGTH,
        return_dense=True,
        return_sparse=True,
        return_colbert_vecs=False,
    )
    result = []
    for dense, lexical in zip(out['dense_vecs'], out['lexical_weights'], strict=True):
        indices, values = sparse_from_lexical(lexical)
        result.append(Encoded([float(x) for x in dense], indices, values))
    return result
