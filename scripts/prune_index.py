'''Dọn điểm "mồ côi" khỏi Qdrant: điểm thuộc văn bản đã archived trong manifest, hoặc có sha256 không còn
là tệp nguồn chính (phiên bản cũ). Retriever đã bỏ qua chúng khi truy vấn; script này chỉ giúp kho gọn.

  python -m scripts.prune_index            # chỉ liệt kê (dry-run)
  python -m scripts.prune_index --apply    # xóa thật

Thay thế cho "--archive" trong Pipeline §5.1: để archive một văn bản, đặt "status": "archived" trong
docs/corpus/documents.json rồi chạy lệnh này. File gốc và registry vẫn được giữ.'''
import argparse
from collections import Counter

from core import config, corpus_catalog


def active_pairs(catalog) -> set:
    return {(d.document_id, sha) for d in catalog if d.status != 'archived' for sha in d.active_sha256}


def find_stale(points, active: set) -> list:
    '''points: các điểm có .id và .payload (document_id, sha256). Trả về [(id, document_id, sha256)] cần xóa.'''
    stale = []
    for p in points:
        payload = p.payload or {}
        key = (payload.get('document_id'), payload.get('sha256'))
        if key not in active:
            stale.append((p.id, key[0], key[1]))
    return stale


def scan(client, collection: str) -> list:
    points, offset = [], None
    while True:
        batch, offset = client.scroll(
            collection_name=collection,
            limit=256,
            offset=offset,
            with_payload=['document_id', 'sha256'],
            with_vectors=False,
        )
        points.extend(batch)
        if offset is None:
            return points


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--apply', action='store_true', help='xóa thật (mặc định chỉ liệt kê)')
    args = parser.parse_args()

    from qdrant_client import models

    from backend.services import retriever

    client = retriever.get_client()
    points = scan(client, config.COLLECTION)
    stale = find_stale(points, active_pairs(corpus_catalog.load_catalog()))
    print(f'Tổng {len(points)} điểm; mồ côi: {len(stale)}')
    for (doc, sha), n in sorted(Counter((d, (s or '')[:8]) for _, d, s in stale).items()):
        print(f'  {doc} sha {sha}…: {n} điểm')
    if not stale:
        return 0
    if not args.apply:
        print('Dry-run: thêm --apply để xóa.')
        return 0
    ids = [i for i, _, _ in stale]
    for offset in range(0, len(ids), 256):
        client.delete(
            collection_name=config.COLLECTION,
            points_selector=models.PointIdsList(points=ids[offset : offset + 256]),
            wait=True,
        )
    print(f'Đã xóa {len(ids)} điểm.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
