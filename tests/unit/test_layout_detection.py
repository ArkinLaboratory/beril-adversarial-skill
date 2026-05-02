"""Tests for adversarial_review.sh's v0.3.1+/v0.3.0 layout detection.

v0.5.2 added cross-version draft layout support: the bash script
detects whether the draft uses presentation-maker's v0.3.1+ 4-zone
layout (working/, narrative/, audit/, deliverable/) or the v0.3.0
flat layout, and resolves required-input paths accordingly.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "src/beril_adversarial/skill/tools/adversarial_review.sh"
)


def _setup_beril_root(tmp_path: Path) -> Path:
    """Build a synthetic BERIL root with .claude/skills/ + symlinked
    adversarial skill so the script's preflight passes."""
    beril_root = tmp_path / "beril"
    skills = beril_root / ".claude" / "skills"
    skills.mkdir(parents=True)
    # Symlink the actual adversarial skill so the script's tools/
    # discovery resolves.
    skill_src = SCRIPT.parent.parent
    (skills / "beril-adversarial").symlink_to(skill_src)
    return beril_root


def _run(draft_dir: Path, beril_root: Path,
         *extra_args: str) -> subprocess.CompletedProcess:
    cmd = ["bash", str(SCRIPT), str(draft_dir), "--type", "presentation",
           "--beril-root", str(beril_root), *extra_args]
    return subprocess.run(cmd, capture_output=True, text=True)


def _mk_v031_in(beril_root: Path) -> Path:
    """Build a synthetic v0.3.1+ draft inside beril_root/projects/."""
    project = beril_root / "projects" / "demo"
    draft = project / "talks" / "draft_1"
    for zone in ("deliverable", "narrative", "working", "audit"):
        (draft / zone).mkdir(parents=True)
    (draft / "working" / "03_slides").mkdir()
    (draft / "working" / "slide_spec.json").write_text("{}")
    (draft / "narrative" / "00_throughline.md").write_text("# tl")
    (draft / "narrative" / "02_substories.md").write_text("# sub")
    (draft / "working" / "03_slides" / "qa_anticipated.json").write_text("{}")
    (project / "REPORT.md").write_text("# report")
    return draft


def _mk_v030_in(beril_root: Path) -> Path:
    """Build a synthetic v0.3.0 legacy draft inside beril_root/projects/."""
    project = beril_root / "projects" / "demo"
    draft = project / "talks" / "draft_1"
    (draft / "03_slides").mkdir(parents=True)
    (draft / "slide_spec.json").write_text("{}")
    (draft / "00_throughline.md").write_text("# tl")
    (draft / "02_substories.md").write_text("# sub")
    (draft / "03_slides" / "qa_anticipated.json").write_text("{}")
    (project / "REPORT.md").write_text("# report")
    return draft


def test_detects_v031_layout(tmp_path: Path):
    beril = _setup_beril_root(tmp_path)
    draft = _mk_v031_in(beril)
    result = _run(draft, beril)
    assert "detected presentation-maker draft layout: v0.3.1+" in result.stderr, (
        f"expected v0.3.1+ detection in stderr; got:\n{result.stderr}"
    )


def test_detects_v030_legacy_layout(tmp_path: Path):
    beril = _setup_beril_root(tmp_path)
    draft = _mk_v030_in(beril)
    result = _run(draft, beril)
    assert "detected presentation-maker draft layout: v0.3.0-legacy" in result.stderr, (
        f"expected v0.3.0-legacy detection in stderr; got:\n{result.stderr}"
    )


def test_rejects_draft_without_slide_spec(tmp_path: Path):
    """Neither layout has slide_spec.json → clear error mentioning both
    expected paths."""
    beril = _setup_beril_root(tmp_path)
    project = beril / "projects" / "demo"
    draft = project / "talks" / "draft_1"
    draft.mkdir(parents=True)
    (project / "REPORT.md").write_text("# report")

    result = _run(draft, beril)
    assert result.returncode == 2
    assert "slide_spec.json" in result.stderr
    assert "v0.3.1+" in result.stderr
    assert "v0.3.0 legacy" in result.stderr


def test_v031_partial_layout_reports_specific_missing_file(tmp_path: Path):
    """v0.3.1+ slide_spec exists but throughline missing → error names
    the v0.3.1+ path."""
    beril = _setup_beril_root(tmp_path)
    draft = _mk_v031_in(beril)
    (draft / "narrative" / "00_throughline.md").unlink()
    result = _run(draft, beril)
    assert result.returncode == 2
    assert "narrative/00_throughline.md" in result.stderr
    assert "v0.3.1+ layout but is incomplete" in result.stderr


def test_v030_partial_layout_reports_specific_missing_file(tmp_path: Path):
    """v0.3.0 legacy slide_spec exists but throughline missing → error
    names the legacy path."""
    beril = _setup_beril_root(tmp_path)
    draft = _mk_v030_in(beril)
    (draft / "00_throughline.md").unlink()
    result = _run(draft, beril)
    assert result.returncode == 2
    assert "00_throughline.md" in result.stderr
    # Should NOT mention narrative/ since this is a v0.3.0 layout
    assert "narrative/00_throughline.md" not in result.stderr
