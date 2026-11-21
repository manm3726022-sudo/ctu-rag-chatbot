'''Danh mục văn bản. Logic được kiểm bằng manifest TỰ TẠO để test không vỡ khi nhóm thêm, sửa hay ngừng dùng
văn bản trong docs/corpus/documents.json; manifest thật chỉ được kiểm ở mức "đọc được và hợp lệ".'''
import json
import os

import pytest

from core import corpus_catalog as cc
from core.config import ROOT


def row(doc_id, number, **kw):
    sha = (doc_id[-1] if doc_id[-1].isalnum() else 'a') * 64
    base = {
        'document_id': doc_id, 'document_number': number, 'title': f'Văn bản {doc_id}', 'status': 'registered',
        'effective_date': None, 'effective_from_term': None, 'effective_until_term_exclusive': None,
        'files': [{'file_name': f'{doc_id}.pdf', 'sha256': sha, 'source_kind': 'pdf_text', 'pages': 1, 'origin': 'x'}],
    }
    base.update(kw)
    return base


def write(path, rows):
    path.write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
    return path


def test_term_key():
    assert cc.term_key('2024-HK2') == 20242 and cc.term_key(None) is None
    with pytest.raises(ValueError):
        cc.term_key('2024-HK4')


def test_manifest_that_doc_duoc_va_hop_le():
    docs = cc.load_catalog(ROOT / 'docs/corpus/documents.json')
    assert docs and len({d.document_id for d in docs}) == len(docs)
    for d in docs:
        assert d.document_number and d.kind in {'qd', 'tt', 'hd', ''}
        assert d.active_sha256, f'{d.document_id} không có tệp nguồn chính nào để nạp'
        assert all(len(s) == 64 for s in d.active_sha256)


@pytest.mark.parametrize('number, kind, num', [
    ('3266/QĐ-ĐHCT', 'qd', '3266'), ('40/2026/TT-BGDĐT', 'tt', '40'), ('2427/HD-ĐHCT', 'hd', '2427'),
    ('5976/QD-DHCT', 'qd', '5976'), ('khong-co-so', '', ''),
])
def test_nhan_dien_loai_va_so_hieu(tmp_path, number, kind, num):
    (d,) = cc.load_catalog(write(tmp_path / 'm.json', [row('x1', number)]))
    assert (d.kind, d.number) == (kind, num)


def test_nguon_chinh_dung_quy_tac_cua_ingest(tmp_path):
    pdf = {'file_name': 'a.pdf', 'sha256': '1' * 64, 'source_kind': 'pdf_scan', 'pages': 3, 'origin': 'x'}
    word = {'file_name': 'a.docx', 'sha256': '2' * 64, 'source_kind': 'docx_scan', 'pages': 3, 'origin': 'x'}
    summary = {'file_name': 'b.docx', 'sha256': '3' * 64, 'source_kind': 'summary', 'pages': None, 'origin': 'x'}
    rows = [
        row('a1', '1/QĐ-T', files=[word], ingestion_source=pdf),  # có ingestion_source: dùng nó, không dùng files
        row('b1', '2/QĐ-T', files=[pdf, summary]),  # bản tóm tắt (summary) không được tính
        row('c1', '3/QĐ-T', files=[word]),
    ]
    a, b, c = cc.load_catalog(write(tmp_path / 'm.json', rows))
    assert a.active_sha256 == ('1' * 64,) and b.active_sha256 == ('1' * 64,) and c.active_sha256 == ('2' * 64,)


def synthetic(tmp_path, **status):
    rows = [
        row('qa', '1/QĐ-T', effective_from_term='2024-HK2', **status.get('qa', {})),
        row('qb', '2/QĐ-T', effective_from_term='2026-HK1', **status.get('qb', {})),
        row('tc', '3/TT-T', effective_date='2026-06-30'),
        row('hd', '4/HD-T'),
    ]
    return cc.load_catalog(write(tmp_path / 'm.json', rows))


def test_hieu_luc_theo_hoc_ky(tmp_path):
    cat = synthetic(tmp_path)
    ids = lambda t: [d.document_id for d in cc.valid_documents(t, cat)]  # noqa: E731
    assert 'qa' not in ids(20241) and 'qa' in ids(20242)
    assert 'qb' not in ids(20252) and 'qb' in ids(20261)
    assert {'tc', 'hd'} <= set(ids(20241))  # chỉ có ngày hiệu lực hoặc không có mốc: giữ lại, không đoán
    assert ids(None) == ['qa', 'qb', 'tc', 'hd']


def test_archived_va_ky_ket_thuc(tmp_path):
    cat = synthetic(tmp_path, qa={'status': 'archived'}, qb={'effective_until_term_exclusive': '2027-HK1'})
    assert 'qa' not in [d.document_id for d in cc.valid_documents(None, cat)]
    assert 'qb' in [d.document_id for d in cc.valid_documents(20262, cat)]
    assert 'qb' not in [d.document_id for d in cc.valid_documents(20271, cat)]


def test_doc_lai_khi_manifest_doi(tmp_path):
    path = write(tmp_path / 'm.json', [row('x1', '1/QĐ-T')])
    assert len(cc.load_catalog(path)) == 1
    write(path, [row('x1', '1/QĐ-T'), row('y2', '2/QĐ-T'), row('z3', '3/QĐ-T')])
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10**9))  # đảm bảo mtime khác dù ghi liên tiếp rất nhanh
    assert len(cc.load_catalog(path)) == 3
