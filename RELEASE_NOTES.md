# beril-adversarial-skill — Release Notes

---

## v0.6.2 — 2026-05-02 (JSON-validity hardening)

**Problem:** First live paper review on draft_7 (post-v0.6.1) found
substantively excellent issues (8 P0s including fabricated numbers
cross-referenced to reframing_log entries marked "escalated but not
repaired") — but the .json output was malformed. The reviewer wrote
unescaped inner quotes inside a `paragraph_quote` field:

```
"paragraph_quote": "Robust rank analysis (Methods §"Experimental Prioritization") identified ..."
```

Parser saw the string end at `§"`, then choked on `Experimental`.
Per memory entry `feedback_llm_json_unfixable_in_parser.md`, this
specific failure mode is **NOT algorithmically repairable** — the
parser cannot disambiguate "unescaped inner quote" from "two
adjacent strings with no comma." The fix is at the prompt.

A second LLM JSON failure mode (trailing commas before `}` or `]`)
IS algorithmically repairable per `feedback_llm_json_trailing_commas_repairable.md`
— added defensively even though it didn't surface in the draft_7 run.

### Fix

**1. Prompt-level anti-pattern.** Both `adversarial_paper.v2.md` and
`adversarial_presentation.v2.md` now include an explicit
"unescaped-inner-quote" anti-pattern in their JSON validity sections:
- The wrong way (literal example matching the draft_7 failure)
- Four correct alternatives: backslash-escape, curly quotes,
  single quotes, rephrasing
- Explicit warning that the validator CANNOT fix this and the run
  is wasted if it occurs
- List of common offender fields per reviewer (paragraph_quote,
  title_quote, issue, report_evidence quotes, fix_hint)

**2. Lenient JSON loader.** `validate_presentation_review.py` adds a
`lenient_json_load(text)` helper that:
- Tries strict `json.loads(text)` first
- On failure, regex-strips trailing commas (`,(\s*[}\]])` → `\1`)
- Re-tries
- On second failure, raises the ORIGINAL error (so the operator sees
  the actual problem, not a confusing post-repair artifact at a
  different line/column)

This catches one common LLM JSON failure mode (trailing commas) for
free without false positives. It does NOT fix unescaped-quote
failures — those still surface as validator FAIL with a helpful
hint pointing at the likely cause.

**3. Diagnostic hint.** When the validator fails on a JSONDecodeError
mentioning "delimiter," it now prints a hint suggesting the operator
check for unescaped inner quotes. Saves a context-switch to the
docs.

### Tests

+9 new tests:
- 5 lenient-loader tests: clean JSON unchanged; trailing-comma
  repair (object, array, multi-location); unrepairable failures
  surface original error.
- 2 CLI subprocess tests: trailing-comma doc validates clean;
  unescaped-inner-quote doc fails with helpful hint.
- 2 prompt-content tests: paper.v2 prompt + presentation.v2 prompt
  both contain the anti-pattern guidance.

Full suite: 164/164 pass.

### Operator impact

```bash
pipx install --force <v0.6.2 wheel>
beril-adversarial install-skill <BERIL_ROOT>
```

The next paper or presentation review run picks up the prompt
update. v0.6.0/v0.6.1 reviews that produced malformed JSON can be
re-run with v0.6.2 to get valid JSON output.

### What v0.6.2 does NOT do

- Does NOT attempt heuristic repair of unescaped inner quotes — per
  memory, these are not safely repairable. The fix is the prompt.
- Does NOT bump the schema. paper.v2 and presentation.v2 schemas
  unchanged. This is purely prompt + validator hardening.
- Does NOT re-validate Adam's existing draft_7 audit JSON. That
  file is still malformed; the .md report is intact and contains
  the substantive findings.

### Recurring pattern observation

This is the third LLM-output-discipline backstop in the v0.4-v0.6
series:
- v0.4.1: summary count auto-correction (LLM arithmetic on
  self-output)
- v0.6.2: JSON validity (unescaped inner quotes; trailing commas)
- (Future): consider catching other patterns in the same place

The pattern: prompts try to discipline; validators enforce what's
algorithmically enforceable; failures that aren't algorithmically
repairable get sharp prompt anti-patterns + diagnostic hints. Don't
prompt-train arithmetic; don't try to repair quotes; do auto-correct
counts; do repair trailing commas.

---

## v0.6.1 — 2026-05-02 (UX hotfix: schema-aware labels)

**One-line problem:** The validator's PASS message and `summary_stats`
keys hard-coded the presentation vocabulary ("slide-level finding(s)",
"deck-level finding(s)") regardless of which schema the JSON used. On
v0.6.0's first live paper review (against
`functional_dark_matter/papers/draft_7`), the success message read:

```
PASS: 11 slide-level finding(s), 5 deck-level finding(s) (8 P0, 7 P1, 0 P2, 1 info)
```

…for a paper review. Confusing because papers don't have slides.
The underlying counts were correct (11 section-level + 5 manuscript-
wide), just labeled with the wrong terminology.

### Fix

`tools/validate_presentation_review.py` `validate()` now returns
schema-aware labels in `summary_stats`:

- **Presentation schemas** (v1 + v2): `locus_label = "slide-level"`,
  `non_locus_label = "deck-level"` (preserves existing terminology).
- **Paper schema** (`adversarial-review-paper.v2`):
  `locus_label = "section-level"`, `non_locus_label = "manuscript-wide"`.

`main()`'s success message uses these labels. A paper review now reads:

```
PASS: 11 section-level finding(s), 5 manuscript-wide finding(s) (8 P0, 7 P1, 0 P2, 1 info)
```

### Backwards compatibility

The legacy `summary_stats["slide_findings"]` and
`summary_stats["deck_findings"]` keys are preserved alongside the new
`locus_count` and `non_locus_count` keys. Any caller scraping the
legacy keys continues to work (numbers are correct; only the LABELS
were wrong).

New keys exposed in `summary_stats`:

- `locus_count`, `non_locus_count` — schema-neutral counts
- `locus_label`, `non_locus_label` — schema-appropriate display labels
- `schema_version`, `schema_family` — the validator's detected schema

### Tests

+4 new unit tests asserting the label routing (paper → section-level/
manuscript-wide; presentation → slide-level/deck-level; legacy keys
preserved; CLI success message uses paper labels for paper schema).
+1 integration test updated to check paper-aware labels in the v2
synthetic-review subprocess test. Full suite: 155/155 pass.

### Operator impact

```bash
pipx install --force <v0.6.1 wheel>
beril-adversarial install-skill <BERIL_ROOT>
```

No schema changes; no contract changes. Pure UX correction. paper-
writer team can pick this up at their convenience; v0.6.0 is fully
functional, just with confusing labels.

---

## v0.6.0 — 2026-05-02

**Paper alignment + programmatic CLI subcommand. Coordinated v0.6.x
release with paper-writer.**

paper-writer v0.6.x adopted per-draft directory layout
(`papers/draft_N/manuscript.md` + `00_throughline.md` + ...) replacing
the legacy flat-file layout. The adversarial paper reviewer was still
on v1 architecture (markdown-only output, flat-file inputs), forcing
paper-writer to ship an inline `fallback_reviewer.v1.md` workaround.

v0.6.0 closes the gap on three fronts simultaneously: (1) new paper
prompt that reads paper-writer's current dialect, (2) `adversarial-
review-paper.v2` schema with dual md+json output and the same auto-
correction backstop as presentation v2, (3) `beril-adversarial review`
Python CLI subcommand so paper_writer.sh can invoke the canonical
reviewer programmatically without knowing the deep filesystem path
to the shell script.

### What changed

- **New schema**: `adversarial-review-paper.v2`. Single `findings[]`
  array (no `deck_level_findings` field — single-array invariant
  matches presentation v2). Section-level findings have `section`,
  `line_range`, `paragraph_quote` (the latter is class-conditional —
  required for `register_drift` / `claim_evidence` /
  `unbacked_quantitative` / `report_drift`; optional for the rest,
  mirroring v0.5.3 presentation `title_quote` rules). Manuscript-wide
  findings (narrative_weakness, missing_section, abstract_body_mismatch,
  throughline) omit section-level fields.

- **New prompt**: `prompts/adversarial_paper.v2.md` (1379 lines).
  10 detection classes with strong intersection with presentation v2:
  - Shared (5): `claim_evidence`, `unbacked_quantitative`,
    `register_drift`, `narrative_weakness`, `throughline`
  - Format-specific (2): `missing_section`, `section_arc`
  - Paper-only (3): `citation_reality`, `report_drift`,
    `abstract_body_mismatch`
  Worked examples for register_drift, citation_reality, report_drift,
  and the narrative_weakness killshot — grounded in paper-writer-shaped
  scenarios.

- **Orchestrator update**: `tools/adversarial_review.sh` adds
  `run_paper_review_v2` early dispatch (mirror of
  `run_presentation_review`). `--type paper` requires per-draft
  directory layout; legacy flat-file projects get a clear migration
  message. Output written to
  `papers/draft_N/audit/adversarial_review.{md,json}`. Skips
  `--consolidate`, `--reviewer codex`, `--reviewer claude,codex`
  (single-pass v1 paper mode; revisit fusion in v0.7+).

- **Validator extended**: `tools/validate_presentation_review.py` now
  accepts BOTH presentation v1+v2 AND paper.v2 schemas. Per-schema
  validation enforces clean separation — paper docs reject
  presentation-only classes (`qa_softball`, etc.); presentation docs
  reject paper-only classes (`citation_reality`, etc.). Auto-correction
  behavior from v0.4.1 preserved across all schemas.

- **New CLI subcommand**: `beril-adversarial review <target> --type X
  [options]`. Thin Python wrapper around `tools/adversarial_review.sh`.
  Single source of truth (the shell script); the wrapper just resolves
  the script path and propagates exit codes. Discoverable via
  `beril-adversarial --help`. Suitable for invocation from other
  skills' orchestrators (paper_writer.sh, presentation-maker, etc.).

- **Cross-skill interop contract**: New `CONTRACT.md` documents the
  full surface (CLI, input expectations, output paths, schema family,
  auto-correction behavior). Memory entry
  `feedback_cross_skill_contract_drift.md` warned about the recurring
  drift failure mode; this doc and the new integration tests are the
  durable preventives.

- **Tests**: 140 unit tests + 6 new integration tests in
  `tests/integration/test_paper_writer_interop.py` (synthetic
  paper-writer v0.6+ fixture; orchestrator dispatch validation;
  legacy-layout rejection check; paper.v2 schema validation;
  deck_level_findings rejection). Full suite: 146/146 pass.

### Breaking changes

- **`--type paper` requires per-draft layout.** Legacy
  `papers/draft{N}.md` flat-file projects get a clear migration
  message but cannot be reviewed by v0.6.0. Either re-run
  paper-writer at v0.6+ to produce per-draft directories, or pin
  beril-adversarial at v0.5.3 for legacy projects. Most BERIL
  projects have already migrated; this should be a non-event for
  current paper-writer users.

- **`adversarial_paper.v1.md` replaced with deprecation stub.** v1
  prompt content is preserved in git history. v0.6.0 orchestrator
  loads `adversarial_paper.v2.md` only.

### Migration

- **Existing presentation audits** (presentation v1, presentation v2):
  unchanged. Validator accepts both with the existing rules.
- **paper-writer integration**: install v0.6.0 of beril-adversarial,
  refresh deployed skill via `beril-adversarial install-skill
  <BERIL>`, then paper_writer.sh can invoke `beril-adversarial review
  --type paper <draft_dir>` and either retire `fallback_reviewer.v1.md`
  OR keep the fallback as a fast in-loop option (both serve their
  purposes; see CONTRACT.md).

### Architectural decisions

See `SCHEMA_V2_PAPER_DECISIONS.md` for the schema design rationale,
class enum analysis (5 shared + 2 parallel + 3 paper-only), and the
clean-break decision on legacy paper layout. See `CONTRACT.md` for
the durable interop contract.

### Operator impact

```bash
pipx install --force <v0.6.0 wheel>
beril-adversarial install-skill <BERIL_ROOT>
```

Existing `--type plan|project|presentation` behavior is preserved.
New `--type paper` behavior expects per-draft layout.

---

## v0.5.3 — 2026-05-02 (validator: title_quote class-conditional + model docs)

Two fixes from the live A/B comparison run on
`core_gene_tradeoffs/draft_2`.

### Fix: title_quote requirement is class-conditional

The validator previously required `title_quote` for any finding
with `slide_id` present. This was over-strict for finding classes
whose criticism isn't about specific slide text:

- `substory_arc` — criticism is structural ("this substory is over-
  budget", "S1 has redundant slide"). Reference slide_id is a
  representative slide, not the criticism's target.
- `missing_slide` — by definition, the slide doesn't exist; there
  is no title to quote.
- `throughline`, `narrative_weakness`, `unbacked_quantitative` —
  criticism is about deck-level patterns or numbers whose location
  may not be the slide title.

Live failure: 2026-05-02 sonnet-4-6 review of `core_gene_tradeoffs/
draft_2` produced F015 + F016 as `substory_arc` findings without
title_quote (correctly — the criticism was about S1's redundant
slide and S3's over-budget arc, not slide text). The validator
rejected the JSON, blocking the revise loop.

`TITLE_QUOTE_REQUIRED_CLASSES = {"register_drift", "claim_evidence",
"qa_softball"}`. For these, title_quote is still required when
slide_id is present — the criticism targets specific slide text and
the reviewer must quote it for accountability. For other slide-
level finding classes, title_quote is optional.

5 new tests cover the class-conditional logic: parametrized over
the 4 optional-quote classes (substory_arc, missing_slide,
throughline, unbacked_quantitative) and the 3 required-quote
classes (register_drift, claim_evidence, qa_softball). Plus a test
that other slide-level fields (slide_position, slide_layout) are
still required regardless of class.

### New: Model selection documentation in SKILL.md

A new "Model selection" section captures the empirical Sonnet 4.6
vs Opus 4.6 A/B comparison from the May 2026 live run:

- Sonnet 4.6 default justified: 17 findings vs Opus's 16; ~5× cost
  ratio doesn't justify the marginal unique catches.
- Different blind spots — Sonnet catches detail (citation existence,
  verbatim text), Opus catches methodology grounding + null-
  hypothesis framing.
- Fusion (`--reviewer claude,codex`) recommended for high-stakes
  decks; Sonnet-alone for routine iteration.

### Verification

- 50 tests pass (45 in v0.5.2 + 5 new for class-conditional title_quote).
- Re-validating the failed `adversarial.sonnet-4-6.json` from the
  live A/B: validator now reports 0 errors + 4 auto-correctable
  summary corrections (which exit 2, rewrite summary, allow revise
  loop to proceed). The JSON is now usable as revise-loop input.

---

## v0.5.2 — 2026-05-02 (presentation-maker v0.3.1+ layout support)

Cross-skill contract drift fix. presentation-maker v0.3.1
(2026-05-01) reorganized per-draft directories into 4 zones —
`deliverable/`, `narrative/`, `working/`, `audit/`. The adversarial
reviewer's read paths were never updated; reviewing a v0.3.1+ draft
errored with "required input missing: slide_spec.json" because it
was looking at the old top-level location instead of `working/`.

### Fix

- `adversarial_review.sh` now detects layout version from disk:
  - v0.3.1+ (4-zone): reads from `working/slide_spec.json`,
    `narrative/00_throughline.md`, `narrative/02_substories.md`,
    `working/03_slides/qa_anticipated.json`,
    `working/04_speaker_notes/`.
  - v0.3.0 legacy (flat): reads from `slide_spec.json`,
    `00_throughline.md`, `02_substories.md`,
    `03_slides/qa_anticipated.json`, `04_speaker_notes/`.
  - Error message names BOTH expected paths if neither layout
    matches.
  - Stderr logs the detected layout version for traceability.
- `adversarial_presentation.v2.md` (the system prompt): the path
  documentation table now shows v0.3.1+ canonical paths with v0.3.0
  legacy as a secondary column. New "Layout note" + "use the runtime
  paths" instruction at the top of the source-files section so the
  LLM doesn't get confused by the dual paths.
- 5 new unit tests in `test_layout_detection.py` exercise both
  layouts + missing-file error cases. Use a synthetic BERIL root
  with symlinked skill directory so the script's preflight passes
  without needing a real install.

### Cross-skill contract — captured

This was the second bug of this class in 24 hours (the first was
the figure resolver at presentation-maker v0.3.2.1, also caused by
v0.3.1's layout reorg landing without consumer updates). Memory
entry `feedback_cross_skill_contract_drift.md` captures the pattern
+ proposed mitigations (versioned shared interface doc, cross-skill
smoke test, change-checklist for layout-coupled changes).

### Companion to presentation-maker v0.3.2.4

That release fixed an orchestrator-side reference to the wrong
adversarial CLI name (`beril-adversarial-cli` → `beril-adversarial`).
Together v0.3.2.4 + this v0.5.2 close the cross-skill integration
gap that surfaced during draft_2 adversarial A/B prep.

---

## v0.5.1 — 2026-05-02 (model bump hotfix)

One-line fix: `CLAUDE_DEFAULT_MODEL` in `adversarial_review.sh`
bumped from `claude-sonnet-4-20250514` to `claude-sonnet-4-6`. The
prior default was the original Sonnet 4 from May 2025 (~12 months
stale); Sonnet 4.5 (Sept 2025) and 4.6 (current) have shipped since.

The `--model` override flag is unchanged; users who pin a specific
model in their invocation are unaffected. Default-only callers get
current-generation Sonnet automatically.

Companion to beril-presentation-maker v0.3.2.4 (same model bump in
that orchestrator + a separate fix that corrects this skill's CLI
name reference from `beril-adversarial-cli` → `beril-adversarial`).

---

## v0.5.0 — 2026-04-29

**Schema bump: `adversarial-review-presentation.v2` collapses the
dual-array structure to a single `findings[]` array.**

Live test of v0.4.1 against draft_10 surfaced the third distinct
schema violation in three runs: the LLM placed `narrative_weakness`
and `missing_slide` findings into the slide-level `findings[]` array
instead of `deck_level_findings[]`, where they failed validation due
to missing slide-level fields. Schema v1's two-array structure was
the root cause — the LLM had to pick which array a finding belonged
in, and prompt-level instruction wasn't load-bearing enough.

v2 eliminates the choice. There is one `findings[]` array. Deck-level
findings are signaled by absence of `slide_id`. The LLM cannot put
findings in the wrong array because there is only one array.

### What changed

- **Schema v2:**
  - Single `findings[]` array. ALL findings live here.
  - `deck_level_findings[]` field is REMOVED. v2 docs that include it
    are rejected.
  - `slide_id`, `slide_position`, `slide_layout`, `title_quote` become
    OPTIONAL on each finding. Presence of `slide_id` triggers the
    requirement for the others (slide-level finding); absence
    indicates a deck-level finding.
  - ID namespace unified: `F001`, `F002`, ... across the entire array.
    `DL###` ids are gone (they were a v1 convention).
- **Prompt v2** (`adversarial_presentation.v2.md`, 1746 lines):
  - Output Contract section rewritten to use single-array schema.
  - JSON schema example shows the new shape with deck-level findings
    inline (no `slide_id` and other slide-level fields omitted).
  - Worked examples updated: missing-slide example uses `F017`
    instead of `DL001`; narrative_weakness killshot uses `F018`
    instead of `DL00X`.
  - Self-skepticism check #9 (id uniqueness) updated to clarify
    single-namespace.
- **Validator dual support** (`validate_presentation_review.py`):
  - Accepts both `adversarial-review-presentation.v1` and `.v2`.
  - v1: emits a deprecation warning on stderr; validates per legacy
    rules (two arrays).
  - v2: rejects `deck_level_findings` field; per-finding slide-level
    fields conditionally required by `slide_id` presence.
  - `compute_correct_summary` works on either shape; auto-correction
    behavior from v0.4.1 unchanged.
  - `summary_stats["slide_findings"]` and `["deck_findings"]` now
    count by `slide_id` presence rather than array membership —
    consistent semantics across both schemas.
- **Orchestrator** (`tools/adversarial_review.sh`): loads `.v2.md`;
  user-prompt body sets `schema_version: adversarial-review-presentation.v2`
  and `prompt_version: adversarial_presentation.v2`. Includes
  explicit instruction "do NOT emit a deck_level_findings field."
- **`adversarial_presentation.v1.md`** is now a deprecation stub
  (preserved because the sandbox cannot `rm` files on the macOS
  mount; safe to remove from the repo with `git rm` when convenient).

### Migration

- **Existing audit files** (e.g., draft_9, draft_10 from v0.4.x runs):
  remain in v1 format. The validator continues to accept them with a
  deprecation warning. Re-running the reviewer produces v2 audits.
- **No real consumers** of v1 yet; presentation-maker v0.3.0 review-
  rewrite loop is planned, not built. v2 is the contract from
  shipment forward.
- **Future schema bumps** will follow a deprecation cycle (v2
  accepted in parallel with v3 for one release). v1's clean drop is
  the exception, not the precedent.

### Tests

+10 new tests across the two test files; full suite 117/117 pass.
Coverage:
- v1 docs accepted with deprecation warning
- Unknown schema_version (`v99`) rejected
- v2 docs with `deck_level_findings` field rejected
- v2 finding without `slide_id` valid (it's deck-level)
- v2 finding with `slide_id` requires the other slide-level fields
- The 4 pre-existing summary-mismatch tests still route to
  `summary_corrections` not errors (auto-correct behavior preserved
  from v0.4.1)
- The v1 prompt file is a deprecation stub (catches accidental
  legacy-content restoration)
- `install-skill` ships `.v2.md`

### Operator impact

- `pipx install --force` the v0.5.0 wheel.
- `beril-adversarial install-skill <BERIL_ROOT>` to refresh the
  deployed prompts.
- New runs emit v2; old audit files (v1) remain readable.

---

## v0.4.1 — 2026-04-29

**Bugfix release: validator auto-corrects summary count mismatches.**

Live test of v0.4.0 against draft_10 (a fresh presentation-maker
output) revealed that the LLM consistently mis-counts between the
findings array and the summary block. Two consecutive runs both
emitted P0/P1 counts that disagreed with the actual array contents
(off-by-one, opposite directions). The mismatches are not stochastic
but deterministic — LLMs are intrinsically bad at arithmetic on their
own output, and the prompt's "recount before emitting" instruction
catches ~80% of cases but isn't reliable.

### Fix

`tools/validate_presentation_review.py` now AUTO-CORRECTS summary
count mismatches:

- New helper `compute_correct_summary(findings, deck_findings)` is
  the single source of truth for deriving summary counts.
- `validate()` now returns `(errors, summary_corrections, warnings,
  stats)` — summary mismatches route to a separate channel from
  hard errors.
- `main()` rewrites the JSON file in place with the corrected summary
  whenever there are mismatches AND no non-correctable errors.
  Original (mismatched) summary is preserved alongside the file as
  `<name>.original-summary.json` for forensics.
- Exit code: 2 (warning) on auto-correction. Was 1 (fail) in v0.4.0.
- Prominent `AUTO-CORRECTED` block on stderr lists the original
  miscounts and points at the sidecar.

### What still fails hard (exit 1)

Non-correctable errors:
- Schema literal mismatch (`schema_version` not the v1 literal).
- Required field missing on any finding.
- Invalid `class` / `severity` / `confidence` enum values.
- Duplicate finding IDs.
- `narrative_weakness` invariant violations (severity not `info`,
  more than one such finding).

These cannot be auto-corrected without changing semantics. Re-run
the reviewer to fix.

### Prompt update

The prompt now tells the LLM that summary auto-correction exists,
with explicit guidance: if you face a choice between "fix the
summary" and "reclassify a finding to make the summary match,"
keep the finding correct and let the validator fix the summary.

### Tests

+4 new tests in `test_validate_presentation_review.py`:
`compute_correct_summary` deterministically derives the canonical
summary; CLI auto-corrects + writes sidecar + exits 2; auto-correction
preserves findings array byte-for-byte; non-correctable errors block
auto-correction (file unchanged, no sidecar written).

The four pre-existing summary-mismatch tests were updated to assert
the routing-to-corrections behavior (was: assert routing-to-errors).

Full suite: 112/112 pass.

### Trade-offs

This change makes summary count mismatches NOT a release-blocker.
The findings array is the ground truth; consumers of the JSON
should parse `findings[]` and `deck_level_findings[]` directly
rather than trust the summary block. The summary is a convenience
for human readers and is now backstopped by deterministic
post-correction.

### Operator impact

Existing v0.4.0 deployments work unchanged — re-installing the
v0.4.1 wheel via `pipx install --force` + `beril-adversarial
install-skill` is the only step. No prompt re-run needed; existing
review JSON files are unchanged unless re-validated.

---

## v0.4.0 — 2026-04-28

**New: `--type presentation` mode.**

Adds adversarial review of `beril-presentation-maker` draft directories.
Single-pass reviewer with 7 detection classes, dual output contract,
and a JSON schema designed as the consumer contract for the
presentation-maker review-rewrite loop (planned v0.3.0).

### What's new

- New system prompt: `prompts/adversarial_presentation.v1.md` (1746
  lines, exceeds spec §11's 1500-line guidance). Operationalizes
  spec §4's seven detection classes: throughline integrity,
  claim-evidence load-bearing, tier-language register, Q&A
  anti-strawman, substory→slide arc coherence, missing-slide /
  coverage gaps, deck's biggest narrative weakness. EIGHT worked
  examples walk through real draft_9 slides:
  - register-drift on slide 14 (61.7% / Fisher p=0.031)
  - missing-slide for top-N candidates
  - Q&A softball on slide 22 (Class 4 introductory pattern)
  - substory-arc burial in S3 (climax slide 19 vs 20)
  - throughline filler punchline (S2 vs S3 contrast)
  - narrative_weakness killshot template
  - **caveat-burial detection on slide 18** (Class 2 sub-pattern;
    added post-first-live-run after the reviewer missed the
    weight-sensitivity caveat absence on slide 18)
  - **Q&A "appears defensive but doesn't land" pattern on slide 22**
    (added post-first-live-run after the reviewer emitted "No
    findings" on Q&A; the new example explicitly flags that "No
    findings" verdict as a sign-of-failure trigger to re-do the
    class)
  Self-skepticism pass updated with explicit re-do triggers for
  Q&A under-fire and caveat-burial cross-reference.
- New orchestrator dispatch: `tools/adversarial_review.sh` accepts
  `--type presentation <draft_dir>`. The draft_dir is an absolute
  path (cwd auto-detection is not supported for this type), and the
  script resolves `<draft_dir>/../..` as the project_dir to find
  REPORT.md (the truth source for quantitative grounding).
- Dual output: writes both `<draft_dir>/audit/adversarial_review.md`
  (human-readable) and `<draft_dir>/audit/adversarial_review.json`
  (machine-readable). The .json carries `schema_version:
  "adversarial-review-presentation.v1"` and is the contract surface
  for the presentation-maker review-rewrite loop.
- New programmatic post-checker:
  `tools/validate_presentation_review.py` (replaces the inline shell
  heredoc validator in v0.4.0 alpha). Verifies schema literal,
  required-field presence per finding, severity/class enum
  membership, summary-count consistency against actual array
  contents, finding-id uniqueness, narrative_weakness invariants
  (exactly one, severity=info). Advisory warnings for zero-P0 on a
  20+ slide deck (possible reviewer under-fire) and missing
  narrative_weakness. Replicates paper-writer's post-checker
  pattern (memory: feedback_prompt_discipline_needs_post_check.md).
- Severity grades: `P0` / `P1` / `P2` / `info`. P0 triggers the
  consumer's revise loop; P1 + P2 + info surface in `next_actions`.
- Narrowed tool grant: the reviewer subprocess gets only
  `Read, Write, Grep, Glob`. No WebSearch (would invite citation
  fabrication on a deck with no canonical bibliography to verify).
  No Bash (the work is grep-and-compare across local files).
- 51 new unit tests across two files:
  `tests/unit/test_presentation_review.py` (26 tests — prompt
  content, dispatch validation, documentation, hard-error guards,
  post-iteration worked-example presence) and
  `tests/unit/test_validate_presentation_review.py` (27 tests
  — pass cases, schema validation, required-field checks, summary
  consistency, narrative_weakness invariants, advisory warnings,
  CLI exit codes). Full suite: 106/106 pass.
- Documentation updated: README.md, SKILL.md, slash command doc all
  describe the new mode + the draft_dir argument shape + the
  per-type defaults.

### Skipped for `--type presentation` v1 (vs. paper/project/plan)

- `--consolidate` (presentation iteration is owned by
  presentation-maker's review-rewrite loop, not by this script).
- `--reviewer claude,codex` fusion (single-pass v1; multi-pass
  fusion is v2).
- `--reviewer codex` solo (no programmatic Write detection on
  codex; dual-file output requires verification).
- `--depth quick|deep` (single depth for v1).
- Compliance critic + fix pass (the prompt enforces JSON validity
  itself; running a critic on dual-file output is non-trivial).
- Citation verification gate (no canonical bibliography to verify
  against on a deck).

### Breaking changes

None. All existing `--type plan|project|paper` behavior is
preserved; the `--type` validation just admits a fourth value.

### Acceptance criteria (from SPEC §11)

- [x] `prompts/adversarial_presentation.v1.md` lands; mirrors
  `adversarial_paper.v1.md` shape.
- [x] `tools/adversarial_review.sh` adds `run_presentation_review`
  dispatch.
- [x] `tests/unit/test_presentation_review.py` ≥5 tests, all pass
  (22 tests shipped; full suite 75/75).
- [x] No breaking changes to `--type paper / plan / project` modes.
- [ ] **Live test against draft_9 finds ≥6 of the 8 spec-listed
  issues.** Cost ≤ $1.50 on Sonnet. *(Pending Adam's run; runbook
  in `V0_4_0_PUNCH_LIST.md` Tier D.)*
- [x] `audit/adversarial_review.md` is human-readable;
  `audit/adversarial_review.json` parses + matches schema (the
  prompt + post-run sanity-check enforces this).
- [x] RELEASE_NOTES.md updated with v0.4.0 narrative *(this file)*.

### Architectural decisions

See `V0_4_0_PUNCH_LIST.md` § "Architectural decisions baked into
v0.4.0" for the 10 decisions made (model choice, schema versioning,
no WebSearch, confidence field, single-pass v1, etc.).

---

## v0.3.0 — 2026-04-?? (predates this notes file)

Adds additivity discipline for multi-round reviews.
Carryover-from-Prior-Rounds section comes first; severity counts
reflect new-this-round only; canonical consolidated file is the
live baseline for the next round.

---

## v0.2.0 — 2026-04-?? (predates this notes file)

Adds the programmatic citation verification gate. Every 9-field
citation block in a review is verified against Crossref (DOI) and
NCBI PubMed (PMID); fabricated citations are marked inline with a
`> ⚠️ **CITATION FABRICATED**` blockquote and listed in a Citation
Verification report appended to the review.

---

## v0.1.0 — first release

Three review types (`plan`, `project`, `paper`), multi-model
fusion (`--reviewer claude,codex`), provenance-tracked
consolidation across rounds, depth tiers, compliance critic
+ fix pass, stream-json parser for end-of-run cost summary
+ programmatic Write verification.
