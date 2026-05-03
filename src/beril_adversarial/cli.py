"""`beril-adversarial` top-level CLI entry point.

Dispatches to command modules under beril_adversarial.commands/.

Subcommands:
  install-skill  Copy shipped skill/ tree into BERIL/.claude/skills/beril-adversarial/.
  configure      Verify claude/codex CLIs are present and tools work.
  review         Run an adversarial review (paper, presentation, plan, project).
                 Programmatic entry point — thin wrapper around the shipped
                 tools/adversarial_review.sh shell script. Suitable for
                 invocation from other skills' orchestrators (e.g.,
                 paper_writer.sh).

Exit codes:
  0  success
  1  user error (bad args, missing BERIL_ROOT, missing file user should fix)
  2  runtime error (subprocess failed; OR validator auto-corrected with
     advisory warnings — the .json is still consumer-safe)
  3  config error (claude/codex not installed; tools unavailable)
"""

from __future__ import annotations

import argparse
import sys
from typing import Optional

from beril_adversarial import __version__
from beril_adversarial.commands import (
    configure,
    install_skill,
    review,
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="beril-adversarial",
        description=(
            "BERIL Adversarial Reviewer — harsher review with multi-model "
            "fusion and provenance-tracked consolidation. See "
            "https://github.com/ArkinLaboratory/beril-adversarial-skill."
        ),
    )
    p.add_argument(
        "--version",
        action="version",
        version=f"beril-adversarial-skill {__version__}",
    )
    subparsers = p.add_subparsers(dest="command", metavar="<command>")

    install_skill.add_parser(subparsers)
    configure.add_parser(subparsers)
    review.add_parser(subparsers)

    return p


def _detect_pre_v060_shape(raw_argv: list[str]) -> Optional[str]:
    """Detect v0.5.x-shape invocations and return a migration hint.

    The CLI gained a required `review` subcommand in v0.6.0. Prior to v0.6.0,
    the orchestrator was invoked as `beril-adversarial --type <kind> <project_id>`.
    Consumers (e.g., paper-writer's paper_writer.sh) that haven't migrated to
    the new shape produce argparse usage errors that are confusing without
    context.

    If we detect `--type` (or `-t`) at the top level WITHOUT a preceding
    `review` subcommand, return a tailored migration hint pointing at
    CONTRACT.md. Otherwise return None and let argparse handle normally.

    Returns: hint string or None.
    """
    if "review" in raw_argv:
        # Subcommand present — let argparse handle whatever issue comes up.
        return None

    if "--type" in raw_argv or "-t" in raw_argv:
        # v0.5.x-shape invocation: --type at top level, no `review` subcommand.
        # Reconstruct the new-shape command for the hint.
        try:
            type_idx = raw_argv.index("--type") if "--type" in raw_argv else raw_argv.index("-t")
            kind = raw_argv[type_idx + 1] if type_idx + 1 < len(raw_argv) else "<kind>"
        except (ValueError, IndexError):
            kind = "<kind>"

        # The trailing positional was <project_id> in v0.5.x; in v0.6+ it's
        # <draft_dir> for paper/presentation, <project_id> for project/plan.
        if kind in ("paper", "presentation"):
            new_positional = "<draft_dir>"
            extra_note = (
                "\nNOTE: For --type paper|presentation, the trailing positional "
                "is now <draft_dir> (e.g., papers/draft_3 or talks/draft_5), NOT "
                "<project_id>. The reviewer reads from a per-draft directory layout."
            )
        else:
            new_positional = "<project_id>"
            extra_note = ""

        return (
            f"\nberil-adversarial CLI changed in v0.6.0.\n\n"
            f"OLD shape (pre-v0.6.0):\n"
            f"  beril-adversarial --type {kind} <positional>\n\n"
            f"NEW shape (v0.6.0+):\n"
            f"  beril-adversarial review --type {kind} {new_positional}\n"
            f"{extra_note}\n\n"
            f"See CONTRACT.md in the beril-adversarial-skill repo for the "
            f"full migration guide:\n"
            f"  https://github.com/ArkinLaboratory/beril-adversarial-skill/blob/main/CONTRACT.md\n"
        )

    return None


def main(argv: Optional[list[str]] = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)

    # Detect v0.5.x-shape invocations and emit a migration hint before
    # argparse produces a less-informative usage error.
    pre_v060_hint = _detect_pre_v060_shape(raw_argv)
    if pre_v060_hint is not None:
        print(pre_v060_hint, file=sys.stderr)
        return 1

    parser = build_parser()
    args = parser.parse_args(raw_argv)

    if not args.command:
        parser.print_help()
        return 1

    func = getattr(args, "func", None)
    if func is None:
        print(f"Error: unknown command {args.command!r}", file=sys.stderr)
        return 1

    try:
        return int(func(args) or 0)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
