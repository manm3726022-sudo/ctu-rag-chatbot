"""Text preparation shared by PhoRanker and ingestion."""

from functools import lru_cache
from threading import Lock

PAIR_LIMIT = 256
PASSAGE_LIMIT = 200
_segment_lock = Lock()


@lru_cache(maxsize=1024)
def segment(text):
    from pyvi import ViTokenizer

    # PyVi shares a stateful CRF tagger between requests.
    with _segment_lock:
        return ViTokenizer.tokenize(text)


@lru_cache(maxsize=1)
def tokenizer(model_name):
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained(model_name)


def format_passage(number, section, content):
    heading = ' · '.join(value for value in (number, section) if value)
    return f'{heading}\n{content}'.strip()
