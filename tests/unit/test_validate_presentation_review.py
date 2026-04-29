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
