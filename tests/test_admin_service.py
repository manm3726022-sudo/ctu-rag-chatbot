import csv
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from qdrant_client import models

from app import admin_service
from backend.services import retriever
from core import config
from core.corpus_metadata import ChunkRecord
from ingestion.approvals import append_approved
from ingestion.chunking import update_chunk_content
from scripts.ingest import _load_document_records


def test_upload_registers_source_hash_and_creates_pending_catalog_record(
    tmp_path, monkeypatch
):
    manifest = tmp_path / "documents.json"
    manifest.write_text("[]\n", encoding="utf-8")
    admin_manifest = tmp_path / "admin_documents.json"
    admin_manifest.write_text("[]\n", encoding="utf-8")
    raw_dir = tmp_path / "raw"
    monkeypatch.setattr(config, "MANIFEST_PATH", manifest)
    monkeypatch.setattr(config, "ADMIN_MANIFEST_PATH", admin_manifest)
    monkeypatch.setattr(admin_service, "RAW_DIR", raw_dir)

    content = b"%PDF-1.7\nfake but signature-valid test bytes"
    row = admin_service.register_uploaded_document(
        {
            "document_id": "qd9999",
            "document_number": "9999/QD-DHCT",
            "title": "Quy định thử nghiệm",
            "issuer": "Đại học Cần Thơ",
            "issued_on": "2026-01-01",
            "applicability": "Sinh viên",
            "source_kind": "pdf_text",
        },
        "some-user-file.pdf",
        content,
    )

    assert row["status"] == "registered"
    assert row["files"][0]["sha256"]
    assert (raw_dir / row["files"][0]["file_name"]).read_bytes() == content
    assert json.loads(manifest.read_text(encoding="utf-8")) == []
    assert json.loads(admin_manifest.read_text(encoding="utf-8")) == [row]
    monkeypatch.setattr(config, "MANIFEST_PATH", manifest)
    assert [
        document.document_id for document in _load_document_records(manifest)
    ] == ["qd9999"]


def test_upload_rejects_path_like_ids_and_format_mismatch(tmp_path, monkeypatch):
    manifest = tmp_path / "documents.json"
    manifest.write_text("[]\n", encoding="utf-8")
    monkeypatch.setattr(config, "MANIFEST_PATH", manifest)
    monkeypatch.setattr(admin_service, "RAW_DIR", tmp_path / "raw")
    metadata = {
        "document_id": "../bad",
        "document_number": "1/QD",
        "title": "Test",
        "issuer": "Test",
        "issued_on": "2026-01-01",
        "applicability": "Test",
        "source_kind": "pdf_text",
    }

    with pytest.raises(ValueError, match="Mã văn bản"):
        admin_service.register_uploaded_document(metadata, "a.pdf", b"%PDF-test")

    metadata["document_id"] = "doc1"
    with pytest.raises(ValueError, match="PDF hoặc DOCX"):
        admin_service.register_uploaded_document(metadata, "a.docx", b"%PDF-test")


def test_status_update_for_registered_main_corpus_document_does_not_fail(
    tmp_path, monkeypatch
):
    manifest = tmp_path / "documents.json"
    manifest.write_text(
        json.dumps(
            [
                {
                    "document_id": "qd3266",
                    "status": "indexed",
                }
            ]
        ),
        encoding="utf-8",
    )
    admin_manifest = tmp_path / "admin_documents.json"
    admin_manifest.write_text("[]\n", encoding="utf-8")
    monkeypatch.setattr(config, "MANIFEST_PATH", manifest)
    monkeypatch.setattr(config, "ADMIN_MANIFEST_PATH", admin_manifest)

    document = admin_service._update_document_status("qd3266", "indexed")

    assert document["document_id"] == "qd3266"
    assert json.loads(admin_manifest.read_text(encoding="utf-8")) == []


def test_approved_listing_joins_content_from_processed_chunks(
    tmp_path, monkeypatch
):
    chunk_id = str(uuid4())
    sha = "a" * 64
    manifest = tmp_path / "documents.json"
    manifest.write_text(
        json.dumps(
            [
                {
                    "document_id": "doc1",
                    "document_number": "1/QD",
                    "title": "Quy định",
                    "status": "indexed",
                    "ingestion_source": {
                        "file_name": "doc1.pdf",
                        "sha256": sha,
                        "source_kind": "pdf_text",
                    },
                    "files": [],
                }
            ]
        ),
        encoding="utf-8",
    )
    processed = tmp_path / "processed"
    processed.mkdir()
    path = processed / f"doc1-{sha}.chunks.jsonl"
    path.write_text(
        json.dumps(
            {
                "chunk_id": chunk_id,
                "document_id": "doc1",
                "sha256": sha,
                "section": "Điều 1",
                "page_start": 1,
                "page_end": 1,
                "content": "Nội dung đã duyệt",
                "review_status": "pending",
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    approved_path = tmp_path / "approved.csv"
    admin_manifest = tmp_path / "admin_documents.json"
    admin_manifest.write_text("[]\n", encoding="utf-8")
    append_approved(
        approved_path,
        [
            {
                "chunk_id": chunk_id,
                "document_id": "doc1",
                "section": "Điều 1",
                "page_start": 1,
                "page_end": 1,
            }
        ],
        "Admin",
        "2026-11-23",
    )
    monkeypatch.setattr(config, "MANIFEST_PATH", manifest)
    monkeypatch.setattr(config, "ADMIN_MANIFEST_PATH", admin_manifest)
    monkeypatch.setattr(config, "APPROVED_PATH", approved_path)
    monkeypatch.setattr(admin_service, "PROCESSED_DIR", processed)

    result = admin_service.list_review_chunks("checked")

    assert len(result) == 1
    assert result[0]["content"] == "Nội dung đã duyệt"
    assert result[0]["review_status"] == "checked"


def test_approve_updates_qdrant_ledger_and_processed_chunk(tmp_path, monkeypatch):
    chunk_id = str(uuid4())
    sha = "b" * 64
    manifest = tmp_path / "documents.json"
    manifest.write_text(
        json.dumps(
            [
                {
                    "document_id": "doc2",
                    "document_number": "2/QD",
                    "title": "Quy định 2",
                    "status": "indexed",
                    "ingestion_source": {
                        "file_name": "doc2.pdf",
                        "sha256": sha,
                        "source_kind": "pdf_text",
                    },
                    "files": [],
                }
            ]
        ),
        encoding="utf-8",
    )
    processed = tmp_path / "processed"
    processed.mkdir()
    path = processed / f"doc2-{sha}.chunks.jsonl"
    row = {
        "chunk_id": chunk_id,
        "document_id": "doc2",
        "sha256": sha,
        "section": "Điều 2",
        "page_start": 1,
        "page_end": 1,
        "content": "Nội dung pending",
        "review_status": "pending",
    }
    path.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")
    approved_path = tmp_path / "approved.csv"
    admin_manifest = tmp_path / "admin_documents.json"
    admin_manifest.write_text("[]\n", encoding="utf-8")
    monkeypatch.setattr(config, "MANIFEST_PATH", manifest)
    monkeypatch.setattr(config, "ADMIN_MANIFEST_PATH", admin_manifest)
    monkeypatch.setattr(config, "APPROVED_PATH", approved_path)
    monkeypatch.setattr(config, "COLLECTION", "test")
    monkeypatch.setattr(admin_service, "PROCESSED_DIR", processed)

    class FakeClient:
        def __init__(self):
            self.payload_updates = []

        def retrieve(self, collection_name, ids, **kwargs):
            return [SimpleNamespace(id=chunk_id)]

        def set_payload(self, **kwargs):
            self.payload_updates.append(kwargs)

    client = FakeClient()
    monkeypatch.setattr(retriever, "get_client", lambda: client)

    count = admin_service.approve_chunks([chunk_id], "Reviewer")

    updated = json.loads(path.read_text(encoding="utf-8"))
    assert count == 1
    assert updated["review_status"] == "checked"
    assert client.payload_updates[0]["points"] == [chunk_id]
    with approved_path.open(encoding="utf-8", newline="") as stream:
        approved_rows = list(csv.DictReader(stream))
    assert approved_rows[0]["chunk_id"] == chunk_id


def test_edit_approved_chunk_persists_override_and_new_approval(tmp_path, monkeypatch):
    source = {
        "file_name": "doc3.pdf",
        "sha256": "c" * 64,
        "source_kind": "pdf_text",
        "pages": None,
        "origin": "test",
    }
    base = ChunkRecord(
        document_id="doc3",
        sha256=source["sha256"],
        section="Điều 3",
        page_start=3,
        page_end=3,
        chunk_id=uuid4(),
        content="Nội dung có lỗi",
        review_status="checked",
    )
    current = {
        **base.model_dump(mode="json"),
        "document_title": "Quy định 3",
        "document_number": "3/QD",
        "processed_path": tmp_path / "doc3-chunks.jsonl",
    }
    expected = update_chunk_content(base, "Nội dung đã sửa").model_copy(
        update={"review_status": "checked"}
    )
    processed_path = current["processed_path"]
    processed_path.write_text(
        json.dumps(base.model_dump(mode="json"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    override_path = tmp_path / "chunk_overrides.json"
    approved_path = tmp_path / "approved.csv"
    manifest = tmp_path / "documents.json"
    admin_manifest = tmp_path / "admin_documents.json"
    admin_manifest.write_text("[]\n", encoding="utf-8")
    manifest.write_text(
        json.dumps(
            [
                {
                    "document_id": "doc3",
                    "document_number": "3/QD",
                    "title": "Quy định 3",
                    "issuer": "Đại học Cần Thơ",
                    "issued_on": "2026-01-01",
                    "effective_date": None,
                    "effective_from_term": None,
                    "effective_until_term_exclusive": None,
                    "applicability": "Sinh viên",
                    "source_url": None,
                    "relations": [],
                    "files": [source],
                    "status": "indexed",
                    "ingestion_source": source,
                }
            ]
        ),
        encoding="utf-8",
    )
    class FakeClient:
        def __init__(self):
            self.deleted = []

        def delete(self, **kwargs):
            self.deleted.append(kwargs)
            return SimpleNamespace(status=models.UpdateStatus.COMPLETED)

    client = FakeClient()
    monkeypatch.setattr(retriever, "get_client", lambda: client)
    monkeypatch.setattr(config, "ADMIN_MANIFEST_PATH", admin_manifest)
    monkeypatch.setattr(config, "MANIFEST_PATH", manifest)
    monkeypatch.setattr(config, "APPROVED_PATH", approved_path)
    monkeypatch.setattr(config, "CHUNK_OVERRIDES_PATH", override_path)
    monkeypatch.setattr(config, "COLLECTION", "test")
    monkeypatch.setattr(
        admin_service, "list_review_chunks", lambda status, document_id=None: [current]
    )
    from core import embedding
    from ingestion import index

    monkeypatch.setattr(embedding, "get_model", lambda: object())
    monkeypatch.setattr(
        index,
        "encode",
        lambda model, document, file_record, chunks: [
            SimpleNamespace(id=str(chunks[0].chunk_id))
        ],
    )
    upserted = []
    monkeypatch.setattr(
        index,
        "upsert",
        lambda client, collection, points: upserted.extend(points),
    )

    new_id = admin_service.edit_approved_chunk(
        str(base.chunk_id), "Nội dung đã sửa", "Reviewer"
    )

    assert new_id == str(expected.chunk_id)
    override = json.loads(override_path.read_text(encoding="utf-8"))[
        str(base.chunk_id)
    ]
    assert override["content"] == "Nội dung đã sửa"
    assert override["review_status"] == "checked"
    updated = json.loads(processed_path.read_text(encoding="utf-8"))
    assert updated["chunk_id"] == new_id
    assert updated["content"] == "Nội dung đã sửa"
    assert len(upserted) == 1
    assert client.deleted[0]["points_selector"].points == [str(base.chunk_id)]
    with approved_path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert rows[0]["chunk_id"] == new_id
