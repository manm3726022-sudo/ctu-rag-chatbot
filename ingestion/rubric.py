"""Retain the reviewed QĐ 4932 scoring table and its cross-page locators."""

import csv
from pathlib import Path

from ingestion.chunking import Unit, make_chunk


def read_rubric(path: Path, doc, source):
    if doc.document_id != "qd4932":
        return [], []
    chunks, rules = [], []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            if (row["document_id"], row["sha256"]) != (doc.document_id, source.sha256):
                continue
            for field in (
                "points",
                "criterion_cap",
                "group_cap",
                "page_start",
                "page_end",
            ):
                row[field] = int(row[field])
            first, last = row["page_start"], row["page_end"]
            if not 1 <= first <= last <= source.pages:
                raise ValueError(f"Rubric position out of range: {row['item']}")
            section = f"Phụ lục {row['item']}"
            content = (
                f"{row['criterion']}. {row['rule']}: {row['points']} điểm. "
                f"Trần tiêu chí: {row['criterion_cap']} điểm. "
                f"Trần nhóm {row['group']}: {row['group_cap']} điểm. "
                f"{row['condition_or_evidence']}"
            ).strip()
            chunks.append(
                make_chunk(
                    doc,
                    source,
                    Unit(section, first, last, content),
                    review_status="checked",
                )
            )
            rules.append({**row, "section": section, "review_status": "checked"})
    return chunks, rules
