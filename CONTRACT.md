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

## Severity vocabulary mapping

The v2 schemas use `P0` / `P1` / `P2` / `info` for severity values
(bug-tracker conventions; "P0" carries clearer "blocks ship"
semantics than "Critical"). Legacy markdown reviewers (`--type
project` / `--type plan`) and paper-writer's
`fallback_reviewer.v1.md` use the older `Critical` / `Important` /
`Suggested` vocabulary.

Consumers parsing the v2 JSON who need the legacy form (e.g., for
display continuity with older tools) can apply this bijective
mapping:

| v2 schema severity | Legacy markdown severity | When used |
|---|---|---|
| `P0` | `Critical` | Blocks ship — fabricated number, broken figure link, silent REPORT drift, abstract overclaim, citation fabrication. Triggers consumer's revise loop. |
| `P1` | `Important` | Visible quality regression — register drift, citation drift, missing-section, structural arc issues. Surfaces in next_actions. |
| `P2` | `Suggested` | Polish — wording preferences, citation drift on non-load-bearing claims, vague evidence pointers. |
| `info` | _no legacy equivalent_ | Reserved for the single Class 7 / Class 10 `narrative_weakness` finding — the deck/paper's biggest weakness as a strategic note for the speaker / author. Not a fix-ticket. |

Example consumer-side translation in Python:

```python
SEVERITY_TO_LEGACY = {"P0": "critical", "P1": "important",
                     "P2": "suggested", "info": "narrative_weakness"}

review = json.load(open("audit/adversarial_review.json"))
counts = {"critical": 0, "important": 0, "suggested": 0,
          "narrative_weakness": 0}
for f in review["findings"]:
    counts[SEVERITY_TO_LEGACY[f["severity"]]] += 1
```

**We deliberately do NOT emit a `severity_label` convenience field
in the JSON.** Adding optional carrier fields invites schema bloat;
the mapping is bijective and trivially computed. If display
continuity matters to a consumer, compute it in their parser.

---

## Iteration pattern (running the reviewer multiple times per draft)

The default output paths
(`<draft_dir>/audit/adversarial_review.{md,json}`) **overwrite** on
each run. This is fine for single-shot audit (the canonical use
case: user reviews → fixes → re-runs to verify) but hostile to
scripted iteration loops that need to compare findings across
rounds.

If your consumer runs the reviewer multiple times per draft (e.g.,
inside a review-rewrite loop that wants to measure delta), use
ONE of these two patterns:

### Pattern A — `--output` flag for per-run paths

The shell script's `--output` flag accepts a custom output
basename. Direct each run to a numbered file:

```bash
for round in 1 2 3; do
  beril-adversarial review "$draft_dir" \
      --type paper \
      --output "$draft_dir/audit/adversarial_review_round_${round}.md"
  # JSON path is derived from --output by replacing .md → .json:
  # adversarial_review_round_1.json, _2.json, _3.json
done
```

Note: `--output` is currently honored for `--type project|plan`
(which already auto-numbers their markdown outputs). For `--type
paper|presentation`, the v0.6.x default is canonical-name overwrite.
Auto-numbering for paper/presentation modes is being considered for
v0.7+; in v0.6.x, use Pattern B if you can't pass `--output`.

### Pattern B — Rename audit/ between runs

Move the previous audit aside before re-running:

```bash
for round in 1 2 3; do
  beril-adversarial review "$draft_dir" --type paper
  if (( round < 3 )); then
    mv "$draft_dir/audit" "$draft_dir/audit-round-$round"
  fi
done
# After loop: audit-round-1/, audit-round-2/, audit/ (final round)
```

**Pattern B is preferred** for downstream consumers because:
- It works identically for paper, presentation, and any future v2
  schema modes.
- The full `audit/` directory is preserved per round (including the
  auto-correction sidecar `*.original-summary.json` if it fired).
- Recovery from a bad round is `mv audit-round-N audit` — one step.

### Future: `--auto-number` flag (v0.7+)

A planned `--auto-number` flag for v0.7+ will, when set, name
outputs `adversarial_review_<N>.{md,json}` per run within `audit/`,
making Pattern A work without `--output` for paper and
presentation. **Default behavior in v0.6.x and after will remain
canonical-name overwrite** to avoid breaking existing consumers
(presentation-maker's `revise_loop.py` parses by canonical name).

---

## Validator ownership and shared-tool semantics

`tools/validate_presentation_review.py` (filename retained from
v0.5.x; handles both presentation v1+v2 and paper.v2 schemas as of
v0.6.0) is **owned by beril-adversarial-skill**. Both the
presentation-maker and paper-writer review-rewrite loops consume
its output (the validated/auto-corrected JSON) but should NOT
import or vendor it.

Why this matters:
- The validator implements the auto-correction behavior described
  above. Bypassing it means consumers see the LLM's miscounted
  summary block.
- Any schema additions (new classes, new optional fields) land
  here first. Consumers that re-implement validation will drift.
- The validator file is shipped inside this skill's wheel
  (`src/beril_adversarial/skill/tools/`) and deployed via
  `beril-adversarial install-skill <BERIL>`. Consumers should
  invoke `beril-adversarial review` (which runs the validator
  internally) and rely on its exit code, not call the validator
  directly.

If a consumer needs to re-validate a stored audit JSON
out-of-band, they MAY call the validator script directly via
`python3 <BERIL>/.claude/skills/beril-adversarial/tools/validate_presentation_review.py <path>`,
but this is a debugging convenience, not a contract surface.
Schema bumps may rename or relocate the script.

---

## Workflow example — paper-writer's perspective

The intended call flow when paper-writer wants a heavy adversarial
audit pass after assembling a draft. paper-writer's lighter
in-loop reviewer (`fallback_reviewer.v1.md`) keeps running per
drafting iteration; the canonical reviewer fires when paper-writer
wants the deeper audit (typically end of draft, before submission,
or before user review).

```bash
# Inside paper_writer.sh, after manuscript.md is assembled:
draft_dir="$PROJECT_DIR/papers/draft_$N"

# Invoke canonical reviewer via the CLI subcommand. Single source
# of truth; no need to know the deep filesystem path to the shell
# script.
beril-adversarial review "$draft_dir" --type paper
EXIT=$?

# Per-exit-code branching:
case $EXIT in
  0)
    # PASS — clean validation. JSON is consumer-safe.
    json="$draft_dir/audit/adversarial_review.json"
    md="$draft_dir/audit/adversarial_review.md"
    # Surface the .md to the user; route P0 findings from the JSON
    # to the planned v0.7+ review-rewrite loop.
    ;;
  2)
    # PASS-with-advisory: auto-correction or warnings fired.
    # The .json is still consumer-safe (validator rewrote the
    # summary block from the findings array). Sidecar at
    # <name>.original-summary.json preserves the LLM's miscount
    # for forensics. Treat the same as exit 0 for downstream
    # consumption; surface the auto-correction note to the user
    # if they want to debug LLM behavior.
    ;;
  1)
    # FAIL: non-correctable validation error. Most common cause
    # is unescaped " inside a JSON string field (per memory
    # feedback_llm_json_unfixable_in_parser.md). Re-running often
    # resolves it. The .md may still be useful for human review;
    # the .json is unsafe for downstream parsing.
    echo "Adversarial reviewer produced unsafe JSON; re-running" >&2
    beril-adversarial review "$draft_dir" --type paper
    EXIT=$?
    if [[ $EXIT -ne 0 && $EXIT -ne 2 ]]; then
      echo "Persistent failure; manual escalation needed" >&2
      # Fall back to fallback_reviewer.v1.md if you still need a
      # review for this drafting cycle.
    fi
    ;;
  3)
    # Config error: claude CLI missing, prompt missing, etc.
    # User must fix install. Don't retry.
    exit $EXIT
    ;;
esac
```

**On the v0.7+ review-rewrite loop (planned):** when paper-writer
adds a loop that consumes the JSON to drive revise prompts, the
intended pattern is:

```python
import json
findings = json.load(open(f"{draft_dir}/audit/adversarial_review.json"))["findings"]
for f in findings:
    if f["severity"] == "P0":
        # Route by fix_target field. Each value names a paper-writer
        # prompt: results.v1.md, methods.v1.md, abstract.v1.md, etc.
        # See SCHEMA_V2_PAPER_DECISIONS.md §"fix_target values".
        invoke_revise_prompt(
            target_prompt=f["fix_target"],
            section=f.get("section"),  # absent for manuscript-wide findings
            line_range=f.get("line_range"),
            paragraph_quote=f.get("paragraph_quote"),
            issue=f["issue"],
            fix_hint=f["fix_hint"],
        )
# After the revise pass, re-run the reviewer to measure improvement.
```

**Coordinating with `fallback_reviewer.v1.md`:** the fallback
reviewer is intentionally lighter scope (3 detection classes vs
canonical's 10). Both modes can coexist:
- Fallback for fast in-loop iteration during drafting (cheap,
  narrow).
- Canonical for thorough audit passes (full 10 classes, dual
  output, JSON for consumer-loop use).

paper-writer team picks the default. Both are valid.

---

## Workflow example — presentation-maker's perspective

The intended call flow for presentation-maker's `revise_loop.py`
after `merge_and_assemble` produces a deck:

```python
import json
import subprocess
import sys

def adversarial_review(draft_dir):
    """Invoke beril-adversarial review on a presentation draft.
    Returns parsed JSON if consumer-safe; raises if not."""
    result = subprocess.run(
        ["beril-adversarial", "review", str(draft_dir),
         "--type", "presentation"],
        capture_output=True, text=True,
    )
    sys.stderr.write(result.stderr)  # surface validator output
    sys.stdout.write(result.stdout)

    if result.returncode in (0, 2):
        # PASS or PASS-with-advisory; .json is consumer-safe
        json_path = draft_dir / "audit" / "adversarial_review.json"
        return json.load(open(json_path))
    elif result.returncode == 1:
        # FAIL — non-correctable; one retry, then escalate
        raise RuntimeError(
            "Adversarial reviewer produced unsafe JSON; "
            "see stderr for details. Re-run or escalate."
        )
    else:  # exit 3 — config error
        raise RuntimeError("beril-adversarial not installed properly")

# In revise_loop.py main flow:
review = adversarial_review(draft_dir)

# Walk findings and route revise prompts per-finding
for finding in review["findings"]:
    if finding["severity"] != "P0":
        continue  # default policy: P0 → revise; P1+P2+info → next_actions
    target = finding["fix_target"]
    if target == "slide_compose.v1.md":
        invoke_revise_slide(
            slide_id=finding["slide_id"],
            issue=finding["issue"],
            fix_hint=finding["fix_hint"],
        )
    elif target == "qa_anticipated.v1.md":
        invoke_revise_qa(...)
    elif target == "00_throughline.md":
        # Throughline changes cascade; surface for user confirmation
        # rather than auto-revise.
        next_actions.append(finding)
    # ... etc
```

**Layout-detection awareness:** presentation-maker v0.3.1+ uses a
4-zone draft directory (`deliverable/`, `narrative/`, `working/`,
`audit/`). The orchestrator auto-detects this layout (added v0.5.2)
and reads `slide_spec.json` from `working/` if present, else from
the top level (legacy v0.3.0). `revise_loop.py` doesn't need to
know which layout — the reviewer handles both transparently.

**The audit/ directory is shared:** both presentation-maker (which
may write its own audit artifacts) and beril-adversarial (which
writes `adversarial_review.{md,json}`) co-exist in
`<draft_dir>/audit/`. Filename collision is avoided by the
canonical names; if presentation-maker adds new audit artifacts in
the future, prefix them clearly to keep the namespace clean.

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
