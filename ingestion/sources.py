"""Resolve manifest sources and validate their exact bytes before extraction."""

import hashlib
import ntpath
import tempfile
from pathlib import Path, PureWindowsPath
from urllib.parse import unquote, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup

from core.corpus_metadata import DocumentRecord, FileRecord

EXTENSIONS = {
    "pdf_text": {".pdf"},
    "pdf_scan": {".pdf"},
    "docx_text": {".docx"},
    "docx_scan": {".docx"},
    "html": {".html", ".htm"},
    "txt": {".txt"},
}
MAX_BYTES = 100 * 1024**2
BINARY_OR_TEXT_EXTENSIONS = {".pdf", ".docx", ".txt"}


def _get(url: str) -> requests.Response:
    if urlsplit(url).scheme not in {"http", "https"}:
        raise ValueError("Source download URL must use HTTP or HTTPS")
    response = requests.get(url, stream=True, timeout=(10, 45))
    try:
        response.raise_for_status()
    except requests.RequestException:
        response.close()
        raise
    return response


def _save(response: requests.Response, target: Path, expected_hash: str) -> None:
    digest = hashlib.sha256()
    size = 0
    with tempfile.TemporaryDirectory(dir=target.parent) as folder:
        downloaded = Path(folder) / "download"
        with downloaded.open("wb") as stream:
            for data in response.iter_content(chunk_size=65536):
                size += len(data)
                if size > MAX_BYTES:
                    raise ValueError("Download exceeds 100 MiB")
                digest.update(data)
                stream.write(data)
        if digest.hexdigest() != expected_hash:
            raise ValueError("Downloaded file SHA-256 does not match the manifest")
        downloaded.replace(target)


def _attachment(response: requests.Response, name: str) -> str:
    content = bytearray()
    for data in response.iter_content(chunk_size=65536):
        content.extend(data)
        if len(content) > 2 * 1024**2:
            raise ValueError("Attachment listing exceeds 2 MiB")
    links = BeautifulSoup(bytes(content), "html.parser").find_all("a", href=True)
    urls = {urljoin(response.url, link["href"]) for link in links}
    matches = {
        url
        for url in urls
        if urlsplit(url).scheme in {"http", "https"}
        and Path(unquote(urlsplit(url).path)).name.casefold() == name.casefold()
    }
    if len(matches) != 1:
        raise ValueError(f"Expected one attachment named {name} at the source URL")
    return matches.pop()


def acquire(doc: DocumentRecord, source: FileRecord, raw_dir: Path) -> Path:
    name = PureWindowsPath(source.file_name)
    extensions = EXTENSIONS[source.source_kind]
    reserved = (
        ntpath.isreserved(source.file_name)
        if hasattr(ntpath, "isreserved")
        else name.is_reserved()
    )
    if (
        name.name != source.file_name
        or ":" in source.file_name
        or reserved
        or name.suffix.lower() not in extensions
    ):
        raise ValueError(f"Invalid {source.source_kind} file name: {source.file_name}")
    target = raw_dir / source.file_name
    if target.exists():
        with target.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != source.sha256:
                raise ValueError(f"Local file SHA-256 does not match: {target}")
        return target

    url = doc.source_url
    suffix = Path(unquote(urlsplit(url or "").path)).suffix.lower()
    if not url or suffix in BINARY_OR_TEXT_EXTENSIONS - extensions:
        raise ValueError(f"Place the original from the team handoff at {target}")

    raw_dir.mkdir(parents=True, exist_ok=True)
    with _get(url) as response:
        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
        if source.source_kind != "html" and content_type in {
            "text/html",
            "application/xhtml+xml",
        }:
            url = _attachment(response, source.file_name)
        else:
            _save(response, target, source.sha256)
            return target
    with _get(url) as response:
        _save(response, target, source.sha256)
    return target
