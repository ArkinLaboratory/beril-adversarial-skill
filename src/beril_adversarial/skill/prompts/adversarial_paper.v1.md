# DEPRECATED: see adversarial_paper.v2.md

This prompt has been superseded by `adversarial_paper.v2.md`, which:

- Reads paper-writer v0.6.x's per-draft directory layout
  (`papers/draft_N/manuscript.md` + `00_throughline.md` + ...) instead
  of the legacy flat-file layout (`papers/draft{N}.md` +
  `papers/THROUGHLINE.md` + `papers/bibliography.bib`).
- Emits dual output: human-readable `audit/adversarial_review.md` +
  machine-readable `audit/adversarial_review.json` with
  `schema_version: "adversarial-review-paper.v2"`.
- Uses the unified single-`findings[]`-array structure (mirror of
  presentation v2). Section-level findings have `section`,
  `line_range`, `paragraph_quote`. Manuscript-wide findings (like
  `narrative_weakness`, `missing_section`) omit those fields.
- Implements 10 detection classes with strong intersection with the
  presentation reviewer's 8 classes (5 shared, 2 parallel-but-renamed,
  3 paper-only: `citation_reality`, `report_drift`,
  `abstract_body_mismatch`).

**Why the bump:** paper-writer v0.6.x adopted per-draft directories
in May 2026; the v1 paper reviewer's input contract was stale and
paper-writer was relying on an inline `fallback_reviewer.v1.md` for
in-loop iteration. v0.6.0 of beril-adversarial provides the
canonical reviewer that speaks paper-writer's current dialect, with
the dual md+json output the planned paper-writer review-rewrite
loop (v0.7+) will consume.

The orchestrator script `tools/adversarial_review.sh` loads
`adversarial_paper.v2.md` only. This file (`v1.md`) is preserved
as a marker; do NOT load it as a system prompt.

The validator (`tools/validate_review.py`) accepts schemas v1
(presentation only — paper v1 had no schema), v2 (presentation),
and paper.v2 simultaneously, for forensic compatibility with older
audit files.

For the v1 paper reviewer's content (depth modes, additivity,
literature-scan subagent spec, 9-field strict citation format), see
git log:
`git log --all --full-history -- src/beril_adversarial/skill/prompts/adversarial_paper.v1.md`

Several v1 capabilities are intentionally deferred from v2:
- Depth modes (quick/standard/deep) — single depth in v0.6.0;
  revisit if cost/scope tuning needed.
- Additivity / carryover across rounds — orthogonal to schema; the
  consumer can compute carryover from successive run JSONs. Defer
  to v0.6.1 if needed.
- Literature-scan subagent — defer; paper-writer's review-rewrite
  loop can invoke literature scanning as a separate prompt if
  desired.
- WebSearch citation verification — v0.6.0 paper reviewer is text-
  only (Read/Write/Grep/Glob). Citation reality is verified against
  references.md and citation_map.md. WebSearch verification is
  v0.6.x opt-in.
