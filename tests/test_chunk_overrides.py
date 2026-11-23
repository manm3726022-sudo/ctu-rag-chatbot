import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from core import config
from core.corpus_metadata import ChunkRecord
from ingestion.chunking import update_chunk_content
from ingestion.overrides import apply_overrides, read_overrides, write_overrides
from scripts import ingest


def test_content_edit_changes_chunk_id_and_survives_future_ingestion(tmp_path):
    chunk = ChunkRecord(
        document_id="qd9999",
        sha256="a" * 64,
        section="Điều 1",
        page_start=1,
        page_end=1,
        chunk_id=uuid4(),
        content="Sai nội dung OCR",
        review_status="pending",
    )
    edited = update_chunk_content(chunk, "Nội dung đã được sửa chính xác")
    assert edited.chunk_id != chunk.chunk_id

    path = tmp_path / "chunk_overrides.json"
    write_overrides(
        path,
        {
            str(chunk.chunk_id): {
                "content": edited.content,
                "review_status": "checked",
            }
        },
    )
    restored = apply_overrides([chunk], read_overrides(path))[0]

    assert restored.chunk_id == edited.chunk_id
    assert restored.content == edited.content
    assert restored.review_status == "checked"


def test_ingestion_reapplies_chunk_override(tmp_path, monkeypatch):
    chunk = ChunkRecord(
        document_id="qd9999",
        sha256="b" * 64,
        section="Điều 2",
        page_start=2,
        page_end=2,
        chunk_id=uuid4(),
        content="Nguồn chưa sửa",
        review_status="pending",
    )
    override_path = tmp_path / "chunk_overrides.json"
    write_overrides(
        override_path,
        {
            str(chunk.chunk_id): {
                "content": "Nội dung đã hiệu chỉnh",
                "review_status": "checked",
            }
        },
    )
    output = tmp_path / "processed"
    output.mkdir()
    monkeypatch.setattr(config, "CHUNK_OVERRIDES_PATH", override_path)
    monkeypatch.setattr(ingest, "extract_pages", lambda path, source: ["page text"])
    monkeypatch.setattr(ingest, "_build_chunks", lambda *args: ([chunk], []))

    ingest._prepare(
        SimpleNamespace(document_id="qd9999"),
        SimpleNamespace(sha256=chunk.sha256),
        Path("source.pdf"),
        output,
    )

    chunks_path = next(output.glob("*.chunks.jsonl"))
    prepared = json.loads(chunks_path.read_text(encoding="utf-8").splitlines()[0])
    assert prepared["content"] == "Nội dung đã hiệu chỉnh"
    assert prepared["review_status"] == "checked"
