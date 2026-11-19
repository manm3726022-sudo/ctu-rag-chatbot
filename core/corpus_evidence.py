"""Chuyển đoạn nguồn đã duyệt sang hợp đồng bằng chứng của TV4."""

from backend.schemas import EvidenceChunk
from core.corpus_metadata import ChunkRecord, DocumentRecord


def to_evidence(
    doc: DocumentRecord, chunk: ChunkRecord, position: int, score: float = 0.0
) -> EvidenceChunk:
    if doc.document_id != chunk.document_id or doc.status == "archived":
        raise ValueError("Đoạn trích không thuộc văn bản đang dùng")
    if position < 1 or chunk.review_status != "checked":
        raise ValueError("Cần thứ tự từ 1 và đoạn đã đối chiếu")
    source = next((f for f in doc.files if f.sha256 == chunk.sha256), None)
    if (
        source is None
        or source.source_kind == "summary"
        or source.pages is None
        or chunk.page_end > source.pages
    ):
        raise ValueError("Chưa xác minh được tệp nguồn và trang")
    return EvidenceChunk(
        source_id=f"S{position}",
        chunk_id=str(chunk.chunk_id),
        document_id=doc.document_id,
        doc_title=doc.title,
        doc_number=doc.document_number,
        section=chunk.section,
        page_start=chunk.page_start,
        page_end=chunk.page_end,
        source_url=doc.source_url,
        text=chunk.content,
        score=score,
    )
