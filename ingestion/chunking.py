"""Normalize CTU policy text, retain its hierarchy and build source-located chunks."""

import json
import re
import unicodedata
from dataclasses import dataclass
from itertools import groupby
from uuid import NAMESPACE_URL, uuid5

from core.corpus_metadata import ChunkRecord, DocumentRecord, FileRecord
from core.tokens import count_tokens

PART = re.compile(
    r"^(Quyết định|Quy định|Quy chế|Phụ lục|Thông tư|Hướng dẫn)(?=\s|[:.]|$)",
    re.IGNORECASE,
)
HEADING = re.compile(
    r"^(Chương|Mục|Điều)\s+([IVXLCDM]+|\d+[a-z]?)(?=$|[\s.:])", re.IGNORECASE
)
LIST_ITEM = re.compile(r"^(?:\d+[.)]|[a-zđ][)])\s+", re.IGNORECASE)
APPENDIX_ITEM = re.compile(
    r"^(?P<item>[IVXLCDM]+(?:\.[a-z])?)[.)](?:\s+|$)", re.IGNORECASE
)
GUIDANCE_SECTION = re.compile(r"^([IVXLCDM]+)\.\s+")
GUIDANCE_SUBSECTION = re.compile(r"^(\d+\.(?:\d+(?:\.\d+)*)?)\s+\D")
TOKEN_LIMIT = 480
CLAUSE_START = re.compile(r"^\d+[.)]\s+")
SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?;])\s+")


@dataclass
class Unit:
    section: str
    page_start: int
    page_end: int
    text: str
    cells: tuple[str, ...] = ()


def _units(pages: list[str], doc: DocumentRecord, source: FileRecord) -> list[Unit]:
    prefix = doc.document_number.split("/", 1)[-1]
    part = "Văn bản"
    if prefix.startswith("QĐ"):
        part = "Quyết định"
    elif "TT-" in prefix:
        part = "Thông tư"
    elif prefix.startswith("HD"):
        part = "Hướng dẫn"
    headings = []
    units = []
    new_paragraph = True
    for page_number, raw in enumerate(pages, 1):
        text = unicodedata.normalize("NFC", raw).translate(
            {0xAD: None, 0x200B: None, 0xFEFF: None}
        )
        lines = text.strip().splitlines()
        page_labels = {str(page_number)}
        if part == "Hướng dẫn":
            page_labels.add(f"{page_number}/{len(pages)}")
        if len(lines) > 1 and lines[0].strip() in page_labels:
            lines.pop(0)
        if len(lines) > 1 and lines[-1].strip() in page_labels:
            lines.pop()
        for line in lines:
            clean = " ".join(line.split())
            if not clean:
                new_paragraph = True
                continue
            heading = HEADING.match(clean)
            match_part = PART.match(clean)
            if match_part and not clean.isupper():
                remainder = clean[match_part.end() :].lstrip()
                if remainder and not remainder.startswith((":", ".")):
                    match_part = None
            if match_part:
                part = match_part[1].capitalize()
                headings.clear()
            elif heading:
                rank = ("chương", "mục", "điều").index(heading[1].lower())
                headings = [(level, label) for level, label in headings if level < rank]
                headings.append((rank, f"{heading[1].capitalize()} {heading[2]}"))
            elif part == "Phụ lục" and (item := APPENDIX_ITEM.match(clean)):
                headings = [(0, item["item"])]
                heading = item
            elif part == "Hướng dẫn":
                if heading := GUIDANCE_SECTION.match(clean):
                    headings = [(0, f"Mục {heading[1]}")]
                elif headings and (heading := GUIDANCE_SUBSECTION.match(clean)):
                    headings = [headings[0], (1, heading[1].rstrip("."))]

            cells = tuple(re.split(r"\s*\|\s*", line.strip()))
            if (
                len(cells) == 1
                and source.source_kind == "pdf_text"
                and part == "Phụ lục"
            ):
                # shortcut: wide PDF column gaps are candidates; use the checked rubric for exact rows and caps.
                columns = tuple(re.split(r"\s{4,}", line.strip()))
                if len(columns) >= 3:
                    cells = columns
            section = " > ".join([part, *(label for _, label in headings)])
            if len(cells) > 1:
                units.append(
                    Unit(section, page_number, page_number, " | ".join(cells), cells)
                )
                new_paragraph = True
            elif (
                new_paragraph
                or heading
                or match_part
                or LIST_ITEM.match(clean)
                or not units
            ):
                units.append(Unit(section, page_number, page_number, clean))
                new_paragraph = False
            else:
                units[-1].text += " " + clean
                units[-1].page_end = page_number
    return units


def make_chunk(
    doc: DocumentRecord, source: FileRecord, unit: Unit, review_status="pending"
) -> ChunkRecord:
    chunk_id = chunk_id_for(
        doc.document_id,
        source.sha256,
        unit.section,
        unit.page_start,
        unit.page_end,
        unit.text,
    )
    return ChunkRecord(
        document_id=doc.document_id,
        sha256=source.sha256,
        section=unit.section,
        page_start=unit.page_start,
        page_end=unit.page_end,
        chunk_id=chunk_id,
        content=unit.text,
        review_status=review_status,
    )


def chunk_id_for(document_id, sha256, section, page_start, page_end, content):
    identity = json.dumps(
        [document_id, sha256, section, page_start, page_end, content]
    )
    return uuid5(NAMESPACE_URL, identity)


def update_chunk_content(chunk: ChunkRecord, content: str) -> ChunkRecord:
    content = content.strip()
    if not content:
        raise ValueError("Chunk content cannot be empty")
    return chunk.model_copy(
        update={
            "content": content,
            "chunk_id": chunk_id_for(
                chunk.document_id,
                chunk.sha256,
                chunk.section,
                chunk.page_start,
                chunk.page_end,
                content,
            ),
        }
    )


def _pieces(text: str):
    if len(text) <= 1 or count_tokens(text) <= TOKEN_LIMIT:
        yield text
        return
    midpoint = len(text) // 2
    cut = (
        text.rfind(" ", 0, midpoint)
        if " " in text[:midpoint]
        else text.find(" ", midpoint)
    )
    if cut < 1:
        cut = midpoint
    yield from _pieces(text[:cut].rstrip())
    yield from _pieces(text[cut:].lstrip())


def _clause_spans(text):
    """Keep numbered clauses and their lettered points together when possible."""
    start = 0
    offset = 0
    for line in text.splitlines(keepends=True):
        if offset and CLAUSE_START.match(line) and not (
            start == 0 and text[:offset].count("\n") == 1 and HEADING.match(text)
        ):
            yield text[start:offset]
            start = offset
        offset += len(line)
    yield text[start:]


def _split_to_fit(text, fits):
    if fits(text):
        yield text
        return

    midpoint = len(text) // 2
    for boundary in (r"\n", SENTENCE_BOUNDARY, r"\s+"):
        splits = [match.start() for match in re.finditer(boundary, text)
                  if 0 < match.start() < len(text) - 1]
        if splits:
            cut = min(splits, key=lambda pos: abs(midpoint - pos))
            break
    else:
        if len(text) <= 1:
            raise ValueError("Passage budget is too small for this section")
        cut = midpoint

    yield from _split_to_fit(text[:cut].rstrip(), fits)
    yield from _split_to_fit(text[cut:].lstrip(), fits)


def _pack_clauses(text, fits):
    current = ""
    for span in _clause_spans(text):
        for part in _split_to_fit(span.strip(), fits):
            combined = f"{current}\n{part}" if current else part
            if current and not fits(combined):
                yield current
                current = part
            else:
                current = combined
    if current:
        yield current


def split_for_phoranker(doc, source, chunks, count_passage):
    """Split oversized chunks into verbatim spans with the parent's source range."""
    from core.pho_text import PASSAGE_LIMIT

    result = {}
    for chunk in chunks:
        def fits(text, section=chunk.section):
            return count_passage(section, text) <= PASSAGE_LIMIT

        if fits(chunk.content):
            if chunk.chunk_id not in result or chunk.review_status == "checked":
                result[chunk.chunk_id] = chunk
            continue

        for text in _pack_clauses(chunk.content, fits):
            unit = Unit(chunk.section, chunk.page_start, chunk.page_end, text)
            child = make_chunk(doc, source, unit, chunk.review_status)
            child = child.model_copy(update={
                "applies_from_cohort": chunk.applies_from_cohort,
                "applies_to_cohort": chunk.applies_to_cohort,
            })
            if child.chunk_id not in result or child.review_status == "checked":
                result[child.chunk_id] = child
    return list(result.values())


def parse_pages(
    doc: DocumentRecord, source: FileRecord, pages: list[str]
) -> tuple[list[ChunkRecord], list[dict]]:
    chunks = {}
    tables = []
    for section, units in groupby(
        _units(pages, doc, source), key=lambda unit: unit.section
    ):
        current = None
        for unit in units:
            if unit.cells:
                tables.append(
                    {
                        "document_id": doc.document_id,
                        "sha256": source.sha256,
                        "section": section,
                        "page_start": unit.page_start,
                        "page_end": unit.page_end,
                        "cells": list(unit.cells),
                        "review_status": "pending",
                    }
                )
            for part in _pieces(unit.text):
                combined = f"{current.text}\n{part}" if current else part
                if current and count_tokens(combined) > TOKEN_LIMIT:
                    chunk = make_chunk(doc, source, current)
                    chunks[chunk.chunk_id] = chunk
                    current = None
                if current:
                    current.text = combined
                    current.page_end = unit.page_end
                else:
                    current = Unit(section, unit.page_start, unit.page_end, part)
        if current:
            chunk = make_chunk(doc, source, current)
            chunks[chunk.chunk_id] = chunk
    return list(chunks.values()), tables
