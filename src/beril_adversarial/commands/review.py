"""`beril-adversarial review` — programmatic entry point for adversarial review.

Thin Python wrapper around the shipped `tools/adversarial_review.sh`
shell script. The shell script is the single source of truth for review
orchestration (claude invocation, retry logic, validator dispatch,
auto-correction). This subcommand provides:

- A discoverable CLI surface (so callers like paper_writer.sh don't need
  to know the deep filesystem path to the shell script).
- argparse-based input validation + helpful error messages.
- Subprocess delegation with exit-code preservation.

Usage:
    beril-adversarial review <project_or_draft_dir> --type {paper|presentation|plan|project} \\
        [--model MODEL] [--reviewer claude|codex|claude,codex] \\
        [--depth quick|standard|deep] [--output OUT_PATH] \\
        [--beril-root PATH] [--no-stream] [--no-critic] \\
        [--no-verify-citations] [--consolidate]

Positional argument shape varies by --type:
- paper / presentation: <draft_dir> (absolute path to per-draft directory).
- plan / project: <project_id> (project name under projects/).

Exit codes (preserved from the shell script):
- 0  success
- 1  user error (bad args, validation failure)
- 2  runtime error (subprocess failed, output not produced; OR validator
     auto-corrected and emitted advisory warnings — non-fatal)
- 3  config error (claude CLI not installed, prompt missing)
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from importlib import resources
from pathlib import Path

from beril_adversarial import discovery


VALID_TYPES = ("plan", "project", "paper", "presentation")
VALID_REVIEWERS = ("claude", "codex", "claude,codex")
VALID_DEPTHS = ("quick", "standard", "deep")


def add_parser(subparsers: argparse._SubParsersAction) -> argparse.ArgumentParser:
    p = subparsers.add_parser(
        "review",
        help="Run an adversarial review of a paper, presentation, project, or plan.",
        description=(
            "Programmatic entry point for adversarial review. Delegates to "
            "the shipped tools/adversarial_review.sh shell script.\n\n"
            "Positional argument is a draft_dir (absolute path) for "
            "--type paper or --type presentation, or a project_id for "
            "--type plan or --type project.\n\n"
            "Exit codes match the shell script: 0 success, 1 user error, "
            "2 runtime error or advisory warning, 3 config error."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "target",
        help=(
            "draft_dir (absolute path) for --type paper|presentation, OR "
            "project_id (under projects/) for --type plan|project."
        ),
    )
    p.add_argument(
        "--type",
        dest="review_type",
        required=True,
        choices=VALID_TYPES,
        help="What to review.",
    )
    p.add_argument(
        "--model",
        help=(
            "Claude model override (default: configured in the shell "
            "script, currently claude-sonnet-4-6)."
        ),
    )
    p.add_argument(
        "--reviewer",
        choices=VALID_REVIEWERS,
        help=(
            "Backend reviewer (default: claude). claude,codex runs both "
            "in parallel and fuses (only supported for --type plan/project/paper "
            "legacy path; presentation+paper v2 modes are single-pass)."
        ),
    )
    p.add_argument(
        "--depth",
        choices=VALID_DEPTHS,
        help=(
            "Review depth (default: standard). Only --type plan/project/paper "
            "legacy paths use this; presentation and paper v2 are single-depth."
        ),
    )
    p.add_argument(
        "--output",
        help=(
            "Override output path (--type plan/project/paper legacy only; "
            "ignored for presentation and paper v2 which write to "
            "<draft_dir>/audit/adversarial_review.{md,json})."
        ),
    )
    p.add_argument(
        "--beril-root",
        help=(
            "BERIL_ROOT directory containing .claude/skills/. Auto-detected "
            "from cwd or environment if not provided."
        ),
    )
    p.add_argument(
        "--no-stream",
        action="store_true",
        help="Disable stream-json parser (legacy paper/project/plan only).",
    )
    p.add_argument(
        "--no-critic",
        action="store_true",
        help="Disable compliance critic (legacy paper/project/plan only).",
    )
    p.add_argument(
        "--no-verify-citations",
        action="store_true",
        help="Disable citation verification gate (legacy paper/project/plan only).",
    )
    p.add_argument(
        "--consolidate",
        action="store_true",
        help=(
            "Synthesize all numbered reviews of matching --type into a "
            "canonical file (legacy paper/project/plan only; not supported "
            "for presentation or paper v2)."
        ),
    )
    p.set_defaults(func=run)
    return p


def _locate_shell_script(beril_root: Path | None) -> Path:
    """Resolve the path to tools/adversarial_review.sh.

    Resolution priority:
    1. BERIL_ROOT/.claude/skills/beril-adversarial/tools/adversarial_review.sh
       (if BERIL_ROOT is provided/discovered AND the script is there).
    2. The shipped copy inside the installed package
       (importlib.resources). Useful when the skill hasn't been installed
       into a BERIL deployment yet — Python wrapper can still invoke
       the script directly from the package.
    """
    # Path 1: deployed location under BERIL_ROOT
    if beril_root is not None:
        deployed = (
            beril_root
            / ".claude"
            / "skills"
            / "beril-adversarial"
            / "tools"
            / "adversarial_review.sh"
        )
        if deployed.is_file():
            return deployed

    # Path 2: shipped copy inside the package
    try:
        package_files = resources.files("beril_adversarial.skill.tools")
        shipped = Path(str(package_files / "adversarial_review.sh"))
        if shipped.is_file():
            return shipped
    except (ModuleNotFoundError, AttributeError):
        pass

    raise FileNotFoundError(
        "Could not locate adversarial_review.sh in any of:\n"
        "  - <BERIL_ROOT>/.claude/skills/beril-adversarial/tools/\n"
        "  - the installed package's bundled skill/tools/\n"
        "Did you run `beril-adversarial install-skill <BERIL_ROOT>`?"
    )


def run(args: argparse.Namespace) -> int:
    # Resolve BERIL_ROOT (best-effort; the shell script will re-derive
    # if needed via its own resolution logic).
    beril_root = None
    explicit_root = getattr(args, "beril_root", None)
    try:
        beril_root = discovery.find_beril_root(explicit=explicit_root)
    except discovery.BerilRootNotFound:
        # OK — the shell script can also auto-resolve from its own
        # install path.
        if explicit_root is not None:
            # User provided an explicit --beril-root that doesn't exist
            # → hard error.
            print(
                f"Error: --beril-root path does not look like a BERIL root: "
                f"{explicit_root}",
                file=sys.stderr,
            )
            print(
                "  Expected to find .claude/skills/ under it.",
                file=sys.stderr,
            )
            return 1

    # Locate the shell script
    try:
        script_path = _locate_shell_script(beril_root)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 3

    if not shutil.which("bash"):
        print("Error: 'bash' not found on PATH; required to run review.", file=sys.stderr)
        return 3

    # Build the shell command
    cmd = ["bash", str(script_path), args.target, "--type", args.review_type]
    if args.model:
        cmd += ["--model", args.model]
    if args.reviewer:
        cmd += ["--reviewer", args.reviewer]
    if args.depth:
        cmd += ["--depth", args.depth]
    if args.output:
        cmd += ["--output", args.output]
    if explicit_root:
        cmd += ["--beril-root", explicit_root]
    elif beril_root is not None:
        cmd += ["--beril-root", str(beril_root)]
    if args.no_stream:
        cmd += ["--no-stream"]
    if args.no_critic:
        cmd += ["--no-critic"]
    if args.no_verify_citations:
        cmd += ["--no-verify-citations"]
    if args.consolidate:
        cmd += ["--consolidate"]

    # Delegate. Pass through stdout/stderr; preserve exit code.
    # Use os.execvp would replace the current process and lose any
    # cleanup; subprocess.run with stdin/stdout passthrough is safer
    # for an installed CLI.
    try:
        result = subprocess.run(
            cmd,
            stdin=sys.stdin if sys.stdin.isatty() else subprocess.DEVNULL,
            check=False,
        )
        return int(result.returncode)
    except KeyboardInterrupt:
        print("\nReview interrupted.", file=sys.stderr)
        return 130
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 3
