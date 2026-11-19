'''Đếm token (runbook §6.2). Chưa tải được tokenizer BGE-M3 thì ước lượng theo số từ.'''
from functools import lru_cache

from core import config


@lru_cache(maxsize=1)
def _tok():
    try:
        from transformers import AutoTokenizer

        return AutoTokenizer.from_pretrained(config.EMBED_MODEL)
    except Exception:  # noqa: BLE001 (chưa có transformers thì ước lượng)
        return None


def count_tokens(text: str) -> int:
    t = _tok()
    if t is None:
        return int(len(text.split()) * 1.6) + 1
    return len(t.encode(text, add_special_tokens=False))
