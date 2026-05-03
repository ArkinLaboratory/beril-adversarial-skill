"""Unit tests for tools/validate_presentation_review.py.

Replicates paper-writer's post-checker test pattern. Tests cover:
  - Pass case (a minimal valid review)
  - Schema literal mismatch
  - Missing required field on a finding
  - Summary count mismatch
  - Duplicate finding IDs
  - Advisory: zero P0s on a large deck
  - Advisory: missing narrative_weakness
  - Hard error: narrative_weakness with non-info severity
  - Hard error: extra info severity on a non-narrative_weakness finding
  - JSON file unparseable (returns exit 1)
  - File not found (exit 3)
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest


SKILL_DIR_SRC = (
    Path(__file__).parent.parent.parent
    / "src"
    / "beril_adversarial"
    / "skill"
)
VALIDATOR_PATH = SKILL_DIR_SRC / "tools" / "validate_presentation_review.py"


# Load the validator module by file path so we can call validate()
# directly without subprocess overhead in most tests.
def _load_validator_module():
    spec = importlib.util.spec_from_file_location(
        "_validate_presentation_review", VALIDATOR_PATH
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_validate_presentation_review"] = mod
    spec.loader.exec_module(mod)
    return mod


validator = _load_validator_module()


def _make_finding(
    fid="F001",
    cls="claim_evidence",
    severity="P1",
    confidence="high",
    slide_id=9,
    slide_position=9,
    slide_layout="data_figure",
    title_quote="Some claim",
    issue="some issue",
    fix_target="slide_compose.v1.md",
    fix_hint="some fix",
    **extra,
):
    """Build a minimum-valid slide-level finding dict."""
    f = {
        "id": fid,
        "class": cls,
        "severity": severity,
        "confidence": confidence,
        "slide_id": slide_id,
        "slide_position": slide_position,
        "slide_layout": slide_layout,
        "title_quote": title_quote,
        "issue": issue,
        "fix_target": fix_target,
        "fix_hint": fix_hint,
    }
    f.update(extra)
    return f


def _make_deck_finding(
    fid="DL001",
    cls="missing_slide",
    severity="P1",
    confidence="high",
    issue="missing X",
    fix_target="slide_compose.v1.md",
    fix_hint="add slide",
    **extra,
):
    """Build a minimum-valid deck-level finding dict (no slide_*)."""
    f = {
        "id": fid,
        "class": cls,
        "severity": severity,
        "confidence": confidence,
        "issue": issue,
        "fix_target": fix_target,
        "fix_hint": fix_hint,
    }
    f.update(extra)
    return f


def _make_doc(
    findings=None,
    deck_findings=None,
    summary=None,
    schema_version="adversarial-review-presentation.v2",
):
    """Build a minimum-valid top-level document, with summary auto-derived
    from findings if not specified explicitly.

    Defaults to schema v2 (the current emit). Pass schema_version=
    "adversarial-review-presentation.v1" to build a legacy v1 doc; in
    that case deck_findings are placed in a separate deck_level_findings
    field. In v2, all findings (including those passed via deck_findings)
    are flattened into the single findings[] array.
    """
    findings = list(findings or [])
    deck_findings = list(deck_findings or [])
    is_v2 = schema_version == "adversarial-review-presentation.v2"

    if is_v2:
        # v2: flatten deck_findings into findings; deck-level findings are
        # those WITHOUT slide_id (the test caller is responsible for
        # constructing them via _make_deck_finding which omits slide_id).
        all_findings = findings + deck_findings
        deck_findings_for_top_level = None  # don't emit deck_level_findings
    else:
        # v1: keep them separate.
        all_findings = findings
        deck_findings_for_top_level = deck_findings

    if summary is None:
        from collections import Counter

        merged = findings + deck_findings  # for counting purposes
        sev = Counter(f["severity"] for f in merged)
        cls = Counter(f["class"] for f in merged)
        summary = {
            "total_findings": len(merged),
            "by_severity": dict(sev),
            "by_class": dict(cls),
        }

    doc = {
        "schema_version": schema_version,
        "draft_dir": "/tmp/fake",
        "project_id": "fake_project",
        "draft_number": 1,
        "reviewed_at": "2026-04-29T13:42:00Z",
        "reviewer_model": "claude-sonnet-4-20250514",
        "prompt_version": (
            "adversarial_presentation.v2" if is_v2
            else "adversarial_presentation.v1"
        ),
        "tier": "STRONG",
        "summary": summary,
        "findings": all_findings,
    }
    if deck_findings_for_top_level is not None:
        # v1 only: emit deck_level_findings as a separate top-level field.
        doc["deck_level_findings"] = deck_findings_for_top_level
    return doc


# ============================================================================
# Pass cases
# ============================================================================


def test_minimal_valid_doc_passes():
    """A doc with one slide finding + the required narrative_weakness
    deck finding (severity=info) should validate clean."""
    doc = _make_doc(
        findings=[_make_finding()],
        deck_findings=[
            _make_deck_finding(
                fid="DL001", cls="narrative_weakness", severity="info"
            )
        ],
    )
    errors, summary_corrections, warnings, stats = validator.validate(doc)
    assert errors == [], f"unexpected errors: {errors}"
    assert stats["slide_findings"] == 1
    assert stats["deck_findings"] == 1
    # warnings is OK (zero P0s on a 1-slide deck won't trip the threshold)


def test_empty_findings_warns_not_errors():
    """Zero findings is a warning (reviewer almost certainly skipped
    detection) but not a hard error — caller decides."""
    doc = _make_doc()
    errors, summary_corrections, warnings, stats = validator.validate(doc)
    assert errors == []
    assert any("zero findings" in w for w in warnings)


# ============================================================================
# Schema-literal validation
# ============================================================================


def test_schema_version_unknown_fails():
    """An unknown schema_version literal must be rejected. Currently
    accepted: v1 (deprecated) and v2 (current). Anything else is an error."""
    doc = _make_doc()
    doc["schema_version"] = "adversarial-review-presentation.v99"
    errors, summary_corrections, _, _ = validator.validate(doc)
    assert any("schema_version" in e for e in errors)


def test_schema_version_v1_accepted_with_deprecation_warning():
    """v1 docs are still accepted (forensic compatibility for older audit
    files like draft_9 / draft_10) but emit a deprecation warning."""
    doc = _make_doc(
        findings=[_make_finding()],
        deck_findings=[
            _make_deck_finding(
                fid="DL001", cls="narrative_weakness", severity="info"
            )
        ],
        schema_version="adversarial-review-presentation.v1",
    )
    errors, summary_corrections, warnings, _ = validator.validate(doc)
    assert errors == [], f"v1 should validate cleanly: {errors}"
    assert any("DEPRECATED" in w for w in warnings), (
        "v1 should emit a deprecation warning"
    )


def test_schema_version_missing_fails():
    doc = _make_doc()
    del doc["schema_version"]
    errors, summary_corrections, _, _ = validator.validate(doc)
    assert any("schema_version" in e for e in errors)


def test_v2_doc_with_deck_level_findings_field_fails():
    """In v2 the deck_level_findings field is removed; an emit that
    includes it should be rejected as a structural error."""
    doc = _make_doc(findings=[_make_finding()])
    doc["deck_level_findings"] = []  # v2 should not have this
    errors, _, _, _ = validator.validate(doc)
    assert any("deck_level_findings" in e for e in errors)


def test_v2_finding_without_slide_id_is_valid():
    """In v2, deck-level findings live in the same findings[] array but
    omit slide_id (and the other slide-level fields). That should
    validate without error."""
    deck_finding = _make_deck_finding(
        fid="F001", cls="narrative_weakness", severity="info"
    )
    # _make_doc with deck_findings flattens this into findings[] under v2
    doc = _make_doc(deck_findings=[deck_finding])
    errors, _, _, stats = validator.validate(doc)
    assert errors == [], f"v2 deck-level finding should validate: {errors}"
    assert stats["slide_findings"] == 0
    assert stats["deck_findings"] == 1


def test_v2_finding_with_slide_id_must_have_other_slide_fields():
    """In v2, presence of slide_id triggers the requirement for the rest
    of the slide-level field set (slide_position, slide_layout,
    title_quote)."""
    bad = _make_finding()  # _make_finding includes all slide-level fields
    del bad["slide_layout"]  # break it
    doc = _make_doc(findings=[bad])
    errors, _, _, _ = validator.validate(doc)
    assert any("slide_layout" in e for e in errors)


# ============================================================================
# Required-field validation
# ============================================================================


def test_missing_required_field_on_slide_finding_fails():
    """An incomplete finding must be flagged."""
    bad = _make_finding()
    del bad["fix_target"]
    doc = _make_doc(findings=[bad])
    errors, summary_corrections, _, _ = validator.validate(doc)
    assert any("fix_target" in e for e in errors)


# ---------------------------------------------------------------------------
# v0.5.3: title_quote requirement is class-specific
#
# Required for finding classes whose criticism targets specific slide
# text — register_drift, claim_evidence, qa_softball.
#
# Optional for classes whose criticism is structural (substory_arc),
# about a slide's absence (missing_slide), about deck-level patterns
# (throughline, narrative_weakness), or about a number whose location
# may not be the slide title (unbacked_quantitative).
# ---------------------------------------------------------------------------


def _slide_finding_no_title_quote(*, cls: str, slide_id: int = 8):
    """Build a slide-level finding with all required fields except
    title_quote. Used to test class-conditional requirement."""
    return {
        "id": "F999",
        "class": cls,
        "severity": "P1",
        "confidence": "high",
        "slide_id": slide_id,
        "slide_position": slide_id,
        "slide_layout": "claim_evidence",
        # NO title_quote
        "issue": "(test fixture)",
        "fix_target": "slide_compose.v1.md",
        "fix_hint": "(test fixture)",
    }


@pytest.mark.parametrize("cls", [
    "substory_arc",
    "missing_slide",
    "throughline",
    "unbacked_quantitative",
])
def test_title_quote_optional_for_non_textual_classes(cls):
    """v0.5.3: classes whose criticism isn't about specific slide text
    don't require title_quote even when slide_id is present.

    Live failure 2026-05-02 (substory_arc): sonnet-4-6 review of
    core_gene_tradeoffs draft_2 produced F015 + F016 as substory_arc
    findings without title_quote (the criticism was about substory
    structure, not about specific slide text). Validator rejected;
    revise loop blocked.
    """
    f = _slide_finding_no_title_quote(cls=cls)
    doc = _make_doc(findings=[f])
    errors, _, _, _ = validator.validate(doc)
    title_quote_errors = [e for e in errors if "title_quote" in e]
    assert title_quote_errors == [], (
        f"class={cls!r} without title_quote should validate; "
        f"got errors: {'; '.join(title_quote_errors)}"
    )


@pytest.mark.parametrize("cls", [
    "register_drift",
    "claim_evidence",
    "qa_softball",
])
def test_title_quote_required_for_textual_classes(cls):
    """The classes whose criticism targets specific slide text MUST
    quote that text for reviewer accountability. Without title_quote,
    the validator rejects."""
    f = _slide_finding_no_title_quote(cls=cls)
    doc = _make_doc(findings=[f])
    errors, _, _, _ = validator.validate(doc)
    assert any("title_quote" in e for e in errors), (
        f"class={cls!r} without title_quote should FAIL; got errors: "
        f"{'; '.join(errors)}"
    )


def test_substory_arc_finding_still_requires_slide_position_and_layout():
    """The relaxation is title_quote-only. slide_position and
    slide_layout remain required."""
    f = _slide_finding_no_title_quote(cls="substory_arc")
    del f["slide_position"]
    del f["slide_layout"]
    doc = _make_doc(findings=[f])
    errors, _, _, _ = validator.validate(doc)
    error_text = "; ".join(errors)
    assert "slide_position" in error_text
    assert "slide_layout" in error_text


def test_v1_missing_slide_level_field_fails():
    """v1: every entry in findings[] is a slide-level finding and must
    have slide_id + slide_position + slide_layout + title_quote.
    (v2 behavior is different: a finding without slide_id is a deck-level
    finding; covered by test_v2_finding_without_slide_id_is_valid.)"""
    bad = _make_finding()
    del bad["slide_id"]
    doc = _make_doc(
        findings=[bad],
        schema_version="adversarial-review-presentation.v1",
    )
    errors, summary_corrections, _, _ = validator.validate(doc)
    assert any("slide_id" in e for e in errors)


def test_deck_level_finding_doesnt_need_slide_fields():
    """deck_level_findings lack a single slide locus; they should NOT
    be flagged for missing slide_id et al."""
    deck = _make_deck_finding(cls="narrative_weakness", severity="info")
    doc = _make_doc(deck_findings=[deck])
    errors, summary_corrections, _, _ = validator.validate(doc)
    # No errors should mention slide_id specifically for the deck finding.
    for e in errors:
        if "slide_id" in e:
            assert "deck_level" not in e, (
                f"deck-level finding spuriously flagged for slide_id: {e}"
            )


def test_invalid_class_value_fails():
    bad = _make_finding(cls="invented_class")
    doc = _make_doc(findings=[bad])
    errors, summary_corrections, _, _ = validator.validate(doc)
    assert any("class=" in e and "invented_class" in e for e in errors)


def test_invalid_severity_value_fails():
    bad = _make_finding(severity="P3")  # P3 is not a valid severity
    doc = _make_doc(findings=[bad])
    errors, summary_corrections, _, _ = validator.validate(doc)
    assert any("severity=" in e and "P3" in e for e in errors)


def test_invalid_confidence_value_fails():
    bad = _make_finding(confidence="certain")
    doc = _make_doc(findings=[bad])
    errors, summary_corrections, _, _ = validator.validate(doc)
    assert any("confidence=" in e for e in errors)


# ============================================================================
# Summary-count consistency
#
# As of v0.4.1, summary count mismatches are AUTO-CORRECTABLE — they go
# into summary_corrections (not errors). The findings array is ground
# truth; LLMs are bad at arithmetic on self-output; the validator
# rewrites the summary block from the array on caller's main() path.
# These tests now verify the routing (corrections, not errors).
# ============================================================================


def test_summary_total_mismatch_routes_to_corrections():
    """Summary count mismatch on total_findings is auto-correctable."""
    doc = _make_doc(findings=[_make_finding()])
    doc["summary"]["total_findings"] = 99  # actual is 1
    errors, summary_corrections, _, _ = validator.validate(doc)
    assert errors == [], (
        f"summary mismatch should not be an error in v0.4.1+: {errors}"
    )
    assert any("total_findings" in c for c in summary_corrections)


def test_summary_by_severity_mismatch_routes_to_corrections():
    doc = _make_doc(findings=[_make_finding(severity="P1")])
    doc["summary"]["by_severity"] = {"P0": 99, "P1": 1}  # P0 fabricated
    errors, summary_corrections, _, _ = validator.validate(doc)
    assert errors == []
    assert any("by_severity" in c and "P0" in c for c in summary_corrections)


def test_summary_by_class_mismatch_routes_to_corrections():
    doc = _make_doc(findings=[_make_finding(cls="claim_evidence")])
    doc["summary"]["by_class"] = {"claim_evidence": 1, "throughline": 5}
    errors, summary_corrections, _, _ = validator.validate(doc)
    assert errors == []
    assert any("by_class" in c and "throughline" in c for c in summary_corrections)


def test_summary_missing_severity_key_routes_to_corrections():
    """If a severity appears in findings but is absent from summary.by_severity,
    that's an auto-correctable count mismatch."""
    doc = _make_doc(findings=[_make_finding(severity="P0")])
    doc["summary"]["by_severity"] = {"P1": 0}  # missing P0 entirely
    errors, summary_corrections, _, _ = validator.validate(doc)
    assert errors == []
    assert any("by_severity" in c and "P0" in c for c in summary_corrections)


# ============================================================================
# Auto-correction (v0.4.1)
#
# Tests for the compute_correct_summary() function and the main() path's
# auto-correction behavior. These are the load-bearing tests for the new
# v0.4.1 design — the LLM consistently mis-counts on summary recount, so
# the validator backstops by rewriting the summary from the findings array.
# ============================================================================


def test_compute_correct_summary_from_findings():
    """compute_correct_summary derives the summary block deterministically
    from findings + deck_findings. This is the source of truth used by both
    the consistency check and the auto-correction path."""
    findings = [
        _make_finding(fid="F001", severity="P0", cls="claim_evidence"),
        _make_finding(fid="F002", severity="P0", cls="claim_evidence"),
        _make_finding(fid="F003", severity="P1", cls="register_drift"),
    ]
    deck = [
        _make_deck_finding(
            fid="DL001", severity="info", cls="narrative_weakness"
        )
    ]
    summary = validator.compute_correct_summary(findings, deck)
    assert summary["total_findings"] == 4
    assert summary["by_severity"] == {"P0": 2, "P1": 1, "info": 1}
    assert summary["by_class"] == {
        "claim_evidence": 2,
        "register_drift": 1,
        "narrative_weakness": 1,
    }


def test_compute_correct_summary_handles_empty_arrays():
    """Empty findings → empty summary structure (no division-by-zero,
    no missing keys)."""
    summary = validator.compute_correct_summary([], [])
    assert summary["total_findings"] == 0
    assert summary["by_severity"] == {}
    assert summary["by_class"] == {}


def test_compute_correct_summary_ignores_invalid_severity_or_class():
    """Bad severity/class values don't propagate into the corrected
    summary — only valid enum values are tallied. Invalid values would
    have been caught upstream as errors."""
    findings = [
        _make_finding(fid="F001", severity="P0", cls="claim_evidence"),
        _make_finding(fid="F002", severity="bogus", cls="invented"),
    ]
    summary = validator.compute_correct_summary(findings, [])
    assert summary["by_severity"] == {"P0": 1}
    assert summary["by_class"] == {"claim_evidence": 1}


def test_cli_auto_corrects_summary_mismatch_exit_2(tmp_path: Path):
    """End-to-end: a JSON with bad summary counts but otherwise-valid
    findings should be auto-corrected in place + exit 2."""
    p = tmp_path / "review.json"
    doc = _make_doc(
        findings=[
            _make_finding(fid="F001", severity="P0"),
            _make_finding(fid="F002", severity="P0"),
            _make_finding(fid="F003", severity="P1"),
        ],
        deck_findings=[
            _make_deck_finding(
                fid="DL001", severity="info", cls="narrative_weakness"
            )
        ],
    )
    # Stomp the summary with the off-by-one mistake we observed in
    # production (P0 declared low, P1 declared high).
    doc["summary"]["by_severity"] = {"P0": 1, "P1": 2, "info": 1}
    doc["summary"]["total_findings"] = 4
    p.write_text(json.dumps(doc), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(VALIDATOR_PATH), str(p)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 2, (
        f"expected auto-correct exit 2; got {result.returncode}\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "AUTO-CORRECTED" in result.stderr
    assert "PASS" in result.stdout

    # File should be rewritten with correct summary
    rewritten = json.loads(p.read_text(encoding="utf-8"))
    assert rewritten["summary"]["by_severity"] == {"P0": 2, "P1": 1, "info": 1}
    assert rewritten["summary"]["total_findings"] == 4

    # Sidecar with original (mismatched) summary should exist
    sidecar = p.with_name(p.stem + ".original-summary.json")
    assert sidecar.is_file(), "sidecar with original summary not created"
    sidecar_doc = json.loads(sidecar.read_text(encoding="utf-8"))
    assert sidecar_doc["original_summary"]["by_severity"] == {
        "P0": 1, "P1": 2, "info": 1,
    }
    assert "corrections_applied" in sidecar_doc
    assert len(sidecar_doc["corrections_applied"]) > 0


def test_cli_auto_correction_preserves_findings_array(tmp_path: Path):
    """Auto-correction must NOT mutate findings[] — only summary fields.
    The findings array is the ground truth."""
    p = tmp_path / "review.json"
    doc = _make_doc(
        findings=[
            _make_finding(fid="F001", severity="P0", title_quote="TQ-001"),
            _make_finding(fid="F002", severity="P1", title_quote="TQ-002"),
        ],
        deck_findings=[
            _make_deck_finding(
                fid="DL001", severity="info", cls="narrative_weakness",
                issue="narrative-issue-text"
            )
        ],
    )
    # Stomp the summary
    doc["summary"]["total_findings"] = 99
    p.write_text(json.dumps(doc), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(VALIDATOR_PATH), str(p)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 2

    rewritten = json.loads(p.read_text(encoding="utf-8"))
    # In v2, _make_doc flattens deck_findings into findings[]:
    # 2 slide-level + 1 deck-level = 3 total.
    assert len(rewritten["findings"]) == 3
    # The slide-level findings must be untouched (order + content):
    slide_level = [f for f in rewritten["findings"] if "slide_id" in f]
    assert len(slide_level) == 2
    assert slide_level[0]["title_quote"] == "TQ-001"
    assert slide_level[1]["title_quote"] == "TQ-002"
    # The deck-level finding must also be untouched:
    deck_level = [f for f in rewritten["findings"] if "slide_id" not in f]
    assert len(deck_level) == 1
    assert deck_level[0]["issue"] == "narrative-issue-text"
    # v2 must NOT have a deck_level_findings field
    assert "deck_level_findings" not in rewritten


def test_cli_non_correctable_error_blocks_auto_correction(tmp_path: Path):
    """If there are non-correctable errors (schema violation, bad enum,
    etc.) AND summary mismatches, the file must NOT be rewritten —
    auto-correction shouldn't paper over a structurally broken JSON."""
    p = tmp_path / "review.json"
    doc = _make_doc(findings=[_make_finding()])
    doc["schema_version"] = "wrong"  # non-correctable error
    doc["summary"]["total_findings"] = 99  # also a count mismatch
    original_text = json.dumps(doc)
    p.write_text(original_text, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(VALIDATOR_PATH), str(p)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 1, (
        f"non-correctable error should block correction; got exit {result.returncode}"
    )
    # File should not have been touched
    assert p.read_text(encoding="utf-8") == original_text
    # Sidecar should NOT exist
    sidecar = p.with_name(p.stem + ".original-summary.json")
    assert not sidecar.exists(), "sidecar created despite non-correctable error"


# ============================================================================
# ID uniqueness
# ============================================================================


def test_duplicate_finding_id_fails():
    doc = _make_doc(
        findings=[
            _make_finding(fid="F001"),
            _make_finding(fid="F001", cls="register_drift"),
        ]
    )
    errors, summary_corrections, _, _ = validator.validate(doc)
    assert any("duplicate" in e.lower() and "F001" in e for e in errors)


# ============================================================================
# narrative_weakness invariants
# ============================================================================


def test_narrative_weakness_with_non_info_severity_fails():
    bad = _make_deck_finding(cls="narrative_weakness", severity="P0")
    doc = _make_doc(deck_findings=[bad])
    errors, summary_corrections, _, _ = validator.validate(doc)
    assert any("narrative_weakness" in e and "info" in e for e in errors)


def test_info_severity_on_non_narrative_weakness_fails():
    bad = _make_finding(severity="info")  # info reserved for narrative_weakness
    doc = _make_doc(findings=[bad])
    errors, summary_corrections, _, _ = validator.validate(doc)
    assert any("info" in e and "narrative_weakness" in e for e in errors)


def test_two_narrative_weakness_findings_fails():
    """Class 7 must produce exactly one finding; multiple is wrong."""
    doc = _make_doc(
        deck_findings=[
            _make_deck_finding(
                fid="DL001", cls="narrative_weakness", severity="info"
            ),
            _make_deck_finding(
                fid="DL002", cls="narrative_weakness", severity="info"
            ),
        ]
    )
    errors, summary_corrections, _, _ = validator.validate(doc)
    assert any("narrative_weakness" in e and "exactly once" in e for e in errors)


def test_missing_narrative_weakness_warns_not_fails():
    """Reviewer might skip Class 7; that's a warning, not a hard fail."""
    doc = _make_doc(findings=[_make_finding()])
    errors, summary_corrections, warnings, _ = validator.validate(doc)
    assert errors == []
    assert any("narrative_weakness" in w for w in warnings)


# ============================================================================
# Advisory checks
# ============================================================================


def test_zero_p0_on_large_deck_warns():
    """Spec §9 lists 3 P0s for draft_9 (26 slides). A zero-P0 review on
    a 20+ slide deck strongly suggests reviewer under-fire."""
    doc = _make_doc(
        findings=[_make_finding(severity="P1", slide_position=25)],
        deck_findings=[
            _make_deck_finding(
                fid="DL001", cls="narrative_weakness", severity="info"
            )
        ],
    )
    errors, summary_corrections, warnings, _ = validator.validate(doc)
    assert errors == []
    assert any("P0" in w and "under-fire" in w for w in warnings)


def test_zero_p0_on_small_deck_no_warn():
    """A small deck (<20 slides) reasonably has no P0s; don't warn."""
    doc = _make_doc(
        findings=[_make_finding(severity="P1", slide_position=5)],
        deck_findings=[
            _make_deck_finding(
                fid="DL001", cls="narrative_weakness", severity="info"
            )
        ],
    )
    errors, summary_corrections, warnings, _ = validator.validate(doc)
    assert errors == []
    assert not any("under-fire" in w for w in warnings)


# ============================================================================
# CLI subprocess tests
# ============================================================================


def test_cli_pass_returns_zero(tmp_path: Path):
    p = tmp_path / "review.json"
    doc = _make_doc(
        findings=[_make_finding()],
        deck_findings=[
            _make_deck_finding(
                fid="DL001", cls="narrative_weakness", severity="info"
            )
        ],
    )
    p.write_text(json.dumps(doc), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(VALIDATOR_PATH), str(p)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, (
        f"unexpected non-zero exit: stdout={result.stdout!r} "
        f"stderr={result.stderr!r}"
    )
    assert "PASS" in result.stdout


def test_cli_missing_file_exits_3(tmp_path: Path):
    p = tmp_path / "nonexistent.json"
    result = subprocess.run(
        [sys.executable, str(VALIDATOR_PATH), str(p)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 3
    assert "not found" in result.stderr


def test_cli_unparseable_json_exits_1(tmp_path: Path):
    p = tmp_path / "broken.json"
    p.write_text("{ this is not json", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(VALIDATOR_PATH), str(p)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 1
    assert "not valid JSON" in result.stderr


def test_cli_validation_failure_exits_1(tmp_path: Path):
    p = tmp_path / "review.json"
    doc = _make_doc(findings=[_make_finding()])
    doc["schema_version"] = "wrong"
    p.write_text(json.dumps(doc), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(VALIDATOR_PATH), str(p)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 1
    assert "FAIL" in result.stderr


def test_cli_warnings_exit_2(tmp_path: Path):
    """Validator should exit 2 (advisory) when there are warnings but
    no errors."""
    p = tmp_path / "review.json"
    # Findings present, narrative_weakness missing → triggers warning only
    doc = _make_doc(findings=[_make_finding()])
    p.write_text(json.dumps(doc), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(VALIDATOR_PATH), str(p)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 2
    assert "PASS" in result.stdout
    assert "WARN" in result.stderr


def test_cli_handles_path_with_special_chars(tmp_path: Path):
    """Heredoc-quoting fix: validator must accept paths that would
    have broken the old inline shell heredoc."""
    weird = tmp_path / "review with spaces.json"
    doc = _make_doc(
        findings=[_make_finding()],
        deck_findings=[
            _make_deck_finding(
                fid="DL001", cls="narrative_weakness", severity="info"
            )
        ],
    )
    weird.write_text(json.dumps(doc), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(VALIDATOR_PATH), str(weird)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, f"path with spaces broke validator: {result.stderr}"


# ============================================================================
# Paper schema (adversarial-review-paper.v2) — v0.6.0 additions
# ============================================================================


def _make_paper_finding(
    fid="F001",
    cls="claim_evidence",
    severity="P1",
    confidence="high",
    section="Results",
    line_range="L142-148",
    paragraph_quote="some paragraph",
    issue="some issue",
    fix_target="results.v1.md",
    fix_hint="some fix",
    **extra,
):
    """Build a minimum-valid paper section-level finding."""
    f = {
        "id": fid, "class": cls, "severity": severity, "confidence": confidence,
        "section": section, "line_range": line_range,
        "paragraph_quote": paragraph_quote,
        "issue": issue, "fix_target": fix_target, "fix_hint": fix_hint,
    }
    f.update(extra)
    return f


def _make_paper_manuscript_wide_finding(
    fid="F002",
    cls="narrative_weakness",
    severity="info",
    confidence="high",
    issue="manuscript-wide issue",
    fix_target="discussion.v1.md",
    fix_hint="add limitations paragraph",
    **extra,
):
    """Build a manuscript-wide paper finding (no section field)."""
    f = {
        "id": fid, "class": cls, "severity": severity, "confidence": confidence,
        "issue": issue, "fix_target": fix_target, "fix_hint": fix_hint,
    }
    f.update(extra)
    return f


def _make_paper_doc(findings=None, summary=None):
    """Minimum-valid paper.v2 doc (single findings[] array, no
    deck_level_findings field)."""
    findings = list(findings or [])
    if summary is None:
        from collections import Counter
        sev = Counter(f["severity"] for f in findings)
        cls = Counter(f["class"] for f in findings)
        summary = {
            "total_findings": len(findings),
            "by_severity": dict(sev),
            "by_class": dict(cls),
        }
    return {
        "schema_version": "adversarial-review-paper.v2",
        "draft_dir": "/tmp/fake/papers/draft_1",
        "project_id": "fake_project",
        "draft_number": 1,
        "reviewed_at": "2026-05-02T13:42:00Z",
        "reviewer_model": "claude-sonnet-4-6",
        "prompt_version": "adversarial_paper.v2",
        "tier": "STRONG",
        "summary": summary,
        "findings": findings,
    }


def test_paper_v2_minimal_valid_doc_passes():
    doc = _make_paper_doc(findings=[
        _make_paper_finding(fid="F001"),
        _make_paper_manuscript_wide_finding(fid="F002"),
    ])
    errors, _, _, stats = validator.validate(doc)
    assert errors == [], f"unexpected errors: {errors}"
    assert stats["slide_findings"] == 1  # the section-level finding
    assert stats["deck_findings"] == 1   # the manuscript-wide finding


def test_paper_v2_rejects_deck_level_findings_field():
    """Paper v2 must NOT have a deck_level_findings field — single array."""
    doc = _make_paper_doc(findings=[_make_paper_finding()])
    doc["deck_level_findings"] = []
    errors, _, _, _ = validator.validate(doc)
    assert any("deck_level_findings" in e for e in errors)


def test_paper_v2_finding_without_section_is_valid():
    """A paper finding without `section` is a manuscript-wide finding —
    valid, just no section-level fields required."""
    doc = _make_paper_doc(findings=[
        _make_paper_manuscript_wide_finding(fid="F001", cls="missing_section", severity="P1"),
        _make_paper_manuscript_wide_finding(fid="F002", cls="narrative_weakness", severity="info"),
    ])
    errors, _, _, _ = validator.validate(doc)
    assert errors == [], f"manuscript-wide findings should validate: {errors}"


def test_paper_v2_finding_with_section_requires_line_range():
    """If section is present, line_range is required."""
    bad = _make_paper_finding()
    del bad["line_range"]
    doc = _make_paper_doc(findings=[bad])
    errors, _, _, _ = validator.validate(doc)
    assert any("line_range" in e for e in errors)


def test_paper_v2_paragraph_quote_required_for_register_drift():
    """register_drift criticism targets specific paper text;
    paragraph_quote is required (mirror of presentation v0.5.3
    title_quote class-conditional rule)."""
    bad = _make_paper_finding(cls="register_drift")
    del bad["paragraph_quote"]
    doc = _make_paper_doc(findings=[bad])
    errors, _, _, _ = validator.validate(doc)
    assert any("paragraph_quote" in e for e in errors)


def test_paper_v2_paragraph_quote_optional_for_section_arc():
    """section_arc criticism is structural, not text-specific;
    paragraph_quote is optional."""
    f = _make_paper_finding(cls="section_arc", severity="P1")
    del f["paragraph_quote"]
    doc = _make_paper_doc(findings=[f])
    errors, _, _, _ = validator.validate(doc)
    # No error about paragraph_quote
    assert not any("paragraph_quote" in e for e in errors), (
        f"section_arc should not require paragraph_quote: {errors}"
    )


def test_paper_v2_rejects_presentation_only_class():
    """Paper schema must not accept presentation-only classes
    (qa_softball, missing_slide, substory_arc)."""
    bad = _make_paper_finding(cls="qa_softball")  # presentation-only
    doc = _make_paper_doc(findings=[bad])
    errors, _, _, _ = validator.validate(doc)
    assert any("class=" in e and "qa_softball" in e for e in errors)


def test_paper_v2_accepts_paper_only_class():
    """Paper schema must accept paper-only classes (citation_reality,
    report_drift, abstract_body_mismatch)."""
    for paper_class in ("citation_reality", "report_drift",
                        "abstract_body_mismatch"):
        f = _make_paper_finding(cls=paper_class, severity="P1")
        doc = _make_paper_doc(findings=[f])
        errors, _, _, _ = validator.validate(doc)
        assert not any("class=" in e and paper_class in e for e in errors), (
            f"paper class {paper_class} should be accepted: {errors}"
        )


def test_presentation_v2_rejects_paper_only_class():
    """Presentation schema must NOT accept paper-only classes (clean
    separation)."""
    bad = _make_finding(cls="citation_reality")  # paper-only
    doc = _make_doc(findings=[bad])  # default schema_version=presentation v2
    errors, _, _, _ = validator.validate(doc)
    assert any("class=" in e and "citation_reality" in e for e in errors)


def test_paper_v2_summary_mismatch_auto_corrects(tmp_path: Path):
    """Auto-correction works on paper v2 docs the same way as
    presentation v2."""
    p = tmp_path / "paper_review.json"
    doc = _make_paper_doc(findings=[
        _make_paper_finding(severity="P0"),
        _make_paper_finding(fid="F002", severity="P0"),
    ])
    doc["summary"]["by_severity"] = {"P0": 1, "P1": 1}  # wrong
    p.write_text(json.dumps(doc), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(VALIDATOR_PATH), str(p)],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 2  # auto-correct exit code
    rewritten = json.loads(p.read_text(encoding="utf-8"))
    assert rewritten["summary"]["by_severity"] == {"P0": 2}


# ============================================================================
# v0.6.1 — schema-aware labels in summary_stats
# ============================================================================


def test_paper_schema_uses_section_level_and_manuscript_wide_labels():
    """v0.6.1 fix: paper schema must report 'section-level' and
    'manuscript-wide' counts, not 'slide-level' / 'deck-level'."""
    doc = _make_paper_doc(findings=[
        _make_paper_finding(fid="F001"),
        _make_paper_manuscript_wide_finding(fid="F002"),
    ])
    _, _, _, stats = validator.validate(doc)
    assert stats["locus_label"] == "section-level"
    assert stats["non_locus_label"] == "manuscript-wide"
    assert stats["schema_family"] == "paper"
    assert stats["schema_version"] == "adversarial-review-paper.v2"
    assert stats["locus_count"] == 1
    assert stats["non_locus_count"] == 1


def test_presentation_schema_uses_slide_level_and_deck_level_labels():
    """Presentation schema retains 'slide-level' / 'deck-level' labels
    (no behavior change in v0.6.1)."""
    doc = _make_doc(
        findings=[_make_finding()],
        deck_findings=[
            _make_deck_finding(
                fid="DL001", cls="narrative_weakness", severity="info"
            )
        ],
    )
    _, _, _, stats = validator.validate(doc)
    assert stats["locus_label"] == "slide-level"
    assert stats["non_locus_label"] == "deck-level"
    assert stats["schema_family"] == "presentation"


def test_legacy_summary_stat_keys_preserved_for_backwards_compat():
    """v0.6.1 added new locus_count / non_locus_count keys but kept the
    legacy slide_findings / deck_findings keys for backwards compat
    with any caller that scrapes by name."""
    doc = _make_paper_doc(findings=[
        _make_paper_finding(fid="F001"),
        _make_paper_manuscript_wide_finding(fid="F002"),
    ])
    _, _, _, stats = validator.validate(doc)
    # Legacy keys still populated and equal to the new keys
    assert "slide_findings" in stats
    assert "deck_findings" in stats
    assert stats["slide_findings"] == stats["locus_count"]
    assert stats["deck_findings"] == stats["non_locus_count"]


def test_cli_paper_pass_message_uses_section_level_label(tmp_path: Path):
    """End-to-end: invoking the validator on a paper.v2 doc should print
    'section-level' in the success message (not 'slide-level')."""
    p = tmp_path / "paper_review.json"
    doc = _make_paper_doc(findings=[
        _make_paper_finding(fid="F001"),
        _make_paper_manuscript_wide_finding(
            fid="F002", cls="narrative_weakness", severity="info"
        ),
    ])
    p.write_text(json.dumps(doc), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(VALIDATOR_PATH), str(p)],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, (
        f"validator unexpectedly failed: {result.stderr}"
    )
    assert "section-level" in result.stdout
    assert "manuscript-wide" in result.stdout
    assert "slide-level" not in result.stdout
    assert "deck-level" not in result.stdout


# ============================================================================
# v0.6.2 — lenient JSON loader (trailing-comma repair)
# ============================================================================


def test_lenient_json_load_passes_clean_json():
    """Valid JSON parses byte-identically through lenient_json_load."""
    text = '{"a": 1, "b": [2, 3, 4]}'
    assert validator.lenient_json_load(text) == {"a": 1, "b": [2, 3, 4]}


def test_lenient_json_load_repairs_trailing_comma_in_object():
    """Single LLM-emitted trailing comma before `}` is repairable."""
    text = '{"a": 1, "b": 2,}'
    assert validator.lenient_json_load(text) == {"a": 1, "b": 2}


def test_lenient_json_load_repairs_trailing_comma_in_array():
    """Single LLM-emitted trailing comma before `]` is repairable."""
    text = '{"items": [1, 2, 3,]}'
    assert validator.lenient_json_load(text) == {"items": [1, 2, 3]}


def test_lenient_json_load_repairs_multiple_trailing_commas():
    """Several trailing commas in one doc — all repaired in one pass."""
    text = '{"a": [1,], "b": {"c": 2,},}'
    assert validator.lenient_json_load(text) == {"a": [1], "b": {"c": 2}}


def test_lenient_json_load_raises_original_error_on_unrepairable_failure():
    """Unescaped inner quotes are NOT repairable — original error
    surfaces, not a confusing post-repair error from a different
    location."""
    text = '{"key": "value with "inner" quote", "other": 1}'
    with pytest.raises(json.JSONDecodeError) as exc:
        validator.lenient_json_load(text)
    # The repair pass should NOT have changed which error gets raised
    # (the unescaped quote is the actual problem, not anything the
    # repair touched).
    assert "delimiter" in str(exc.value) or "Expecting" in str(exc.value)


def test_cli_lenient_loader_handles_trailing_comma_doc(tmp_path: Path):
    """End-to-end: a JSON file with a trailing comma should validate
    cleanly through the CLI (the lenient loader repairs it before
    schema validation runs)."""
    p = tmp_path / "trailing_comma_review.json"
    # Build a minimum-valid presentation v2 doc with a trailing comma
    # in the findings array
    text = '''{
  "schema_version": "adversarial-review-presentation.v2",
  "draft_dir": "/tmp/fake",
  "project_id": "fake",
  "draft_number": 1,
  "reviewed_at": "2026-05-02T00:00:00Z",
  "reviewer_model": "claude-sonnet-4-6",
  "prompt_version": "adversarial_presentation.v2",
  "tier": "STRONG",
  "summary": {"total_findings": 1, "by_severity": {"info": 1}, "by_class": {"narrative_weakness": 1}},
  "findings": [
    {"id": "F001", "class": "narrative_weakness", "severity": "info", "confidence": "high", "issue": "x", "fix_target": "slide_compose.v1.md", "fix_hint": "y"},
  ]
}'''
    p.write_text(text, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(VALIDATOR_PATH), str(p)],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 0, (
        f"trailing-comma doc should pass via lenient loader; got "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "PASS" in result.stdout


def test_cli_unescaped_inner_quote_fails_with_helpful_hint(tmp_path: Path):
    """Unescaped inner quote (the draft_7 failure mode) cannot be
    repaired and should fail with a helpful hint pointing at the
    likely cause."""
    p = tmp_path / "unescaped_quote_review.json"
    # Mimic the draft_7 failure: an unescaped quote inside paragraph_quote
    text = '''{
  "schema_version": "adversarial-review-paper.v2",
  "draft_dir": "/tmp/fake",
  "project_id": "fake",
  "draft_number": 1,
  "reviewed_at": "2026-05-02T00:00:00Z",
  "reviewer_model": "claude-sonnet-4-6",
  "prompt_version": "adversarial_paper.v2",
  "tier": "STRONG",
  "summary": {"total_findings": 0, "by_severity": {}, "by_class": {}},
  "findings": [
    {"id": "F001", "class": "claim_evidence", "severity": "P1", "confidence": "high", "section": "Results", "line_range": "L1", "paragraph_quote": "Methods §"Phase 10" identified ...", "issue": "x", "fix_target": "results.v1.md", "fix_hint": "y"}
  ]
}'''
    p.write_text(text, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(VALIDATOR_PATH), str(p)],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 1
    assert "not valid JSON" in result.stderr
    # The hint about unescaped quotes should appear (helps the operator
    # diagnose without context-switching to docs).
    assert "unescaped" in result.stderr.lower() or "inner" in result.stderr.lower()


# ============================================================================
# v0.6.2 — prompt-side anti-pattern guidance
# ============================================================================


PAPER_V2_PROMPT = SKILL_DIR_SRC / "prompts" / "adversarial_paper.v2.md"
PRESENTATION_V2_PROMPT = SKILL_DIR_SRC / "prompts" / "adversarial_presentation.v2.md"


def test_paper_prompt_includes_unescaped_quote_anti_pattern():
    """v0.6.2: paper.v2 prompt must include the explicit anti-pattern
    against unescaped inner quotes in JSON string fields."""
    text = PAPER_V2_PROMPT.read_text(encoding="utf-8")
    assert "unescaped inner quotes" in text.lower() or "UNFIXABLE BY THE VALIDATOR" in text, (
        "paper.v2 prompt missing unescaped-quote anti-pattern (v0.6.2 fix)"
    )
    # Should show all 4 correct approaches
    assert "Backslash-escape" in text
    assert "curly quotes" in text


def test_presentation_prompt_includes_unescaped_quote_anti_pattern():
    """v0.6.2: presentation.v2 prompt must also include the anti-pattern
    (different reviewer, same JSON failure mode)."""
    text = PRESENTATION_V2_PROMPT.read_text(encoding="utf-8")
    assert "unescaped inner quotes" in text.lower() or "UNFIXABLE BY THE VALIDATOR" in text, (
        "presentation.v2 prompt missing unescaped-quote anti-pattern (v0.6.2 fix)"
    )
