import csv
import json
from types import SimpleNamespace

from ingestion.approvals import FIELDS, append_approved, apply_approved, read_approved
from scripts import prune_index, review_chunks
from tests.fakes import SHA_A, SHA_A_OLD, catalog


class Chunk:
    def __init__(self, chunk_id, status):
        self.chunk_id, self.review_status = chunk_id, status

    def model_copy(self, update):
        return Chunk(self.chunk_id, update.get('review_status', self.review_status))


def test_so_duyet_rong_neu_chua_co_file(tmp_path):
    assert read_approved(tmp_path / 'khong_co.csv') == set()


def test_ghi_them_khong_trung_va_doc_lai(tmp_path):
    path = tmp_path / 'sub' / 'approved.csv'
    rows = [{'chunk_id': 'a', 'document_id': 'd', 'section': 's', 'page_start': 1, 'page_end': 1}, {'chunk_id': 'b'}]
    assert append_approved(path, rows, 'Đăng', '2026-11-20') == 2
    assert append_approved(path, rows, 'Đăng', '2026-11-21') == 0  # đã có thì không ghi lại
    assert read_approved(path) == {'a', 'b'}
    with path.open(encoding='utf-8') as f:
        assert next(csv.reader(f)) == FIELDS


def test_apply_approved_chi_doi_doan_co_trong_so():
    out = apply_approved([Chunk('a', 'pending'), Chunk('b', 'pending'), Chunk('c', 'checked')], {'a', 'c'})
    assert [(c.chunk_id, c.review_status) for c in out] == [('a', 'checked'), ('b', 'pending'), ('c', 'checked')]


def test_so_duyet_cua_repo_dung_dinh_dang():
    '''Chỉ kiểm định dạng, KHÔNG kiểm nội dung: số đoạn đã duyệt thay đổi theo thời gian.'''
    from core.config import APPROVED_PATH

    with APPROVED_PATH.open(encoding='utf-8-sig', newline='') as f:
        assert next(csv.reader(f)) == FIELDS
    assert all(len(chunk_id) == 36 for chunk_id in read_approved(APPROVED_PATH))  # UUID


def _write_chunks(folder, rows):
    (folder / 'qd3266-x.chunks.jsonl').write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in rows), encoding='utf-8')


def test_xuat_danh_sach_can_duyet(tmp_path):
    base = {'document_id': 'qd3266', 'section': 'Quy định > Điều 14', 'page_end': 8}
    _write_chunks(tmp_path, [
        {**base, 'chunk_id': 'a', 'page_start': 8, 'content': 'nội dung a', 'review_status': 'pending'},
        {**base, 'chunk_id': 'b', 'page_start': 2, 'content': 'nội dung b', 'review_status': 'pending'},
        {**base, 'chunk_id': 'c', 'page_start': 3, 'content': 'đã duyệt', 'review_status': 'checked'},
        {**base, 'chunk_id': 'd', 'page_start': 4, 'content': 'có trong sổ', 'review_status': 'pending'},
    ])
    rows = review_chunks.pending_rows(tmp_path, {'d'})
    assert [r['chunk_id'] for r in rows] == ['b', 'a']  # sắp theo trang, bỏ checked và đã có trong sổ


def test_chi_nhan_dong_decision_ok(tmp_path):
    path = tmp_path / 'p.csv'
    with path.open('w', encoding='utf-8-sig', newline='') as f:
        w = csv.DictWriter(f, fieldnames=review_chunks.COLUMNS)
        w.writeheader()
        w.writerow({'chunk_id': 'a', 'decision': 'OK'})
        w.writerow({'chunk_id': 'b', 'decision': ''})
        w.writerow({'chunk_id': 'c', 'decision': 'sai OCR'})
        w.writerow({'chunk_id': 'd', 'decision': ' đạt '})
    assert [r['chunk_id'] for r in review_chunks.approved_rows(path)] == ['a', 'd']


def test_tim_diem_mo_coi():
    pts = [
        SimpleNamespace(id=1, payload={'document_id': 'qd3266', 'sha256': SHA_A}),
        SimpleNamespace(id=2, payload={'document_id': 'qd3266', 'sha256': SHA_A_OLD}),
        SimpleNamespace(id=3, payload={'document_id': 'da_xoa', 'sha256': 'x'}),
        SimpleNamespace(id=4, payload={}),
    ]
    stale = prune_index.find_stale(pts, prune_index.active_pairs(catalog()))
    assert [s[0] for s in stale] == [2, 3, 4]


def test_van_ban_archived_khong_con_active():
    docs = [d for d in catalog()]
    from dataclasses import replace

    docs[0] = replace(docs[0], status='archived')
    assert ('qd3266', SHA_A) not in prune_index.active_pairs(docs)


def test_xuat_loc_theo_van_ban_va_theo_gold(tmp_path):
    rows = [
        {'document_id': 'qd3266', 'section': 'Quy định > Điều 14', 'chunk_id': 'a', 'page_start': 8, 'page_end': 8,
         'content': 'x', 'review_status': 'pending'},
        {'document_id': 'qd3266', 'section': 'Quy định > Điều 9', 'chunk_id': 'b', 'page_start': 5, 'page_end': 5,
         'content': 'y', 'review_status': 'pending'},
        {'document_id': 'tt40', 'section': 'Thông tư > Điều 17', 'chunk_id': 'c', 'page_start': 7, 'page_end': 8,
         'content': 'z', 'review_status': 'pending'},
    ]
    (tmp_path / 'all.chunks.jsonl').write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in rows), encoding='utf-8')
    assert [r['chunk_id'] for r in review_chunks.pending_rows(tmp_path, set(), {'tt40'})] == ['c']
    gold = [{'document_id': 'qd3266', 'page_start': 8, 'page_end': 8}, {'document_id': 'tt40', 'page_start': 8, 'page_end': 9}]
    assert [r['chunk_id'] for r in review_chunks.pending_rows(tmp_path, set(), None, gold)] == ['a', 'c']
    assert [r['chunk_id'] for r in review_chunks.pending_rows(tmp_path, {'a'}, {'qd3266'}, gold)] == []


def test_doc_nguon_gold_chi_lay_cau_answer(tmp_path):
    path = tmp_path / 'g.jsonl'
    path.write_text(
        json.dumps({'action': 'answer', 'sources': [{'document_id': 'd', 'page_start': 1, 'page_end': 1}]}) + '\n'
        + json.dumps({'action': 'abstain', 'sources': [{'document_id': 'x', 'page_start': 2, 'page_end': 2}]}) + '\n',
        encoding='utf-8')
    assert review_chunks.load_gold_sources(path) == [{'document_id': 'd', 'page_start': 1, 'page_end': 1}]


def test_bo_qua_doan_pending_da_co_ban_checked_cung_muc(tmp_path):
    base = {'document_id': 'qd4932', 'content': 'nội dung'}
    rows = [
        {**base, 'chunk_id': 'r1', 'section': 'Phụ lục V.b', 'page_start': 10, 'page_end': 10, 'review_status': 'checked'},
        {**base, 'chunk_id': 'a1', 'section': 'Phụ lục > V.b', 'page_start': 10, 'page_end': 10, 'review_status': 'pending'},
        {**base, 'chunk_id': 'a2', 'section': 'Quy chế > Điều 6', 'page_start': 4, 'page_end': 4, 'review_status': 'pending'},
        {**base, 'chunk_id': 'a3', 'section': 'Phụ lục > V.b', 'page_start': 3, 'page_end': 3, 'review_status': 'pending'},
    ]
    (tmp_path / 'q.chunks.jsonl').write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in rows), encoding='utf-8')
    assert [r['chunk_id'] for r in review_chunks.pending_rows(tmp_path, set())] == ['a3', 'a2']
    assert len(review_chunks.pending_rows(tmp_path, set(), skip_covered=False)) == 3


def test_doan_da_duyet_trong_than_van_ban_khong_che_cac_doan_cung_dieu(tmp_path):
    base = {'document_id': 'qd3266', 'section': 'Quy định > Chương II > Điều 7', 'content': 'nội dung'}
    rows = [
        {**base, 'chunk_id': 'A', 'page_start': 5, 'page_end': 5, 'review_status': 'checked'},  # đã duyệt qua sổ
        {**base, 'chunk_id': 'B', 'page_start': 5, 'page_end': 6, 'review_status': 'pending'},  # cùng Điều, chưa duyệt
    ]
    (tmp_path / 'd.chunks.jsonl').write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in rows), encoding='utf-8')
    assert [r['chunk_id'] for r in review_chunks.pending_rows(tmp_path, {'A'})] == ['B']
    assert [r['chunk_id'] for r in review_chunks.pending_rows(tmp_path, set())] == ['B']


def test_doan_phu_luc_da_duyet_qua_so_cung_khong_che_doan_khac(tmp_path):
    base = {'document_id': 'qd4932', 'section': 'Phụ lục > V.b', 'content': 'nội dung'}
    rows = [
        {**base, 'chunk_id': 'A', 'page_start': 10, 'page_end': 10, 'review_status': 'checked'},  # duyệt qua sổ
        {**base, 'chunk_id': 'B', 'page_start': 10, 'page_end': 10, 'review_status': 'pending'},
    ]
    (tmp_path / 'p.chunks.jsonl').write_text('\n'.join(json.dumps(r, ensure_ascii=False) for r in rows), encoding='utf-8')
    assert [r['chunk_id'] for r in review_chunks.pending_rows(tmp_path, {'A'})] == ['B']
