from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend import main
from backend.services import citation_validator, generator
from core.corpus_evidence import to_evidence
from core.corpus_metadata import ChunkRecord
from scripts.register_corpus import ROOT, read_jsonl, verify
from scripts.review_sources import samples


def test_all_sample_chunks_map_to_tv4_schema():
    docs, _, _ = verify(ROOT)
    docs = {d.document_id: d for d in docs}
    for index, row in enumerate(
        read_jsonl(ROOT / "tests/fixtures/corpus_chunks.jsonl"), 1
    ):
        chunk = ChunkRecord.model_validate(row)
        evidence = to_evidence(docs[chunk.document_id], chunk, index)
        assert evidence.source_id == f"S{index}"
        assert evidence.text == row["content"]
        assert (evidence.page_start, evidence.page_end) == (
            row["page_start"],
            row["page_end"],
        )
        assert evidence.doc_number == docs[chunk.document_id].document_number


def test_pending_chunk_cannot_be_cited():
    docs, _, _ = verify(ROOT)
    chunk = ChunkRecord.model_validate(
        read_jsonl(ROOT / "tests/fixtures/corpus_chunks.jsonl")[0]
    )
    with pytest.raises(ValueError):
        to_evidence(
            next(d for d in docs if d.document_id == chunk.document_id),
            chunk.model_copy(update={"review_status": "pending"}),
            1,
        )


def test_review_flags_unknown_citation_and_number():
    case, ev, _ = list(samples())[1]
    clean, cites, flags = citation_validator.validate(
        "Được 99 điểm [S1] [S9].", ev, case["question"]
    )
    assert "[S9]" not in clean
    assert [c.source_id for c in cites] == ["S1"]
    assert set(flags) == {"invalid_citation_removed", "unsupported_number"}


def test_chat_endpoint_with_real_source_and_controlled_draft(monkeypatch):
    case, ev, answer = list(samples())[1]
    monkeypatch.setattr(
        main.retrieval,
        "retrieve",
        lambda q: SimpleNamespace(
            evidence=ev, top_score=1.0, routed=SimpleNamespace(term_key=None)
        ),
    )

    def reply(question, evidence_text):
        assert question == case["question"]
        assert ev[0].text in evidence_text
        return generator.AnswerDraft(answer)

    monkeypatch.setattr(generator, "generate_answer", reply)
    monkeypatch.setattr(main, "_log", lambda **fields: None)
    response = TestClient(main.app).post("/chat", json={"question": case["question"]})
    assert response.status_code == 200
    result = response.json()
    assert result["answer"] == answer and not result["abstain"]
    assert result["risk_flag"] is None
    (cite,) = result["citations"]
    assert cite["source_id"] == "S1" and "4932/QĐ-ĐHCT" in cite["document"]
    assert (cite["section"], cite["page"], cite["url"]) == (
        "Phụ lục V.b",
        10,
        ev[0].source_url,
    )
