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
  (or for paper schema:
   PASS: 11 section-level findings, 5 manuscript-wide findings (8 P0, 7 P1, 0 P2, 1 info))

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

# Supported schema versions. As of v0.6.0, this validator handles
# BOTH the presentation review schemas (v1 deprecated, v2 current)
# AND the paper review schema (v2 — paper has no v1 schema; the
# v1 paper reviewer in v0.5.x emitted markdown only).
#
# Forensic compatibility: presentation v1 audit files from v0.4.x
# runs (draft_9, draft_10) remain readable. Paper v1 audits don't
# exist (no JSON schema then), so no paper v1 acceptance needed.
SCHEMA_VERSION_PRESENTATION_V1 = "adversarial-review-presentation.v1"
SCHEMA_VERSION_PRESENTATION_V2 = "adversarial-review-presentation.v2"
SCHEMA_VERSION_PAPER_V2 = "adversarial-review-paper.v2"

ACCEPTED_SCHEMA_VERSIONS = {
    SCHEMA_VERSION_PRESENTATION_V1,
    SCHEMA_VERSION_PRESENTATION_V2,
    SCHEMA_VERSION_PAPER_V2,
}

# v1 schemas that are still accepted but deprecated.
DEPRECATED_SCHEMA_VERSIONS = {
    SCHEMA_VERSION_PRESENTATION_V1,
}

# Schema family detection — for routing per-schema validation rules.
PRESENTATION_SCHEMAS = {
    SCHEMA_VERSION_PRESENTATION_V1,
    SCHEMA_VERSION_PRESENTATION_V2,
}
PAPER_SCHEMAS = {SCHEMA_VERSION_PAPER_V2}

# Backwards-compat aliases for code that imported the old constants.
SCHEMA_VERSION_V1 = SCHEMA_VERSION_PRESENTATION_V1
SCHEMA_VERSION_V2 = SCHEMA_VERSION_PRESENTATION_V2
CURRENT_SCHEMA_VERSION = SCHEMA_VERSION_PRESENTATION_V2  # legacy alias
SCHEMA_VERSION_LITERAL = SCHEMA_VERSION_PRESENTATION_V1  # legacy alias

# Severity values that can appear in findings (info is reserved for
# the single Class 7 narrative_weakness finding).
VALID_SEVERITIES = {"P0", "P1", "P2", "info"}

# Class values per schema family. Strong intersection between
# presentation and paper (5 shared classes), with format-specific
# additions. See SCHEMA_V2_PAPER_DECISIONS.md §"Class enum vs
# presentation v2 — overlap report".

# Shared between presentation v1/v2 and paper v2.
SHARED_CLASSES = {
    "throughline",
    "claim_evidence",
    "register_drift",
    "unbacked_quantitative",
    "narrative_weakness",
}

# Presentation-only classes.
PRESENTATION_ONLY_CLASSES = {
    "qa_softball",
    "substory_arc",
    "missing_slide",
}

# Paper-only classes.
PAPER_ONLY_CLASSES = {
    "section_arc",
    "missing_section",
    "citation_reality",
    "report_drift",
    "abstract_body_mismatch",
}

# Union — used when validating without knowing the schema family yet.
VALID_CLASSES = SHARED_CLASSES | PRESENTATION_ONLY_CLASSES | PAPER_ONLY_CLASSES

# Per-schema valid class sets.
VALID_CLASSES_PRESENTATION = SHARED_CLASSES | PRESENTATION_ONLY_CLASSES
VALID_CLASSES_PAPER = SHARED_CLASSES | PAPER_ONLY_CLASSES

VALID_CONFIDENCES = {"high", "medium", "low"}

# Fields required on every finding (universally).
COMMON_REQUIRED_FIELDS = {
    "id",
    "class",
    "severity",
    "confidence",
    "issue",
    "fix_target",
    "fix_hint",
}

# Presentation: slide-level fields required when slide_id is present.
SLIDE_LEVEL_REQUIRED_FIELDS = {
    "slide_id",
    "slide_position",
    "slide_layout",
    "title_quote",
}

# Paper: section-level fields required when section is present.
# paragraph_quote is class-conditional (mirror of v0.5.3 presentation
# title_quote behavior — see PAPER_PARAGRAPH_QUOTE_REQUIRED_CLASSES).
SECTION_LEVEL_REQUIRED_FIELDS = {
    "section",
    "line_range",
}

# Paper: classes for which paragraph_quote is required (criticism
# targets specific text). Mirror of presentation's title_quote rules
# from v0.5.3.
PAPER_PARAGRAPH_QUOTE_REQUIRED_CLASSES = {
    "register_drift",
    "claim_evidence",
    "unbacked_quantitative",
    "report_drift",
}

# Presentation title_quote behavior is defined by the v0.5.3
# TITLE_QUOTE_REQUIRED_CLASSES constant farther down (kept in its
# original location to preserve git blame). Alias for paper-side code:
PRESENTATION_TITLE_QUOTE_REQUIRED_CLASSES = None  # set below; placeholder

# Finding classes for which title_quote is REQUIRED when slide_id is
# present. The principle: title_quote is needed when the criticism
# targets specific slide text — the reviewer must quote that text to
# anchor accountability. For finding classes whose criticism is
# structural (substory_arc), about a slide's absence (missing_slide),
# about a deck-level pattern (throughline, narrative_weakness), or
# about a number whose location may not be the slide title (unbacked_
# quantitative), the title_quote field is OPTIONAL.
#
# v0.5.3 (2026-05-02): live sonnet-4-6 review of core_gene_tradeoffs
# draft_2 had two failures:
#   1. F015/F016 (substory_arc class) — these reference existing
#      slides (slide_id=8, slide_id=15) but criticize substory
#      structure ("S1 has redundant slide"; "S3 over-budget"). The
#      reviewer didn't quote a title because the criticism isn't
#      about the title text. Validator was rejecting these.
#   2. (Also expected to break, though not seen in this run): missing_
#      slide findings. The slide doesn't exist; there is no title to
#      quote. slide_id/slide_position point at insertion location;
#      slide_layout is the proposed layout for the new slide.
TITLE_QUOTE_REQUIRED_CLASSES = {
    "register_drift",
    "claim_evidence",
    "qa_softball",
}
# Wire the alias declared earlier (kept up there for the paper-side
# code that wants a presentation-named symbol).
PRESENTATION_TITLE_QUOTE_REQUIRED_CLASSES = TITLE_QUOTE_REQUIRED_CLASSES

# If the deck has at least this many slides AND the reviewer found
# zero P0 findings, emit a warning (advisory only — exit 2). The
# spec's representative draft_9 has 26 slides + 3 P0s; a zero-P0
# review on a deck this size strongly suggests reviewer under-fire.
ZERO_P0_WARN_SLIDE_THRESHOLD = 20


# Regex for stripping trailing commas before } or ]. Per memory entry
# feedback_llm_json_trailing_commas_repairable.md: trailing commas are
# unambiguous (unlike unescaped quotes, which are not repairable). This
# regex repairs them without false positives.
import re as _re

_TRAILING_COMMA_RE = _re.compile(r",(\s*[}\]])")


def lenient_json_load(text: str) -> Any:
    """Parse JSON; if strict parse fails, attempt trailing-comma repair.

    Pattern: try strict json.loads → on JSONDecodeError, regex-strip
    trailing commas → re-try → on second failure raise the ORIGINAL
    error (so callers see the actual problem, not the post-repair
    artifact).

    This catches one common LLM JSON failure mode (trailing commas).
    It does NOT fix the OTHER common failure (unescaped inner quotes
    inside string values) — that one is unrepairable in the parser
    per feedback_llm_json_unfixable_in_parser.md; the fix is at the
    prompt with explicit anti-pattern guidance.

    Trailing-comma repair only fires when needed (most JSON parses
    clean on the first try); behavior is byte-identical to strict
    json.loads for valid input.
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError as original_err:
        # Try trailing-comma repair
        repaired = _TRAILING_COMMA_RE.sub(r"\1", text)
        if repaired == text:
            # No trailing commas to fix; surface the original error
            raise original_err
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            # Repair didn't help; surface the ORIGINAL error so the
            # caller sees the actual problem, not the post-repair
            # artifact at a different line/column.
            raise original_err from None


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
        # Default to presentation v2 rules for the rest of validation if
        # version is bogus.
        sv = SCHEMA_VERSION_PRESENTATION_V2

    # Schema family + version detection
    is_presentation_v1 = sv == SCHEMA_VERSION_PRESENTATION_V1
    is_presentation_v2 = sv == SCHEMA_VERSION_PRESENTATION_V2
    is_paper_v2 = sv == SCHEMA_VERSION_PAPER_V2

    is_presentation = sv in PRESENTATION_SCHEMAS
    is_paper = sv in PAPER_SCHEMAS

    # Backwards-compat: legacy code paths reference these names.
    is_v1 = is_presentation_v1
    is_v2 = is_presentation_v2 or is_paper_v2  # any v2 schema family

    # Per-schema valid class set
    valid_classes_for_schema = (
        VALID_CLASSES_PAPER if is_paper else VALID_CLASSES_PRESENTATION
    )

    if sv in DEPRECATED_SCHEMA_VERSIONS:
        warnings.append(
            f"schema_version {sv!r} is DEPRECATED. New reviewer runs emit "
            "the v2 family (adversarial-review-presentation.v2 or "
            "adversarial-review-paper.v2). v1 acceptance is for forensic "
            "compatibility with older audit files only; please re-run the "
            "reviewer to produce a v2 audit."
        )

    findings = doc.get("findings")
    if not isinstance(findings, list):
        errors.append(
            f"findings must be a list, got {type(findings).__name__}"
        )
        findings = []

    # deck_level_findings semantics:
    #   - presentation v1: required separate array (slide-level vs
    #     deck-level)
    #   - presentation v2: must NOT be present (collapsed into
    #     findings[])
    #   - paper v2: must NOT be present (paper has no concept of
    #     deck_level_findings; section-level findings have section
    #     field, manuscript-wide omit it)
    deck_findings: list[Any] = []
    if is_presentation_v1:
        deck_findings_raw = doc.get("deck_level_findings")
        if not isinstance(deck_findings_raw, list):
            errors.append(
                "deck_level_findings must be a list (v1), got "
                f"{type(deck_findings_raw).__name__}"
            )
            deck_findings = []
        else:
            deck_findings = deck_findings_raw
    else:  # any v2 schema (presentation or paper)
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
          - presentation v1 from findings[]: True (slide-level fields
            unconditional).
          - presentation v1 from deck_level_findings[]: False.
          - presentation v2 from findings[]: depends on slide_id presence.
          - paper v2 from findings[]: depends on section presence; if
            present, requires section-level field set instead of
            slide-level (paragraph_quote class-conditional).
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
            cls_for_check = f.get("class")
            if is_paper:
                # Paper v2: section-level required fields are SECTION_LEVEL_*
                # (section + line_range), plus paragraph_quote which is
                # class-conditional (mirror of presentation's title_quote
                # behavior from v0.5.3).
                if cls_for_check in PAPER_PARAGRAPH_QUOTE_REQUIRED_CLASSES:
                    required = SECTION_LEVEL_REQUIRED_FIELDS | {"paragraph_quote"}
                else:
                    required = SECTION_LEVEL_REQUIRED_FIELDS
                missing_section_fields = required - f.keys()
                if missing_section_fields:
                    errors.append(
                        f"{tag} (id={f.get('id', '?')!r}): missing section-level "
                        f"field(s): {sorted(missing_section_fields)}"
                    )
            else:
                # Presentation v1/v2: title_quote is class-conditional per
                # v0.5.3. See TITLE_QUOTE_REQUIRED_CLASSES.
                if cls_for_check in TITLE_QUOTE_REQUIRED_CLASSES:
                    required = SLIDE_LEVEL_REQUIRED_FIELDS  # incl title_quote
                else:
                    required = SLIDE_LEVEL_REQUIRED_FIELDS - {"title_quote"}
                missing_slide_fields = required - f.keys()
                if missing_slide_fields:
                    errors.append(
                        f"{tag} (id={f.get('id', '?')!r}): missing slide-level "
                        f"field(s): {sorted(missing_slide_fields)}"
                    )

        # Field-value validity (per-schema valid classes)
        cls = f.get("class")
        if cls is not None and cls not in valid_classes_for_schema:
            errors.append(
                f"{tag} (id={f.get('id', '?')!r}): class={cls!r} not in "
                f"{sorted(valid_classes_for_schema)} (schema {sv})"
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
    elif is_presentation_v2:
        # presentation v2: single findings[] array. slide-level fields
        # required IFF slide_id is present.
        for i, f in enumerate(findings):
            require_locus = isinstance(f, dict) and "slide_id" in f
            validate_finding(
                f, f"findings[{i}]", require_slide_fields=require_locus
            )
    else:
        # paper v2: single findings[] array. section-level fields
        # required IFF section is present. (require_slide_fields is
        # the parameter name but in paper context it means "require
        # the section-level locus fields", per validate_finding's
        # is_paper branch.)
        for i, f in enumerate(findings):
            require_locus = isinstance(f, dict) and "section" in f
            validate_finding(
                f, f"findings[{i}]", require_slide_fields=require_locus
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
    if is_paper:
        # Paper heuristic: if total findings > 5 and zero P0s, warn.
        # A 5000+ word manuscript with NO P0s strongly suggests reviewer
        # under-fire on quantitative grounding or citation reality.
        if p0_count == 0 and len(findings) > 5:
            warnings.append(
                f"zero P0 findings on a paper with {len(findings)} total "
                "findings — possible reviewer under-fire on "
                "unbacked_quantitative or citation_reality classes. Re-run "
                "self-skepticism pass."
            )
    else:
        # Presentation heuristic: if we know how many slides the deck had
        # (the schema doesn't include this directly, but slide_position
        # values give a lower bound), warn on zero P0s above the threshold.
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

    # Count slide-level vs deck-level by locus-field presence.
    # Presentation: locus = slide_id. Paper: locus = section.
    # In v1 presentation, deck_findings live in deck_level_findings[]
    # array — counted as deck/manuscript-wide regardless.
    locus_field = "section" if is_paper else "slide_id"
    slide_level_count = 0
    deck_level_count = 0
    for f in findings:
        if isinstance(f, dict) and locus_field in f:
            slide_level_count += 1
        else:
            deck_level_count += 1
    # v1 presentation only: deck_level_findings entries are all
    # deck-level by definition.
    deck_level_count += len(deck_findings)

    # Schema-appropriate labels for the cumulative counts.
    # Presentation: slide-level vs deck-level findings.
    # Paper: section-level vs manuscript-wide findings.
    if is_paper:
        locus_label = "section-level"
        non_locus_label = "manuscript-wide"
    else:
        locus_label = "slide-level"
        non_locus_label = "deck-level"

    summary_stats = {
        # locus_count = findings WITH the locus field (slide_id or section).
        # non_locus_count = findings WITHOUT it (deck-level / manuscript-wide).
        # Legacy keys "slide_findings" and "deck_findings" preserved for
        # backwards-compat with callers that scrape these by name; new
        # callers should use locus_count / non_locus_count + the *_label
        # fields for schema-appropriate display.
        "locus_count": slide_level_count,
        "non_locus_count": deck_level_count,
        "locus_label": locus_label,
        "non_locus_label": non_locus_label,
        "schema_version": sv,
        "schema_family": "paper" if is_paper else "presentation",
        # Legacy keys (deprecated; kept for callers that read by name).
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
            raw_text = fh.read()
    except OSError as e:
        print(f"Error: could not read file: {e}", file=sys.stderr)
        return 3

    try:
        doc = lenient_json_load(raw_text)
    except json.JSONDecodeError as e:
        # If the lenient loader couldn't repair, surface the ORIGINAL
        # error (not the post-repair error) — see memory entry
        # feedback_llm_json_unfixable_in_parser.md: unescaped inner
        # quotes are NOT repairable; the right fix is at the prompt.
        print(f"Error: file is not valid JSON: {e}", file=sys.stderr)
        # Hint about the most-common cause
        if "delimiter" in str(e):
            print(
                "  Hint: 'Expecting , delimiter' often means an "
                "unescaped \" inside a JSON string value. Check the "
                "indicated line/column for inner quotes (e.g., "
                "scare-quoted technical terms). The reviewer prompt "
                "covers this; if it recurs, the prompt may need "
                "tightening.",
                file=sys.stderr,
            )
        return 1

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
        f"PASS: {stats['locus_count']} {stats['locus_label']} finding(s), "
        f"{stats['non_locus_count']} {stats['non_locus_label']} finding(s) "
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
