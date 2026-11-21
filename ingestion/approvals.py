'''Sổ duyệt đoạn (data/review/approved_chunks.csv): bằng chứng bền vững rằng người phụ trách đã đối chiếu
một đoạn với văn bản gốc. Không có sổ này thì mỗi lần ingest lại, mọi đoạn tự động quay về "pending".

chunk_id là UUID5 sinh từ (văn bản, sha256, mục, trang, NỘI DUNG): nếu OCR/parser đổi chữ thì ID đổi
và đoạn đó tự động cần duyệt lại — không bao giờ duyệt nhầm sang nội dung khác.'''
import csv
from pathlib import Path

FIELDS = ['chunk_id', 'document_id', 'section', 'page_start', 'page_end', 'reviewer', 'reviewed_on']


def read_approved(path) -> set:
    p = Path(path)
    if not p.exists():
        return set()
    with p.open(encoding='utf-8-sig', newline='') as stream:
        return {row['chunk_id'].strip() for row in csv.DictReader(stream) if (row.get('chunk_id') or '').strip()}


def append_approved(path, rows, reviewer: str, reviewed_on: str) -> int:
    '''Ghi thêm các dòng chưa có trong sổ. Trả về số dòng mới.'''
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    known = read_approved(p)
    new = [r for r in rows if r['chunk_id'].strip() not in known]
    exists = p.exists() and p.stat().st_size > 0
    with p.open('a', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        if not exists:
            writer.writeheader()
        for r in new:
            writer.writerow({
                'chunk_id': r['chunk_id'].strip(),
                'document_id': r.get('document_id', ''),
                'section': r.get('section', ''),
                'page_start': r.get('page_start', ''),
                'page_end': r.get('page_end', ''),
                'reviewer': reviewer,
                'reviewed_on': reviewed_on,
            })
    return len(new)


def apply_approved(chunks, approved) -> list:
    '''Đổi review_status của các đoạn có trong sổ sang "checked" (đoạn đã checked giữ nguyên).'''
    return [
        c.model_copy(update={'review_status': 'checked'})
        if str(c.chunk_id) in approved and c.review_status != 'checked'
        else c
        for c in chunks
    ]
