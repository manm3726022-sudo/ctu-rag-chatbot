"""Verify the handover and import its source catalog into the project registry."""

import argparse
import hashlib
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from core.corpus_metadata import ChunkRecord, DocumentRecord, Locator

ROOT = Path(__file__).resolve().parents[1]


def read_jsonl(path):
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def check_locator(loc, files):
    item = files.get((loc.document_id, loc.sha256))
    if item is None or item.source_kind == "summary":
        raise ValueError(f"Nguồn chính không hợp lệ: {loc.section}")
    if item.pages is None or loc.page_end > item.pages:
        raise ValueError(f"Vị trí vượt phạm vi tệp: {loc.section}")


def verify(root):
    catalog = json.loads(
        (root / "docs/corpus/documents.json").read_text(encoding="utf-8")
    )
    documents = [DocumentRecord.model_validate(row) for row in catalog]
    if len({row.document_id for row in documents}) != len(documents):
        raise ValueError("Trùng mã văn bản")
    files = {}
    for document in documents:
        for item in document.files:
            if Path(item.file_name).name != item.file_name:
                raise ValueError("Tên file phải là tên cơ sở")
            folder = (
                "data/ocr/reference_only"
                if item.source_kind == "summary"
                else "data/raw"
            )
            path = root / folder / item.file_name
            with path.open("rb") as stream:
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
            if digest != item.sha256:
                raise ValueError(f"SHA-256 không khớp: {item.file_name}")
            files[document.document_id, item.sha256] = item
    chunks = [
        ChunkRecord.model_validate(x)
        for x in read_jsonl(root / "tests/fixtures/corpus_chunks.jsonl")
    ]
    if len({c.chunk_id for c in chunks}) != len(chunks):
        raise ValueError("Trùng mã đoạn")
    for chunk in chunks:
        check_locator(chunk, files)
    cases = read_jsonl(root / "eval/gold_corpus.jsonl")
    if len({r["case_id"] for r in cases}) != len(cases) or len(
        {r["question"] for r in cases}
    ) != len(cases):
        raise ValueError("Trùng ca kiểm thử")
    for case in cases:
        if not case["expected_answer"].strip() or case["action"] not in {
            "answer",
            "clarify",
            "refer",
            "abstain",
        }:
            raise ValueError(case["case_id"])
        if case["action"] == "answer" and not case["sources"]:
            raise ValueError(f"Thiếu nguồn: {case['case_id']}")
        for item in case["sources"]:
            check_locator(Locator.model_validate(item), files)
    return documents, len(chunks), len(cases)


def register(db, documents):
    db.execute("BEGIN IMMEDIATE")
    with db:
        db.execute("""CREATE TABLE IF NOT EXISTS corpus_versions (
            document_id TEXT NOT NULL, version INTEGER NOT NULL,
            fingerprint TEXT NOT NULL, imported_at TEXT NOT NULL, record_json TEXT NOT NULL,
            PRIMARY KEY (document_id, version))""")
        db.execute("""CREATE VIEW IF NOT EXISTS corpus_current AS
            SELECT v.* FROM corpus_versions AS v
            WHERE v.version = (SELECT MAX(s.version) FROM corpus_versions AS s
                               WHERE s.document_id = v.document_id)""")
        count = 0
        for doc in documents:
            body = json.dumps(
                doc.model_dump(mode="json"), ensure_ascii=False, sort_keys=True
            )
            digest = hashlib.sha256(body.encode()).hexdigest()
            previous = db.execute(
                "SELECT version, fingerprint FROM corpus_current WHERE document_id = ?",
                (doc.document_id,),
            ).fetchone()
            if previous and previous[1] == digest:
                continue
            version = previous[0] + 1 if previous else 1
            db.execute(
                "INSERT INTO corpus_versions VALUES (?, ?, ?, ?, ?)",
                (
                    doc.document_id,
                    version,
                    digest,
                    datetime.now(UTC).isoformat(),
                    body,
                ),
            )
            count += 1
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--db", type=Path, default=ROOT / "data/registry/registry.db")
    args = parser.parse_args()
    docs, chunks, cases = verify(ROOT)
    print(
        f"{len(docs)} văn bản, {sum(len(d.files) for d in docs)} tệp, {chunks} đoạn mẫu, {cases} câu."
    )
    if not args.check_only:
        args.db.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(args.db)
        try:
            print(f"Phiên bản mới ghi: {register(db, docs)}")
        finally:
            db.close()


if __name__ == "__main__":
    main()
