'''Danh mục văn bản đọc thẳng từ manifest docs/corpus/documents.json (JSON thuần, không cần Pydantic).

Đây là NGUỒN SỰ THẬT cho câu hỏi "văn bản nào đang dùng được, ở học kỳ nào, bản tệp nào":
  - payload Qdrant luôn ghi status="indexed" và ingest không xóa điểm cũ, nên không dùng làm căn cứ;
  - văn bản có status="archived" trong manifest bị loại khỏi truy xuất;
  - chỉ các điểm có sha256 trùng tệp nguồn chính (ingestion_source, hoặc files không phải "summary")
    mới được tính là phiên bản đang dùng (cùng quy tắc chọn nguồn với scripts/ingest.py).
Học kỳ mã hóa thành số nguyên: "2024-HK2" -> 20242 (so sánh được bằng toán tử <, <=).'''
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from core import config

TERM_RE = re.compile(r'^(\d{4})-HK([123])$')
NUMBER_RE = re.compile(r'^(\d+)/(?:\d{4}/)?([^\W\d_]+)')
KIND = {'qđ': 'qd', 'qd': 'qd', 'tt': 'tt', 'hd': 'hd', 'hđ': 'hd'}


def term_key(term):
    '''"2024-HK2" -> 20242; None -> None.'''
    if not term:
        return None
    m = TERM_RE.match(term)
    if not m:
        raise ValueError(f'Học kỳ phải có dạng YYYY-HKn: {term!r}')
    return int(m[1]) * 10 + int(m[2])


@dataclass(frozen=True)
class CatalogDoc:
    document_id: str
    document_number: str
    title: str
    status: str
    kind: str  # 'qd' | 'tt' | 'hd' | '' (suy ra từ số hiệu)
    number: str  # '3266', '4932', '40', '2427', '5976'
    from_key: int = None
    until_key: int = None  # loại trừ (exclusive)
    effective_date: str = None
    active_sha256: tuple = ()


def _parse(row) -> CatalogDoc:
    m = NUMBER_RE.match(row['document_number'])
    primary = [row['ingestion_source']] if row.get('ingestion_source') else row['files']
    shas = tuple(f['sha256'] for f in primary if f['source_kind'] != 'summary')
    return CatalogDoc(
        document_id=row['document_id'],
        document_number=row['document_number'],
        title=row['title'],
        status=row.get('status', 'registered'),
        kind=KIND.get(m[2].lower(), '') if m else '',
        number=m[1] if m else '',
        from_key=term_key(row.get('effective_from_term')),
        until_key=term_key(row.get('effective_until_term_exclusive')),
        effective_date=row.get('effective_date'),
        active_sha256=shas,
    )


@lru_cache(maxsize=8)
def _load(
    path: str,
    mtime_ns: int,
    overlay_path: str | None = None,
    overlay_mtime_ns: int | None = None,
) -> tuple:
    rows = json.loads(Path(path).read_text(encoding='utf-8'))
    if overlay_path is not None:
        rows.extend(json.loads(Path(overlay_path).read_text(encoding='utf-8')))
    return tuple(_parse(r) for r in rows)


def load_catalog(path=None) -> tuple:
    '''Đọc manifest và overlay admin; tự đọc lại khi một trong hai tệp được sửa.'''
    p = Path(path or config.MANIFEST_PATH)
    overlay = config.ADMIN_MANIFEST_PATH if path is None else None
    if overlay is not None and overlay.exists():
        return _load(
            str(p),
            p.stat().st_mtime_ns,
            str(overlay),
            overlay.stat().st_mtime_ns,
        )
    return _load(str(p), p.stat().st_mtime_ns)


def valid_documents(term=None, catalog=None) -> list:
    '''Văn bản còn dùng được; nếu có học kỳ (số nguyên) thì thêm điều kiện hiệu lực theo kỳ.

    Văn bản chỉ có ngày hiệu lực (TT 40, QĐ 5976) hoặc không có mốc nào (HD 2427) được GIỮ LẠI vì
    chưa có quy ước đổi học kỳ sang ngày; không đoán (Pipeline B3: không tự suy diễn).'''
    docs = []
    for d in (load_catalog() if catalog is None else catalog):
        if d.status == 'archived':
            continue
        if term is not None:
            if d.from_key is not None and term < d.from_key:
                continue
            if d.until_key is not None and term >= d.until_key:
                continue
        docs.append(d)
    return docs
