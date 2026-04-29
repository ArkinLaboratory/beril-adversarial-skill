# beril-adversarial-skill — Release Notes

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
