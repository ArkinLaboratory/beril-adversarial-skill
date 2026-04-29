# DEPRECATED: see adversarial_presentation.v2.md

This prompt has been superseded by `adversarial_presentation.v2.md`,
which uses the `adversarial-review-presentation.v2` JSON schema with
a single `findings[]` array (no separate `deck_level_findings[]`).

**Why the bump:** schema v1's dual-array structure (slide-level
findings in `findings[]`, deck-level findings in
`deck_level_findings[]`) was a recurring source of LLM mis-routing.
The reviewer kept placing deck-level findings (`narrative_weakness`,
`missing_slide`) into the slide-level array, where they failed
validation due to missing slide-level fields. v2 collapses to one
array; the absence of `slide_id` indicates a deck-level finding.

The orchestrator script `tools/adversarial_review.sh` loads
`adversarial_presentation.v2.md` only. This file (`v1.md`) is
preserved as a marker; do NOT load it as a system prompt.

The validator (`tools/validate_presentation_review.py`) still
accepts `schema_version: "adversarial-review-presentation.v1"` for
forensic compatibility with audit files produced by older runs
(e.g. `draft_9`, `draft_10` audits from v0.4.x). Re-running the
reviewer on those drafts will produce v2 audit files; the old v1
audits remain valid for inspection.

For history of the v1 prompt, see git log:
`git log --all --full-history -- src/beril_adversarial/skill/prompts/adversarial_presentation.v1.md`
