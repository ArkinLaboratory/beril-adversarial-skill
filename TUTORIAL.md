# BERIL Adversarial Reviewer — Tutorial

A step-by-step guide for running adversarial reviews of BERDL projects, research plans, paper drafts, and presentation drafts on the BERIL JupyterHub.

**Audience:** Researchers comfortable at a terminal who have a BERDL project, plan, paper draft, or presentation draft they want a harsh review of.

**Time:** ~5 minutes for install + configure; ~5–10 minutes for a single review (paper or presentation v3); ~10–15 minutes for a project or plan review with fusion.

**Cost:** A single Sonnet-based review costs roughly **$0.50–$1.00** for paper or presentation modes (single-pass), or **$1–$2** for project/plan modes with `--reviewer claude,codex` fusion. Cost scales with input size — a 5,000-word paper draft costs more than a 2,000-word plan. To reduce cost: skip fusion (the default already does), pick a cheaper model with `--model`, or focus reviews on already-mature drafts rather than every iteration.

---

## Prerequisites

Before using the adversarial reviewer, your BERIL fork must have:

- A `.claude/skills/` directory at BERIL_ROOT (Claude Code's skill registry).
- At least one of:
  - **A BERDL project** (`projects/<id>/` with `REPORT.md` + `RESEARCH_PLAN.md`) — for `--type project` or `--type plan`.
  - **A paper draft** (`projects/<id>/papers/draft_<N>/manuscript.md` + `00_throughline.md` + `references.md` + `citation_map.md`) produced by `beril-paper-writer` — for `--type paper`.
  - **A presentation draft** (`projects/<id>/talks/draft_<N>/`) produced by `beril-presentation-maker` — for `--type presentation`.
- **`claude` CLI** on PATH. The reviewer shells out to it.
- **`codex` CLI** on PATH (optional, only needed for `--reviewer codex` or fusion in legacy modes).

The typical BERIL workflow that gets you here:

```
/berdl_start            → opens an analysis session
  (iterate: run notebooks, query data, review literature)
/synthesize             → produces REPORT.md from your work
/beril-paper-writer     → drafts the manuscript
/beril-presentation-maker → drafts the deck
/beril-adversarial      → harsh review of the project/plan/paper/deck (you are here)
```

`/beril-adversarial` is meant for the moments you want a senior-reviewer's skepticism. Run it before submitting a project, before drafting a paper, before presenting publicly, or any time you want an explicit "would this survive peer review?" pass.

---

## 1. Install

On the BERIL JupyterHub, open a terminal and run:

```bash
pipx install --force git+https://github.com/ArkinLaboratory/beril-adversarial-skill.git
```

This installs the `beril-adversarial` CLI. Verify it worked:

```bash
beril-adversarial --version
```

You should see `beril-adversarial-skill 0.7.0.3` (or later).

### Install the skill into your BERIL deployment

Navigate to your BERIL root directory and run:

```bash
cd /path/to/BERIL-research-observatory
beril-adversarial install-skill .
```

This copies the skill's prompts (`adversarial_paper.v3.md`, `adversarial_presentation.v3.md`, `adversarial_plan.v1.md`, `adversarial_project.v1.md`), the orchestrator script, the validator, and the SKILL.md into `.claude/skills/beril-adversarial/`. Re-running the command overwrites every shipped file with the current package version; the `state/` directory is preserved.

---

## 2. Configure

Verify dependencies are in place:

```bash
beril-adversarial configure
```

This checks for:

- **`claude` CLI** on PATH (required).
- **`codex` CLI** on PATH (optional; enables `--reviewer codex` and `--reviewer claude,codex` fusion for legacy `--type plan|project`).
- The deployed skill subtree at the expected location.

Expected output:

```
beril-adversarial-skill v0.7.0.3
  BERIL_ROOT: /home/youruser/BERIL-research-observatory
  [OK]      claude — /home/youruser/.local/bin/claude
  [OK]      codex  — /opt/homebrew/bin/codex  (enables --reviewer codex/claude,codex)
```

If `claude` shows `[FAIL]`, install Claude Code separately and ensure `which claude` returns a path. If `codex` shows `[FAIL]`, you can still use the reviewer — just not fusion.

---

## 3. Run your first review

There are two ways to launch the reviewer: the **slash command** (inside a Claude Code session on the hub) or the **CLI** (from any shell). Both run the same pipeline.

### Option A: Slash command (recommended for interactive use on the hub)

In a Claude Code session at your BERIL root:

```
/beril-adversarial review --type paper
```

The agent will walk a 4-signal project-resolution tree:

1. **Explicit argument.** If you typed a target after the verb, it's used.
2. **Git branch.** If your current branch matches `projects/<id>`, that's the project — strongest signal on the hub.
3. **cwd.** If you're inside `projects/<id>/`, that's the project.
4. **Ask you.** If none of the above resolve, the agent lists projects with `ls projects/` and asks you to pick.

For paper and presentation modes, the agent then auto-detects the latest `draft_N` under `papers/` or `talks/` and asks you to confirm before invoking the review.

Common slash-command shapes:

```
/beril-adversarial review --type paper                   # auto-detect everything
/beril-adversarial review --type paper my_project_id     # pick project; auto-detect draft
/beril-adversarial review --type paper papers/draft_3    # explicit relative path
/beril-adversarial review --type project                 # legacy markdown reviewer
/beril-adversarial review --type plan --reviewer claude,codex   # fusion (legacy modes only)
```

### Option B: CLI (recommended for scripts + CI + non-interactive use)

```bash
beril-adversarial review --type paper \
  /abs/path/to/papers/draft_3 \
  --beril-root /abs/path/to/BERIL-research-observatory
```

The CLI expects absolute paths. The `--beril-root` flag is recommended even though auto-detection exists — it removes ambiguity when the script is invoked outside BERIL_ROOT.

**Common flags:**

| Flag | Effect | Default |
|---|---|---|
| `--type {paper\|presentation\|project\|plan}` | Review mode (required) | — |
| `--model <id>` | Override the LLM model | `claude-sonnet-4-6` |
| `--reviewer {claude\|codex\|claude,codex}` | Backend (fusion only works for `--type project\|plan` in v0.7.x) | `claude` |
| `--output <basename>` | Custom output basename for paper/presentation modes | `adversarial_review` |
| `--beril-root <path>` | BERIL fork root (recommended for CLI) | auto-detect |

Example — paper review with a custom output basename for iteration:

```bash
beril-adversarial review --type paper /abs/path/papers/draft_3 \
  --beril-root . --output review-pre-fix
```

---

## 4. Read the output

When the review finishes, output lands in:

**Paper:**
```
projects/<id>/papers/draft_<N>/audit/
├── adversarial_review.md          ← human-readable; read this
├── adversarial_review.json        ← machine-readable; consumer skills (paper-writer's revise loop) parse this
└── adversarial_review.original-summary.json   ← present only if validator auto-corrected the LLM's summary counts
```

**Presentation:**
```
projects/<id>/talks/draft_<N>/audit/
├── adversarial_review.md
├── adversarial_review.json
└── adversarial_review.original-summary.json   (if applicable)
```

**Project / Plan (legacy markdown modes):**
```
projects/<id>/
├── ADVERSARIAL_REVIEW_<N>.md           ← auto-numbered; for --type project
└── ADVERSARIAL_PLAN_REVIEW_<N>.md      ← for --type plan
```

**Start with the .md report.** Structure:

- **Frontmatter** — reviewer model, schema version, date, total findings.
- **Severity counts** — P0 (blocks ship) / P1 (visible quality regression) / P2 (polish) / info (the single `central_objection` killshot).
- **Class sections** — findings grouped by detection class (claim_evidence, register_drift, citation_reality, etc.).
- **Suggested fixes (consolidated)** — one bullet per finding grouped by `fix_target`. This is your action list.

Each finding includes a **confidence rating** (`high` / `medium` / `low`). Treat low-confidence findings with extra skepticism — the reviewer flagged something it wasn't sure about.

### Auto-corrected summaries

If you see a `WARN: AUTO-CORRECTED summary count mismatches` block on stderr, that's expected and not a problem. The validator caught a summary count mismatch in the LLM's output and rewrote the summary from the findings array (which is ground truth). The `.json` file is consumer-safe; the original miscount is preserved in the `.original-summary.json` sidecar for forensics.

---

## 5. Iterate

The reviewer always writes to the same default output paths (overwrite-on-rerun for paper/presentation; auto-numbered for project/plan). To preserve a "before" review while running an "after" one:

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

Pattern A is cleaner; Pattern B is fine for ad-hoc workflows.

For project and plan modes, output is already auto-numbered (`ADVERSARIAL_REVIEW_1.md`, `_2.md`, ...) so you can rerun freely without overwriting.

### Consolidating multiple reviews (legacy modes)

For project and plan modes, after several review iterations, synthesize into a canonical file:

```bash
beril-adversarial review --type project my_project_id --consolidate \
  --beril-root .
```

This reads all numbered review files and writes a `FINAL_REVIEW.md` (or `FINAL_PLAN_REVIEW.md`).

---

## Cost management

| Mode | Typical cost | Wall clock |
|---|---|---|
| `--type paper` | $0.50–$1.00 | 5–10 min |
| `--type presentation` | $0.50–$1.00 | 5–10 min |
| `--type project` (single reviewer) | $0.30–$0.70 | 5–10 min |
| `--type project --reviewer claude,codex` | $1.00–$1.50 | 10–15 min |
| `--type plan` (single reviewer) | $0.20–$0.50 | 3–7 min |

Costs scale with input size. A 7,000-word paper costs roughly twice what a 3,000-word paper does. A presentation with 30 slides costs more than one with 15.

**To limit spend:**

- Use `--model` to select a cheaper model (verify pricing before assuming).
- Skip fusion (the default already does) for paper/presentation modes — fusion isn't supported there in v0.7.x anyway; coming in v0.7.1.
- Run reviews on already-mature drafts rather than every iteration. The reviewer is a pre-ship audit, not a continuous-integration check.
- For paper drafting, paper-writer's `fallback_reviewer.v1.md` (3-class, ~30s, ~$0.05) handles in-loop revision triage. Use the canonical adversarial only when the draft is close to ship-ready.

---

## Troubleshooting

**"`claude: command not found`"** — The Claude CLI isn't on your PATH. On the hub, check that `~/.local/bin` is in your PATH. Run `beril-adversarial configure` to diagnose.

**"`Error: paper system prompt not found: ...adversarial_paper.v3.md`"** — The deployed skill is stale (from a pre-v0.7.0 release). Refresh:

```bash
pipx install --force git+https://github.com/ArkinLaboratory/beril-adversarial-skill.git
beril-adversarial install-skill .
```

**"`beril-adversarial CLI changed in v0.6.0`" migration hint appears** — You (or a script) invoked the CLI with the pre-v0.6.0 shape (`beril-adversarial --type X <pos>`). The current shape is `beril-adversarial review --type X <target>`. The hint message gives the exact migration; see `CONTRACT.md` for full guidance.

**Review produces 0 P0 findings on a real paper or large deck** — The reviewer under-fired. Re-run; the prompt's self-skepticism pass usually catches this. If it persists, verify the input files are present (`manuscript.md`, `REPORT.md`, etc.).

**`JSON VALIDATION FAILED — non-correctable error(s)`** — The LLM produced JSON the validator can't auto-fix (schema violation, invalid enum, duplicate IDs, `central_objection` invariant violation, dead `narrative_weakness` class in v3). The `.md` report may still be useful, but the `.json` is not consumer-safe. Re-run — most of these are stochastic prompt-discipline failures.

**Wrong project_id detected** — The agent inferred from your branch but you wanted a different project. Override by passing the project_id (or draft_dir) explicitly as the first argument. Explicit arguments always win over branch / cwd inference.

**Auto-correction warning (exit 2)** — Not a problem. The validator caught a summary count mismatch and rewrote from the findings array. The `.json` is consumer-safe.

**Pipeline hangs mid-run** — The orchestrator has a 3-attempt retry on silent Write failures. If it's still hung after several minutes, Ctrl-C, then re-run. The script is idempotent.

**`--output` flag silently ignored (pre-v0.7.0 behavior)** — You're on a stale install. Upgrade to v0.7.0+ where `--output` is honored for paper/presentation modes.

---

## Quick reference

```bash
# Full install sequence
pipx install --force git+https://github.com/ArkinLaboratory/beril-adversarial-skill.git
cd /path/to/BERIL-research-observatory
beril-adversarial install-skill .
beril-adversarial configure

# Review a paper draft (slash command, auto-detects everything)
/beril-adversarial review --type paper

# Review a presentation draft (CLI with explicit paths)
beril-adversarial review --type presentation \
  /abs/path/to/talks/draft_5 --beril-root .

# Review a project (with fusion for blind-spot diversity)
beril-adversarial review --type project my_project_id \
  --reviewer claude,codex --beril-root .

# Review a plan (before data collection)
beril-adversarial review --type plan my_project_id --beril-root .

# Iteration with named outputs
beril-adversarial review --type paper papers/draft_3 \
  --beril-root . --output review-pre-fix

# Consolidate numbered project reviews into FINAL_REVIEW.md
beril-adversarial review --type project my_project_id \
  --consolidate --beril-root .
```

---

## Where to read more

- **[`PLUGIN_GUIDE.md`](PLUGIN_GUIDE.md)** — comprehensive guide covering install, configure, test, operate end-to-end. Read this if you want the full story.
- **[`HUB_INSTALL.md`](HUB_INSTALL.md)** — operator runbook for deploying on a JupyterHub user environment.
- **[`CONTRACT.md`](CONTRACT.md)** — interop contract for downstream skills consuming the JSON output.
- **[`README.md`](README.md)** — repo overview, quick-start examples, architectural summary.
- **[`RELEASE_NOTES.md`](RELEASE_NOTES.md)** — full v0.4.x → v0.7.x changelog with migration notes per release.
