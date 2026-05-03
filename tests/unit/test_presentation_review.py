"""Unit tests for `beril-adversarial --type presentation`.

These tests are mechanical: they verify that

  1. The system prompt file (`adversarial_presentation.v1.md`) ships
     and contains all required sections (the 7 detection classes, the
     dual output contract, the schema_version string).
  2. The orchestrator script's `--type presentation` dispatch validates
     inputs correctly (rejects missing draft_dir, missing slide_spec,
     missing REPORT, conflicting flags) without invoking claude.
  3. SKILL.md and the slash command doc mention `--type presentation`.

No live LLM calls. No claude subprocess. The dispatch tests use a
mock `BERIL_ROOT` containing only the prompt file (provided via
--beril-root) so the script can reach SKILL_DIR resolution before its
argument-validation guards fire.

Live behavior (the reviewer producing real findings against draft_9)
is gated separately via the punch list's Tier D step; that's not in
unit-test scope because it requires a configured `claude` CLI and
costs real tokens.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


# Path to the in-source skill tree (not the installed copy). All tests
# operate on the source directly so they don't depend on `pipx install`
# state.
SKILL_DIR_SRC = (
    Path(__file__).parent.parent.parent
    / "src"
    / "beril_adversarial"
    / "skill"
)
PROMPT_PATH = SKILL_DIR_SRC / "prompts" / "adversarial_presentation.v2.md"
PROMPT_V1_DEPRECATION_STUB = SKILL_DIR_SRC / "prompts" / "adversarial_presentation.v1.md"
ORCHESTRATOR_SCRIPT = SKILL_DIR_SRC / "tools" / "adversarial_review.sh"
SKILL_MD = SKILL_DIR_SRC / "SKILL.md"
SLASH_COMMAND_MD = SKILL_DIR_SRC / "commands" / "beril-adversarial.md"


# ============================================================================
# Prompt-content tests (do not invoke any subprocess)
# ============================================================================


def test_presentation_prompt_file_exists():
    """The system prompt file must ship in the source tree."""
    assert PROMPT_PATH.is_file(), (
        f"adversarial_presentation.v2.md not found at {PROMPT_PATH}"
    )


def test_v1_prompt_either_absent_or_deprecation_stub():
    """The v1 presentation prompt file may have been git rm'd during a
    cleanup commit, OR it may still exist as a deprecation stub. Either
    is fine — what's NOT fine is the legacy v1 content being restored."""
    if not PROMPT_V1_DEPRECATION_STUB.is_file():
        # File was cleaned up — that's the cleanest end-state
        return
    text = PROMPT_V1_DEPRECATION_STUB.read_text(encoding="utf-8")
    assert "DEPRECATED" in text, (
        "v1 file must be the deprecation stub, not the legacy prompt"
    )
    # Stub should be short — if someone accidentally restored the legacy
    # content it would be 1000+ lines.
    line_count = len(text.splitlines())
    assert line_count < 50, (
        f"v1 deprecation stub is {line_count} lines — should be <50; "
        "legacy prompt content may have been restored"
    )


def test_presentation_prompt_names_all_seven_detection_classes():
    """The prompt must explicitly enumerate all 7 detection classes
    from SPEC §4. Skipping a class means the reviewer won't run it."""
    text = PROMPT_PATH.read_text(encoding="utf-8")
    required_class_markers = (
        "Class 1: throughline integrity",
        "Class 2: claim-evidence load-bearing",
        "Class 3: tier-language register",
        "Class 4: Q&A anti-strawman check",
        "Class 5: substory→slide mapping coherence",
        "Class 6: missing slides / coverage gaps",
        "Class 7: the deck's biggest narrative weakness",
    )
    for marker in required_class_markers:
        assert marker in text, f"prompt missing detection class marker: {marker!r}"


def test_presentation_prompt_documents_dual_output_contract():
    """Both audit/adversarial_review.md and audit/adversarial_review.json
    must be named in the prompt (the consumer parses by file name)."""
    text = PROMPT_PATH.read_text(encoding="utf-8")
    assert "audit/adversarial_review.md" in text, (
        "prompt does not name the .md output path"
    )
    assert "audit/adversarial_review.json" in text, (
        "prompt does not name the .json output path"
    )


def test_presentation_prompt_pins_schema_version():
    """The JSON schema_version must be the SPEC-mandated literal —
    consumers parse by exact match."""
    text = PROMPT_PATH.read_text(encoding="utf-8")
    assert "adversarial-review-presentation.v2" in text, (
        "prompt does not pin schema_version literal "
        "'adversarial-review-presentation.v2'"
    )


def test_presentation_prompt_lists_severity_grades():
    """P0/P1/P2/info must all appear; the consumer routes by severity."""
    text = PROMPT_PATH.read_text(encoding="utf-8")
    for grade in ("P0", "P1", "P2"):
        assert grade in text, f"prompt missing severity grade {grade!r}"
    assert "info" in text, (
        "prompt does not name the 'info' severity (Class 7 narrative_weakness)"
    )


def test_presentation_prompt_names_required_inputs():
    """SPEC §2 names 7 input files; the reviewer must read all of them."""
    text = PROMPT_PATH.read_text(encoding="utf-8")
    required_inputs = (
        "slide_spec.json",
        "00_throughline.md",
        "02_substories.md",
        "REPORT.md",
        "RESEARCH_PLAN.md",
        "qa_anticipated.json",
    )
    for f in required_inputs:
        assert f in text, f"prompt does not name required input file {f!r}"


def test_presentation_prompt_includes_worked_register_drift_example():
    """SPEC §6 mandates a worked example for register-drift detection.
    Without a worked example the reviewer drifts toward generic critique."""
    text = PROMPT_PATH.read_text(encoding="utf-8")
    # The worked example references slide 14's "validates 61.7%" overclaim
    # and the Fisher's combined p=0.031 supporting evidence.
    assert "61.7" in text, (
        "prompt missing the worked-example numeric anchor (61.7%)"
    )
    assert (
        "p=0.072" in text or "p=0.031" in text
    ), "prompt missing the worked-example p-value anchors"


def test_presentation_prompt_has_worked_examples_for_underfire_classes():
    """Per the v0.4.0 prompt-tightening pass, classes 1/4/5/7 each got a
    worked example (the original v0.4 draft only had examples for 2/3/6,
    which risked under-fire on the abstract classes per
    feedback_prompt_output_shape_drift.md)."""
    text = PROMPT_PATH.read_text(encoding="utf-8")
    # Each worked example is introduced by an H2 heading; check those
    # headings exist so a future edit can't silently delete them.
    for heading in (
        "## Worked example: Q&A softball detection (Class 4)",
        "## Worked example: substory-arc burial detection (Class 5)",
        "## Worked example: throughline-integrity (filler punchline) detection (Class 1)",
        "## Worked example: narrative weakness (Class 7) — the killshot",
    ):
        assert heading in text, f"prompt missing worked example: {heading!r}"


def test_presentation_prompt_has_post_v040_iteration_examples():
    """Post-first-live-run iteration added two more worked examples to
    address the two gaps the live run revealed: caveat-burial detection
    (slide 18 case the reviewer missed) and a second Q&A softball example
    showing the 'appears defensive but doesn't land' failure mode (the
    reviewer emitted 'No findings' on Q&A in the first live run, which
    is a sign-of-failure we now explicitly call out)."""
    text = PROMPT_PATH.read_text(encoding="utf-8")
    for heading in (
        "## Worked example: caveat-burial detection (Class 2 sub-pattern)",
        "## Worked example: Q&A softball — the \"appears defensive but doesn't land\" pattern",
    ):
        assert heading in text, (
            f"prompt missing post-v0.4.0-iteration worked example: {heading!r}"
        )
    # The Q&A re-do trigger phrase
    assert "SIGN OF FAILURE" in text, (
        "self-skepticism Q&A check missing the explicit re-do trigger"
    )
    # The caveat-burial cross-reference in self-skepticism
    assert "caveat-burial" in text.lower(), (
        "self-skepticism claim_evidence check missing caveat-burial reference"
    )


def test_presentation_prompt_marks_suggested_fixes_section_required():
    """First live run shipped with an empty Suggested-fixes section. The
    prompt must explicitly mark this section as required so the model
    doesn't emit a heading and stop."""
    text = PROMPT_PATH.read_text(encoding="utf-8")
    assert "REQUIRED" in text and "Suggested-fixes" in text, (
        "prompt does not flag Suggested-fixes section as REQUIRED"
    )


def test_presentation_prompt_self_skepticism_has_per_class_check():
    """The self-skepticism pass must include the per-class verification
    step that asks 'did I produce at least one finding per class, or can
    I justify why the class doesn't apply?'. This is the v0.4.0 guard
    against under-fire on abstract classes."""
    text = PROMPT_PATH.read_text(encoding="utf-8")
    assert "per-class" in text.lower() or "in EACH of these classes" in text, (
        "self-skepticism pass missing the per-class detection check"
    )


def test_presentation_prompt_grants_narrow_tools():
    """Per SPEC §6, the reviewer should NOT have WebSearch (would invite
    citation fabrication) or Bash (would drift from on-disk files).
    The prompt's tool-use section should reflect the narrower grant."""
    text = PROMPT_PATH.read_text(encoding="utf-8")
    # The tool-use section should explicitly list Read, Write, Grep, Glob.
    assert "Read" in text and "Write" in text and "Grep" in text, (
        "prompt does not list the expected tool grant"
    )
    # Should explicitly note WebSearch is not granted.
    assert "WebSearch" in text and "not" in text.lower(), (
        "prompt does not mention WebSearch (positive or negative); "
        "expected it to explicitly state WebSearch is not granted"
    )


# ============================================================================
# Orchestrator-script dispatch tests (invoke bash but no claude)
# ============================================================================


@pytest.fixture
def mock_beril_root(tmp_path: Path) -> Path:
    """Build a minimal BERIL root containing the skill tree.

    The dispatch tests need SKILL_DIR resolution to succeed so they can
    exercise the presentation-specific argument validation. Copying the
    real skill tree (rather than synthesizing it) ensures the test
    catches refactors that move/rename the prompt file.
    """
    beril_root = tmp_path / "mock_beril"
    skill_dir = beril_root / ".claude" / "skills" / "beril-adversarial"
    skill_dir.mkdir(parents=True)
    # Copy prompts/, tools/ — the parts the dispatch path reads.
    for sub in ("prompts", "tools"):
        shutil.copytree(SKILL_DIR_SRC / sub, skill_dir / sub)
    # Create state/ (script does mkdir -p, but pre-creating is harmless).
    (skill_dir / "state").mkdir()
    return beril_root


@pytest.fixture
def mock_draft_dir(tmp_path: Path) -> Path:
    """Build a minimal valid draft_dir + project_dir.

    Includes only the structurally required files. No real content; the
    dispatch tests don't invoke claude, so an empty `slide_spec.json`
    is fine for argument-validation purposes.
    """
    project_dir = tmp_path / "mock_project"
    draft_dir = project_dir / "talks" / "draft_test"
    (draft_dir / "03_slides").mkdir(parents=True)

    # Project-level required files
    (project_dir / "REPORT.md").write_text("# Report\n", encoding="utf-8")
    (project_dir / "RESEARCH_PLAN.md").write_text(
        "# Plan\n", encoding="utf-8"
    )

    # Draft-level required files (empty JSON / markdown is fine for dispatch)
    (draft_dir / "slide_spec.json").write_text(
        '{"schema_version": "1.0", "slides": []}', encoding="utf-8"
    )
    (draft_dir / "00_throughline.md").write_text(
        "# Throughline\n", encoding="utf-8"
    )
    (draft_dir / "02_substories.md").write_text(
        "# Substories\n", encoding="utf-8"
    )
    (draft_dir / "03_slides" / "qa_anticipated.json").write_text(
        '{"slides": []}', encoding="utf-8"
    )
    return draft_dir


def _run_script(args: list[str], beril_root: Path) -> subprocess.CompletedProcess:
    """Invoke the orchestrator script with the given args + beril_root."""
    return subprocess.run(
        ["bash", str(ORCHESTRATOR_SCRIPT), *args, "--beril-root", str(beril_root)],
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_dispatch_help_lists_presentation_type():
    """Help text must mention --type presentation so users discover it."""
    result = subprocess.run(
        ["bash", str(ORCHESTRATOR_SCRIPT), "--help"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert "presentation" in result.stdout, (
        "--help output does not mention 'presentation' — "
        "users won't discover the new mode"
    )


def test_dispatch_invalid_type_rejects_with_useful_error():
    """An unknown --type must reject with all four valid options listed."""
    result = subprocess.run(
        ["bash", str(ORCHESTRATOR_SCRIPT), "foo", "--type", "garbage"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert "presentation" in result.stderr or "presentation" in result.stdout, (
        "error message does not list 'presentation' as a valid type"
    )


def test_dispatch_presentation_requires_draft_dir(mock_beril_root: Path):
    """--type presentation with no positional argument must error
    (cwd auto-detection is not supported for this type)."""
    result = subprocess.run(
        [
            "bash", str(ORCHESTRATOR_SCRIPT),
            "--type", "presentation",
            "--beril-root", str(mock_beril_root),
        ],
        capture_output=True,
        text=True,
        cwd="/tmp",  # ensure not inside a projects/ tree
        timeout=30,
    )
    assert result.returncode != 0
    assert "draft_dir" in result.stderr.lower() + result.stdout.lower(), (
        "error message does not mention draft_dir"
    )


def test_dispatch_presentation_rejects_nonexistent_draft_dir(
    mock_beril_root: Path, tmp_path: Path
):
    """A draft_dir that doesn't exist must fail fast with exit code 2."""
    result = _run_script(
        [
            str(tmp_path / "nonexistent_draft"),
            "--type", "presentation",
        ],
        mock_beril_root,
    )
    assert result.returncode == 2
    assert "does not exist" in result.stderr or "does not exist" in result.stdout


def test_dispatch_presentation_rejects_draft_dir_missing_slide_spec(
    mock_beril_root: Path, tmp_path: Path
):
    """A draft_dir without slide_spec.json must fail with exit code 2
    naming the missing file."""
    incomplete = tmp_path / "incomplete_draft"
    incomplete.mkdir()
    result = _run_script(
        [str(incomplete), "--type", "presentation"],
        mock_beril_root,
    )
    assert result.returncode == 2
    output = result.stderr + result.stdout
    assert "slide_spec.json" in output, (
        f"error did not name slide_spec.json; got:\n{output}"
    )


def test_dispatch_presentation_rejects_missing_report(
    mock_beril_root: Path, tmp_path: Path
):
    """A draft_dir whose grandparent has no REPORT.md must fail with
    exit code 2 — REPORT is the truth source for quantitative grounding."""
    # Build a draft_dir but DON'T create the project-level REPORT.md
    project_dir = tmp_path / "no_report_project"
    draft_dir = project_dir / "talks" / "draft_test"
    (draft_dir / "03_slides").mkdir(parents=True)
    # Required draft-level files
    (draft_dir / "slide_spec.json").write_text("{}", encoding="utf-8")
    (draft_dir / "00_throughline.md").write_text("", encoding="utf-8")
    (draft_dir / "02_substories.md").write_text("", encoding="utf-8")
    (draft_dir / "03_slides" / "qa_anticipated.json").write_text(
        "{}", encoding="utf-8"
    )
    # Note: no REPORT.md in project_dir.

    result = _run_script(
        [str(draft_dir), "--type", "presentation"],
        mock_beril_root,
    )
    assert result.returncode == 2
    output = result.stderr + result.stdout
    assert "REPORT.md" in output, (
        f"error did not name REPORT.md; got:\n{output}"
    )


def test_dispatch_presentation_rejects_consolidate(
    mock_beril_root: Path, mock_draft_dir: Path
):
    """--consolidate is a paper/project/plan concept; reject for presentation."""
    result = _run_script(
        [str(mock_draft_dir), "--type", "presentation", "--consolidate"],
        mock_beril_root,
    )
    assert result.returncode != 0
    output = result.stderr + result.stdout
    assert "consolidate" in output.lower(), (
        f"error did not mention --consolidate rejection; got:\n{output}"
    )


def test_dispatch_presentation_rejects_codex_fusion(
    mock_beril_root: Path, mock_draft_dir: Path
):
    """--reviewer claude,codex fusion is paper/project/plan-shaped;
    presentation v1 is single-pass."""
    result = _run_script(
        [
            str(mock_draft_dir),
            "--type", "presentation",
            "--reviewer", "claude,codex",
        ],
        mock_beril_root,
    )
    assert result.returncode != 0
    output = result.stderr + result.stdout
    assert "fusion" in output.lower() or "codex" in output.lower(), (
        f"error did not mention codex/fusion rejection; got:\n{output}"
    )


def test_dispatch_presentation_rejects_codex_solo(
    mock_beril_root: Path, mock_draft_dir: Path
):
    """codex-only path doesn't have programmatic Write detection;
    reject for presentation since dual-file output requires verification."""
    result = _run_script(
        [
            str(mock_draft_dir),
            "--type", "presentation",
            "--reviewer", "codex",
        ],
        mock_beril_root,
    )
    assert result.returncode != 0
    output = result.stderr + result.stdout
    assert "codex" in output.lower(), (
        f"error did not mention codex rejection; got:\n{output}"
    )


# ============================================================================
# Skill documentation tests
# ============================================================================


def test_skill_md_documents_presentation_type():
    """SKILL.md must mention --type presentation so users / Claude
    Code discover the new mode at skill-listing time."""
    text = SKILL_MD.read_text(encoding="utf-8")
    assert "presentation" in text, (
        "SKILL.md does not mention 'presentation' — Claude Code "
        "skill-list will not surface the new mode"
    )


def test_slash_command_md_documents_presentation_type():
    """The /beril-adversarial slash command doc must mention the
    presentation type and the dual-output contract."""
    text = SLASH_COMMAND_MD.read_text(encoding="utf-8")
    assert "presentation" in text
    assert "draft_dir" in text or "talks/" in text, (
        "slash command doc does not explain the draft_dir argument shape"
    )


def test_install_skill_includes_presentation_prompt():
    """Verify that the prompts/ directory shipped via install-skill
    contains the presentation prompt. We probe at the source-tree
    level since that's where install-skill copies from."""
    assert (SKILL_DIR_SRC / "prompts" / "adversarial_presentation.v2.md").is_file(), (
        "presentation v2 prompt not in shipped prompts/ — install-skill "
        "will not deploy it"
    )


# ============================================================================
# Hard-error guards (catch regressions in the dispatch wiring)
# ============================================================================


def test_orchestrator_script_syntactically_valid():
    """`bash -n` must accept the script. Catches stray-brace / quote
    bugs before they hit a real run."""
    result = subprocess.run(
        ["bash", "-n", str(ORCHESTRATOR_SCRIPT)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, (
        f"bash -n rejected the script:\n{result.stderr}"
    )


def test_orchestrator_script_validates_type_with_four_values():
    """Verify the --type validation block lists all four values.
    Regression guard: an early implementation only accepted three."""
    text = ORCHESTRATOR_SCRIPT.read_text(encoding="utf-8")
    assert '"$REVIEW_TYPE" != "plan"' in text
    assert '"$REVIEW_TYPE" != "project"' in text
    assert '"$REVIEW_TYPE" != "paper"' in text
    assert '"$REVIEW_TYPE" != "presentation"' in text
