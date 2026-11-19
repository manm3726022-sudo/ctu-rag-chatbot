import hashlib
import json
import sys
from contextlib import closing
from io import BytesIO
from types import SimpleNamespace

import pytest
from docx import Document
from docx.enum.text import WD_BREAK
from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from core.corpus_evidence import to_evidence
from core.corpus_metadata import ChunkRecord, DocumentRecord
from ingestion import chunking, extract, sources
from ingestion.rubric import read_rubric
from scripts import ingest


def _record(name, kind, data, pages=1, url=None):
    return DocumentRecord(
        document_id="policy",
        document_number="1/QĐ-ĐHCT",
        title="Chính sách thử nghiệm",
        issuer="Đại học Cần Thơ",
        issued_on="2026-01-01",
        effective_date=None,
        effective_from_term=None,
        applicability="Sinh viên",
        source_url=url,
        relations=[],
        files=[
            {
                "file_name": name,
                "source_kind": kind,
                "pages": pages,
                "sha256": hashlib.sha256(data).hexdigest(),
                "origin": "fixture",
            }
        ],
    )


def test_download_attachment_checks_hash_before_saving(tmp_path, monkeypatch):
    url = "https://example.com/detail.html?id=1"
    pdf = b"%PDF-1.7 verified"
    doc = _record("policy.pdf", "pdf_text", pdf, url=url)
    source = doc.files[0]
    calls = []

    def get(url, *, stream, timeout):
        from requests import Response

        calls.append(url)
        response = Response()
        response.status_code = 200
        response.url = url
        response._content_consumed = True
        if url.endswith(".pdf"):
            response.headers["Content-Type"] = "application/pdf"
            response._content = pdf
        else:
            response.headers["Content-Type"] = "text/html; charset=utf-8"
            response._content = (
                b'<a href="/files/policy.pdf">PDF</a><a href="/other.pdf">Other</a>'
            )
        return response

    monkeypatch.setattr(sources.requests, "get", get)
    with pytest.raises(ValueError, match="SHA-256"):
        sources.acquire(doc, source.model_copy(update={"sha256": "0" * 64}), tmp_path)
    assert not (tmp_path / source.file_name).exists()
    assert sources.acquire(doc, source, tmp_path).read_bytes() == pdf
    assert sources.acquire(doc, source, tmp_path).read_bytes() == pdf
    assert calls == [url, "https://example.com/files/policy.pdf"] * 2


def test_text_pdf_and_scan_dispatch_preserve_page_order(tmp_path, monkeypatch):
    writer = PdfWriter()
    page = writer.add_blank_page(width=100, height=100)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
        }
    )
    content = DecodedStreamObject()
    content.set_data(b"BT /F1 10 Tf 5 50 Td (Sample policy) Tj ET")
    page.replace_contents(content)
    writer.add_blank_page(width=100, height=100)
    path = tmp_path / "mixed.pdf"
    writer.write(path)
    doc = _record(path.name, "pdf_text", path.read_bytes(), pages=2)
    calls = []

    def ocr(data):
        assert data.startswith(b"\x89PNG")
        calls.append(data)
        return f"OCR {len(calls)}"

    monkeypatch.setattr(extract, "_ocr", ocr)
    assert extract.extract_pages(path, doc.files[0]) == ["Sample policy", "OCR 1"]
    scanned = doc.files[0].model_copy(update={"source_kind": "pdf_scan"})
    assert extract.extract_pages(path, scanned) == ["OCR 2", "OCR 3"]


def test_docx_text_and_scans_use_document_order(tmp_path, monkeypatch):
    document = Document()
    paragraph = document.add_paragraph("Điều 1")
    paragraph.add_run().add_break(WD_BREAK.PAGE)
    paragraph.add_run("Điều 2")
    table = document.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Điểm"
    table.cell(0, 1).text = "3"
    images = []
    for color in ("red", "blue", "red"):
        data = BytesIO()
        Image.new("RGB", (10, 10), color=color).save(data, "PNG")
        images.append(data.getvalue())
        document.add_picture(BytesIO(images[-1]))
    path = tmp_path / "policy.docx"
    document.save(path)
    doc = _record(path.name, "docx_text", path.read_bytes(), pages=2)
    first, second = extract.extract_pages(path, doc.files[0])
    assert "Điều 1" in first and "Điều 2" in second and "Điểm | 3" in second
    monkeypatch.setattr(
        extract, "_ocr", lambda data: str(Image.open(BytesIO(data)).getpixel((0, 0)))
    )
    source = doc.files[0].model_copy(update={"source_kind": "docx_scan", "pages": 3})
    assert extract.extract_pages(path, source) == [
        "(255, 0, 0)",
        "(0, 0, 255)",
        "(255, 0, 0)",
    ]


def test_chunks_keep_article_boundary_and_cross_page_condition(monkeypatch):
    monkeypatch.setattr(chunking, "count_tokens", lambda text: len(text.split()))
    doc = _record("policy.pdf", "pdf_text", b"", pages=2)
    pages = [
        "Điều 2. Hiệu lực\nĐây là quyết định.\nQUY ĐỊNH CÔNG TÁC HỌC VỤ\nĐiều 2. Điều kiện\n1. Điều kiện bắt đầu ở đây",
        "2\nvà kết thúc ở trang sau.\nĐiều 3. Giới hạn\n" + "dài " * 1000,
    ]
    chunks, _ = chunking.parse_pages(doc, doc.files[0], pages)
    assert chunks[0].section == "Quyết định > Điều 2"
    assert chunks[2].section == "Quy định > Điều 2"
    assert chunks[2].content.endswith("ở đây và kết thúc ở trang sau.")
    assert (chunks[2].page_start, chunks[2].page_end) == (1, 2)
    assert all(
        chunking.count_tokens(chunk.content) <= chunking.TOKEN_LIMIT for chunk in chunks
    )
    assert chunks == chunking.parse_pages(doc, doc.files[0], pages)[0]


def test_guidance_chunks_keep_numbered_sections_across_pages(monkeypatch):
    monkeypatch.setattr(chunking, "count_tokens", lambda text: len(text.split()))
    doc = _record("guidance.pdf", "pdf_text", b"", pages=2).model_copy(
        update={"document_number": "2427/HD-ĐHCT"}
    )
    pages = [
        "1/2\nI. QUY TRÌNH CÔNG TÁC\n1. Cơ sở thực hiện\n4.1 Đối với sinh viên năm thứ nhất",
        "2/2\nTham khảo kế hoạch học tập.\nII. TỔ CHỨC THỰC HIỆN",
    ]
    chunks, _ = chunking.parse_pages(doc, doc.files[0], pages)
    assert [chunk.section for chunk in chunks] == [
        "Hướng dẫn > Mục I",
        "Hướng dẫn > Mục I > 1",
        "Hướng dẫn > Mục I > 4.1",
        "Hướng dẫn > Mục II",
    ]
    assert (chunks[2].page_start, chunks[2].page_end) == (1, 2)
    assert "2/2" not in chunks[2].content


def test_reviewed_rubric_keeps_the_scoring_caps_and_spanning_rows():
    manifest = json.loads(
        (ingest.ROOT / "docs/corpus/documents.json").read_text(encoding="utf-8")
    )
    doc = DocumentRecord.model_validate(
        next(row for row in manifest if row["document_id"] == "qd4932")
    )
    chunks, rules = read_rubric(ingest.RUBRIC, doc, doc.files[0])
    assert len(chunks) == len(rules) == 47
    assert any(row["page_start"] < row["page_end"] for row in rules)
    event = next(chunk for chunk in chunks if chunk.section == "Phụ lục V.b")
    assert event.review_status == "checked"
    assert (
        "3 điểm" in event.content
        and "12 điểm" in event.content
        and "20 điểm" in event.content
    )


def test_ingestion_cli_upserts_dense_sparse_and_provenance(tmp_path, monkeypatch):
    import qdrant_client
    from qdrant_client import QdrantClient, models

    monkeypatch.setattr(chunking, "count_tokens", lambda text: len(text.split()))
    html = b"<nav>Menu</nav><main><h1>Policy</h1><p>Applies to students.</p><table><tr><td>Credits</td><td>24</td></tr></table></main>"
    doc = _record("policy.html", "html", html)
    source = doc.files[0]
    handoff = source.model_copy(
        update={
            "file_name": "policy.docx",
            "source_kind": "docx_scan",
            "sha256": "1" * 64,
        }
    )
    doc = doc.model_copy(update={"files": [handoff], "ingestion_source": source})
    manifest = tmp_path / "catalog.json"
    manifest.write_text(f"[{doc.model_dump_json()}]", encoding="utf-8")
    (tmp_path / source.file_name).write_bytes(html)
    output = tmp_path / "processed"
    database = str(tmp_path / "qdrant")

    class Model:
        def __init__(self, name, use_fp16):
            pass

        def encode_corpus(self, texts, *, return_dense, return_sparse, **kwargs):
            assert return_dense and return_sparse
            assert all("Menu" not in text for text in texts)
            return {
                "dense_vecs": [[1.0, 0.0]] * len(texts),
                "lexical_weights": [{"24": 1.0}] * len(texts),
            }

    monkeypatch.setitem(
        sys.modules, "FlagEmbedding", SimpleNamespace(BGEM3FlagModel=Model)
    )
    monkeypatch.setattr(
        qdrant_client, "QdrantClient", lambda **kwargs: QdrantClient(path=database)
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ingest",
            "--manifest",
            str(manifest),
            "--raw-dir",
            str(tmp_path),
            "--output-dir",
            str(output),
        ],
    )
    ingest.main()
    ingest.main()
    with closing(QdrantClient(path=database)) as client:
        collection = ingest.config.COLLECTION
        assert client.count(collection).count == 1
        (point,) = client.query_points(
            collection, query=[1.0, 0.0], using="dense", with_vectors=True
        ).points
        (hit,) = client.query_points(
            collection,
            query=models.SparseVector(indices=[24], values=[1.0]),
            using="sparse",
        ).points
        assert point.id == hit.id
        assert set(point.vector) == {"dense", "sparse"}
        assert point.payload["document_number"] == doc.document_number
        assert point.payload["sha256"] == source.sha256
        assert point.payload["review_status"] == "pending"
        assert point.payload["status"] == "indexed"
    (tables,) = output.glob("*.tables.jsonl")
    assert json.loads(tables.read_text(encoding="utf-8"))["cells"] == ["Credits", "24"]
    (chunks,) = output.glob("*.chunks.jsonl")
    chunk = ChunkRecord.model_validate_json(chunks.read_bytes())
    reviewed = chunk.model_copy(update={"review_status": "checked"})
    assert to_evidence(doc, reviewed, 1).page_start == 1
