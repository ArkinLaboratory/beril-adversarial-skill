# Cross-skill interop contract

**Status:** Authored alongside v0.6.0 (2026-05-02). Version-pinned
contract for downstream consumers of beril-adversarial.

This doc pins the interop surface that other skills (beril-paper-writer,
beril-presentation-maker) depend on. Changes to this contract are
breaking changes for those consumers and require coordinated updates.
The recurring failure mode it prevents is documented in memory entry
`feedback_cross_skill_contract_drift.md` — drift between paper-writer
v0.6.x output structure and the adversarial paper reviewer's input
expectations cost paper-writer two release cycles and forced an inline
fallback reviewer as a workaround.

---

## CLI surface (programmatic invocation)

```
beril-adversarial review <target> --type {paper|presentation|plan|project} [options]
```

For `--type paper` and `--type presentation`: `<target>` is an
**absolute path to the per-draft directory**.

For `--type plan` and `--type project`: `<target>` is a **project_id**
(directory name under `projects/`).

Exit codes:

| Code | Meaning | Consumer policy |
|---|---|---|
| 0 | Review completed clean | Use the JSON freely |
| 1 | User error (bad args, validation failure) | Surface to user; don't retry |
| 2 | Validator auto-corrected summary mismatches OR advisory warnings | The JSON is consumer-safe; proceed |
| 3 | Config error (claude CLI missing, prompt missing) | Surface; user must install/configure |

The wrapper is a thin Python delegation to `tools/adversarial_review.sh`;
exit codes propagate through unchanged.

---

## Paper review interop (`--type paper`)

### Required inputs (read by the reviewer)

The reviewer expects **paper-writer v0.6+ per-draft directory layout**:

```
projects/<project_id>/papers/draft_N/
├── manuscript.md           ← REQUIRED — assembled draft
├── 00_throughline.md       ← REQUIRED — chosen throughline + evidence map
├── references.md           ← REQUIRED — bibliography (markdown form)
├── citation_map.md         ← REQUIRED — claim→citation contract (NOTE: underscore, not hyphen)
├── reframing_log.md        ← OPTIONAL — auditable REPORT-drift acknowledgments (warns if absent — report_drift detection lacks context)
├── methods_provenance.md   ← OPTIONAL — tools/versions/snapshots
├── figures_inventory.md    ← OPTIONAL
├── tables_inventory.md     ← OPTIONAL (v0.6+ tables pipeline)
└── audit/                  ← created by the reviewer
```

Plus from the project root:
```
projects/<project_id>/
├── REPORT.md               ← REQUIRED — truth source for quantitative grounding
└── RESEARCH_PLAN.md        ← OPTIONAL — design intent for missing-section detection
```

If `manuscript.md` is missing AND the parent directory contains
flat-file drafts (`papers/draft{N}.md`), the reviewer emits a clear
migration message — legacy flat-file layout is NOT supported in
v0.6.0 (clean break per SCHEMA_V2_PAPER_DECISIONS.md).

### Output contract (written by the reviewer)

```
projects/<project_id>/papers/draft_N/audit/
├── adversarial_review.md   ← human-readable report
└── adversarial_review.json ← machine-readable; consumer contract
```

**Both files are written on every run.** Output paths are deterministic
(no auto-numbering); existing files are overwritten. Consumers should
move/rename old `audit/` directories before re-running if they need
to preserve prior reviews.

### JSON schema (`adversarial-review-paper.v2`)

See `SCHEMA_V2_PAPER_DECISIONS.md` for full design rationale. Quick
reference:

- **Single `findings[]` array.** No `deck_level_findings` field.
- **Section-level findings** have `section`, `line_range`,
  `paragraph_quote` (paragraph_quote is class-conditional —
  required for register_drift / claim_evidence /
  unbacked_quantitative / report_drift; optional for other
  classes).
- **Manuscript-wide findings** (narrative_weakness, missing_section,
  abstract_body_mismatch, throughline) OMIT `section` and the
  other section-level fields.
- **Severity:** P0 / P1 / P2 / info. info reserved for the single
  narrative_weakness finding.
- **Class enum (10 classes):**
  - Shared with presentation: `claim_evidence`,
    `unbacked_quantitative`, `register_drift`, `narrative_weakness`,
    `throughline`
  - Format-specific (paper-equivalent): `missing_section`,
    `section_arc`
  - Paper-only: `citation_reality`, `report_drift`,
    `abstract_body_mismatch`
- **`fix_target` values** (paper-writer prompt names): `methods.v1.md`,
  `results.v1.md`, `discussion.v1.md`, `introduction.v1.md`,
  `abstract.v1.md`, `limitations.v1.md`, `references.v1.md`,
  `00_throughline.md`, `reframing_log.md`, `manuscript.v1.md`.

### Auto-correction behavior

If the LLM's `summary` block disagrees with the actual `findings[]`
counts, the validator REWRITES the JSON with the derived summary,
preserves the LLM's original miscount to
`<draft_dir>/audit/adversarial_review.original-summary.json`, and
exits 2 (advisory). The .json is consumer-safe.

Findings array is the ground truth; consumers should parse
`findings[]` directly rather than trusting the summary block (the
summary block is for human readers and should now match thanks to
auto-correction, but the array is canonical).

---

## Presentation review interop (`--type presentation`)

### Required inputs

Presentation-maker per-draft directory (v0.3.1+ zone layout):

```
projects/<project_id>/talks/draft_N/
├── working/slide_spec.json     ← REQUIRED (v0.3.1+; legacy v0.3.0 = top-level)
├── 00_throughline.md           ← REQUIRED
├── 02_substories.md            ← REQUIRED
├── 03_slides/qa_anticipated.json ← REQUIRED
└── audit/                      ← created by the reviewer
```

The orchestrator detects layout version (v0.3.1+ vs legacy v0.3.0)
and reads from the right zone — added in v0.5.2 to handle
presentation-maker's zone reorganization.

### Output contract

Same shape as paper:

```
projects/<project_id>/talks/draft_N/audit/
├── adversarial_review.md
└── adversarial_review.json
```

### JSON schema (`adversarial-review-presentation.v2`)

See `SCHEMA_V2_DECISIONS.md` for full design. Same architectural
patterns as paper.v2 (single array; locus signaled by `slide_id`
presence; class-conditional `title_quote`; auto-correction).

Presentation v1 (`adversarial-review-presentation.v1`) is still
accepted by the validator with a deprecation warning, for forensic
compatibility with audit files from v0.4.x runs.

---

## Schema family compatibility matrix

| Schema | Status | Validator behavior |
|---|---|---|
| `adversarial-review-presentation.v1` | Deprecated | Accepted; deprecation warning; exit 2 |
| `adversarial-review-presentation.v2` | Current | Accepted; full validation |
| `adversarial-review-paper.v2` | Current (new in v0.6.0) | Accepted; full validation |

Future schema bumps will follow a deprecation cycle (new schema
accepted in parallel with prior for one release). Paper v1 is
explicitly NOT a thing — paper schema launched directly at v2.

---

## Cross-skill smoke test responsibility

Each consumer skill SHOULD have a smoke test that verifies its output
structure passes adversarial-skill's input validation. The
adversarial-skill side has `tests/integration/test_paper_writer_interop.py`
(added v0.6.0) that builds a synthetic paper-writer-shaped fixture
and asserts the orchestrator accepts it without input-validation
errors.

Paper-writer's responsibility (separate repo): a smoke test that
constructs a typical paper-writer output directory and invokes
`beril-adversarial review --type paper <draft_dir>` to verify the
canonical reviewer accepts the output structure.

When this contract changes (e.g., adding required input files,
renaming output paths, bumping schema version), BOTH smoke tests
need to be updated AND the consumer skills need coordinated releases.

---

## Coordinating retirement of paper-writer's fallback_reviewer.v1.md

paper-writer ships a `prompts/fallback_reviewer.v1.md` (291 lines,
3 detection classes — overclaim, citation rigor, throughline-
alignment) that runs as the in-loop reviewer when canonical
adversarial isn't available.

**The fallback reviewer is intentionally lighter scope and serves a
different purpose.** It is NOT a workaround to remove. After v0.6.0
of beril-adversarial lands, paper-writer can:

- Option A: Keep both. Use fallback for fast in-loop iteration; use
  canonical (`beril-adversarial review --type paper`) for thorough
  audit passes (e.g., before final draft).
- Option B: Switch to canonical by default; deprecate fallback.

The decision belongs to paper-writer team. This contract just makes
both options possible.
