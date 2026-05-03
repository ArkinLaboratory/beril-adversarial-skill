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

**Current: v0.6.2** — see `RELEASE_NOTES.md` for the full v0.4.x →
v0.6.x trajectory. Highlights since v0.4.0:

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
