"""Download, extract and index the CTU corpus described in its manifest."""

import argparse
import json
import re
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

import requests

from core import config
from core.corpus_metadata import DocumentRecord
from ingestion.approvals import apply_approved, read_approved
from ingestion.chunking import parse_pages, split_for_phoranker
from ingestion.extract import extract_pages
from ingestion.rubric import read_rubric
from ingestion.sources import acquire

ROOT = Path(__file__).resolve().parents[1]
RUBRIC = ROOT / "data/structured_rules/qd4932_rubric.csv"


def _write_jsonl(path: Path, rows) -> None:
    with TemporaryDirectory(dir=path.parent) as folder:
        temp = Path(folder) / path.name
        with temp.open("w", encoding="utf-8", newline="\n") as stream:
            for row in rows:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        temp.replace(path)


def _build_chunks(doc, source, pages, approved):
    chunks, tables = parse_pages(doc, source, pages)
    reviewed, rules = read_rubric(RUBRIC, doc, source)
    if config.CHUNKING_MODE == "phoranker":
        if config.RERANK_BACKEND != "phoranker":
            raise ValueError("CHUNKING_MODE=phoranker requires RERANK_BACKEND=phoranker")
        from core.pho_text import format_passage, segment, tokenizer

        pho_tokenizer = tokenizer(config.RERANK_MODEL)

        def count_passage(section, text):
            passage = segment(format_passage(doc.document_number, section, text))
            return len(pho_tokenizer.encode(passage, add_special_tokens=False, verbose=False))

        chunks = split_for_phoranker(doc, source, apply_approved(chunks, approved), count_passage)
    elif config.CHUNKING_MODE != "legacy":
        raise ValueError(f"Unknown CHUNKING_MODE: {config.CHUNKING_MODE}")
    return apply_approved(chunks + reviewed, approved), tables + rules


def _prepare(doc, source, path, output, approved=frozenset()):
    pages = extract_pages(path, source)
    chunks, tables = _build_chunks(doc, source, pages, approved)
    prefix = output / f"{doc.document_id}-{source.sha256}"
    _write_jsonl(
        prefix.with_suffix(".pages.jsonl"),
        ({"page": index, "text": text} for index, text in enumerate(pages, 1)),
    )
    _write_jsonl(prefix.with_suffix(".tables.jsonl"), tables)
    _write_jsonl(
        prefix.with_suffix(".chunks.jsonl"),
        (chunk.model_dump(mode="json") for chunk in chunks),
    )
    return chunks


def run(
    manifest: Path,
    raw_dir: Path,
    output: Path,
    selected,
    prepare_only: bool,
    approved=frozenset(),
) -> int:
    from pydantic import TypeAdapter

    docs = TypeAdapter(list[DocumentRecord]).validate_json(manifest.read_bytes())
    ids = [doc.document_id for doc in docs]
    if len(set(ids)) != len(ids) or any(
        not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", name) for name in ids
    ):
        raise ValueError(
            "Manifest must use unique document IDs containing lowercase letters, numbers, underscores or hyphens"
        )
    eligible = {doc.document_id for doc in docs if doc.status != "archived"}
    if invalid := set(selected) - eligible:
        raise ValueError(
            f"Unknown or archived document IDs: {', '.join(sorted(invalid))}"
        )
    jobs = [
        (doc, source)
        for doc in docs
        if doc.document_id in (selected or eligible)
        for source in ([doc.ingestion_source] if doc.ingestion_source else doc.files)
        if source.source_kind != "summary"
    ]
    if not jobs:
        raise ValueError("No primary files selected")
    sources, errors = [], []
    for doc, source in jobs:
        try:
            sources.append((doc, source, acquire(doc, source, raw_dir)))
        except (OSError, ValueError, requests.RequestException) as exc:
            errors.append(f"{doc.document_id} ({source.file_name}): {exc}")
    if errors:
        raise ValueError(
            "Could not acquire all selected sources:\n" + "\n".join(errors)
        )

    output.mkdir(parents=True, exist_ok=True)
    prepared = []
    for doc, source, path in sources:
        try:
            chunks = _prepare(doc, source, path, output, approved)
        except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
            raise ValueError(f"{doc.document_id} ({source.file_name}): {exc}") from exc
        prepared.append((doc, source, chunks))
        print(f"{doc.document_id}: prepared {len(chunks)} chunks", flush=True)
    if prepare_only:
        return 0

    from qdrant_client import QdrantClient

    from core.embedding import get_model
    from ingestion.index import encode, upsert

    model = get_model()
    points = [
        point
        for doc, source, chunks in prepared
        for point in encode(model, doc, source, chunks)
    ]
    client = QdrantClient(url=config.QDRANT_URL, timeout=60)
    try:
        upsert(client, config.COLLECTION, points)
    finally:
        client.close()
    return len(points)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path, default=ROOT / "docs/corpus/documents.json"
    )
    parser.add_argument("--raw-dir", type=Path, default=ROOT / "data/raw")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/processed")
    parser.add_argument(
        "--document",
        action="append",
        default=[],
        metavar="ID",
        help="Process only this registered document (repeatable)",
    )
    parser.add_argument(
        "--approved",
        type=Path,
        default=config.APPROVED_PATH,
        help="Sổ duyệt đoạn (CSV): đoạn có trong sổ được ghi là checked thay vì pending",
    )
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="Write page, table and chunk JSONL without indexing",
    )
    args = parser.parse_args()
    try:
        indexed = run(
            args.manifest,
            args.raw_dir,
            args.output_dir,
            args.document,
            args.prepare_only,
            read_approved(args.approved),
        )
    except (OSError, ValueError, ImportError) as exc:
        parser.exit(1, f"Ingestion failed: {exc}\n")
    if indexed:
        print(f"Upserted {indexed} points into {config.COLLECTION}")


if __name__ == "__main__":
    main()
