"""Unit tests for the citation verification gate.

Network-dependent paths (Crossref, NCBI eutils) are stubbed via
monkeypatching so tests run offline and deterministically.

What's tested:
- Citation block regex catches the formats the prompt enforces (and
  variants the model emits in practice — bracket vs no-bracket on PMID)
- title_overlap stopword-aware Jaccard
- classify() maps registry responses to the right enum values
- mutation logic inserts inline warnings without shifting line numbers
- report builder produces a parseable Citation Verification section
- main() exit codes: 0 (clean), 2 (fabrication found), 3 (file missing)
- empty review (no citations) → exit 0, no mutation
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


# Load verify_citations.py as a module by file path so we can monkeypatch
# its functions directly. The script is also exposed as a CLI but unit
# tests want fine-grained access to verify_doi/verify_pmid stubs.
SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "beril_adversarial"
    / "skill"
    / "tools"
    / "verify_citations.py"
)


@pytest.fixture(scope="module")
def vc():
    spec = importlib.util.spec_from_file_location("verify_citations", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["verify_citations"] = mod
    spec.loader.exec_module(mod)
    return mod


# --- Parsing ---


def test_parses_canonical_citation_block(vc, tmp_path):
    review = tmp_path / "review.md"
    review.write_text(
        '# Adversarial Review\n\n'
        '**Schavemaker, P., Lynch, M. (2022). "Flagellar energy costs '
        'across the tree of life." eLife 11:e77266.** '
        'doi:10.7554/eLife.77266 [PMID:35471186, PMCID:PMC9090332]\n'
    )
    entries, _ = vc.parse_review(review)
    assert len(entries) == 1
    e = entries[0]
    assert e["doi"] == "10.7554/eLife.77266"
    assert e["pmid"] == "35471186"
    assert "Flagellar energy costs" in e["title"]


def test_parses_pmid_without_brackets(vc, tmp_path):
    """The model's actual output sometimes drops the brackets around IDs."""
    review = tmp_path / "review.md"
    review.write_text(
        '**Green, S.J. et al. (2012). "Title." AEM 78(4):1039-47.** '
        'doi:10.1128/AEM.06435-11 PMID:22179242\n'
    )
    entries, _ = vc.parse_review(review)
    assert len(entries) == 1
    assert entries[0]["pmid"] == "22179242"
    assert entries[0]["doi"] == "10.1128/AEM.06435-11"


def test_skips_non_citation_lines(vc, tmp_path):
    review = tmp_path / "review.md"
    review.write_text(
        "## Statistical Rigor\n\n"
        "Some prose without a citation block.\n"
        "**Bold but no DOI here, just emphasis.**\n"
        "**Author 2024.** No identifier.\n"
    )
    entries, _ = vc.parse_review(review)
    assert entries == []


def test_parses_multiple_citations(vc, tmp_path):
    review = tmp_path / "review.md"
    review.write_text(
        '**A. (2022). "T1." V1.** doi:10.1/a [PMID:1]\n'
        'prose between\n'
        '**B. (2023). "T2." V2.** doi:10.2/b [PMID:2]\n'
    )
    entries, _ = vc.parse_review(review)
    assert len(entries) == 2
    assert entries[0]["doi"] == "10.1/a"
    assert entries[1]["doi"] == "10.2/b"


# --- title_overlap ---


def test_title_overlap_identical(vc):
    assert vc.title_overlap("A B C", "A B C") == 1.0


def test_title_overlap_disjoint(vc):
    # Stopwords filtered out, so "the" and "of" don't count.
    assert vc.title_overlap("alpha beta", "gamma delta") == 0.0


def test_title_overlap_partial(vc):
    # 3 shared content words ("flagellar", "energy", "costs") in claim;
    # 2 shared with actual after stopword filter — partial overlap.
    ov = vc.title_overlap(
        "Flagellar energy costs in bacteria",
        "Flagellar energy costs across the tree of life",
    )
    # Expect substantial but not perfect overlap.
    assert 0.4 < ov < 1.0


def test_title_overlap_handles_none(vc):
    assert vc.title_overlap(None, "x") == 0.0
    assert vc.title_overlap("x", None) == 0.0


def test_title_overlap_below_threshold_for_mismatch(vc):
    # Two papers with completely different topics — should be well under
    # the 0.40 threshold.
    ov = vc.title_overlap(
        "Flagellar energy costs in bacteria",
        "Quantum chromodynamics on the lattice",
    )
    assert ov < 0.4


# --- classify (with stubbed network) ---


def _patch_network(vc, monkeypatch, doi_response=None, pmid_response=None):
    """Patch verify_doi and verify_pmid to return canned responses.

    Each *_response is a (status, title) tuple, e.g. ("found", "real title")
    or ("not_found", None) or ("network_error", None).
    """
    if doi_response is not None:
        monkeypatch.setattr(vc, "verify_doi", lambda d, ua, t: doi_response)
    if pmid_response is not None:
        monkeypatch.setattr(vc, "verify_pmid", lambda p, ua, t: pmid_response)
    # Skip the rate limit sleeps in tests.
    monkeypatch.setattr(vc.time, "sleep", lambda _: None)


def test_classify_verified_doi(vc, monkeypatch):
    _patch_network(vc, monkeypatch, doi_response=("found", "Flagellar energy costs"))
    e = {"doi": "10.7554/eLife.77266", "pmid": None, "title": "Flagellar energy costs"}
    status, _ = vc.classify(e, "ua", 5.0, 0.0)
    assert status == vc.S_VERIFIED


def test_classify_fabricated_doi(vc, monkeypatch):
    _patch_network(vc, monkeypatch, doi_response=("not_found", None))
    e = {"doi": "10.9999/fake", "pmid": None, "title": "X"}
    status, reason = vc.classify(e, "ua", 5.0, 0.0)
    assert status == vc.S_FABRICATED
    assert "Crossref" in reason


def test_classify_doi_resolves_to_different_paper(vc, monkeypatch):
    """DOI exists but points to an unrelated paper — common LLM mode."""
    _patch_network(
        vc,
        monkeypatch,
        doi_response=("found", "Quantum chromodynamics on the lattice"),
    )
    e = {
        "doi": "10.1/x",
        "pmid": None,
        "title": "Flagellar energy costs in bacteria",
    }
    status, reason = vc.classify(e, "ua", 5.0, 0.0)
    assert status == vc.S_FABRICATED_MISMATCH
    assert "Quantum chromodynamics" in reason


def test_classify_fabricated_pmid(vc, monkeypatch):
    _patch_network(
        vc,
        monkeypatch,
        doi_response=None,
        pmid_response=("not_found", None),
    )
    e = {"doi": None, "pmid": "99999999", "title": "X"}
    status, _ = vc.classify(e, "ua", 5.0, 0.0)
    assert status == vc.S_FABRICATED


def test_classify_missing_identifier(vc, monkeypatch):
    e = {"doi": None, "pmid": None, "title": "Some title"}
    status, _ = vc.classify(e, "ua", 5.0, 0.0)
    assert status == vc.S_MISSING_IDENTIFIER


def test_classify_doi_network_falls_through_to_pmid(vc, monkeypatch):
    """If Crossref is unreachable but PMID succeeds, classify as VERIFIED."""
    _patch_network(
        vc,
        monkeypatch,
        doi_response=("network_error", None),
        pmid_response=("found", "Flagellar energy"),
    )
    e = {
        "doi": "10.1/x",
        "pmid": "1234",
        "title": "Flagellar energy",
    }
    status, _ = vc.classify(e, "ua", 5.0, 0.0)
    assert status == vc.S_VERIFIED


def test_classify_both_registries_unreachable(vc, monkeypatch):
    _patch_network(
        vc,
        monkeypatch,
        doi_response=("network_error", None),
        pmid_response=("network_error", None),
    )
    e = {"doi": "10.1/x", "pmid": "1234", "title": "X"}
    status, _ = vc.classify(e, "ua", 5.0, 0.0)
    assert status == vc.S_UNVERIFIABLE


# --- Mutation ---


def test_inline_warnings_inserted_above_fabricated(vc):
    lines = [
        "preamble",
        '**Author. (2024). "T." V.** doi:10.1/x [PMID:1]',
        "trailing prose",
    ]
    entries = [
        {
            "line_num": 1,
            "raw_line": lines[1],
            "status": vc.S_FABRICATED,
            "reason": "DOI not found",
        }
    ]
    new_lines = vc.insert_inline_warnings(lines, entries)
    assert len(new_lines) == 4
    assert "CITATION FABRICATED" in new_lines[1]
    # Original citation is still on next line.
    assert new_lines[2] == lines[1]


def test_inline_warnings_skip_verified(vc):
    lines = [
        '**A. (2024). "T." V.** doi:10.1/x [PMID:1]',
    ]
    entries = [
        {
            "line_num": 0,
            "raw_line": lines[0],
            "status": vc.S_VERIFIED,
            "reason": "ok",
        }
    ]
    new_lines = vc.insert_inline_warnings(lines, entries)
    assert new_lines == lines


# --- Report ---


def test_report_section_lists_fabricated_with_line_numbers(vc):
    entries = [
        {
            "line_num": 5,
            "status": vc.S_FABRICATED,
            "reason": "DOI 10.X/Y not found in Crossref",
        },
        {
            "line_num": 12,
            "status": vc.S_VERIFIED,
            "reason": "DOI ok",
        },
    ]
    report = vc.build_report_section(entries)
    text = "\n".join(report)
    assert "## Citation Verification" in text
    assert "Verified: 1" in text
    assert "Fabricated: 1" in text
    # Line number is 1-indexed in the report.
    assert "Line 6:" in text
    assert "DOI 10.X/Y not found" in text


def test_report_inserted_before_run_metadata(vc):
    lines = ["body", "more body", "## Run Metadata", "- elapsed: 1m"]
    report = ["", "## Citation Verification", "report content"]
    out = vc.insert_report_section(lines, report)
    # Report inserted before Run Metadata
    md_idx = out.index("## Run Metadata")
    cv_idx = out.index("## Citation Verification")
    assert cv_idx < md_idx


def test_report_appended_when_no_run_metadata(vc):
    lines = ["body", "more body"]
    report = ["", "## Citation Verification"]
    out = vc.insert_report_section(lines, report)
    assert out[-1] == "## Citation Verification"


# --- End-to-end via main() ---


def test_main_exit_3_on_missing_file(vc, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["verify_citations.py", str(tmp_path / "nope.md")])
    rc = vc.main()
    assert rc == 3


def test_main_exit_0_on_no_citations(vc, tmp_path, monkeypatch, capsys):
    review = tmp_path / "review.md"
    review.write_text("# Review\n\nProse only, no citations.\n")
    monkeypatch.setattr(sys, "argv", ["verify_citations.py", str(review)])
    rc = vc.main()
    assert rc == 0
    # File untouched.
    assert review.read_text() == "# Review\n\nProse only, no citations.\n"


def test_main_exit_2_on_fabrication_and_mutates_file(
    vc, tmp_path, monkeypatch
):
    """End-to-end: fabricated citation triggers exit 2, inline marker, and
    Citation Verification section appended."""
    review = tmp_path / "review.md"
    original = (
        "# Adversarial Review\n\n"
        '**Fake Author. (2099). "Hallucinated title." Made-up Journal '
        '99(99):1-1.** doi:10.9999/fake [PMID:99999999]\n'
    )
    review.write_text(original)

    # Stub network.
    monkeypatch.setattr(
        vc, "verify_doi", lambda d, ua, t: ("not_found", None)
    )
    monkeypatch.setattr(
        vc, "verify_pmid", lambda p, ua, t: ("not_found", None)
    )
    monkeypatch.setattr(vc.time, "sleep", lambda _: None)
    monkeypatch.setattr(sys, "argv", ["verify_citations.py", str(review)])
    rc = vc.main()
    assert rc == 2
    text = review.read_text()
    assert "CITATION FABRICATED" in text
    assert "## Citation Verification" in text
    assert "Fabricated: 1" in text


def test_main_exit_0_with_metadata_out(vc, tmp_path, monkeypatch):
    review = tmp_path / "review.md"
    review.write_text("# Review\n\nNo cites.\n")
    meta = tmp_path / "meta.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["verify_citations.py", str(review), "--metadata-out", str(meta)],
    )
    rc = vc.main()
    assert rc == 0
    data = json.loads(meta.read_text())
    assert data == {
        "total": 0,
        "verified": 0,
        "fabricated": 0,
        "unverifiable": 0,
        "missing_identifier": 0,
    }
