'''Quy trình duyệt đoạn pending (TV1 đối chiếu nội dung, TV2 hỗ trợ). Có hai lệnh:

  1) Xuất danh sách cần duyệt (cần đã chạy: python -m scripts.ingest --prepare-only):
       python -m scripts.review_chunks export
       python -m scripts.review_chunks export --gold                  # chỉ đoạn mà câu hỏi chuẩn trỏ tới (duyệt trước)
       python -m scripts.review_chunks export --document qd3266       # chỉ một văn bản (lặp được)
     -> data/review/pending_review.csv (mở bằng Excel). Người duyệt đối chiếu cột "content" với PDF gốc
        (đúng trang page_start–page_end), điền cột "decision" = ok nếu đúng; sửa/ghi chú nếu sai.

  2) Ghi nhận các đoạn đã duyệt:
       python -m scripts.review_chunks apply --file data/review/pending_review.csv --reviewer "Tên người duyệt"
     -> thêm vào data/review/approved_chunks.csv (nhớ commit file này) và đổi review_status=checked trong
        Qdrant (không cần nạp lại). Lần ingest sau đọc sổ này nên không bị quay về pending.

Đoạn sai chữ (OCR) thì KHÔNG đánh ok: sửa parser/chunking hoặc bổ sung bảng quy tắc đã duyệt như rubric.'''
import argparse
import csv
import json
import re
from datetime import date
from pathlib import Path

from core import config
from eval.metrics import hits
from ingestion.approvals import append_approved, read_approved

PROCESSED = config.ROOT / 'data/processed'
PENDING_CSV = config.ROOT / 'data/review/pending_review.csv'
OK_VALUES = {'ok', 'đạt', 'dat', 'checked'}
COLUMNS = ['chunk_id', 'document_id', 'section', 'page_start', 'page_end', 'content', 'decision', 'note']


def load_gold_sources(path: Path) -> list:
    '''Các nguồn (văn bản + khoảng trang) của những câu hỏi chuẩn có đáp án.'''
    sources = []
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            if line.strip():
                case = json.loads(line)
                if case['action'] == 'answer':
                    sources.extend(case['sources'])
    return sources


def _norm_section(section: str) -> str:
    return re.sub(r'\s*>\s*', ' ', section or '').strip().lower()


def _covered(row: dict, checked: list) -> bool:
    '''Đoạn pending ở PHỤ LỤC đã có bản checked cùng mục, chồng trang (phụ lục QĐ 4932 đã có hàng rubric đã
    duyệt): không cần duyệt lại vì retriever luôn ưu tiên bản checked. Chỉ áp dụng cho phụ lục: với thân văn
    bản, nhiều đoạn có thể cùng một Điều nên một đoạn đã duyệt KHÔNG được che các đoạn còn lại.'''
    section = _norm_section(row['section'])
    if not section.startswith('phụ lục'):
        return False
    return any(
        c['document_id'] == row['document_id']
        and _norm_section(c['section']) == section
        and c['page_start'] <= row['page_end']
        and row['page_start'] <= c['page_end']
        for c in checked
    )


def pending_rows(processed: Path, approved: set, documents=None, gold_sources=None, skip_covered=True) -> list:
    '''Các đoạn pending chưa có trong sổ duyệt. documents: chỉ các văn bản này; gold_sources: chỉ đoạn
    trùng (văn bản + chồng trang) với ít nhất một nguồn của câu hỏi chuẩn; skip_covered: bỏ đoạn đã có bản
    checked cùng mục.'''
    rows, checked = [], []
    for path in sorted(processed.glob('*.chunks.jsonl')):
        with path.open(encoding='utf-8') as stream:
            for line in stream:
                if not line.strip():
                    continue
                c = json.loads(line)
                if c['review_status'] == 'checked' or c['chunk_id'] in approved:
                    if c['chunk_id'] not in approved:  # chỉ bản checked "gốc" (rubric), không tính đoạn người đã duyệt
                        checked.append(c)
                    continue
                if c['review_status'] != 'pending':
                    continue
                if documents and c['document_id'] not in documents:
                    continue
                if gold_sources is not None and not any(hits(c, s) for s in gold_sources):
                    continue
                rows.append({k: c[k] for k in ('chunk_id', 'document_id', 'section', 'page_start', 'page_end', 'content')})
    if skip_covered:
        rows = [r for r in rows if not _covered(r, checked)]
    rows.sort(key=lambda r: (r['document_id'], r['page_start'], r['section']))
    return rows


def approved_rows(csv_path: Path) -> list:
    with csv_path.open(encoding='utf-8-sig', newline='') as stream:
        return [r for r in csv.DictReader(stream) if (r.get('decision') or '').strip().lower() in OK_VALUES]


def cmd_export(args) -> int:
    gold = load_gold_sources(args.gold_file) if args.gold else None
    approved = read_approved(config.APPROVED_PATH)
    rows = pending_rows(args.processed, approved, set(args.document), gold)
    skipped = len(pending_rows(args.processed, approved, set(args.document), gold, skip_covered=False)) - len(rows)
    if not rows:
        print('Không có đoạn pending nào khớp điều kiện (đã chạy --prepare-only chưa?).')
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f'Đã xuất {len(rows)} đoạn cần duyệt vào {args.out}')
    if skipped:
        print(f'  (bỏ qua {skipped} đoạn đã có bản checked cùng mục, ví dụ phụ lục QĐ 4932 đã có hàng rubric)')
    for doc in sorted({r['document_id'] for r in rows}):
        print(f"  {doc}: {sum(1 for r in rows if r['document_id'] == doc)} đoạn")
    return 0


def cmd_apply(args) -> int:
    rows = approved_rows(args.file)
    if not rows:
        print('Không có dòng nào có decision = ok.')
        return 1
    added = append_approved(config.APPROVED_PATH, rows, args.reviewer, date.today().isoformat())
    print(f'Sổ duyệt: thêm {added} đoạn (tổng đã duyệt: {len(read_approved(config.APPROVED_PATH))}).')
    if args.no_qdrant:
        return 0
    from backend.services import retriever

    client = retriever.get_client()
    ids = [r['chunk_id'].strip() for r in rows]
    for offset in range(0, len(ids), 128):
        client.set_payload(
            collection_name=config.COLLECTION,
            payload={'review_status': 'checked'},
            points=ids[offset : offset + 128],
            wait=True,
        )
    print(f'Đã đổi review_status=checked cho {len(ids)} điểm trong Qdrant.')
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    export = sub.add_parser('export', help='xuất các đoạn pending ra CSV để duyệt')
    export.add_argument('--processed', type=Path, default=PROCESSED)
    export.add_argument('--out', type=Path, default=PENDING_CSV)
    export.add_argument('--document', action='append', default=[], metavar='ID', help='chỉ xuất đoạn của văn bản này (lặp được)')
    export.add_argument('--gold', action='store_true', help='chỉ xuất đoạn mà câu hỏi chuẩn có đáp án trỏ tới')
    export.add_argument('--gold-file', type=Path, default=config.ROOT / 'eval/gold_corpus.jsonl')
    export.set_defaults(func=cmd_export)
    apply = sub.add_parser('apply', help='ghi nhận các đoạn đã duyệt')
    apply.add_argument('--file', type=Path, default=PENDING_CSV)
    apply.add_argument('--reviewer', required=True)
    apply.add_argument('--no-qdrant', action='store_true', help='chỉ ghi sổ, không cập nhật Qdrant')
    apply.set_defaults(func=cmd_apply)
    args = parser.parse_args()
    return args.func(args)


if __name__ == '__main__':
    raise SystemExit(main())
