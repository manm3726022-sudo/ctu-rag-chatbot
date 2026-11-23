"""Persistent, human-edited chunk text overrides."""

import json
import os
import tempfile
from pathlib import Path

from ingestion.chunking import update_chunk_content


def read_overrides(path) -> dict:
    target = Path(path)
    if not target.exists():
        return {}
    with target.open(encoding="utf-8") as stream:
        value = json.load(stream)
    if not isinstance(value, dict):
        raise TypeError(f"Chunk override file must contain an object: {target}")
    return value


def apply_overrides(chunks, overrides) -> list:
    updated = []
    for chunk in chunks:
        override = overrides.get(str(chunk.chunk_id))
        if override is None:
            updated.append(chunk)
            continue
        edited = update_chunk_content(chunk, override["content"])
        if override.get("review_status") == "checked":
            edited = edited.model_copy(update={"review_status": "checked"})
        updated.append(edited)
    return updated


def write_overrides(path, overrides) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target.parent,
            prefix=f".{target.name}.",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            json.dump(overrides, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temporary, target)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
