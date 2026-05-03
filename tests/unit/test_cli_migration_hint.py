"""Unit tests for the v0.5.x → v0.6+ CLI migration hint in beril_adversarial.cli.

The CLI gained a required `review` subcommand in v0.6.0. Pre-v0.6.0 invocations
(`beril-adversarial --type <kind> <project_id>`) should produce a tailored
migration hint pointing at CONTRACT.md, NOT the default argparse usage error.

Driven by paper-writer team's draft_9 incident (2026-05-03) where the
orchestrator captured argparse stderr as the canonical adversarial review.
"""

from __future__ import annotations

import pytest

from beril_adversarial.cli import _detect_pre_v060_shape, main


class TestDetectPreV060Shape:
    """The detector returns a string hint for v0.5.x-shape; None otherwise."""

    def test_review_subcommand_present_no_hint(self):
        # Even with --type, presence of `review` means user is on new shape.
        assert _detect_pre_v060_shape(["review", "--type", "paper", "/tmp/draft_3"]) is None

    def test_help_no_hint(self):
        assert _detect_pre_v060_shape(["--help"]) is None
        assert _detect_pre_v060_shape(["-h"]) is None

    def test_version_no_hint(self):
        assert _detect_pre_v060_shape(["--version"]) is None

    def test_empty_args_no_hint(self):
        assert _detect_pre_v060_shape([]) is None

    def test_install_skill_subcommand_no_hint(self):
        assert _detect_pre_v060_shape(["install-skill", "/path/to/beril"]) is None

    def test_v05x_paper_invocation_returns_hint(self):
        hint = _detect_pre_v060_shape(["--type", "paper", "fdm_test"])
        assert hint is not None
        assert "v0.6.0" in hint
        assert "review --type paper" in hint
        assert "<draft_dir>" in hint
        assert "CONTRACT.md" in hint

    def test_v05x_presentation_invocation_returns_hint(self):
        hint = _detect_pre_v060_shape(["--type", "presentation", "fdm_test"])
        assert hint is not None
        assert "review --type presentation" in hint
        assert "<draft_dir>" in hint

    def test_v05x_project_invocation_returns_hint_with_project_id(self):
        # For project/plan, the new positional is still <project_id>, not <draft_dir>.
        hint = _detect_pre_v060_shape(["--type", "project", "fdm_test"])
        assert hint is not None
        assert "review --type project" in hint
        assert "<project_id>" in hint
        # No draft_dir note for project type
        assert "per-draft directory layout" not in hint

    def test_v05x_short_t_flag_returns_hint(self):
        hint = _detect_pre_v060_shape(["-t", "paper", "fdm_test"])
        assert hint is not None
        assert "review --type paper" in hint

    def test_v05x_with_extra_flags_still_detected(self):
        hint = _detect_pre_v060_shape(["--type", "paper", "--output", "review.md", "fdm_test"])
        assert hint is not None

    def test_type_at_end_handled_gracefully(self):
        # Edge case: --type with no value following (malformed).
        hint = _detect_pre_v060_shape(["--type"])
        # Should still detect v0.5.x shape, with kind defaulting to placeholder.
        assert hint is not None
        assert "<kind>" in hint or "review" in hint


class TestMainWithPreV060Shape:
    """End-to-end: main() should print the hint to stderr and return 1."""

    def test_v05x_paper_invocation_returns_1_and_prints_hint(self, capsys):
        rc = main(["--type", "paper", "fdm_test"])
        assert rc == 1
        captured = capsys.readouterr()
        assert "v0.6.0" in captured.err
        assert "CONTRACT.md" in captured.err

    def test_v05x_presentation_invocation_returns_1_and_prints_hint(self, capsys):
        rc = main(["--type", "presentation", "fdm_test"])
        assert rc == 1
        captured = capsys.readouterr()
        assert "review --type presentation" in captured.err

    def test_help_does_not_trigger_hint(self, capsys):
        # --help triggers SystemExit(0) from argparse; hint should NOT fire.
        with pytest.raises(SystemExit) as exc_info:
            main(["--help"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        # Help text goes to stdout, not stderr; no migration hint should be present.
        assert "v0.6.0" not in captured.err
        assert "CONTRACT.md" not in captured.err

    def test_review_subcommand_passes_through_to_argparse(self):
        # `review --help` should produce the review subcommand's own help, not the hint.
        with pytest.raises(SystemExit) as exc_info:
            main(["review", "--help"])
        assert exc_info.value.code == 0
