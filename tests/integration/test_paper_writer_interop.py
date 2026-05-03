"""Cross-skill smoke test: paper-writer ↔ beril-adversarial v0.6.0 interop.

Memory entry `feedback_cross_skill_contract_drift.md` documents the
recurring failure mode: when paper-writer changes its output structure
without coordinated adversarial-reviewer updates, the integration breaks
silently. This test catches that drift early.

What we test:

1. **Synthetic paper-writer-shaped draft_dir.** Build a minimal but
   structurally-complete fixture mirroring paper-writer v0.6+'s per-draft
   layout. Confirm the adversarial orchestrator's input-validation phase
   accepts it (does NOT error before invoking claude).

2. **Legacy flat-file rejection.** Build a fixture with
   `papers/draft1.md` (legacy layout) and confirm the orchestrator
   emits the migration error message.

3. **Validator accepts a synthetic v2 paper review JSON.** Build a
   minimum-valid `adversarial-review-paper.v2` JSON; confirm the
   validator validates it without errors.

We do NOT actually invoke claude — these are dispatch-validation +
schema-validation tests, not live LLM calls. The adversarial orchestrator
errors AFTER input validation when claude is unavailable; we look for
"claude invocation failed" or "claude not installed" as proof we got past
the input-validation phase.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


pytestmark = pytest.mark.integration


SKILL_DIR_SRC = (
    Path(__file__).parent.parent.parent
    / "src"
    / "beril_adversarial"
    / "skill"
)
ORCHESTRATOR = SKILL_DIR_SRC / "tools" / "adversarial_review.sh"
VALIDATOR = SKILL_DIR_SRC / "tools" / "validate_presentation_review.py"


@pytest.fixture
def mock_beril_root(tmp_path: Path) -> Path:
    """Build a minimal BERIL root containing the skill tree (mirror of
    test_presentation_review.py's fixture)."""
    beril_root = tmp_path / "mock_beril"
    skill_dir = beril_root / ".claude" / "skills" / "beril-adversarial"
    skill_dir.mkdir(parents=True)
    for sub in ("prompts", "tools"):
        shutil.copytree(SKILL_DIR_SRC / sub, skill_dir / sub)
    (skill_dir / "state").mkdir()
    return beril_root


@pytest.fixture
def paper_writer_v06_fixture(tmp_path: Path) -> Path:
    """Build a synthetic paper-writer v0.6+ per-draft directory.

    Structurally complete (all REQUIRED inputs per CONTRACT.md present),
    but content is minimal — claude won't be invoked because we want to
    test dispatch validation only.
    """
    project_dir = tmp_path / "mock_project"
    draft_dir = project_dir / "papers" / "draft_1"
    draft_dir.mkdir(parents=True)

    # Project-level required files
    (project_dir / "REPORT.md").write_text(
        "# Report\n\n## Finding 1\nResult X holds.\n",
        encoding="utf-8",
    )
    (project_dir / "RESEARCH_PLAN.md").write_text(
        "# Plan\n\n## Hypothesis\nX is the case.\n",
        encoding="utf-8",
    )

    # paper-writer v0.6+ required per-draft files
    (draft_dir / "manuscript.md").write_text(
        "# Manuscript\n\n## Abstract\n...\n## Introduction\n...\n",
        encoding="utf-8",
    )
    (draft_dir / "00_throughline.md").write_text(
        "# Throughline\n\n## Evidence map\n| Claim | Source |\n|---|---|\n| X | §Finding 1 |\n",
        encoding="utf-8",
    )
    (draft_dir / "references.md").write_text(
        "# References\n\nSmith J. 2024. Title. Journal 1:1-10. doi:10.1/x\n",
        encoding="utf-8",
    )
    (draft_dir / "citation_map.md").write_text(
        "# Citation Map\n\nSmith2024 → Discussion paragraph 1, claim about X.\n",
        encoding="utf-8",
    )

    # Optional but recommended
    (draft_dir / "reframing_log.md").write_text(
        "# Reframing log\n\n(no reframings applied)\n",
        encoding="utf-8",
    )
    return draft_dir


# ============================================================================
# Dispatch validation tests (orchestrator side)
# ============================================================================


def test_orchestrator_accepts_paper_writer_v06_layout(
    mock_beril_root: Path, paper_writer_v06_fixture: Path
):
    """Synthetic paper-writer v0.6+ draft_dir must pass input validation.

    The orchestrator will then attempt to invoke claude, which won't be
    available in the test environment — we check that the failure mode
    is 'claude invocation failed' or 'claude not installed', proving we
    got past the per-skill input validation phase.
    """
    result = subprocess.run(
        [
            "bash", str(ORCHESTRATOR),
            str(paper_writer_v06_fixture),
            "--type", "paper",
            "--beril-root", str(mock_beril_root),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    output = result.stderr + result.stdout
    # MUST NOT error on input validation — these substrings indicate
    # we never made it to claude:
    assert "required input missing" not in output, (
        f"orchestrator rejected paper-writer v0.6+ layout:\n{output}"
    )
    assert "draft_dir does not look like" not in output, (
        f"orchestrator misidentified paper-writer v0.6+ layout:\n{output}"
    )
    assert "REPORT.md not found" not in output, (
        f"orchestrator failed REPORT resolution from paper-writer fixture:\n{output}"
    )
    # SHOULD reach the claude invocation phase. That'll fail in test env
    # because claude isn't logged in, but that's fine — the dispatch is
    # what we're testing.
    assert (
        "Invoking Claude paper reviewer" in output
        or "claude invocation failed" in output
        or "claude' CLI is not installed" in output
        or "Not logged in" in output
    ), f"orchestrator did not reach claude invocation:\n{output}"


def test_orchestrator_rejects_legacy_flat_file_layout_with_migration_msg(
    mock_beril_root: Path, tmp_path: Path
):
    """A legacy flat-file paper layout (papers/draft1.md) must be rejected
    with a clear migration message — clean break per v0.6.0 design."""
    project_dir = tmp_path / "legacy_project"
    papers = project_dir / "papers"
    papers.mkdir(parents=True)
    # Legacy flat file
    (papers / "draft1.md").write_text("# Legacy draft\n", encoding="utf-8")
    (project_dir / "REPORT.md").write_text("# Report\n", encoding="utf-8")
    # Pretend draft_1 is the per-draft dir but it's empty (no manuscript.md)
    legacy_draft_dir = papers / "draft_1"
    legacy_draft_dir.mkdir()

    result = subprocess.run(
        [
            "bash", str(ORCHESTRATOR),
            str(legacy_draft_dir),
            "--type", "paper",
            "--beril-root", str(mock_beril_root),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    output = result.stderr + result.stdout
    assert result.returncode == 2
    # Migration message should mention the legacy layout detection
    assert "legacy flat-file paper layout" in output, (
        f"expected migration message; got:\n{output}"
    )


def test_orchestrator_rejects_paper_with_codex_fusion(
    mock_beril_root: Path, paper_writer_v06_fixture: Path
):
    """v0.6.0 paper is single-pass. --reviewer claude,codex must be
    rejected with a diagnostic."""
    result = subprocess.run(
        [
            "bash", str(ORCHESTRATOR),
            str(paper_writer_v06_fixture),
            "--type", "paper",
            "--reviewer", "claude,codex",
            "--beril-root", str(mock_beril_root),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    output = result.stderr + result.stdout
    assert result.returncode != 0
    assert "fusion" in output.lower() or "codex" in output.lower()


def test_orchestrator_rejects_paper_consolidate(
    mock_beril_root: Path, paper_writer_v06_fixture: Path
):
    """--consolidate is not supported in v0.6.0 paper mode."""
    result = subprocess.run(
        [
            "bash", str(ORCHESTRATOR),
            str(paper_writer_v06_fixture),
            "--type", "paper",
            "--consolidate",
            "--beril-root", str(mock_beril_root),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    output = result.stderr + result.stdout
    assert result.returncode != 0
    assert "consolidate" in output.lower()


# ============================================================================
# Schema validation tests (validator side)
# ============================================================================


def test_validator_accepts_synthetic_paper_v2_review(tmp_path: Path):
    """A minimum-valid adversarial-review-paper.v2 JSON must still parse
    cleanly via the validator (forensic acceptance for v0.6.x audit
    files).

    As of v0.7.0, v2 schemas are DEPRECATED — the validator emits a
    deprecation warning and returns exit code 2 (warn-only), not 0.
    The .json content is still consumer-readable; the warning is
    advisory and tells consumers to migrate to v3. v2 acceptance will
    be removed in the next release after both consumer teams confirm
    v3 adoption.
    """
    review_json = tmp_path / "adversarial_review.json"
    doc = {
        "schema_version": "adversarial-review-paper.v2",
        "draft_dir": str(tmp_path),
        "project_id": "fake_project",
        "draft_number": 1,
        "reviewed_at": "2026-05-02T13:42:00Z",
        "reviewer_model": "claude-sonnet-4-6",
        "prompt_version": "adversarial_paper.v2",
        "tier": "STRONG",
        "summary": {
            "total_findings": 2,
            "by_severity": {"P1": 1, "info": 1},
            "by_class": {"register_drift": 1, "narrative_weakness": 1},
        },
        "findings": [
            {
                "id": "F001",
                "class": "register_drift",
                "severity": "P1",
                "confidence": "high",
                "section": "Results",
                "line_range": "L142-148",
                "paragraph_quote": "validates 61.7%",
                "issue": "over-claim relative to REPORT",
                "report_evidence": [
                    {"section": "§Finding 7", "quote": "binomial p=0.072"}
                ],
                "fix_target": "results.v1.md",
                "fix_hint": "soften 'validates' or cite Fisher",
            },
            {
                "id": "F002",
                "class": "narrative_weakness",
                "severity": "info",
                "confidence": "high",
                "issue": "central weakness paragraph...",
                "fix_target": "discussion.v1.md",
                "fix_hint": "add Limitations paragraph conceding...",
            },
        ],
    }
    review_json.write_text(json.dumps(doc), encoding="utf-8")
    result = subprocess.run(
        ["python3", str(VALIDATOR), str(review_json)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    # v0.7.0: v2 is deprecated → exit 2 (warn-only), not 0. The doc is
    # still forensically readable; the deprecation warning is on stderr.
    assert result.returncode == 2, (
        f"validator should accept v2 with deprecation warning (exit 2), "
        f"got exit {result.returncode}:\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "DEPRECATED" in result.stderr
    assert "adversarial-review-paper.v3" in result.stderr


def test_validator_accepts_synthetic_paper_v3_review(tmp_path: Path):
    """A minimum-valid adversarial-review-paper.v3 JSON must pass clean
    (exit 0). v3 is the current schema as of v0.7.0; renames
    narrative_weakness -> central_objection."""
    review_json = tmp_path / "adversarial_review.json"
    doc = {
        "schema_version": "adversarial-review-paper.v3",
        "draft_dir": str(tmp_path),
        "project_id": "fake_project",
        "draft_number": 1,
        "reviewed_at": "2026-05-03T13:42:00Z",
        "reviewer_model": "claude-sonnet-4-6",
        "prompt_version": "adversarial_paper.v3",
        "tier": "STRONG",
        "summary": {
            "total_findings": 2,
            "by_severity": {"P1": 1, "info": 1},
            "by_class": {"register_drift": 1, "central_objection": 1},
        },
        "findings": [
            {
                "id": "F001",
                "class": "register_drift",
                "severity": "P1",
                "confidence": "high",
                "section": "Results",
                "line_range": "L142-148",
                "paragraph_quote": "validates 61.7%",
                "issue": "over-claim relative to REPORT",
                "report_evidence": [
                    {"section": "§Finding 7", "quote": "binomial p=0.072"}
                ],
                "fix_target": "results.v1.md",
                "fix_hint": "soften 'validates' or cite Fisher",
            },
            {
                "id": "F002",
                "class": "central_objection",
                "severity": "info",
                "confidence": "high",
                "issue": "central objection paragraph...",
                "fix_target": "discussion.v1.md",
                "fix_hint": "add Limitations paragraph conceding...",
            },
        ],
    }
    review_json.write_text(json.dumps(doc), encoding="utf-8")
    result = subprocess.run(
        ["python3", str(VALIDATOR), str(review_json)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, (
        f"validator rejected valid paper.v3 doc:\n"
        f"stdout={result.stdout}\nstderr={result.stderr}"
    )
    assert "PASS" in result.stdout
    # v0.6.1: paper schema gets paper-aware labels
    # ("section-level" / "manuscript-wide" instead of "slide-level"
    # / "deck-level").
    assert "1 section-level finding" in result.stdout, (
        f"expected 'section-level' label for paper schema; got {result.stdout}"
    )
    assert "1 manuscript-wide finding" in result.stdout, (
        f"expected 'manuscript-wide' label for paper schema; got {result.stdout}"
    )


def test_validator_rejects_paper_v2_with_deck_level_findings_field(tmp_path: Path):
    """Paper v2 docs must NOT have deck_level_findings field — single-array
    invariant."""
    review_json = tmp_path / "adversarial_review.json"
    doc = {
        "schema_version": "adversarial-review-paper.v2",
        "draft_dir": str(tmp_path),
        "project_id": "fake_project",
        "draft_number": 1,
        "reviewed_at": "2026-05-02T13:42:00Z",
        "reviewer_model": "claude-sonnet-4-6",
        "prompt_version": "adversarial_paper.v2",
        "tier": "STRONG",
        "summary": {"total_findings": 0, "by_severity": {}, "by_class": {}},
        "findings": [],
        "deck_level_findings": [],  # ← not allowed in any v2 schema
    }
    review_json.write_text(json.dumps(doc), encoding="utf-8")
    result = subprocess.run(
        ["python3", str(VALIDATOR), str(review_json)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 1
    assert "deck_level_findings" in result.stderr
