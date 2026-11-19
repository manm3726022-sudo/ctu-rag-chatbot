import sqlite3
from copy import deepcopy

import pytest
from pydantic import ValidationError

from core.corpus_metadata import Locator
from scripts.register_corpus import ROOT, check_locator, read_jsonl, register, verify


@pytest.fixture(scope="module")
def catalog():
    docs, chunks, cases = verify(ROOT)
    assert (len(docs), chunks, cases) == (5, 24, 100)
    return docs


def test_second_import_is_idempotent(catalog):
    with sqlite3.connect(":memory:") as db:
        assert register(db, catalog) == 5
        assert register(db, catalog) == 0
        assert db.execute("SELECT COUNT(*) FROM corpus_current").fetchone() == (5,)


def test_new_version_retains_history(catalog):
    docs = deepcopy(catalog)
    with sqlite3.connect(":memory:") as db:
        register(db, docs)
        docs[0].status = "archived"
        assert register(db, docs) == 1
        assert db.execute(
            "SELECT version FROM corpus_current WHERE document_id='qd3266'"
        ).fetchone() == (2,)
        assert db.execute("SELECT COUNT(*) FROM corpus_versions").fetchone() == (6,)


def test_locators_are_bound_to_a_primary_file(catalog):
    files = {(d.document_id, f.sha256): f for d in catalog for f in d.files}
    loc = Locator.model_validate(
        read_jsonl(ROOT / "eval/gold_corpus.jsonl")[0]["sources"][0]
    )
    check_locator(loc, files)
    with pytest.raises(ValueError):
        check_locator(loc.model_copy(update={"page_end": 1000}), files)
    summary = next(f for f in files.values() if f.source_kind == "summary")
    with pytest.raises(ValueError):
        check_locator(
            loc.model_copy(update={"document_id": "qd5976", "sha256": summary.sha256}),
            files,
        )
    with pytest.raises(ValidationError):
        Locator.model_validate({**loc.model_dump(), "page_end": 1})


def test_all_cross_document_cases_need_multiple_sources():
    cases = read_jsonl(ROOT / "eval/gold_corpus.jsonl")
    for case in cases:
        if case["category"] == "lien_van_ban":
            assert len({ref["document_id"] for ref in case["sources"]}) >= 2


def test_rubric_matches_source_and_keeps_caps(catalog):
    import csv

    file = ROOT / "data/structured_rules/qd4932_rubric.csv"
    with file.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    source = next(d for d in catalog if d.document_id == "qd4932").files[0]
    assert len(rows) == 47
    assert {r["group"]: int(r["group_cap"]) for r in rows} == {
        "I": 20,
        "II": 25,
        "III": 20,
        "IV": 15,
        "V": 20,
    }
    for row in rows:
        assert row["sha256"] == source.sha256
        assert 5 <= int(row["page_start"]) <= int(row["page_end"]) <= source.pages
        assert (
            0 < int(row["points"]) <= int(row["criterion_cap"]) <= int(row["group_cap"])
        )
    event = next(r for r in rows if r["item"] == "V.b")
    assert min(5 * int(event["points"]), int(event["criterion_cap"])) == 12
    assert event["condition_or_evidence"]


def test_registry_rolls_back_incomplete_batch(catalog):
    with sqlite3.connect(":memory:") as db:
        register(db, catalog)
        db.execute("""CREATE TRIGGER reject_second BEFORE INSERT ON corpus_versions
            WHEN NEW.document_id = 'qd4932' BEGIN SELECT RAISE(ABORT, 'test'); END""")
        changed = deepcopy(catalog)
        for doc in changed:
            doc.status = "archived"
        with pytest.raises(sqlite3.IntegrityError):
            register(db, changed)
        assert db.execute("SELECT COUNT(*) FROM corpus_versions").fetchone() == (5,)
