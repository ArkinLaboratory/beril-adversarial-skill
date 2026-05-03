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


def main(argv: Optional[list[str]] = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)

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
