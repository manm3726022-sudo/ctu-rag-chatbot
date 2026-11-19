"""Extract ordered page, image, or logical-page content."""

import subprocess
from pathlib import Path

from core.corpus_metadata import FileRecord


def _ocr(image: bytes) -> str:
    try:
        result = subprocess.run(
            ["tesseract", "stdin", "stdout", "-l", "vie+eng"],
            input=image,
            capture_output=True,
            check=True,
            timeout=180,
        )
    except FileNotFoundError as exc:
        raise ValueError(
            "Install Tesseract with vie and eng language data and add it to PATH"
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise ValueError(
            f"Tesseract failed: {exc.stderr.decode('utf-8', errors='replace').strip()}"
        ) from exc
    return result.stdout.decode("utf-8")


def _pdf(path: Path, force_ocr: bool) -> list[str]:
    from io import BytesIO

    from pypdf import PdfReader

    with path.open("rb") as stream:
        reader = PdfReader(stream)
        pages = [
            "" if force_ocr else page.extract_text(extraction_mode="layout")
            for page in reader.pages
        ]
    if all(page.strip() for page in pages):
        return pages

    from pypdfium2 import PdfDocument

    with PdfDocument(path) as pdf:
        for index, text in enumerate(pages):
            if text.strip():
                continue
            page = pdf[index]
            try:
                bitmap = page.render(scale=300 / 72)
                try:
                    with BytesIO() as png:
                        bitmap.to_pil().save(png, "PNG")
                        pages[index] = _ocr(png.getvalue())
                finally:
                    bitmap.close()
            finally:
                page.close()
    return pages


def _docx(path: Path, scan: bool) -> list[str]:
    from docx import Document
    from docx.oxml.ns import qn
    from docx.text.paragraph import Paragraph

    doc = Document(path)
    if scan:
        embedded = {
            qn("a:blip"): qn("r:embed"),
            "{urn:schemas-microsoft-com:vml}imagedata": qn("r:id"),
        }
        pages = []
        for node in doc.element.body.iter(*embedded):
            image = node.get(embedded[node.tag])
            if image not in doc.part.related_parts:
                raise ValueError("Scanned DOCX contains an image that is not embedded")
            pages.append(_ocr(doc.part.related_parts[image].blob))
        return pages

    pages = [""]
    for block in doc.iter_inner_content():
        if isinstance(block, Paragraph):
            if block.paragraph_format.page_break_before and pages[-1]:
                pages.append("")
            text = []
            for node in block._p.iter(qn("w:t"), qn("w:tab"), qn("w:br"), qn("w:cr")):
                if node.tag == qn("w:t"):
                    text.append(node.text or "")
                elif node.get(qn("w:type")) == "page":
                    pages[-1] += "".join(text)
                    pages.append("")
                    text.clear()
                else:
                    text.append(" " if node.tag == qn("w:tab") else "\n")
            pages[-1] += "".join(text) + "\n\n"
        else:
            pages[-1] += (
                "\n".join(
                    " | ".join(" ".join(cell.text.split()) for cell in row.cells)
                    for row in block.rows
                )
                + "\n\n"
            )
    # shortcut: Word's automatic pagination requires a renderer; use explicit page breaks or scanned images for page citations.
    return pages


def _html(path: Path) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(path.read_bytes(), "html.parser")
    for node in soup.select("script, style, nav, footer, noscript, template, [hidden]"):
        node.decompose()
    root = soup.find("main") or soup.find("article") or soup.body or soup
    lines = []
    blocks = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "pre", "tr"}
    for node in root.find_all(blocks):
        if any(parent.name in blocks for parent in node.parents):
            continue
        if node.name == "tr":
            cells = node.find_all(["td", "th"], recursive=False)
            lines.append(" | ".join(cell.get_text(" ", strip=True) for cell in cells))
        else:
            lines.append(node.get_text(" ", strip=True))
    return "\n\n".join(lines) or root.get_text("\n", strip=True)


def extract_pages(path: Path, source: FileRecord) -> list[str]:
    kind = source.source_kind
    if kind in {"pdf_text", "pdf_scan"}:
        pages = _pdf(path, force_ocr=kind == "pdf_scan")
    elif kind in {"docx_text", "docx_scan"}:
        pages = _docx(path, scan=kind == "docx_scan")
    elif kind == "html":
        pages = [_html(path)]
    elif kind == "txt":
        pages = path.read_text(encoding="utf-8-sig").split("\f")
    else:
        raise ValueError(f"Unsupported primary source type: {kind}")
    if source.pages is not None and len(pages) != source.pages:
        raise ValueError(
            f"Expected {source.pages} pages/images, extracted {len(pages)}"
        )
    if not any(page.strip() for page in pages):
        raise ValueError("No text was extracted")
    return pages
