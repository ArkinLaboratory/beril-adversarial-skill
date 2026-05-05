# beril-adversarial-skill

A harsh, detail-oriented adversarial reviewer for BERDL analysis projects,
research plans, paper drafts, and presentation drafts. Distributed as a
Claude Code skill that runs inside a BERIL deployment.

Built as a complement to BERIL's `/berdl-review` (the lighter automated
review), `/beril-adversarial` is meant for the moment you want a senior
reviewer's skepticism: statistical-rigor checks, hypothesis vetting,
biological-claim verification against current literature, and explicit
flagging of inferential leaps.

## Status

**Current: v0.7.0.2** — see `RELEASE_NOTES.md` for the full v0.4.x →
v0.7.x trajectory. Highlights since v0.4.0:

- **v0.7.0 — schema bundle (v3).** Three breaking changes bundled:
  rename `narrative_weakness` → `central_objection` (same role:
  one finding per review, severity=info, deck/paper-wide synthesis;
  v3 docs containing the dead class name are HARD-REJECTED by the
  validator); NEW `citation_reality` class on presentation v3 for
  parity with paper (detects fabricated/drifting citations on
  slides with footers, in-text markers, or `provenance_pin`);
  `--output` flag now HONORED for `--type paper|presentation`
  (was silently ignored in v0.6.x). Argparse migration hint
  surfaces tailored guidance when consumers invoke the v0.5.x-shape
  CLI. v3 prompts adversarially reviewed by 3 parallel agents
  before validator code; design contracts D1-D6, C1-C3, G1-G5
  captured in `SCHEMA_V3_DECISIONS.md`. v0.7.0.1 added 4-signal
  project resolution tree in `SKILL.md` (git branch is the
  strongest signal on the BERIL hub) + draft auto-detection +
  surface terminology clarification (slash command vs Python CLI).
  v0.7.0.2 closed release-cleanliness gaps surfaced by adversarial
  audit: HISTORICAL banners on legacy schema docs, CONTRACT.md
  Python example KeyError fix, README/SKILL version-string
  refresh, bash usage default-model accuracy.
- **v0.6.x — paper alignment + programmatic CLI subcommand.** Paper
  reviewer rewritten to read paper-writer v0.6+ per-draft directory
  layout (`papers/draft_N/manuscript.md` + `00_throughline.md` +
  `references.md` + `citation_map.md` + ...). Dual md+json output
  with schema `adversarial-review-paper.v2`. New
  `beril-adversarial review <target> --type X` Python CLI subcommand
  for programmatic invocation from other skills. Cross-skill interop
  pinned in `CONTRACT.md`. Schema-aware labels in validator output
  ("section-level"/"manuscript-wide" for paper; "slide-level"/
  "deck-level" for presentation). Unescaped-quote anti-pattern in
  both v2 prompts; trailing-comma repair in the validator.
- **v0.5.x — single-array schema bump for presentation.** Schema
  collapsed to one `findings[]` array (was two). Auto-correcting
  validator backstops LLM summary count mismatches (sidecar
  preserves the original miscount for forensics). Default model
  bumped to Claude Sonnet 4.6. Cross-skill layout-detection added
  for presentation-maker v0.3.1+ zone reorg
  (deliverable/narrative/working/audit).
- **v0.4.0 — adds `--type presentation` mode** for adversarial review
  of `beril-presentation-maker` draft directories.
- **v0.3.0 — additivity discipline** for multi-round reviews.
- **v0.2.0 — programmatic citation verification gate.**

No breaking changes to existing `--type plan` or `--type project`
modes. `--type paper` did break in v0.6.0 (per-draft layout required;
flat-file rejected with migration message).

## Documentation map

| Doc | Audience | What's in it |
|---|---|---|
| **[TUTORIAL.md](TUTORIAL.md)** | Researcher using `/beril-adversarial` on the BERIL hub | Skill-specific: reading findings, the 8/10 detection classes, the `central_objection` killshot, `citation_id` semantics, iteration patterns. **Defers cross-skill install/configure to PARTICIPANT-RUNBOOK below.** |
| **[HUB_INSTALL.md](HUB_INSTALL.md)** | Operator deploying on JupyterHub | 3-step install runbook (pipx + install-skill + configure), first-run validation queries, slash command verification, upgrading, uninstalling, hub-specific troubleshooting. |
| **[CONTRACT.md](CONTRACT.md)** | Integrator consuming this skill's output (paper-writer, presentation-maker, future skills) | Schema family compatibility matrix, severity vocabulary mapping, v0.7.0 migration section, consumer-side smoke test pattern. **Read this first if you're integrating.** |
| **[RELEASE_NOTES.md](RELEASE_NOTES.md)** | Anyone tracking changes | Version-by-version changelog from v0.4.x → v0.7.x with migration notes per release. |
| **[LAYOUT.md](LAYOUT.md)** | Maintainer | Directory and file organization. |
| **[SCHEMA_V3_DECISIONS.md](SCHEMA_V3_DECISIONS.md)** | Schema designer / consumer wanting design rationale | Why v3 looks the way it does; D1-D6, C1-C3, G1-G5 implementation contracts. |
| Cross-skill: **[PARTICIPANT-RUNBOOK.md](https://github.com/ArkinLaboratory/beril-presentation-maker-skill/blob/main/docs/cross-skill/PARTICIPANT-RUNBOOK.md)** | Researcher using ANY of the 4 BERIL plug-in skills (paper-writer / presentation-maker / adversarial / atlas) | Hub workflow integration (`/berdl_start` → install → configure → run any skill), recovery, cost. |
| Reference: [PLUGIN_GUIDE.md](PLUGIN_GUIDE.md) | Reader who wants the full story in one doc | Comprehensive single-doc reference. Per the May 2026 cross-skill doc-consistency agreement, this is no longer a target for new writing — granular docs above are canonical. Kept for completeness. |
| Historical: [SCHEMA_V2_DECISIONS.md](SCHEMA_V2_DECISIONS.md), [SCHEMA_V2_PAPER_DECISIONS.md](SCHEMA_V2_PAPER_DECISIONS.md), [SPEC_TYPE_PRESENTATION.md](SPEC_TYPE_PRESENTATION.md), [V0_4_0_PUNCH_LIST.md](V0_4_0_PUNCH_LIST.md) | Archaeology — design rationale for older releases | Each carries a HISTORICAL banner pointing at the current canonical doc. |

## Quick start

There are **two ways to invoke a review** — pick the one that fits
your context. Both run the same shell script under the hood; same
exit codes, same output paths, same JSON schema.

| Surface | Use this when... |
|---|---|
| **`/beril-adversarial` slash command** in Claude Code (BERIL deployment) | You're an end-user reviewing a paper, deck, or project interactively. Claude Code agent reads the output, summarizes the findings to you, and suggests follow-ups. |
| **`beril-adversarial review` Python CLI subcommand** | You're another skill calling adversarial programmatically. paper_writer.sh, presentation-maker's revise loop, scripted workflows, CI/CD. Exit codes propagate so your script can branch on them. |

The four review modes (`--type project|paper|presentation|plan`)
are documented in detail in
[`SKILL.md` → Mode selection matrix](src/beril_adversarial/skill/SKILL.md#mode-selection--one-matrix-four-modes)
— the single source of truth for per-mode inputs, outputs, schemas,
and supported flags. Don't memorize them; reference the matrix.

### Example 1 — Review a paper draft (interactive, slash command)

You just shipped `papers/draft_5/manuscript.md` from paper-writer
and want a heavy adversarial audit before submission. From inside
Claude Code in your BERIL deployment:

```
/beril-adversarial /Users/you/projects/my_project/papers/draft_5 --type paper
```

What happens:
1. The slash-command agent runs the shell script for `--type paper`.
2. Reviewer reads `manuscript.md` + `00_throughline.md` + `references.md` + `citation_map.md` + `<project>/REPORT.md` (+ optional `reframing_log.md`, `methods_provenance.md`).
3. Writes `papers/draft_5/audit/adversarial_review.md` (human-readable) + `papers/draft_5/audit/adversarial_review.json` (`adversarial-review-paper.v2` schema).
4. Validator auto-corrects summary count mismatches if the LLM miscounted (sidecar preserves the original for forensics).
5. The agent reads the .md, summarizes findings to you, surfaces P0s, suggests follow-ups.

Expected validator output line:
```
PASS: 9 section-level finding(s), 5 manuscript-wide finding(s) (8 P0, 5 P1, 0 P2, 1 info)
```

Or if auto-correction fired:
```
PASS: 9 section-level finding(s), 5 manuscript-wide finding(s) (8 P0, 5 P1, 0 P2, 1 info)
================================================================
AUTO-CORRECTED: summary count mismatches in the LLM's output
================================================================
  - summary.by_severity['P0']=6 but actual count = 8
  ...
================================================================
```

The `.json` is consumer-safe in either case. P0 findings are
typically paper-killing issues (fabricated numbers, broken figure
links, abstract-body mismatch, silent REPORT drift). The Class 7
narrative_weakness "info" finding is the killshot — the single
sharpest objection a peer reviewer would write.

### Example 2 — Review a presentation draft (programmatic, from another skill)

You're inside `beril-presentation-maker`'s `revise_loop.py`. After
`merge_and_assemble` produces a deck, you want to invoke the
adversarial reviewer and consume its JSON to drive a revise pass:

```bash
# From paper-writer / presentation-maker / any other shell:
beril-adversarial review \
    "$draft_dir" \
    --type presentation
EXIT=$?
case $EXIT in
  0|2)  # PASS or PASS-with-auto-correction (advisory) — JSON is consumer-safe
        json="$draft_dir/audit/adversarial_review.json"
        # Parse it, route findings by fix_target to revise prompts...
        ;;
  1)    # FAIL — non-correctable (schema violation, malformed JSON, etc.)
        echo "Reviewer produced unsafe JSON; re-running once" >&2
        # Optionally re-run; manual escalation if persistent
        ;;
  3)    # Config error (claude CLI missing, prompt missing)
        echo "beril-adversarial not properly installed" >&2
        exit $EXIT
        ;;
esac
```

What happens:
1. CLI subcommand resolves the shell script via `BERIL_ROOT` discovery (or the `--beril-root` flag if you pass one), then invokes it.
2. Reviewer reads the standard presentation-maker draft inputs (auto-detects v0.3.0 top-level vs v0.3.1+ zone layout — `working/` etc.).
3. Writes dual md+json output to `<draft_dir>/audit/`.
4. Same auto-correction backstop, same exit-code semantics as the slash command.
5. Your revise loop parses the JSON's `findings[]` array; routes each finding by `fix_target` to the appropriate revise prompt; re-runs the reviewer after the revise pass.

See `CONTRACT.md` for the durable interop surface (CLI signature,
input expectations, output paths, schema family, auto-correction
behavior, fallback-reviewer coordination).

### Example 3 — Re-run after fixing P0s

After acting on the findings from Example 1 or 2, re-run the same
command. Output overwrites the previous `audit/` (no auto-numbering;
the reviewer treats each invocation as a fresh review). To preserve
a prior review, rename the audit directory first:

```bash
# Preserve the prior review for comparison
mv papers/draft_5/audit papers/draft_5/audit-prev

# Re-run
/beril-adversarial /Users/you/projects/my_project/papers/draft_5 --type paper
# OR via CLI:
beril-adversarial review /Users/you/projects/my_project/papers/draft_5 --type paper

# Diff the findings (manual eyeball or scripted)
diff papers/draft_5/audit-prev/adversarial_review.md papers/draft_5/audit/adversarial_review.md
```

Iteration is owned by you (or by your downstream consumer's
review-rewrite loop). The reviewer itself is single-pass per
invocation — no built-in carryover or additive review across runs
(that's a planned v0.7+ feature).

### Where to go next

- **`SKILL.md`** — full slash-command syntax + mode matrix + Claude Code agent workflow.
- **`CONTRACT.md`** — the durable interop surface for skill-to-skill integration. Read v0.7.0 migration section first if you're a consumer.
- **`SCHEMA_V3_DECISIONS.md`** — current schema design rationale. **`SCHEMA_V2_DECISIONS.md`** + **`SCHEMA_V2_PAPER_DECISIONS.md`** — historical (v2 deprecated as of v0.7.0).
- **`RELEASE_NOTES.md`** — full changelog with migration notes.

## Project & draft discovery (BERIL hub workflow)

When you invoke `/beril-adversarial review --type X` inside Claude
Code on a BERIL deployment, the agent figures out which project + draft
you mean from four signals, in order:

1. **Explicit argument.** If you typed a target after the slash command
   (e.g., `/beril-adversarial review --type paper my_project_id` or
   `/beril-adversarial review --type presentation /abs/path/to/draft_3/`),
   the agent uses it directly.

2. **Git branch convention.** The hub uses `projects/<id>` as the
   branch-naming convention (e.g., `projects/gene_function_ecological_agora`).
   If your current branch matches that pattern, the agent infers the
   project from it and confirms with you before running. This is the
   most common path on the hub because users typically stay at
   BERIL_ROOT.

3. **cwd.** If you `cd`'d into `projects/<id>/` before invoking the
   slash command, the agent picks `<id>` up from your working directory.

4. **Ask you.** If none of the above resolve, the agent lists projects
   (`ls projects/`) and asks you to pick. If you just ran `/berdl_start`,
   the agent will reference the project list it already showed you.

For `--type paper` and `--type presentation`, after resolving the
project, the agent picks a draft:

- If you supplied a full path to `papers/draft_N/` or `talks/draft_N/`
  in step 1, that's the draft.
- Otherwise the agent runs `ls papers/` (or `talks/`), proposes the
  highest-numbered `draft_N` as the default, and asks you to confirm
  or pick another.

**Discoverability shortcuts you can use directly:**

```bash
# From your shell on the hub:
ls $HOME/BERIL-research-observatory/projects/                    # list all projects
ls $HOME/BERIL-research-observatory/projects/<id>/papers/        # list paper drafts
ls $HOME/BERIL-research-observatory/projects/<id>/talks/         # list presentation drafts

# Or just ask Claude:
"What projects do I have in BERIL?"
"What's the latest paper draft for <project>?"
"Run adversarial review on the latest presentation draft for <project>"
```

The slash command is the front door, but plain English requests work
too — the agent has shell access and follows the same resolution
logic.

## Install

```bash
# HTTPS (works on shared hosts where SSH keys aren't registered with GitHub —
# e.g. JupyterHub instances; relies on a credential helper or a PAT)
pipx install --force git+https://github.com/ArkinLaboratory/beril-adversarial-skill.git

cd <BERIL_ROOT>
beril-adversarial install-skill .
beril-adversarial configure   # sanity-check claude/codex CLIs
```

If you have an SSH key registered with the ArkinLaboratory GitHub org, the
SSH URL also works (and avoids needing a credential helper):

```bash
pipx install --force git+ssh://git@github.com/ArkinLaboratory/beril-adversarial-skill.git
```

The `git@` is mandatory — `git+ssh://github.com/...` (without it) fails
auth on private repos.

`pipx ensurepath` once after a fresh pipx install if `pipx` writes its
bin dir to a PATH location that isn't on your `$PATH` yet, then `exec
$SHELL -l` to reload.

The first command installs the Python CLI. The second copies the
Claude Code skill into `<BERIL_ROOT>/.claude/skills/beril-adversarial/`.
The third confirms `claude` is on PATH and reports whether `codex` is
also available (codex is optional; needed for `--reviewer codex` and
`--reviewer claude,codex` fusion).

`install-skill` is idempotent: re-running it overwrites the shipped files
(`commands/`, `prompts/`, `references/`, `tools/`, `SKILL.md`) but
preserves `state/` (learned-patterns memory). To upgrade after a new
release: `pipx upgrade beril-adversarial-skill && beril-adversarial install-skill <BERIL_ROOT>`.

## Usage

From inside a BERIL deployment, in Claude Code:

```
/beril-adversarial [<project_id>|<draft_dir>]
                   [--type plan|project|paper|presentation]
                   [--reviewer claude|codex|claude,codex]
                   [--model <model_id>]
                   [--depth quick|standard|deep]
                   [--no-stream] [--no-critic]
                   [--consolidate]
```

**Common defaults work:** `/beril-adversarial my_project` is enough
for a standard project review.
`/beril-adversarial /abs/path/to/talks/draft_9 --type presentation`
runs the presentation reviewer.

### Flags

- `<project_id>|<draft_dir>` — project directory under `projects/`
  (auto-detected from cwd if inside `projects/<id>/`) for plan/project/
  paper reviews; absolute path to a presentation-maker draft directory
  for `--type presentation`.
- `--type plan|project|paper|presentation` — what to review (default
  `project`). The `presentation` type writes
  `<draft_dir>/audit/adversarial_review.{md,json}`; the JSON is the
  consumer contract for the presentation-maker review-rewrite loop.
- `--reviewer claude|codex|claude,codex` — backend (default `claude`).
  Pass `claude,codex` for parallel multi-model review with dated-provenance
  fusion.
- `--depth quick|standard|deep` — thoroughness (default `standard`).
  Quick (~1–2m) skips literature subagents and bio-claim WebSearch
  verification — good for fast development iteration. Deep (~15–25m)
  expands literature scan, multi-source verification, and sensitivity
  analyses — for pre-publication review.
- `--model <model_id>` — override the default model
  (`claude-sonnet-4-6` for claude — bumped from sonnet-4 in v0.5.1;
  `gpt-5.4` for codex).
- `--no-stream` — opt out of the stream-json parser (disables
  programmatic Write verification, automatic retry on silent-failure,
  cost summary, and stream log). Default: parser is on.
- `--no-critic` — opt out of the post-review compliance critic.
  Default: critic runs and triggers a fix pass on format/discipline
  violations.
- `--no-verify-citations` — opt out of the citation verification gate.
  Default: every 9-field citation block is programmatically verified
  against Crossref (DOI) and NCBI PubMed (PMID) after the compliance
  critic loop. Fabricated citations are marked inline with a
  `> ⚠️ **CITATION FABRICATED**` blockquote and listed in a
  `## Citation Verification` section appended to the review. Adds
  zero LLM token cost (just HTTP calls to free registries).
- `--consolidate` — synthesize all numbered reviews into a canonical
  file with revision-history provenance; numbered files are preserved
  as audit trail. The canonical file becomes the live baseline for
  the next adversarial run (see "Additive multi-round reviews"
  below).

### Additive multi-round reviews

Adversarial review is iterative. Each round produces an **additive
delta** against the prior baseline rather than a fresh full review.
The reviewer:

- Reads the prior baseline (`ADVERSARIAL_REVIEW.md` if it exists,
  else the highest-numbered `ADVERSARIAL_REVIEW_N.md`)
- Leads the new review's body with a `## Carryover from Prior Rounds`
  section: every prior issue with a one-line disposition (`resolved`,
  `partially_addressed`, `still_open`, `obsolete`)
- Reserves the per-section issue lists for genuinely NEW findings
- `severity_counts` in the YAML frontmatter reflect new-this-round
  only; carryover dispositions go under `prior_round_disposition`

Typical lifecycle:

```
round 1: /beril-adversarial my_project
         → ADVERSARIAL_REVIEW_1.md (8 critical, 12 important)

round 2: (after addressing some issues)
         /beril-adversarial my_project
         → ADVERSARIAL_REVIEW_2.md (carryover: 5 still_open,
           3 resolved, 4 partial; 2 new important issues)

round 3: /beril-adversarial my_project
         → ADVERSARIAL_REVIEW_3.md (similar structure)

         /beril-adversarial my_project --consolidate
         → ADVERSARIAL_REVIEW.md (canonical baseline,
           current-state ledger of all 28 issues raised across
           the chain, with disposition tracking)

round 4: /beril-adversarial my_project
         → ADVERSARIAL_REVIEW_4.md (reads ADVERSARIAL_REVIEW.md
           as baseline; the numbered files are no longer needed
           by the model, but persist on disk as audit trail)
```

The `round_number` field in frontmatter persists across consolidation
— consolidation does not reset the counter.

## How it fits into the BERIL workflow

The typical BERIL research lifecycle:

```
  /berdl_start                         start a research project
       │
       ▼
  iterate: /berdl, /berdl-query,       develop the analysis
           /literature-review
       │
       ▼
  /beril-adversarial --type plan       harsh plan review BEFORE data work
                                       — catches design issues early
       │
       ▼
  /synthesize                          produce REPORT.md
       │
       ▼
  /berdl-review                        light automated review
       │
       ▼
  /beril-adversarial                   harsh project review
                                       — multiple rounds during iteration
       │
       ▼
  /beril-adversarial --consolidate     synthesize review history into
                                       a canonical record
       │
       ▼
  /submit                              final BERIL submission
       │
       ▼
  (paper-writing skill, future)        when adopting beril-paper-skill:
  /beril-adversarial --type paper      harsh review of paper drafts
```

Three integration points worth highlighting:

1. **Plan review before data work** — `/beril-adversarial --type plan`
   is mandatory-style: it always runs the literature-scan subagent,
   detects whether the question is already answered, and proposes
   missing controls / better methods / additional datasets. Catching
   design issues here saves weeks downstream.

2. **Project review during iteration** — `/beril-adversarial` (default
   `--type project`) on REPORT.md after `/synthesize`. Persists across
   `/submit` cycles (unlike `REVIEW_*.md` which `/submit` clears),
   so adversarial reviews accumulate as audit trail. Use `--depth quick`
   for fast iteration, `--depth standard` for substantive checkpoints.

3. **Consolidation before submission** — once you have several
   numbered adversarial reviews, `/beril-adversarial --consolidate`
   synthesizes them into a single canonical review with revision
   history. Useful both as a final audit before `/submit` and as
   archival documentation of how the project's review trajectory
   evolved.

## What the skill produces

After a standard project review, the project directory contains:

```
projects/<project_id>/
├── README.md, RESEARCH_PLAN.md, REPORT.md, REVIEW.md  (existing BERIL artifacts)
├── ADVERSARIAL_REVIEW_1.md           ← numbered, persists across /submit
├── ADVERSARIAL_REVIEW_2.md
├── ADVERSARIAL_REVIEW.md             ← canonical (after --consolidate)
└── papers/                            ← if --type paper
    ├── draft1-review.md
    └── FINAL_REVIEW.md               ← canonical paper review
```

For multi-model fusion (`--reviewer claude,codex`), each numbered
review is accompanied by `_claude.md` and `_codex.md` intermediates
preserved as audit trail.

A typical review file looks like:

```markdown
---
reviewer: BERIL Adversarial Review (Claude, claude-sonnet-4-20250514)
type: project
date: 2026-04-25
project: my_project
review_number: 1
prompt_version: adversarial_project.v1
severity_counts:
  critical: 2
  important: 5
  suggested: 3
biological_claims_checked: 5
biological_claims_flagged: 1
prior_reviews_considered:
  - REVIEW.md
---

# Adversarial Review — <Project Title>

## Summary
<one-paragraph verdict>

## Overall Scientific Critique
<scientific-soundness, logic, scope, narrative honesty>

## Statistical Rigor
### Critical
- C1: <issue> — <location> — <suggested fix>
### Important
...

## Hypothesis Vetting
### H1: <hypothesis>
- Falsifiable?: ...
- Evidence presented: ...
- Alternative explanations: ...
- Verdict: ...

## Biological Claims
### Claim 1: <claim>
**Authors (Year). "Title." Journal vol(issue):pages.** doi:DOI [PMID]
- Studied: ...
- Finding: "<direct quote>"
- Scope alignment: ...
- Assessment: ...

## Data Support
<verified claims, requires-verification flags>

## Literature and External Resources
<gaps, missing tools, cross-references>

## Issues from Prior Reviews
<resolved / still-open / new>

## Review Metadata
- Reviewer, Date, Scope, AI-disclaimer

## Run Metadata
- Elapsed: 11:48
- Model: claude-sonnet-4-20250514
- Tokens: input=2,364,391 output=20,695 (cache_read=590,041)
- Estimated cost: $1.470
- Pipeline: main + critic + fix + re-critic (4 calls)
```

## Costs and timing

Per-review estimates for a typical Sonnet-4 standard-depth run:

| Configuration | Wall clock | Estimated cost |
|---|---|---|
| `--depth quick` | 1–3 minutes | ~$0.10–0.20 |
| `--depth standard` (default) | 8–14 minutes | ~$1.00–1.80 |
| `--depth deep` | 20–30 minutes | ~$3.00–5.00 |
| `--reviewer claude,codex` | adds ~5–10 minutes + ~$0.50 | |
| `--consolidate` | 1–3 minutes | ~$0.10–0.20 |

Standard runs cost more than quick because the pipeline includes the
main review, the compliance critic, a likely fix pass, and a re-critic
to confirm the fix. Cumulative cost is reported in the Run Metadata
section at the end of the review file.

## Adherence guarantees

The skill defends review quality through three mechanisms:

- **Programmatic Write-tool verification.** The stream-json parser
  detects when claude produces a chat-response review without
  invoking Write (a known stochastic failure mode of `claude -p`
  with rich tool grants). On detection, retry with an escalated
  prompt — up to 3 attempts.

- **Automatic retry on silent-failure.** Stream-json parser exit
  code 2 triggers a retry; exit code 3 (Write to wrong path)
  surfaces a `mv` recovery hint and fails non-retryably.

- **Compliance critic + fix pass.** After the main review, a
  separate claude call audits the file for format/discipline
  violations (no Sources/References sections, strict 9-field
  citation format, no vague non-citations, no vague missing-citation
  suggestions). On violations, a targeted fix pass re-runs the
  reviewer with the violation list and corrects in place.
  Re-critic confirms the fix landed before declaring success.

These run by default; `--no-stream` and `--no-critic` opt out.

## Architecture

Lean, intentionally:

- **Python CLI** (`src/beril_adversarial/`) — install + configure
  only. Zero runtime dependencies (stdlib only).
- **Shell script** (`tools/adversarial_review.sh`) — orchestrates
  the review pipeline, manages retries, runs the critic + fix pass.
- **Stream-json parser** (`tools/stream_progress.py`) — audits Write
  invocations, computes per-call cost, writes JSON metadata sidecars.
- **Cumulative metadata aggregator** (`tools/aggregate_metadata.py`)
  — sums per-call metadata across the pipeline and writes one Run
  Metadata section to the review file.
- **System prompts** (`prompts/`) — five `.v1.md` files: project,
  plan, paper, fusion, consolidation. Plus `compliance_critic.v1.md`.
- **Reference rubric** (`references/adversarial-checklist.md`) — a
  starting-point list referenced (not mechanically walked) by all
  prompts.

The Python package ships the skill folder as `package_data`;
`beril-adversarial install-skill` copies it into `<BERIL>/.claude/skills/beril-adversarial/`.

## Troubleshooting

**`beril-adversarial: command not found`** after install →
`pipx ensurepath; exec $SHELL`. Restart Claude Code.

**`claude: command not found`** during configure → install Claude
Code from https://docs.claude.com and ensure `claude` is on PATH.

**Review takes longer than expected** → standard depth's pipeline
(main + critic + fix + re-critic) is 8–14 minutes by design. Use
`--depth quick` for faster iteration, or `--no-critic` to skip the
critic+fix passes.

**`Write tool was NEVER invoked` (parser exit 2)** → known
stochastic failure of `claude -p` with rich tool grants. The retry
logic should handle it; if it persists across all 3 attempts,
inspect `<output>.stream.log` to see what the reviewer did instead.

**`Write was invoked but on a different path` (parser exit 3)** →
the parser surfaces a `mv` recovery one-liner pointing at the actual
location. Run it to relocate the file. This is rare since we use
absolute paths in prompts; persistent occurrences indicate a
script-level path-resolution bug.

**Compliance critic flags violations after fix pass** → the audit
log is preserved at `<output>.audit2.md`. Inspect to see what the
critic flagged. The review is still usable, but format/discipline
issues remain that the prompt didn't catch automatically.

## Layout reference

See [LAYOUT.md](LAYOUT.md) for the full architecture spec, including
canonical review structure, learned-patterns memory model, retry
semantics, and BERIL_ROOT discovery.

## License

MIT — see [LICENSE](LICENSE).
