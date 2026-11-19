"""Schema metadata cho kho văn bản CTU, phiên bản 1."""

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

Text = Annotated[str, Field(min_length=1)]
Hash = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Term = Annotated[str, Field(pattern=r"^[0-9]{4}-HK[123]$")]


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class FileRecord(Record):
    file_name: Text
    sha256: Hash
    source_kind: Literal[
        "pdf_text", "pdf_scan", "docx_text", "docx_scan", "html", "txt", "summary"
    ]
    pages: Annotated[int, Field(ge=1)] | None
    origin: Text


class Relation(Record):
    kind: Literal["replaces", "cites", "implements", "amends"]
    target_number: Text
    evidence: Text


class DocumentRecord(Record):
    document_id: Text
    document_number: Text
    title: Text
    issuer: Text
    issued_on: date
    effective_date: date | None
    effective_from_term: Term | None
    effective_until_term_exclusive: Term | None = None
    applicability: Text
    source_url: str | None
    relations: list[Relation]
    files: list[FileRecord] = Field(min_length=1)
    status: Literal["registered", "indexed", "archived"] = "registered"
    ingestion_source: FileRecord | None = Field(
        default=None, exclude_if=lambda source: source is None
    )


class Locator(Record):
    document_id: Text
    sha256: Hash
    section: Text
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)

    @model_validator(mode="after")
    def ordered_pages(self):
        if self.page_end < self.page_start:
            raise ValueError("Trang cuối phải lớn hơn hoặc bằng trang đầu")
        return self


class ChunkRecord(Locator):
    chunk_id: UUID
    content: Text
    review_status: Literal["checked", "pending"]
    applies_from_cohort: int | None = None
    applies_to_cohort: int | None = None
