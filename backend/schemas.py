'''Hợp đồng dữ liệu giữa backend và giao diện (runbook §3.4). Không đổi tên trường khi chưa thống nhất cả nhóm.'''
from typing import Literal

from pydantic import BaseModel, Field


class ChatTurn(BaseModel):
    role: Literal['user', 'assistant']
    content: str = Field(min_length=1, max_length=2000)
    need_clarification: bool = False


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=6)


class EvidenceChunk(BaseModel):
    source_id: str  # 'S1', 'S2', ...
    chunk_id: str
    document_id: str
    doc_title: str
    doc_number: str | None = None
    article: str | None = None
    section: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    source_url: str | None = None
    text: str
    score: float = 0.0


class Citation(BaseModel):
    source_id: str
    document: str
    section: str | None = None
    page: int | None = None
    url: str | None = None


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation] = []
    need_clarification: bool = False
    abstain: bool = False
    risk_flag: str | None = None
