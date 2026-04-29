#!/usr/bin/env python3
"""Programmatic post-checker for adversarial_review.json files.

Validates that a presentation reviewer's JSON output conforms to the
``adversarial-review-presentation.v1`` schema and is internally
consistent. Replicates the proven post-checker pattern used by
paper-writer (see memory: feedback_prompt_discipline_needs_post_check.md).

The reviewer's prompt instructs it to recount summary blocks before
emitting; this script enforces that programmatically because prompt-
level discipline alone has been shown to drift in practice.

Behavior on summary count mismatch (added in v0.4.1):
  The findings array is ground truth; the summary block is derived data.
  LLMs are intrinsically bad at arithmetic-on-self-output, so summary
  count mismatches happen even with explicit recount instructions in
  the prompt. Rather than fail the run, the validator AUTO-CORRECTS the
  summary by recomputing it from the findings array, writes the
  corrected JSON in place, preserves the original (mismatched) summary
  to a sidecar `.original-summary.json` for forensics, and exits with
  warning (code 2) instead of failure (code 1). The .json becomes
  consumer-safe automatically; the LLM's arithmetic failure is logged.

  This auto-correction does NOT mutate the findings array (which is the
  ground truth) — only the summary fields. Other validation errors
  (schema violation, missing required fields, invalid enum values,
  duplicate IDs, narrative_weakness invariant violations) still cause
  exit code 1 because they cannot be auto-corrected without changing
  semantics.

Exit codes:
  0  pass (all required fields present, counts match, schema literal OK)
  1  fail (non-correctable validation errors; details on stderr)
  2  warn-only (advisory issues OR auto-corrected summary mismatch)
  3  cli/usage error

Stdout is one summary line on success, e.g.:
  PASS: 17 slide-level findings, 2 deck-level findings (3 P0, 9 P1, 5 P2, 1 info)

Stderr carries diagnostic detail. When auto-correction is applied,
stderr also includes a "AUTO-CORRECTED" block listing the original
miscounts and the corrected values.

Usage:
    python3 validate_presentation_review.py <path/to/adversarial_review.json>
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

# Supported schema versions. v2 is the current emit; v1 is accepted
# for forensic compatibility with audit files from v0.4.x runs (e.g.,
# the draft_9 / draft_10 audits). New reviewer runs (v0.5.0+) emit v2
# only.
SCHEMA_VERSION_V1 = "adversarial-review-presentation.v1"
SCHEMA_VERSION_V2 = "adversarial-review-presentation.v2"
ACCEPTED_SCHEMA_VERSIONS = {SCHEMA_VERSION_V1, SCHEMA_VERSION_V2}
CURRENT_SCHEMA_VERSION = SCHEMA_VERSION_V2

# Backwards-compat alias for code that imported the v1 literal directly.
SCHEMA_VERSION_LITERAL = SCHEMA_VERSION_V1

# Severity values that can appear in findings (info is reserved for
# the single Class 7 narrative_weakness finding).
VALID_SEVERITIES = {"P0", "P1", "P2", "info"}

# Class values per SPEC §4.
VALID_CLASSES = {
    "throughline",
    "claim_evidence",
    "register_drift",
    "qa_softball",
    "substory_arc",
    "missing_slide",
    "unbacked_quantitative",
    "narrative_weakness",
}

VALID_CONFIDENCES = {"high", "medium", "low"}

# Fields required on every finding (slide-level and deck-level).
COMMON_REQUIRED_FIELDS = {
    "id",
    "class",
    "severity",
    "confidence",
    "issue",
    "fix_target",
    "fix_hint",
}

# Fields additionally required on slide-level findings.
SLIDE_LEVEL_REQUIRED_FIELDS = {
    "slide_id",
    "slide_position",
    "slide_layout",
    "title_quote",
}

# If the deck has at least this many slides AND the reviewer found
# zero P0 findings, emit a warning (advisory only — exit 2). The
# spec's representative draft_9 has 26 slides + 3 P0s; a zero-P0
# review on a deck this size strongly suggests reviewer under-fire.
ZERO_P0_WARN_SLIDE_THRESHOLD = 20


def compute_correct_summary(
    findings: list[Any], deck_findings: list[Any]
) -> dict[str, Any]:
    """Derive the canonical summary block from the findings arrays.

    The summary is purely derived data; this function is the source of
    truth. Used both for validation (compare against declared summary)
    and for auto-correction (rewrite a mismatched summary).

    Returns a dict matching the SPEC §3 summary schema.
    """
    sev_counter: Counter[str] = Counter()
    cls_counter: Counter[str] = Counter()
    for arr in (findings, deck_findings):
        for f in arr:
            if not isinstance(f, dict):
                continue
            sev = f.get("severity")
            if sev in VALID_SEVERITIES:
                sev_counter[sev] += 1
            cls = f.get("class")
            if cls in VALID_CLASSES:
                cls_counter[cls] += 1
    return {
        "total_findings": len(findings) + len(deck_findings),
        "by_severity": dict(sev_counter),
        "by_class": dict(cls_counter),
    }


def validate(
    doc: dict[str, Any],
) -> tuple[list[str], list[str], list[str], dict[str, int]]:
    """Validate a parsed JSON document.

    Returns (errors, summary_corrections, warnings, summary_stats):
      - errors: non-correctable issues (schema violation, missing
        required fields, invalid enums, duplicate IDs, narrative_weakness
        invariants). Caller treats these as exit-code-1 failures.
      - summary_corrections: auto-correctable summary count mismatches.
        Caller can apply compute_correct_summary() to fix these in place
        and exit with warning (code 2) instead of failure.
      - warnings: advisory issues (zero P0 on large deck, missing
        narrative_weakness, etc.). Don't block ship.
      - summary_stats: convenience tallies for the success message.

    Empty errors AND empty summary_corrections ⇒ pass.
    """
    errors: list[str] = []
    summary_corrections: list[str] = []
    warnings: list[str] = []

    # ----- top-level structure -----
    sv = doc.get("schema_version")
    if sv not in ACCEPTED_SCHEMA_VERSIONS:
        accepted = sorted(ACCEPTED_SCHEMA_VERSIONS)
        errors.append(
            f"schema_version must be one of {accepted}, got {sv!r}"
        )
        # Default to v2 rules for the rest of validation if version is bogus
        sv = CURRENT_SCHEMA_VERSION

    is_v1 = sv == SCHEMA_VERSION_V1
    is_v2 = sv == SCHEMA_VERSION_V2

    if is_v1:
        warnings.append(
            "schema_version 'adversarial-review-presentation.v1' is "
            "DEPRECATED. New reviewer runs emit v2. v1 acceptance is for "
            "forensic compatibility with older audit files only; please "
            "re-run the reviewer to produce a v2 audit."
        )

    findings = doc.get("findings")
    if not isinstance(findings, list):
        errors.append(
            f"findings must be a list, got {type(findings).__name__}"
        )
        findings = []

    # In v1: deck_level_findings is required. In v2: must NOT be present.
    deck_findings: list[Any] = []
    if is_v1:
        deck_findings_raw = doc.get("deck_level_findings")
        if not isinstance(deck_findings_raw, list):
            errors.append(
                "deck_level_findings must be a list (v1), got "
                f"{type(deck_findings_raw).__name__}"
            )
            deck_findings = []
        else:
            deck_findings = deck_findings_raw
    else:  # v2
        if "deck_level_findings" in doc:
            errors.append(
                "deck_level_findings field is not allowed in schema v2 — "
                "all findings live in the single findings[] array. Findings "
                "without slide_id are deck-level."
            )

    summary = doc.get("summary")
    if not isinstance(summary, dict):
        errors.append(f"summary must be a dict, got {type(summary).__name__}")
        summary = {}

    # ----- per-finding validation -----
    severity_counter: Counter[str] = Counter()
    class_counter: Counter[str] = Counter()
    seen_ids: set[str] = set()

    def validate_finding(f: Any, tag: str, require_slide_fields: bool) -> None:
        """Validate a single finding entry.

        require_slide_fields semantics:
          - v1, called from findings[]: True (v1 slide-level findings need
            slide_id et al. unconditionally).
          - v1, called from deck_level_findings[]: False.
          - v2, called from findings[]: depends on whether slide_id is
            present. If slide_id present → require the rest of the slide-
            level field set; if absent → it's a deck-level finding,
            slide-level fields not required.
        """
        if not isinstance(f, dict):
            errors.append(f"{tag}: finding must be a dict, got {type(f).__name__}")
            return
        # Required fields
        missing = COMMON_REQUIRED_FIELDS - f.keys()
        if missing:
            errors.append(
                f"{tag} (id={f.get('id', '?')!r}): missing required field(s): "
                f"{sorted(missing)}"
            )
        if require_slide_fields:
            missing_slide = SLIDE_LEVEL_REQUIRED_FIELDS - f.keys()
            if missing_slide:
                errors.append(
                    f"{tag} (id={f.get('id', '?')!r}): missing slide-level "
                    f"field(s): {sorted(missing_slide)}"
                )

        # Field-value validity
        cls = f.get("class")
        if cls is not None and cls not in VALID_CLASSES:
            errors.append(
                f"{tag} (id={f.get('id', '?')!r}): class={cls!r} not in "
                f"{sorted(VALID_CLASSES)}"
            )
        if cls is not None:
            class_counter[cls] += 1

        sev = f.get("severity")
        if sev is not None and sev not in VALID_SEVERITIES:
            errors.append(
                f"{tag} (id={f.get('id', '?')!r}): severity={sev!r} not in "
                f"{sorted(VALID_SEVERITIES)}"
            )
        if sev is not None:
            severity_counter[sev] += 1

        conf = f.get("confidence")
        if conf is not None and conf not in VALID_CONFIDENCES:
            errors.append(
                f"{tag} (id={f.get('id', '?')!r}): confidence={conf!r} not "
                f"in {sorted(VALID_CONFIDENCES)}"
            )

        # ID uniqueness
        fid = f.get("id")
        if isinstance(fid, str):
            if fid in seen_ids:
                errors.append(f"{tag}: duplicate finding id {fid!r}")
            seen_ids.add(fid)

        # narrative_weakness must be severity=info; nothing else should be info
        if cls == "narrative_weakness" and sev != "info":
            errors.append(
                f"{tag} (id={fid!r}): narrative_weakness must have "
                f"severity='info', got {sev!r}"
            )
        if sev == "info" and cls != "narrative_weakness":
            errors.append(
                f"{tag} (id={fid!r}): severity='info' is reserved for "
                f"narrative_weakness, but class={cls!r}"
            )

    if is_v1:
        # v1: findings[] is slide-level, deck_level_findings[] is deck-level.
        for i, f in enumerate(findings):
            validate_finding(f, f"findings[{i}]", require_slide_fields=True)
        for i, f in enumerate(deck_findings):
            validate_finding(
                f, f"deck_level_findings[{i}]", require_slide_fields=False
            )
    else:
        # v2: single findings[] array. slide-level fields required IFF
        # slide_id is present.
        for i, f in enumerate(findings):
            if isinstance(f, dict) and "slide_id" in f:
                # Slide-level finding — require the rest of the field set.
                validate_finding(
                    f, f"findings[{i}]", require_slide_fields=True
                )
            else:
                # Deck-level finding (no slide_id). Slide-level fields not
                # required, but if any of them is present we still check
                # nothing — partial slide_* presence is allowed (e.g.,
                # substory_id) but the four anchor fields together
                # indicate slide-level. Future tightening can require all
                # or none, but for now: presence-of-slide_id is the gate.
                validate_finding(
                    f, f"findings[{i}]", require_slide_fields=False
                )

    # ----- summary count consistency -----
    # Summary count mismatches are AUTO-CORRECTABLE (the findings array
    # is the ground truth; the summary is derived). LLMs are intrinsically
    # bad at arithmetic-on-self-output, so we backstop the prompt's recount
    # instruction in the validator. Mismatches go into summary_corrections,
    # not errors — the caller rewrites the file with the corrected summary.
    total = len(findings) + len(deck_findings)
    declared_total = summary.get("total_findings")
    if declared_total is not None and declared_total != total:
        summary_corrections.append(
            f"summary.total_findings={declared_total} but actual "
            f"findings + deck_level_findings = {total}"
        )

    by_severity = summary.get("by_severity", {})
    if isinstance(by_severity, dict):
        for sev, declared in by_severity.items():
            actual = severity_counter.get(sev, 0)
            if declared != actual:
                summary_corrections.append(
                    f"summary.by_severity[{sev!r}]={declared} but actual "
                    f"count = {actual}"
                )
        # Also flag severities present in findings but absent from summary
        for sev, actual in severity_counter.items():
            if sev not in by_severity and actual > 0:
                summary_corrections.append(
                    f"summary.by_severity is missing key {sev!r} "
                    f"(actual count = {actual})"
                )

    by_class = summary.get("by_class", {})
    if isinstance(by_class, dict):
        for cls, declared in by_class.items():
            actual = class_counter.get(cls, 0)
            if declared != actual:
                summary_corrections.append(
                    f"summary.by_class[{cls!r}]={declared} but actual "
                    f"count = {actual}"
                )
        for cls, actual in class_counter.items():
            if cls not in by_class and actual > 0:
                summary_corrections.append(
                    f"summary.by_class is missing key {cls!r} "
                    f"(actual count = {actual})"
                )

    # ----- advisory checks (warnings, not errors) -----
    p0_count = severity_counter.get("P0", 0)
    # Heuristic: if we know how many slides the deck had (the schema
    # doesn't include this directly, but slide_position values give a
    # lower bound), warn on zero P0s above the threshold.
    max_position = 0
    for f in findings:
        if isinstance(f, dict):
            pos = f.get("slide_position")
            if isinstance(pos, int) and pos > max_position:
                max_position = pos
    if p0_count == 0 and max_position >= ZERO_P0_WARN_SLIDE_THRESHOLD:
        warnings.append(
            f"zero P0 findings on a deck with at least {max_position} "
            "slides — possible reviewer under-fire. Spec §9 lists 3 P0s "
            "for draft_9; review the prompt's self-skepticism pass."
        )

    if not findings and not deck_findings:
        warnings.append(
            "reviewer produced zero findings total — almost certainly "
            "did not run the detection protocol. Re-run."
        )

    # narrative_weakness should appear exactly once across both arrays
    narrative_count = class_counter.get("narrative_weakness", 0)
    if narrative_count == 0:
        warnings.append(
            "no narrative_weakness finding emitted — Class 7 is supposed "
            "to produce exactly one. Reviewer skipped the killshot."
        )
    elif narrative_count > 1:
        errors.append(
            f"narrative_weakness should appear exactly once, got "
            f"{narrative_count}"
        )

    # Count slide-level vs deck-level by slide_id presence (consistent
    # across v1 and v2). In v1, deck_findings live in the deck_level_findings
    # array; we count those as deck-level regardless of slide_id (none of
    # them should have slide_id but defensive sum for v1's case is safe).
    slide_level_count = 0
    deck_level_count = 0
    for f in findings:
        if isinstance(f, dict) and "slide_id" in f:
            slide_level_count += 1
        else:
            # findings[] entry without slide_id is deck-level (v2)
            deck_level_count += 1
    # In v1, all entries in deck_level_findings are deck-level by definition.
    deck_level_count += len(deck_findings)

    summary_stats = {
        "slide_findings": slide_level_count,
        "deck_findings": deck_level_count,
        "p0": severity_counter.get("P0", 0),
        "p1": severity_counter.get("P1", 0),
        "p2": severity_counter.get("P2", 0),
        "info": severity_counter.get("info", 0),
    }
    return errors, summary_corrections, warnings, summary_stats


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(
            "Usage: validate_presentation_review.py <path/to/adversarial_review.json>",
            file=sys.stderr,
        )
        return 3

    path = Path(argv[1])
    if not path.is_file():
        print(f"Error: file not found: {path}", file=sys.stderr)
        return 3

    try:
        with path.open("r", encoding="utf-8") as fh:
            doc = json.load(fh)
    except json.JSONDecodeError as e:
        print(f"Error: file is not valid JSON: {e}", file=sys.stderr)
        return 1
    except OSError as e:
        print(f"Error: could not read file: {e}", file=sys.stderr)
        return 3

    errors, summary_corrections, warnings, stats = validate(doc)

    # Non-correctable errors fail hard.
    if errors:
        print(f"FAIL: {len(errors)} validation error(s) in {path.name}", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        if summary_corrections:
            print(
                f"  Plus {len(summary_corrections)} summary count "
                f"mismatch(es) (would auto-correct, but other errors block):",
                file=sys.stderr,
            )
            for sc in summary_corrections:
                print(f"    - {sc}", file=sys.stderr)
        if warnings:
            print(f"  Plus {len(warnings)} warning(s):", file=sys.stderr)
            for w in warnings:
                print(f"    - {w}", file=sys.stderr)
        return 1

    # Apply auto-correction for summary count mismatches. The findings
    # array is ground truth; LLMs are bad at arithmetic-on-self-output;
    # correct in place rather than fail. Preserve the original summary
    # to a sidecar for forensics.
    auto_corrected = False
    if summary_corrections:
        original_summary = doc.get("summary", {})
        # Preserve the original (mismatched) summary alongside the file.
        sidecar = path.with_name(path.stem + ".original-summary.json")
        try:
            sidecar.write_text(
                json.dumps(
                    {
                        "note": (
                            "Original summary block from the LLM, preserved "
                            "by validate_presentation_review.py auto-correction. "
                            "The actual JSON has been rewritten with counts "
                            "derived from the findings arrays."
                        ),
                        "original_summary": original_summary,
                        "corrections_applied": summary_corrections,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError as e:
            print(
                f"Warning: could not write forensic sidecar {sidecar}: {e}",
                file=sys.stderr,
            )

        # Compute and write the corrected summary.
        findings = doc.get("findings", [])
        deck_findings = doc.get("deck_level_findings", [])
        if isinstance(findings, list) and isinstance(deck_findings, list):
            doc["summary"] = compute_correct_summary(findings, deck_findings)
            try:
                path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
                auto_corrected = True
            except OSError as e:
                print(
                    f"Error: could not write corrected JSON to {path}: {e}",
                    file=sys.stderr,
                )
                return 1

    msg = (
        f"PASS: {stats['slide_findings']} slide-level finding(s), "
        f"{stats['deck_findings']} deck-level finding(s) "
        f"({stats['p0']} P0, {stats['p1']} P1, {stats['p2']} P2, "
        f"{stats['info']} info)"
    )
    print(msg)

    # Auto-correction emits a prominent stderr block so the operator
    # knows the LLM's summary block was wrong.
    if auto_corrected:
        print("", file=sys.stderr)
        print(
            "================================================================",
            file=sys.stderr,
        )
        print(
            "AUTO-CORRECTED: summary count mismatches in the LLM's output",
            file=sys.stderr,
        )
        print(
            "================================================================",
            file=sys.stderr,
        )
        for sc in summary_corrections:
            print(f"  - {sc}", file=sys.stderr)
        print("", file=sys.stderr)
        print(
            "  The summary block has been rewritten from the findings array.",
            file=sys.stderr,
        )
        print(
            f"  Original summary preserved at: {path.stem}.original-summary.json",
            file=sys.stderr,
        )
        print(
            "  The .json file is now consumer-safe.",
            file=sys.stderr,
        )
        print(
            "================================================================",
            file=sys.stderr,
        )

    if warnings or auto_corrected:
        if warnings:
            print(f"WARN: {len(warnings)} advisory issue(s):", file=sys.stderr)
            for w in warnings:
                print(f"  - {w}", file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
