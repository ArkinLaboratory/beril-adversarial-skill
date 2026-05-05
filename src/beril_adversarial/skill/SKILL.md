---
name: beril-adversarial
description: |
  Run a harsh, detailed adversarial review of a BERDL analysis project,
  research plan, or paper draft. Supports multi-model fusion (claude +
  codex) and provenance-tracked consolidation across review rounds.
  Use when /berdl-review's lighter pass isn't enough — when the project
  needs a senior-bio-data-scientist level of skepticism, biological-claim
  verification via web search, and explicit data-support checks.
allowed-tools: Bash, Read, Write
user-invocable: true
---

# BERIL Adversarial Reviewer

A harsher parallel to `/berdl-review`. Same artifact graph (README,
RESEARCH_PLAN, REPORT, notebooks, figures, references.md, paper drafts);
different expectations: statistical rigor, hypothesis vetting,
biological-claim verification via WebSearch, scope boundary on data
support, multi-model fusion, and consolidation across rounds with full
revision-history provenance.

The skill ships as a pip-installable Python package
(`beril-adversarial-skill`) plus a Claude Code skill installed at
`<BERIL>/.claude/skills/beril-adversarial/`. The Python layer handles
install + configuration. The review itself is a shell script
(`tools/adversarial_review.sh`) that invokes `claude` or `codex` with
the right system prompt — same pattern as BERIL's `tools/review.sh`.

**Status: v0.7.x — current.** Single-array v3 schemas
(`adversarial-review-presentation.v3`,
`adversarial-review-paper.v3`) with auto-correcting validator
(`tools/validate_presentation_review.py`), v2 schemas accepted
with deprecation warning for forensic compatibility, and
`beril-adversarial review` Python CLI subcommand. Cross-skill
interop documented in `CONTRACT.md` (read the v0.7.0 migration
section first if you're a consumer). Active integration with
`beril-paper-writer` v0.6+ and `beril-presentation-maker` v0.3+.
Default reviewer model is Claude Sonnet 4.6 (`claude-sonnet-4-6`).
Iterative improvement ongoing — see `RELEASE_NOTES.md` for the
v0.4.x → v0.7.x trajectory.

## Two ways to invoke a review

The skill exposes the same review functionality via two surfaces.
Pick the right surface for your context:

| Surface | When to use | How it's called | Where it lives |
|---|---|---|---|
| **`/beril-adversarial` slash command** | Interactive use inside Claude Code from a BERIL deployment. User-driven review of a paper, project, plan, or presentation. | `/beril-adversarial <target> --type X` (Claude Code agent then runs the shell script per the workflow below). | `commands/beril-adversarial.md` (this skill). |
| **`beril-adversarial review` CLI subcommand** | Programmatic invocation from another skill's orchestrator (e.g., `paper_writer.sh`, `assemble.sh`). Scripted workflows. CI/CD. | `beril-adversarial review <target> --type X` (Python wrapper that delegates to the same shell script). | `src/beril_adversarial/commands/review.py`; installed alongside `install-skill` and `configure`. |

Both surfaces dispatch to the same `tools/adversarial_review.sh`
under the hood — single source of truth. Same exit codes, same
output paths, same JSON schema. The slash command adds Claude-Code
agent procedural steps (read summary, present to user, suggest
follow-ups); the CLI subcommand is a thin wrapper that propagates
exit codes for downstream scripts to act on.

**For end users in Claude Code:** use the slash command.
**For skill-to-skill integration:** use the CLI subcommand. See
`CONTRACT.md` for the full programmatic interop surface.

### Surface syntax — DO NOT conflate the two

The two surfaces have **functionally equivalent behavior** but
**slightly different syntax**. When the user types a command, identify
which surface they used and respond using that surface's exact shape;
do not describe one surface as if it were the other.

| | Slash command | Python CLI subcommand |
|---|---|---|
| Invocation prefix | `/beril-adversarial` | `beril-adversarial` |
| Subcommand keyword | NONE — target follows directly | **`review`** required (other subcommands: `install-skill`, `configure`) |
| Full shape | `/beril-adversarial <target> --type X` | `beril-adversarial review <target> --type X` |
| Where it runs | Claude Code agent inside a BERIL deployment | Shell (any environment with the pipx install) |
| Behind-the-scenes | Agent runs `tools/adversarial_review.sh` directly | Python wrapper invokes the same shell script |

**Common conflation to avoid:** when responding to a user who typed
`beril-adversarial review --type X` (CLI shape, with `review`), do
NOT say things like "the slash command takes `<project_id>` directly
without a `review` keyword" — that is correct about the slash
command but irrelevant when the user is using the CLI. Mirror the
user's chosen surface in your response.

**Both surfaces share:** the same project resolution tree (Step 1
below), the same draft auto-detection (Step 2), the same shell script
+ validator + exit codes, the same output paths, and the same JSON
schema. Differences are syntactic only.

## Mode selection — one matrix, four modes

The `--type` flag picks the review mode. Each mode has a different
input shape, output path, and supported flag set. **This table is
the single source of truth for per-mode behavior;** the slash
command, the CLI subcommand, and `CONTRACT.md` all reference it
rather than re-stating per-mode details.

| Mode | Use case | Positional argument | Required inputs | Output paths | Schema | Auto-correction | `--consolidate` | `--reviewer codex` / `claude,codex` (fusion) | `--depth quick\|deep` | Compliance critic + citation gate |
|---|---|---|---|---|---|---|---|---|---|---|
| **`--type paper`** (v0.6+) | Adversarial review of a paper-writer v0.6+ per-draft directory. Heavy audit pass; complements paper-writer's lighter `fallback_reviewer.v1.md`. | `<draft_dir>` — absolute path to `papers/draft_N/`. | `manuscript.md`, `00_throughline.md`, `references.md`, `citation_map.md`, `<project>/REPORT.md`. Optional: `reframing_log.md`, `methods_provenance.md`, `figures_inventory.md`, `tables_inventory.md`. | `<draft_dir>/audit/adversarial_review.{md,json}` | `adversarial-review-paper.v2` | ✓ summary count auto-correction (LLM arithmetic backstop) | ✗ rejected (single-pass v1) | ✗ rejected (single-pass v1) | ✗ ignored (single depth v1) | ✗ N/A |
| **`--type presentation`** (v0.4+; v2 schema since v0.5.0) | Adversarial review of a presentation-maker draft. Consumed by presentation-maker's review-rewrite loop. | `<draft_dir>` — absolute path to `talks/draft_N/`. | `slide_spec.json`, `00_throughline.md`, `02_substories.md`, `03_slides/qa_anticipated.json`, `<project>/REPORT.md`. Auto-detects v0.3.0 (top-level) vs v0.3.1+ zone layout (`working/`). | `<draft_dir>/audit/adversarial_review.{md,json}` | `adversarial-review-presentation.v2` (legacy v1 accepted by validator with deprecation warning for forensics only) | ✓ summary count auto-correction | ✗ rejected (single-pass v1) | ✗ rejected (single-pass v1) | ✗ ignored (single depth v1) | ✗ N/A |
| **`--type project`** (default; legacy mode) | Heavyweight project-level adversarial review of a BERDL project. Includes statistical-rigor checks, hypothesis vetting, biological-claim WebSearch verification. | `<project_id>` — directory name under `projects/`. Auto-detected if cwd is inside `projects/<id>/`. | All canonical artifacts: `README`, `RESEARCH_PLAN.md`, `REPORT.md`, prior `REVIEW_*.md`, `notebooks/`, `figures/`, `references.md`. | `projects/<id>/ADVERSARIAL_REVIEW_N.md` (auto-numbered, single markdown file) | _none — markdown only_ | _N/A — no JSON to auto-correct_ | ✓ supported (synthesizes numbered reviews into `ADVERSARIAL_REVIEW.md`) | ✓ supported | ✓ supported (`quick` ~1-2m / `standard` ~5-10m / `deep` ~15-25m) | ✓ enabled by default; `--no-critic` / `--no-verify-citations` to opt out |
| **`--type plan`** (legacy mode) | Adversarial review of a research plan **before** data collection. Sanity-check the design before investing analysis time. | `<project_id>` — same shape as `--type project`. | `RESEARCH_PLAN.md`, `README.md`, `references.md`. | `projects/<id>/ADVERSARIAL_PLAN_REVIEW_N.md` (auto-numbered) | _none — markdown only_ | _N/A_ | ✓ supported (synthesizes into `ADVERSARIAL_PLAN_REVIEW.md`) | ✓ supported | ✓ supported | ✓ enabled by default |

**Reading the matrix:**

- **Modes that emit JSON contracts** (paper, presentation): single-
  pass review, dual md+json output, downstream consumer-loops can
  parse the JSON. Single-array `findings[]` schema (paper.v2 +
  presentation.v2). Validator auto-corrects summary count
  mismatches. No fusion / consolidation / depth modes — those
  belong to the older project/plan modes.
- **Modes that emit markdown only** (project, plan): legacy
  reviewer architecture from v0.1-v0.3. Heavyweight workflow with
  fusion (`--reviewer claude,codex`), depth control, compliance
  critic, citation verification gate, multi-round consolidation.
  No JSON contract; output is human-readable only.

**Why the split:** v0.4+ added `--type presentation` and v0.6+
added the new-architecture `--type paper`, both with JSON contracts
to enable downstream review-rewrite loops in their respective
consumer skills. Project/plan modes remain on the legacy
architecture because no consumer-loop is planned for them — they're
human-driven review tools, not pipelines.

## Slash commands

### `/beril-adversarial` — run a review

```
/beril-adversarial [<project_id>|<draft_dir>] [--type plan|project|paper|presentation]
                   [--reviewer claude|codex|claude,codex]
                   [--model <model_id>]
                   [--depth quick|standard|deep]
                   [--no-stream] [--no-critic]
                   [--consolidate]
```

**Arguments:**

- `<project_id>` — project directory under `projects/`. Optional if cwd
  is inside `projects/<id>/`. Used for `--type plan|project|paper`.
- `<draft_dir>` — absolute path to a presentation-maker draft
  directory (e.g., `projects/<id>/talks/draft_<N>/`). Required for
  `--type presentation`; cwd auto-detection is not supported.
- `--type plan|project|paper|presentation` — what to review. Default
  `project`. The `presentation` type writes
  `<draft_dir>/audit/adversarial_review.{md,json}`; the JSON is the
  consumer contract for the presentation-maker review-rewrite loop.
- `--reviewer claude|codex|claude,codex` — backend. Default `claude`.
  `claude,codex` runs both in parallel and fuses the results.
- `--model <model_id>` — override default model. Default
  `claude-sonnet-4-6` (v0.5.1+). See "Model selection" below for
  empirical comparison data + when alternatives are worth the cost.
- `--depth quick|standard|deep` — thoroughness. Default `standard`.
  `quick` (~1-2m) skips subagents and bio-claim verification — short
  sharp review for fast iteration. `standard` (~5-10m) is the full
  flow. `deep` (~15-25m) expands literature scan, multi-source
  bio-claim verification, sensitivity analyses.
- **(default)** End-of-run summary printed to stderr after the bash
  command returns: tool-call breakdown, subagent count, token usage,
  estimated cost. Programmatically verifies that the Write tool was
  actually invoked — silent-failure detection drives automatic retry
  (up to 3 attempts). Sidecar `<output>.stream.log` preserves raw
  stream-json for post-mortem.
- `--no-stream` — opt out of the stream-json parser. Disables the
  end-of-run summary, programmatic Write verification, retry on
  silent failure, and the sidecar log. Falls back to claude's default
  text output. Useful only for debugging the parser itself or for
  systems where python3 isn't available.
- `--no-critic` — opt out of the post-review compliance critic.
  Default behavior: after the main review writes successfully, a
  separate claude call audits the review against format/discipline
  rules (no Sources sections, strict citation format, no vague
  citation handles, no vague missing-citation suggestions). On
  violations, a targeted fix pass re-runs the original reviewer with
  the violation list to fix in place. Adds 1–3 minutes of latency and
  ~$0.05–0.10 per review but produces substantially more compliant
  output.
- `--consolidate` — skip review; synthesize all numbered reviews of
  matching `--type` into a canonical file with revision history.

**Per-mode defaults:** see the [Mode selection matrix](#mode-selection--one-matrix-four-modes) above. Don't duplicate the matrix here.

**Tools granted to the reviewer subprocess:**
`Read, Write, Bash, Grep, Glob, WebSearch, Agent, ToolSearch`. Richer
than `/berdl-review`. The reviewer can grep notebooks, verify
biological claims via web search, run small Python via Bash for Tier
1 calculations, delegate sub-analysis to subagents (e.g., the
literature-scan subagent), and dynamically load BERIL's MCP tools
(PubMed, paper-search, paperblast) via ToolSearch.

### `/beril-adversarial-configure` — verify environment

Confirm `claude` (required) and `codex` (optional) CLIs are installed
and that WebSearch is reachable. Run once after install, or any time
the toolchain changes.

## Workflow (run a review)

When the user invokes `/beril-adversarial`:

### Step 1 — Resolve project context

This is the agent's most load-bearing inference step. On the BERIL hub,
users may invoke the slash command from many starting points (just
opened Claude Code, in the middle of a research workflow, after
`/berdl_start`, etc.) and they often stay at BERIL_ROOT in cwd rather
than `cd`-ing into a specific project. Walk this resolution tree IN
ORDER and stop at the first match:

**1a. Explicit argument.** If the user typed a target after the slash
command (e.g., `/beril-adversarial review --type paper my_project_id`,
or `/beril-adversarial review --type presentation /abs/path/to/draft_3/`),
use it as-is. For `--type paper|plan|project`, the argument is a
`<project_id>`; for `--type presentation`, it's a `<draft_dir>` (full
path to `projects/<id>/talks/draft_N/`). Validate the path/id exists;
ask the user to clarify if it doesn't.

**1b. Git branch convention.** Run `git -C $BERIL_ROOT branch
--show-current`. The hub uses a `projects/<id>` branch-naming
convention — branch `projects/gene_function_ecological_agora` means the
active research project is `gene_function_ecological_agora`. Strip the
`projects/` prefix; that's the project_id. **Confirm with the user
before acting:** "I see you're on branch `projects/<id>`. Run review
against that project? [Y/n]". This is the strongest signal on the hub
because users typically stay at BERIL_ROOT.

**1c. cwd.** Run `pwd`. If the path is inside `projects/<id>/`, that
`<id>` is the project_id. Common when the user `cd`'d into a project
manually.

**1d. Ask the user.** If 1a–1c didn't resolve, present the project list
and ask:

```bash
ls $BERIL_ROOT/projects/        # all available project_ids
```

For projects that have a `beril.yaml` manifest, surface the project's
status alongside the id. If the user just ran `/berdl_start`, reference
the project list it already displayed rather than re-listing.

After resolving project_id, validate `projects/<project_id>/` exists
before proceeding.

### Step 2 — Resolve draft (paper / presentation modes only)

For `--type plan` and `--type project`, draft selection does not
apply — skip to Step 3.

**For `--type paper`:**

- If the user passed an absolute or relative path to a specific
  `papers/draft_N/` directory in Step 1a, use that.
- Else: list paper drafts under the resolved project and pick a
  default:

  ```bash
  ls $BERIL_ROOT/projects/<project_id>/papers/
  ```

  Pick the highest-numbered `draft_N` as the proposed default.
  Confirm with the user before invoking the review: "Found drafts
  `draft_1` through `draft_5`. Latest is `draft_5`. Review that, or
  pick another? [Y/n/N=specific number]".

**For `--type presentation`:**

- Same logic as paper, but under `projects/<project_id>/talks/` instead
  of `papers/`.

The reviewer's `<draft_dir>` argument needs the absolute path:
`$BERIL_ROOT/projects/<project_id>/talks/draft_<N>/` (or `papers/draft_<N>/`).

### Step 3 — Invoke the reviewer

Run the shipped shell script:

    bash .claude/skills/beril-adversarial/tools/adversarial_review.sh \
        <project_id> [--type ...] [--reviewer ...] [--model ...]

The script:

- Auto-numbers the output file race-safely via noclobber-atomic claim.
- Loads the system prompt from `prompts/adversarial_<type>.v1.md`.
- Invokes `claude -p` (or `codex exec`) with the system prompt and a
  short review prompt that points at the project artifacts.
- Pipes claude's stream-json output through `tools/stream_progress.py`
  for programmatic Write-tool verification and per-call cost summary.
  Auto-retries on silent failure (Write not invoked) up to 3 attempts.
- For `--reviewer claude,codex`: runs both in parallel as
  `*_claude.md` and `*_codex.md` intermediate files, then a third
  `claude -p` with `prompts/fusion.v1.md` produces the unified
  numbered file with dated provenance preserved.
- After the main review writes successfully (and unless `--no-critic`),
  invokes the compliance critic via `prompts/compliance_critic.v1.md`.
  The critic audits format/discipline violations (no Sources sections,
  strict 9-field citation format, no vague non-citations, no vague
  missing-citation suggestions). On violations: runs a targeted fix
  pass that re-invokes the original reviewer with the violation list
  to fix in place. Re-runs the critic to confirm the fix landed.
- Aggregates per-call metadata (main + critic + fix + re-critic) and
  appends one cumulative `## Run Metadata` section to the review file:
  total elapsed, tokens, cost, pipeline labels.

Run from `BERIL_ROOT` (the directory containing `projects/` and
`.claude/`). The script auto-resolves BERIL_ROOT from its own install
path if needed.

### Step 4 — Verify completion

After the script returns:

1. Check the output file was created and is non-empty.
2. Confirm it has YAML frontmatter and a body (the script does this
   too, but a final visual check helps).
3. Print a brief summary: severity counts, biological claims checked,
   any prior-review issues addressed.

### Step 5 — Guidance

Based on the review outcome:

- **No critical issues** — note the project may be ready for `/submit`
  or for paper-writing. Remind the user that adversarial reviews
  PERSIST across rounds and across `/submit` (unlike numbered
  `REVIEW_*.md`, which `/submit` clears).
- **Critical issues** — list them with locations and suggested fixes.
  Offer to help address them. Suggest re-running `/beril-adversarial`
  after fixes to verify.

## Workflow (consolidate)

When the user invokes `/beril-adversarial --consolidate`:

The shell script's consolidation path:

1. Walks all `ADVERSARIAL_REVIEW_*.md` (or `ADVERSARIAL_PLAN_REVIEW_*.md`,
   or `papers/draft*-review.md`) of matching `--type`.
2. Invokes `claude -p` with `prompts/consolidation.v1.md` as system
   prompt, passing all numbered files plus the current artifact
   (REPORT, plan, or latest paper draft).
3. Writes a canonical file:
   - `ADVERSARIAL_REVIEW.md` (project root) for `--type project`
   - `ADVERSARIAL_PLAN_REVIEW.md` for `--type plan`
   - `papers/FINAL_REVIEW.md` for `--type paper`
4. Numbered source files are PRESERVED (audit trail). The canonical
   file's body has a Revision History section that cites each round's
   source file, model, and date inline in square brackets.

## Output artifacts

```
projects/{project_id}/
├── ADVERSARIAL_REVIEW_1.md          # numbered, persists across /submit
├── ADVERSARIAL_REVIEW_2.md
├── ADVERSARIAL_REVIEW_2_claude.md   # intermediate (when --reviewer claude,codex)
├── ADVERSARIAL_REVIEW_2_codex.md
├── ADVERSARIAL_REVIEW_3.md
├── ADVERSARIAL_REVIEW.md            # canonical (after --consolidate)
├── ADVERSARIAL_PLAN_REVIEW_1.md     # for --type plan
├── ADVERSARIAL_PLAN_REVIEW.md       # consolidated plan review
└── papers/
    ├── draft1-review.md             # for --type paper
    ├── draft2-review.md
    └── FINAL_REVIEW.md              # consolidated paper review
```

Numbered files are append-only across the project lifecycle. Only
`/beril-adversarial --consolidate` writes the canonical files;
`/submit` does not touch any `ADVERSARIAL_*` file.

## Reviewer memory (learned-patterns)

The reviewer maintains cross-project meta-memory at
`.claude/skills/beril-adversarial/state/learned-patterns.md` (this
install only — never shipped). Entries record patterns the reviewer
has flagged before that are GENERALIZABLE (not project-specific
gotchas; those go in `docs/pitfalls.md` via the existing
pitfall-capture protocol).

The reviewer reads this file at the start of every review and may
append new entries at the end if it identified a novel general pattern.
Discipline rules in the system prompts keep growth bounded.

## When to use this skill vs. /berdl-review

| Scenario | Use |
| --- | --- |
| Quick feedback during development | `/berdl-review` |
| Pre-publication review of a project | `/beril-adversarial --type project` |
| Plan stage, before data collection / analysis | `/beril-adversarial --type plan` |
| Paper draft from `/beril-paper` | `/beril-adversarial --type paper` |
| Presentation draft from `/beril-presentation-maker` | `/beril-adversarial --type presentation <draft_dir>` |
| Multi-perspective second opinion | `/beril-adversarial --reviewer claude,codex` |
| Consolidating review history into a single canonical doc | `/beril-adversarial --consolidate` |

## Model selection

**Default: `claude-sonnet-4-6`** (set in v0.5.1).

This default is empirically grounded: in May 2026 we ran an A/B
comparison of Sonnet 4.6 vs Opus 4.6 on the same presentation deck
(`core_gene_tradeoffs/draft_2`, 23 slides). Both models produced
publication-quality reviews with substantive overlap on the deck's
worst issues. Concrete numbers:

| Metric | Sonnet 4.6 | Opus 4.6 |
|---|---|---|
| Total findings | 17 | 16 |
| P0 findings | 7 | 6 |
| P1 findings | 7 | 9 |
| Cost (per review, approx) | ~$0.50–1 | ~$2.50–5 |
| JSON validation | failed (2 false-positive errors; v0.5.3 fixed) | passed |

**Where Sonnet wins:** detail-level checks — specific citation
existence (caught a hallucinated "Scott et al. 2010" reference), verbatim text-comparison findings, evidence-map inflation in the
throughline doc.

**Where Opus wins:** methodology grounding (caught two unbacked
statistical method claims Sonnet missed: "32 bacterial species",
"Fisher's exact test / BH-FDR"), null-hypothesis thinking (caught
the deck's strongest absent objection — the integration-depth null
hypothesis for the OR=1.29 finding).

**Different blind spots, similar coverage.** Neither model
dominates. Opus produced 1–2 unique high-value findings per review;
Sonnet produced 3–4 unique findings.

**Verdict: Sonnet 4.6 default. Opus is not worth ~5× cost** for
adversarial review on a single deck. The marginal Opus catches
don't justify routing infrastructure complexity.

### When to override the default

```bash
# Try Opus when stakes are high and budget allows
.../adversarial_review.sh <draft_dir> --type presentation \
    --model claude-opus-4-6

# Cross-model fusion catches both blind spots (~2× claude-only cost)
.../adversarial_review.sh <draft_dir> --type presentation \
    --reviewer claude,codex
# Codex (gpt-5.4) reviews in parallel; fusion call consolidates.

# Faster iteration with Haiku (lower quality, NOT recommended for
# production reviews — keeps inclusion to spot-check)
.../adversarial_review.sh <draft_dir> --type presentation \
    --model claude-haiku-4-5-20251001
```

### When fusion (`--reviewer claude,codex`) is worth the cost

The Opus A/B argued for *blind-spot diversity* over *depth*. Two
different models reviewing in parallel + fusion is more likely to
recover both unique-finding sets than one expensive model reviewing
alone. Consider fusion for:

- Decks destined for high-stakes audiences (program reviews, grant
  panels, public talks)
- v1.0 ship-readiness validation (run fusion on the candidate; only
  release if it passes)
- One-off deep-dive reviews when cost is amortized across many
  draft iterations

For routine drafting iterations, Sonnet-alone is sufficient.

## Notes

- The system prompts (`prompts/adversarial_{plan,project,paper}.v1.md`,
  `fusion.v1.md`, `consolidation.v1.md`) are the locus of reviewer
  intelligence. They iterate via `.v{N}.md` versioning.
- The rubric reference `references/adversarial-checklist.md` is a
  starting-point list; the system prompts instruct the reviewer not to
  walk it mechanically.
- This skill never modifies project files. All output goes to numbered
  review files or, on consolidation, to canonical review files.
- For provider/model configuration: `claude` and `codex` CLIs carry
  their own configs. This skill does not edit `.env` or hold API keys.

## Pitfall detection

When you encounter errors, unexpected results, or surprising review
outcomes during invocation of this skill, follow the pitfall-capture
protocol. Read `.claude/skills/pitfall-capture/SKILL.md` and follow its
instructions to determine whether the issue belongs in
`docs/pitfalls.md`. Review-meta-patterns belong in `state/learned-patterns.md`
(the reviewer manages that file directly).
