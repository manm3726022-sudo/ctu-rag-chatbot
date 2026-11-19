"""Đối chiếu hai câu mẫu qua bộ kiểm tra trích dẫn TV4, chạy ngoại tuyến."""

from backend.services.citation_validator import validate
from core.corpus_evidence import to_evidence
from core.corpus_metadata import ChunkRecord
from scripts.register_corpus import ROOT, read_jsonl, verify


def samples():
    documents, _, _ = verify(ROOT)
    docs = {d.document_id: d for d in documents}
    chunks = [
        ChunkRecord.model_validate(x)
        for x in read_jsonl(ROOT / "tests/fixtures/corpus_chunks.jsonl")
    ]
    cases = {r["case_id"]: r for r in read_jsonl(ROOT / "eval/gold_corpus.jsonl")}
    for case_id, answer in [
        ("CTU-009", "Tối đa 20 tín chỉ trong một học kỳ [S1]."),
        ("CTU-056", "Năm đợt đủ điều kiện được tính tối đa 12 điểm ở V.b [S1]."),
    ]:
        case = cases[case_id]
        evidence = []
        for position, loc in enumerate(case["sources"], start=1):
            chunk = next(
                c for c in chunks if all(getattr(c, k) == v for k, v in loc.items())
            )
            evidence.append(to_evidence(docs[chunk.document_id], chunk, position))
        yield case, evidence, answer


def main():
    for case, evidence, answer in samples():
        clean, citations, flags = validate(answer, evidence, case["question"])
        print(case["case_id"], case["question"])
        print("Phản hồi mẫu:", clean)
        for cite in citations:
            print(
                cite.source_id,
                cite.document,
                cite.section,
                "trang/ảnh",
                cite.page,
                cite.url,
            )
        print("Cờ kiểm tra:", flags)
        if flags or len(citations) != len(evidence):
            raise SystemExit("Cần kiểm tra lại ánh xạ bằng chứng")


if __name__ == "__main__":
    main()
