"""Admin operations for document ingestion and reviewed chunk maintenance."""

import hashlib
import json
import os
import re
import tempfile
from datetime import date
from pathlib import Path

from core import config
from core.corpus_metadata import DocumentRecord, FileRecord
from ingestion.approvals import append_approved, read_approved
from ingestion.chunking import update_chunk_content
from ingestion.overrides import read_overrides, write_overrides
from ingestion.sources import MAX_BYTES

MAX_UPLOAD_BYTES = MAX_BYTES
RAW_DIR = config.ROOT / "data/raw"
PROCESSED_DIR = config.ROOT / "data/processed"
DOCUMENT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
UPLOAD_TYPES = {
    ".pdf": ("pdf_text", "pdf_scan"),
    ".docx": ("docx_text", "docx_scan"),
}


def _read_manifest() -> list[dict]:
    if not config.ADMIN_MANIFEST_PATH.exists():
        return []
    with config.ADMIN_MANIFEST_PATH.open(encoding="utf-8") as stream:
        rows = json.load(stream)
    if not isinstance(rows, list):
        raise TypeError("Admin document manifest must contain a list")
    return rows


def _read_all_manifests() -> list[dict]:
    with config.MANIFEST_PATH.open(encoding="utf-8") as stream:
        base_rows = json.load(stream)
    if not isinstance(base_rows, list):
        raise TypeError("Document manifest must contain a list")
    return [*base_rows, *_read_manifest()]


def _atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _write_manifest(rows: list[dict]) -> None:
    _atomic_json(config.ADMIN_MANIFEST_PATH, rows)


def register_uploaded_document(metadata: dict, filename: str, content: bytes) -> dict:
    """Validate and register an uploaded source without indexing it yet."""
    document_id = (metadata.get("document_id") or "").strip()
    if not DOCUMENT_ID_RE.fullmatch(document_id):
        raise ValueError("Mã văn bản chỉ gồm chữ thường, số, gạch ngang hoặc gạch dưới")
    if not content:
        raise ValueError("Tệp tải lên đang rỗng")
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("Dung lượng tệp vượt quá giới hạn 100 MiB")

    extension = Path(filename).suffix.lower()
    source_kind = metadata.get("source_kind")
    if extension not in UPLOAD_TYPES or source_kind not in UPLOAD_TYPES[extension]:
        raise ValueError("MVP hiện chỉ nhận PDF hoặc DOCX với loại tệp tương ứng")
    if extension == ".pdf" and not content.startswith(b"%PDF-"):
        raise ValueError("Nội dung tệp không có định dạng PDF hợp lệ")
    if extension == ".docx" and not content.startswith(b"PK"):
        raise ValueError("Nội dung tệp không có định dạng DOCX hợp lệ")

    rows = _read_all_manifests()
    if any(row.get("document_id") == document_id for row in rows):
        raise ValueError(f"Mã văn bản {document_id!r} đã tồn tại trong danh mục")
    admin_rows = _read_manifest()

    digest = hashlib.sha256(content).hexdigest()
    stored_name = f"{document_id}-{digest[:12]}{extension}"
    source = FileRecord(
        file_name=stored_name,
        sha256=digest,
        source_kind=source_kind,
        pages=None,
        origin="Uploaded through the admin interface",
    )
    row = {
        "document_id": document_id,
        "document_number": metadata["document_number"].strip(),
        "title": metadata["title"].strip(),
        "issuer": metadata["issuer"].strip(),
        "issued_on": metadata["issued_on"],
        "effective_date": metadata.get("effective_date") or None,
        "effective_from_term": metadata.get("effective_from_term") or None,
        "effective_until_term_exclusive": (
            metadata.get("effective_until_term_exclusive") or None
        ),
        "applicability": metadata["applicability"].strip(),
        "source_url": None,
        "relations": [],
        "files": [source.model_dump(mode="json")],
        "status": "registered",
        "ingestion_source": source.model_dump(mode="json"),
    }
    validated = DocumentRecord.model_validate(row).model_dump(
        mode="json", exclude_none=False
    )

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    target = RAW_DIR / stored_name
    created_file = False
    if target.exists():
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Existing upload path has different content: {stored_name}")
    else:
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=RAW_DIR,
                prefix=f".{stored_name}.",
                delete=False,
            ) as stream:
                temporary = Path(stream.name)
                stream.write(content)
            os.replace(temporary, target)
            created_file = True
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()

    try:
        _write_manifest([*admin_rows, validated])
    except (OSError, TypeError):
        if created_file:
            target.unlink(missing_ok=True)
        raise
    return validated


def _update_document_status(document_id: str, status: str) -> dict:
    rows = _read_manifest()
    for row in rows:
        if row.get("document_id") == document_id:
            row["status"] = status
            _write_manifest(rows)
            return row
    for row in _read_all_manifests():
        if row.get("document_id") == document_id:
            return row
    raise ValueError(f"Document not found in manifest: {document_id}")


def process_document(document_id: str) -> int:
    """Run the existing extraction, chunking, embedding and Qdrant indexing pipeline."""
    rows = _read_all_manifests()
    if not any(row.get("document_id") == document_id for row in rows):
        raise ValueError(f"Document not found in manifest: {document_id}")

    from scripts.ingest import run

    indexed = run(
        config.MANIFEST_PATH,
        RAW_DIR,
        PROCESSED_DIR,
        [document_id],
        False,
        read_approved(config.APPROVED_PATH),
    )
    _update_document_status(document_id, "indexed")
    return indexed


def list_registered_documents() -> list[dict]:
    return [row for row in _read_manifest() if row.get("status") == "registered"]


def list_review_chunks(status: str, document_id: str | None = None) -> list[dict]:
    if status not in {"pending", "checked"}:
        raise ValueError(f"Unsupported review status: {status}")
    documents = {
        row["document_id"]: row
        for row in _read_all_manifests()
        if row.get("status") != "archived"
    }
    approved = read_approved(config.APPROVED_PATH)
    result = []
    for path in sorted(PROCESSED_DIR.glob("*.chunks.jsonl")):
        with path.open(encoding="utf-8") as stream:
            chunks = [json.loads(line) for line in stream if line.strip()]
        for chunk in chunks:
            document = documents.get(chunk["document_id"])
            if document_id and chunk["document_id"] != document_id:
                continue
            if document is None:
                continue
            sources = (
                [document["ingestion_source"]]
                if document.get("ingestion_source")
                else document["files"]
            )
            active_hashes = {
                source["sha256"]
                for source in sources
                if source["source_kind"] != "summary"
            }
            if chunk["sha256"] not in active_hashes:
                continue
            source = next(
                source
                for source in sources
                if source["sha256"] == chunk["sha256"]
                and source["source_kind"] != "summary"
            )
            current_status = (
                "checked"
                if chunk["review_status"] == "checked"
                or str(chunk["chunk_id"]) in approved
                else "pending"
            )
            if current_status != status:
                continue
            result.append(
                {
                    **chunk,
                    "review_status": current_status,
                    "document_title": document["title"],
                    "document_number": document["document_number"],
                    "source_path": RAW_DIR / source["file_name"],
                    "source_kind": source["source_kind"],
                    "processed_path": path,
                }
            )
    result.sort(
        key=lambda chunk: (
            chunk["document_id"],
            chunk["page_start"],
            chunk["section"],
        )
    )
    return result


def _rewrite_processed_chunks(chunks: list[dict], replacements: dict[str, dict]) -> None:
    paths = {chunk["processed_path"] for chunk in chunks}
    for path in paths:
        with path.open(encoding="utf-8") as stream:
            rows = [json.loads(line) for line in stream if line.strip()]
        for row in rows:
            replacement = replacements.get(str(row["chunk_id"]))
            if replacement:
                row.update(replacement)
        _write_jsonl(path, rows)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            for row in rows:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _document_and_source(document_id: str, sha256: str):
    row = next(
        (
            item
            for item in _read_all_manifests()
            if item.get("document_id") == document_id
        ),
        None,
    )
    if row is None:
        raise ValueError(f"Document not found in manifest: {document_id}")
    document = DocumentRecord.model_validate(row)
    sources = (
        [document.ingestion_source]
        if document.ingestion_source
        else document.files
    )
    source = next(
        (
            item
            for item in sources
            if item.sha256 == sha256 and item.source_kind != "summary"
        ),
        None,
    )
    if source is None:
        raise ValueError(
            f"Chunk source {sha256} is not active in document {document_id}"
        )
    return document, source


def approve_chunks(chunk_ids: list[str], reviewer: str) -> int:
    reviewer = reviewer.strip()
    if not reviewer:
        raise ValueError("Cần nhập tên người duyệt")
    wanted = set(chunk_ids)
    if not wanted:
        return 0
    pending = {
        str(chunk["chunk_id"]): chunk
        for chunk in list_review_chunks("pending")
        if str(chunk["chunk_id"]) in wanted
    }
    if pending.keys() != wanted:
        missing = sorted(wanted - pending.keys())
        raise ValueError(f"Các đoạn không còn pending hoặc không tồn tại: {', '.join(missing)}")

    from backend.services import retriever

    client = retriever.get_client()
    missing_in_index = set()
    for offset in range(0, len(chunk_ids), 128):
        batch = chunk_ids[offset : offset + 128]
        found = client.retrieve(
            collection_name=config.COLLECTION,
            ids=batch,
            with_payload=False,
            with_vectors=False,
        )
        missing_in_index.update(set(batch) - {str(point.id) for point in found})
    if missing_in_index:
        raise ValueError(
            "Một số đoạn chưa được lập chỉ mục trong Qdrant: "
            + ", ".join(sorted(missing_in_index))
        )

    for offset in range(0, len(chunk_ids), 128):
        client.set_payload(
            collection_name=config.COLLECTION,
            payload={"review_status": "checked"},
            points=chunk_ids[offset : offset + 128],
            wait=True,
        )

    selected = [pending[chunk_id] for chunk_id in chunk_ids]
    append_approved(
        config.APPROVED_PATH,
        selected,
        reviewer,
        date.today().isoformat(),
    )
    _rewrite_processed_chunks(
        selected,
        {chunk_id: {"review_status": "checked"} for chunk_id in chunk_ids},
    )
    return len(chunk_ids)


def edit_approved_chunk(chunk_id: str, content: str, reviewer: str) -> str:
    reviewer = reviewer.strip()
    if not reviewer:
        raise ValueError("Cần nhập tên người chỉnh sửa")
    content = content.strip()
    if not content:
        raise ValueError("Nội dung đoạn không được để trống")
    current = next(
        (
            chunk
            for chunk in list_review_chunks("checked")
            if str(chunk["chunk_id"]) == chunk_id
        ),
        None,
    )
    if current is None:
        raise ValueError("Không tìm thấy đoạn approved đang hoạt động")
    if content == current["content"]:
        return chunk_id

    from core.corpus_metadata import ChunkRecord

    current_chunk = ChunkRecord.model_validate(
        {key: value for key, value in current.items() if key in ChunkRecord.model_fields}
    )
    edited = update_chunk_content(current_chunk, content).model_copy(
        update={"review_status": "checked"}
    )
    overrides = read_overrides(config.CHUNK_OVERRIDES_PATH)
    base_id = next(
        (
            key
            for key, value in overrides.items()
            if value.get("current_chunk_id") == chunk_id
            or chunk_id in value.get("superseded_chunk_ids", [])
        ),
        chunk_id,
    )
    old_override = overrides.get(base_id, {})
    superseded = set(old_override.get("superseded_chunk_ids", []))
    superseded.update({base_id, chunk_id})
    overrides[base_id] = {
        "document_id": edited.document_id,
        "content": content,
        "current_chunk_id": str(edited.chunk_id),
        "review_status": "checked",
        "superseded_chunk_ids": sorted(superseded),
        "reviewer": reviewer,
        "reviewed_on": date.today().isoformat(),
    }
    write_overrides(config.CHUNK_OVERRIDES_PATH, overrides)

    document, source = _document_and_source(
        edited.document_id, edited.sha256
    )
    from backend.services import retriever
    from core.embedding import get_model
    from ingestion.index import encode, upsert

    points = encode(get_model(), document, source, [edited])
    if len(points) != 1:
        raise RuntimeError("Expected exactly one replacement chunk for reindexing")
    client = retriever.get_client()
    upsert(client, config.COLLECTION, points)
    stale_ids = sorted(superseded - {str(edited.chunk_id)})
    if stale_ids:
        from qdrant_client import models

        result = client.delete(
            collection_name=config.COLLECTION,
            points_selector=models.PointIdsList(points=stale_ids),
            wait=True,
        )
        if result.status != models.UpdateStatus.COMPLETED:
            raise RuntimeError(f"Qdrant did not delete superseded points: {result.status}")

    revised = {
        **edited.model_dump(mode="json"),
        "document_title": document.title,
        "document_number": document.document_number,
        "processed_path": current["processed_path"],
    }
    _rewrite_processed_chunks(
        [current],
        {chunk_id: edited.model_dump(mode="json")},
    )
    append_approved(
        config.APPROVED_PATH,
        [revised],
        reviewer,
        date.today().isoformat(),
    )
    return str(edited.chunk_id)
