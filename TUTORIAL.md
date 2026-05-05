# BERIL Adversarial Reviewer — Tutorial

A skill-specific guide for reading, interpreting, and iterating on adversarial reviews. Assumes you've already installed the skills and have a draft to review.

> **For install + configure + first-time setup**, start with the cross-skill **[PARTICIPANT-RUNBOOK.md](https://github.com/ArkinLaboratory/beril-presentation-maker-skill/blob/main/docs/cross-skill/PARTICIPANT-RUNBOOK.md)** (covers all 4 plug-in skills end-to-end). This tutorial is the adversarial-specific layer that sits on top.

> **For operator hub deployment**, see [HUB_INSTALL.md](HUB_INSTALL.md). For consumer integration (paper-writer / presentation-maker), see [CONTRACT.md](CONTRACT.md).

**Audience:** Researchers using `/beril-adversarial` in Claude Code on the BERIL hub who have already run a review and want to make the most of it.

**Time:** 5 minutes to read; 5–10 minutes per review run.

**Cost:** $0.50–$1.00 per single-pass review (paper or presentation v3); $1–$2 with `--reviewer claude,codex` fusion (legacy `--type project|plan` only in v0.7.x).

---

## Pick the right review mode

| Mode | When | Output schema | Severity vocabulary | Fusion |
|---|---|---|---|---|
| `--type paper` | Pre-ship audit of a paper draft | `adversarial-review-paper.v3` JSON + .md | P0 / P1 / P2 / info | not in v0.7.x |
| `--type presentation` | Pre-presentation audit of a deck | `adversarial-review-presentation.v3` JSON + .md | P0 / P1 / P2 / info | not in v0.7.x |
| `--type project` | Top-to-bottom skeptical pass on a BERDL project | Legacy markdown only | Critical / Important / Suggested | ✓ supported |
| `--type plan` | Pre-data-collection plan review | Legacy markdown only | Critical / Important / Suggested | ✓ supported |

**The two v3 modes (paper, presentation) emit structured JSON** that downstream skills consume (paper-writer's revise loop, presentation-maker's revise loop). **The two legacy modes (project, plan) emit Markdown only** — meant for humans reading directly.

Severity vocabulary is bijectively mappable: `P0 ↔ Critical`, `P1 ↔ Important`, `P2 ↔ Suggested`, `info ↔ central_objection`. v3 modes use `P0/P1/P2/info` because "P0" carries clearer "blocks ship" semantics than "Critical."

---

## Reading the output

Output for **paper** and **presentation** modes lands at:

```
projects/<id>/papers/draft_<N>/audit/adversarial_review.{md,json}
projects/<id>/talks/draft_<N>/audit/adversarial_review.{md,json}
```

Read the `.md` first. The `.json` is for consumer skills.

### Severity counts

The frontmatter header has the breakdown — e.g., `total_findings: 16 (5 P0, 9 P1, 1 P2, 1 info)`. **The single `info` finding is always `central_objection`** — see below. Counts of P0 vs P1 vs P2 tell you the report's shape:

- **Many P0s, few P1s** — fundamental issues; needs structural revision.
- **Few P0s, many P1s** — solid draft with quality regressions; targeted edits.
- **Many P2s** — polish-pass territory; the reviewer over-fired.
- **Zero P0s on a 5,000+ word paper or 20+ slide deck** — the reviewer probably under-fired. Re-run.

### The 8 (presentation) / 10 (paper) detection classes

Each class flags a different failure mode. Findings are grouped by class in the .md report.

**Both schemas (shared classes):**

| Class | What it catches | Typical severity |
|---|---|---|
| `claim_evidence` | Text/title makes a claim the supporting evidence doesn't actually support | P0 (overreach), P1 (citation drift) |
| `unbacked_quantitative` | Numbers/percentages in the draft that don't trace verbatim to REPORT.md | P0 always |
| `register_drift` | Language tier doesn't match REPORT's hedging — over-claiming or under-claiming | P0 (STRONG-tier confident verb on marginal evidence), P1 (milder) |
| `central_objection` | The single biggest objection a hostile peer reviewer would raise. EXACTLY ONE per review. | `info` (always) |
| `throughline` | The deck/paper's spine bends, breaks, or gets abandoned mid-flow | P0 (no climax), P1 (hourglass break) |
| `citation_reality` | Cited source doesn't exist or doesn't support the specific claim it's pinned to | P0 (fabricated), P1 (drift) |

**Paper-only (4 additional classes):**

| Class | What it catches |
|---|---|
| `missing_section` | Throughline promises evidence the paper doesn't deliver in any section |
| `section_arc` | Section ordering or internal arc issue (Discussion engages prior work before Results establish claims) |
| `report_drift` | Paper claim silently contradicts REPORT.md or silently changes a finding without acknowledgment in `reframing_log.md` |
| `abstract_body_mismatch` | Abstract overclaims (P0) or under-claims (P1) relative to body |

**Presentation-only (3 additional classes):**

| Class | What it catches |
|---|---|
| `missing_slide` | Throughline promises a slide that the deck doesn't deliver |
| `substory_arc` | Substory-internal ordering issue (climax buried; methods after evidence) |
| `qa_softball` | Q&A slides frame easy questions while ducking sharp ones |

### The `central_objection` finding (the killshot)

Every review produces **exactly one** `central_objection` finding at severity `info`. It synthesizes the single sharpest objection a hostile peer reviewer would land on the work. The class was renamed from `narrative_weakness` in v0.7.0 because the v2 label was being misread as a quality judgment ("the deck has a weak narrative") rather than the function ("identify the central thing the work needs to defend against").

Read this finding carefully even if your draft has zero P0s. It's the strategic note for the author — what to be ready for at peer review or in Q&A. Often the right response isn't to fix the draft but to add a Limitations paragraph or rehearse a defense.

### `citation_reality` and `citation_id` (NEW in v3 for presentation)

When a slide or section has a citation surface (footer, in-text marker, or `provenance_pin` block) that's fabricated or misattributed, the reviewer flags it as `citation_reality` and includes a `citation_id` field — the bibtex key, DOI, or REPORT.md section reference being flagged. **Important:** on presentation v3, `citation_id` may NOT be a bibtex key — it can be `"REPORT§Finding 7"` or any string identifier. Don't assume bibliographic format.

Citations are flagged ONLY when they're **present and questionable**. A slide that lacks any citation entirely is NOT a `citation_reality` finding (silent absence routes to `claim_evidence` or `unbacked_quantitative` instead).

### Confidence ratings

Each finding has `confidence: high | medium | low`. Treat low-confidence findings with extra skepticism — the reviewer flagged something it wasn't sure about. High-confidence findings should rarely be dismissed.

### Auto-correction warnings (exit 2)

If the review exits with code 2 and prints a `WARN: AUTO-CORRECTED` block, that's expected and not a problem. The validator caught a summary count mismatch in the LLM's output and rewrote the summary from the findings array (which is ground truth). The `.json` file is consumer-safe; the original miscount is preserved in `<output>.original-summary.json` for forensics.

---

## Iteration patterns

The reviewer always writes to the same default output paths. To preserve a "before" review while running an "after" one:

**Pattern A — `--output` flag (preferred since v0.7.0):**

```bash
beril-adversarial review --type paper papers/draft_3 \
  --beril-root . --output review-pre-fix
# ... apply fixes ...
beril-adversarial review --type paper papers/draft_3 \
  --beril-root . --output review-post-fix
```

Both reviews coexist in `audit/`; you can diff them side-by-side.

**Pattern B — rename `audit/` between runs:**

```bash
beril-adversarial review --type paper papers/draft_3 --beril-root .
mv papers/draft_3/audit papers/draft_3/audit-pre-fix
# ... apply fixes ...
beril-adversarial review --type paper papers/draft_3 --beril-root .
```

For project and plan modes, output is already auto-numbered (`ADVERSARIAL_REVIEW_1.md`, `_2.md`, ...) so you can rerun freely without overwriting.

---

## When to use `--reviewer claude,codex` fusion

Fusion runs both `claude` and `codex` reviewers in parallel and merges findings, giving you blind-spot diversity at ~2× cost and time. **In v0.7.x, fusion is supported only for `--type project` and `--type plan` (legacy markdown modes).** Paper and presentation v3 fusion ships in v0.7.1 post-event.

When fusion is worth the cost: pre-submission project audits, pre-publication plans, anything where you want a second perspective. Skip for routine in-cycle reviews.

---

## Consolidating numbered project/plan reviews

After several iterations, synthesize all numbered reviews into a canonical file:

```bash
beril-adversarial review --type project my_project_id --consolidate \
  --beril-root .
```

This reads all `ADVERSARIAL_REVIEW_*.md` files and writes `FINAL_REVIEW.md`. (Same for `--type plan` → `FINAL_PLAN_REVIEW.md`.)

Not supported for paper/presentation v3 modes — those use the `--output` flag for iteration management instead.

---

## Adversarial-specific troubleshooting

For install / configure / general hub issues, see [PARTICIPANT-RUNBOOK.md §Troubleshooting](https://github.com/ArkinLaboratory/beril-presentation-maker-skill/blob/main/docs/cross-skill/PARTICIPANT-RUNBOOK.md). The issues below are adversarial-only.

**Review produces 0 P0 findings on a real paper or large deck** — The reviewer under-fired. Re-run; the prompt's self-skepticism pass usually catches this. If it persists, verify the input files are present (`manuscript.md`, `REPORT.md`, etc.).

**`JSON VALIDATION FAILED — non-correctable error(s)`** — The LLM produced JSON the validator can't auto-fix (schema violation, invalid enum, duplicate IDs, `central_objection` invariant violation, dead `narrative_weakness` class in v3). The `.md` report may still be useful, but the `.json` is not consumer-safe. Re-run — most of these are stochastic prompt-discipline failures.

**Wrong project_id detected** — The agent inferred from your branch but you wanted a different project. Override by passing the project_id (or draft_dir) explicitly as the first argument. Explicit arguments always win over branch / cwd inference.

**`beril-adversarial CLI changed in v0.6.0` migration hint** — You (or an upstream script) invoked the CLI with the pre-v0.6.0 shape (`beril-adversarial --type X <pos>`). Current shape: `beril-adversarial review --type X <target>`. For paper/presentation, the trailing positional changed too — it's `<draft_dir>` (full path), not `<project_id>`.

**`Error: paper system prompt not found: ...adversarial_paper.v3.md`** — The deployed skill is stale (pre-v0.7.0). Refresh with `pipx install --force` then `beril-adversarial install-skill <BERIL_ROOT>`.

---

## Where to read more

- **[PARTICIPANT-RUNBOOK.md](https://github.com/ArkinLaboratory/beril-presentation-maker-skill/blob/main/docs/cross-skill/PARTICIPANT-RUNBOOK.md)** — cross-skill participant guide (install, configure, BERIL workflow integration, all 4 skill flows).
- **[HUB_INSTALL.md](HUB_INSTALL.md)** — operator runbook for JupyterHub deployment.
- **[CONTRACT.md](CONTRACT.md)** — schema versions, field semantics, consumer migration. Read this if you're integrating adversarial output into another skill.
- **[README.md](README.md)** — repo overview, status, doc map.
- **[RELEASE_NOTES.md](RELEASE_NOTES.md)** — full v0.4.x → v0.7.x changelog.
- **[PLUGIN_GUIDE.md](PLUGIN_GUIDE.md)** — comprehensive single-doc reference (legacy; the granular docs above supersede it for new readers).
