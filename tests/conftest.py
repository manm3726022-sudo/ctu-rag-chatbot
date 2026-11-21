import json
import os
from pathlib import Path

import pytest

# Test không bao giờ gọi Groq thật và luôn dùng retriever giả (test retriever import trực tiếp
# backend.services.retriever nên không bị ảnh hưởng).
os.environ['RETRIEVER'] = 'mock'
os.environ['GROQ_API_KEY'] = ''

from core import config as app_config  # noqa: E402 (phải import SAU khi đặt biến môi trường ở trên)

ROOT = Path(__file__).resolve().parents[1]
PINNED_CONFIG = {
    'RETRIEVE_REQUIRE_CHECKED': True,
    'RETRIEVE_PREFETCH': 20,
    'RETRIEVE_LIMIT': 20,
    'RETRIEVE_MAX_PINNED': 8,
    'EVIDENCE_MAX_CHUNKS': 6,
    'EVIDENCE_MAX_TOKENS': 3000,
    'EVIDENCE_DIVERSITY_RATIO': 0.5,
}
# Hai file test của TV1 đối chiếu hash với TỆP THẬT trong gói bàn giao (ZIP), không có trên GitHub.
NEED_HANDOVER = {'test_corpus_metadata.py', 'test_tv1_integration.py'}


def missing_handover_files() -> list:
    '''Các tệp trong manifest chưa có trên máy (cùng quy tắc thư mục với scripts/register_corpus.verify).'''
    rows = json.loads((ROOT / 'docs/corpus/documents.json').read_text(encoding='utf-8'))
    missing = []
    for row in rows:
        for f in row['files']:
            folder = 'data/ocr/reference_only' if f['source_kind'] == 'summary' else 'data/raw'
            if not (ROOT / folder / f['file_name']).exists():
                missing.append(f'{folder}/{f["file_name"]}')
    return missing


def pytest_collection_modifyitems(config, items):
    missing = missing_handover_files()
    if not missing:
        return
    skip = pytest.mark.skip(reason=f'Thiếu {len(missing)} tệp của gói bàn giao TV1 (ZIP); xem docs/tv3-retrieval.md')
    for item in items:
        if item.path.name in NEED_HANDOVER:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def pin_retrieval_config(monkeypatch):
    '''Test truy xuất luôn chạy với cấu hình mặc định, dù .env của người chạy đặt giá trị khác.'''
    for key, value in PINNED_CONFIG.items():
        monkeypatch.setattr(app_config, key, value)
