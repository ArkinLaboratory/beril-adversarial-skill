# adversarial-review-paper schema v2 — design decisions

> **HISTORICAL — v0.6.0 design.** Paper v2 was deprecated as of
> v0.7.0 (2026-05-03). The current paper schema is **v3** — see
> [`SCHEMA_V3_DECISIONS.md`](SCHEMA_V3_DECISIONS.md) for the active
> design (which consolidated paper + presentation v3 into one doc)
> and [`CONTRACT.md`](CONTRACT.md) §"v0.7.0 migration" for consumer
> migration guidance. v2 paper docs continue to be readable by the
> validator (forensic compatibility); v3 is what new runs emit.
> This doc is preserved for archaeological context.

**Status:** Decisions for v0.6.0 implementation. Author: Claude (this
session, 2026-05-02). Mirrors `SCHEMA_V2_DECISIONS.md` (presentation
schema decisions for v0.5.0).

## Why v2 (skipping v1 entirely for paper)

The paper reviewer in v0.5.x emits markdown only — no structured JSON
exists for paper. So there's no "v1" to deprecate. We launch directly
at v2 to inherit the architectural lessons from presentation v2:
single array, derived summary, optional slide/section-level fields,
auto-corrected counts.

## Why "clean break" on input layout

paper-writer v0.6.3 ships per-draft directories
(`papers/draft_N/manuscript.md` + `00_throughline.md` + ...). The
legacy flat-file layout (`papers/draft{N}.md` + `papers/THROUGHLINE.md`)
is from earlier paper-writer versions; no current consumers expect it.

The orchestrator's `--type paper` branch will require per-draft layout
and reject the flat-file shape. Forensic compatibility for old paper
review JSONs is preserved at the validator level — old `.md`-only
audit files don't have JSON to validate; existing JSON-shaped paper
reviews don't exist (this is the first paper schema). Effectively no
forensic-compat burden; clean cut.

## Schema structure

Mirror of `adversarial-review-presentation.v2`. Single `findings[]`
array. Section-level findings have section/line/quote fields;
deck-wide-equivalent findings (narrative_weakness, etc.) omit them.

```json
{
  "schema_version": "adversarial-review-paper.v2",
  "draft_dir": "/abs/path/to/papers/draft_N",
  "project_id": "string",
  "draft_number": 3,
  "reviewed_at": "2026-05-02T13:42:00Z",
  "reviewer_model": "claude-sonnet-4-6",
  "prompt_version": "adversarial_paper.v2",
  "tier": "STRONG",
  "summary": {
    "total_findings": 14,
    "by_severity": {"P0": 2, "P1": 9, "P2": 2, "info": 1},
    "by_class": {"claim_evidence": 4, ...}
  },
  "findings": [
    {
      "id": "F001",
      "class": "claim_evidence",
      "severity": "P0",
      "confidence": "high",
      "section": "Results",
      "line_range": "L142-148",
      "paragraph_quote": "Lab-field concordance validates 61.7% of dark gene phenotypes...",
      "issue": "...",
      "report_evidence": [{"section": "§Finding 7", "quote": "..."}],
      "fix_target": "results.v1.md",
      "fix_hint": "..."
    }
  ]
}
```

## Per-finding fields

**Universally required** (every finding has these, same as presentation):

- `id` (string, F### sequential)
- `class` (enum — see below)
- `severity` (enum: P0, P1, P2, info)
- `confidence` (enum: high, medium, low)
- `issue` (string)
- `fix_target` (string — paper-writer prompt name, e.g.
  `methods.v1.md`, `results.v1.md`, `discussion.v1.md`,
  `references.v1.md`, or `00_throughline.md`)
- `fix_hint` (string — concrete change)

**Optional — section-level findings** (presence ⇒ in-text finding;
absence ⇒ deck-wide-equivalent):

- `section` (string: Introduction, Methods, Results, Discussion,
  Abstract, Limitations) — analogous to `slide_id` / `slide_position`
  in presentation; the section the finding lives in
- `line_range` (string: "L142-148") — best-effort; manuscript line
  numbers are unstable so this is advisory not load-bearing
- `paragraph_quote` (string) — the exact text being critiqued —
  analogous to presentation's `title_quote`
- `citation_id` (string) — for citation-class findings, the bibtex
  key or citation marker being flagged

**Optional — claim-evidence findings**:

- `report_evidence` (array of `{section, quote}`) — REQUIRED for
  P0/P1 findings in classes `claim_evidence`, `unbacked_quantitative`,
  `register_drift`, `report_drift`. Optional otherwise.
- `bibliography_evidence` (array of `{citation_id, quote_or_doi}`) —
  for citation-class findings, the cited paper's actual content if
  the reviewer can verify it (e.g., from the bibliography or via
  WebSearch in a future opt-in version)

## Class enum (10 classes)

Adopting the "strong intersection" principle from Adam's call:
identical names where semantics match across paper + presentation;
format-specific names only where genuinely distinct.

**Shared with presentation v2 (identical semantics — 5 classes):**

- `claim_evidence` — text/title makes a claim the supporting evidence
  doesn't actually support
- `unbacked_quantitative` — number/percentage/ratio appears in text
  but not verbatim in REPORT.md (sub-class of claim_evidence in
  presentation; promoted to first-class for paper because numbers
  are denser)
- `register_drift` — language tier doesn't match REPORT's hedging;
  over- or under-claiming
- `narrative_weakness` — the deck/paper's single biggest objection;
  exactly ONE per review; severity=info; deck/paper-wide synthesis
- `throughline` — throughline integrity issue (paper-writer has
  00_throughline.md; same evidence-map structure)

**Format-specific (semantically parallel to presentation classes,
different name — 2 classes):**

- `missing_section` — paper-equivalent of presentation's
  `missing_slide`. The throughline promises evidence the paper
  doesn't deliver in any section.
- `section_arc` — paper-equivalent of presentation's `substory_arc`.
  Section ordering or internal arc issue (e.g., Discussion engages
  prior work before Results establish claims).

(NOTE for future v3 alignment: a future schema bump COULD rename
both `missing_slide`/`substory_arc` → `missing_section`/`section_arc`
or to fully neutral `coverage_gap`/`arc_coherence`. v0.6.0 keeps
presentation v2 stable; paper v2 uses paper-appropriate names.)

**Paper-only (3 classes):**

- `citation_reality` — citation fabrication, citation drift
  (cited paper doesn't exist; or cited paper exists but doesn't
  support the specific claim it's pinned to). Replaces presentation's
  `qa_softball` slot in the format-specific quadrant. Paper-specific
  because papers have formal bibliographic citations; presentations
  rarely do.
- `report_drift` — paper claim silently contradicts REPORT.md or
  silently changes a REPORT finding. The paper may reorder and
  reframe, but it MUST NOT silently change a conclusion. Paper-
  specific because presentation's content slides are typically tied
  more tightly to single REPORT findings; paper has more synthesis
  surface.
- `abstract_body_mismatch` — abstract claims things the body doesn't
  support, OR body proves things the abstract under-states. Direction
  matters: abstract overclaim ⇒ critical; abstract under-claim ⇒
  acceptable but flag-worthy. Paper-specific because presentations
  don't have abstracts.

## Class enum vs presentation v2 — overlap report

| Class | presentation v2 | paper v2 |
|---|---|---|
| claim_evidence | ✓ | ✓ |
| unbacked_quantitative | ✓ | ✓ |
| register_drift | ✓ | ✓ |
| narrative_weakness | ✓ | ✓ |
| throughline | ✓ | ✓ |
| missing_slide | ✓ | — |
| missing_section | — | ✓ |
| substory_arc | ✓ | — |
| section_arc | — | ✓ |
| qa_softball | ✓ | — |
| citation_reality | — | ✓ |
| report_drift | — | ✓ |
| abstract_body_mismatch | — | ✓ |

**Intersection: 5 classes identical** (50% of paper, 62% of
presentation).
**Parallel-but-renamed: 2 classes** (semantic correspondence preserved).
**Format-only: 4 classes** (1 presentation-only `qa_softball`; 3
paper-only `citation_reality`/`report_drift`/`abstract_body_mismatch`).

This satisfies "strong intersection" without forcing semantic
contortions in either format.

## Severity grades (unchanged from presentation v2)

P0 / P1 / P2 / info. info reserved for the single narrative_weakness
finding. Consumer policy: P0 → revise loop trigger; P1+P2+info →
next_actions.

## fix_target values (paper-specific)

paper-writer prompt names that the consumer (paper-writer review-
rewrite loop, future v0.7+) will route to:

- `methods.v1.md`, `results.v1.md`, `discussion.v1.md`,
  `introduction.v1.md`, `abstract.v1.md`, `limitations.v1.md` —
  per-section revise routing
- `references.v1.md` — for citation-class findings
- `00_throughline.md` — for throughline-class findings (likely
  surfaced for user review, not auto-revised, due to cascade risk —
  same pattern as presentation)
- `manuscript.v1.md` — for cross-section findings
  (abstract_body_mismatch, narrative_weakness)
- `revise_paper.v1.md` (future) — generic revise prompt

## Validator behavior

`tools/validate_review.py` (renaming from `validate_presentation_review.py`)
accepts:
- `adversarial-review-presentation.v1` (deprecated; warning)
- `adversarial-review-presentation.v2` (current presentation)
- `adversarial-review-paper.v2` (current paper)

Per-schema validation rules:
- `paper.v2` rejects `slide_id` and other slide-level field names
  (those are presentation-specific)
- `paper.v2` accepts `section`, `line_range`, `paragraph_quote`,
  `citation_id` as section-level fields
- `compute_correct_summary` works generically (counts findings;
  derives by_severity / by_class from any v2 schema)
- Auto-correction behavior (sidecar + exit 2) preserved
- class-conditional `paragraph_quote` (mirror of v0.5.3
  presentation's class-conditional `title_quote`):
  - Required for `register_drift`, `claim_evidence`,
    `unbacked_quantitative`, `report_drift`
  - Optional for `narrative_weakness`, `missing_section`,
    `throughline`, `section_arc`, `citation_reality`,
    `abstract_body_mismatch`

## Reviewer behavior (post-v0.6.0)

`adversarial_paper.v2.md` emits ONLY paper.v2 schema. Reads
paper-writer v0.6.x's per-draft layout. Writes to
`papers/draft_N/audit/adversarial_review.{md,json}`.

The fallback reviewer in paper-writer (`fallback_reviewer.v1.md`)
remains as the fast inline option — different scope, different
purpose. paper-writer's `paper_writer.sh` will offer both modes
once v0.6.0 lands; team decides default.

## Files changed in v0.6.0

| File | Change |
|---|---|
| `prompts/adversarial_paper.v1.md` | Replace with deprecation stub (mirrors v1 presentation stub pattern) |
| `prompts/adversarial_paper.v2.md` | New; mirror of presentation v2 structure with paper-specific worked examples |
| `tools/adversarial_review.sh` | --type paper branch reads per-draft layout; loads .v2.md prompt; emits dual md+json |
| `tools/validate_review.py` | Renamed from validate_presentation_review.py; accepts paper.v2 schema |
| `src/beril_adversarial/commands/review.py` | New; thin Python CLI wrapper around adversarial_review.sh |
| `src/beril_adversarial/cli.py` | Wire `review` subcommand |
| `tests/unit/test_paper_review.py` | New; mirrors test_presentation_review.py shape |
| `tests/unit/test_validate_review.py` | Renamed from test_validate_presentation_review.py; covers both schemas |
| `tests/integration/test_paper_writer_interop.py` | New; cross-skill smoke test |
| `pyproject.toml` + `__init__.py` | 0.5.3 → 0.6.0 |
| `RELEASE_NOTES.md` | v0.6.0 entry |
| `CONTRACT.md` | New; durable interop doc for downstream consumers (paper-writer, presentation-maker) |
| `.commit-message-v0_6_0.txt` | Staged for git commit -F |
