# beril-adversarial — Plugin Guide

> **NOTE (2026-05-05):** This is the comprehensive single-doc reference, kept for readers who want the full story in one read. **If you're new, start with one of the granular docs instead** — they're scoped to specific audiences and don't drift against each other:
> - **[TUTORIAL.md](TUTORIAL.md)** — researcher using the reviewer (skill-specific; defers cross-skill flow to PARTICIPANT-RUNBOOK).
> - **[HUB_INSTALL.md](HUB_INSTALL.md)** — operator deploying on JupyterHub.
> - **[CONTRACT.md](CONTRACT.md)** — integrator consuming the JSON output.
> - **[PARTICIPANT-RUNBOOK.md](https://github.com/ArkinLaboratory/beril-presentation-maker-skill/blob/main/docs/cross-skill/PARTICIPANT-RUNBOOK.md)** — cross-skill participant flow across all 4 BERIL plug-in skills.
>
> Per the cross-skill doc-consistency agreement (May 2026), `PLUGIN_GUIDE.md` is no longer a target for new writing — it's preserved here as adversarial-specific reference, not as a uniform pattern. The granular docs above are the canonical entry points.

End-to-end guide to installing, configuring, testing, and operating the `beril-adversarial` skill within a BERIL deployment. Covers the BERIL hub workflow, the four review modes, consumer-facing integration patterns, and troubleshooting.

> **Audience.** Researchers using BERIL on the JupyterHub or a local fork, integrators wiring this skill into other skills' orchestrators, and operators deploying it on shared infrastructure. Not the design rationale — for that read [`SCHEMA_V3_DECISIONS.md`](SCHEMA_V3_DECISIONS.md) and [`CONTRACT.md`](CONTRACT.md).

> **Skill version.** This guide tracks `beril-adversarial-skill v0.7.0.2`. For the changelog, see [`RELEASE_NOTES.md`](RELEASE_NOTES.md).

---

## Table of contents

1. [What this skill does and where it fits in BERIL](#1-what-this-skill-does-and-where-it-fits-in-beril)
2. [3-minute orientation](#2-3-minute-orientation)
3. [Installation](#3-installation)
4. [Skill deployment into BERIL](#4-skill-deployment-into-beril)
5. [Configuration](#5-configuration)
6. [Testing the skill](#6-testing-the-skill)
7. [Operation inside BERIL workflow](#7-operation-inside-beril-workflow)
8. [The four review modes](#8-the-four-review-modes)
9. [Adversarial review's specific role](#9-adversarial-reviews-specific-role)
10. [Cross-skill integration](#10-cross-skill-integration)
11. [Troubleshooting](#11-troubleshooting)
12. [Where to read more](#12-where-to-read-more)

---

## 1. What this skill does and where it fits in BERIL

`beril-adversarial` is a **harsh, scientifically-skeptical reviewer** for the artifacts BERIL produces — research projects, plans, paper drafts, and presentation drafts. Its job is to catch what looser reviewers miss: fabricated quantitative claims, citation drift, silent REPORT contradictions, register over-claiming, abstract-body mismatches, narrative weaknesses a peer reviewer would land on, and the citation-reality gaps that LLM-generated text routinely hallucinates.

It complements BERIL's lighter `/berdl-review` rather than replacing it. Use `/berdl-review` continuously during research; reach for `/beril-adversarial` at the moments you want a senior-reviewer's skepticism — before submitting a project, before drafting a paper from a project, before presenting a deck publicly, or any time you want an explicit "would this survive peer review?" pass.

**Position in the BERIL lifecycle:**

```
Research Plan ──► Notebooks/Analyses ──► REPORT.md ──► Paper / Presentation
      │                                         │              │
      ▼                                         ▼              ▼
/beril-adversarial    /beril-adversarial   /beril-adversarial
   --type plan          --type project      --type paper
                                            --type presentation
```

The skill emits **two files per review** — a human-readable Markdown report and a machine-readable JSON file — both written into `<draft_dir>/audit/` (for paper/presentation) or `projects/<id>/` (for plan/project). Other skills (`beril-paper-writer`'s revise loop; `beril-presentation-maker`'s revise loop) consume the JSON to drive automated fixes; humans read the Markdown.

---

## 2. 3-minute orientation

Most common use case, on the BERIL hub, after the skill is installed:

```bash
# In your shell, on the hub, at BERIL_ROOT (no need to cd into a project):
git checkout projects/my_project_id            # branch convention; many projects already on a project branch

# In Claude Code:
/beril-adversarial review --type paper         # auto-detects project from branch + draft from papers/
```

The agent will confirm the project, propose the latest paper draft, and run the review. Output lands at `projects/my_project_id/papers/draft_<N>/audit/adversarial_review.{md,json}`. Read the `.md`; consumer skills (paper-writer, presentation-maker) read the `.json` for revise loops.

If you're outside Claude Code or scripting, use the Python CLI — same behavior, slightly different syntax:

```bash
beril-adversarial review --type paper /abs/path/to/papers/draft_3 \
  --beril-root /abs/path/to/beril-fork
```

For everything else read the rest of this doc.

---

## 3. Installation

### Prerequisites

- **Python 3.10 or newer** (the wheel is universal but the package targets 3.10+).
- **`pipx`** for isolated installation. Install with `python3 -m pip install --user pipx && python3 -m pipx ensurepath` if not already present. Some hub Python installs are PEP 668-locked; in that case use `python3 -m pip install --user --break-system-packages pipx`.
- **`claude` CLI** on PATH. The skill shells out to it for actual review invocation; `which claude` must return a path. Install Claude Code separately if missing.
- **`codex` CLI** (optional). Required only for fusion-mode reviews (`--reviewer codex` or `--reviewer claude,codex`). `which codex` must return a path if you intend to use it.
- **`bash`** (any modern version; the orchestrator is a bash script).

### Install from GitHub (recommended for hub deployments)

```bash
pipx install --force git+https://github.com/ArkinLaboratory/beril-adversarial-skill.git
```

This works on shared hosts (e.g., JupyterHub instances) without SSH keys registered with GitHub. It uses HTTPS and relies on a credential helper or a personal access token if the repo is private.

### Install from a wheel (offline / pinned environments)

If you have a wheel file (e.g., from a release tag or a colleague's build):

```bash
pipx install --force /path/to/beril_adversarial_skill-0.7.0.2-py3-none-any.whl
```

### SSH alternative (if you have a registered SSH key)

```bash
pipx install --force git+ssh://git@github.com/ArkinLaboratory/beril-adversarial-skill.git
```

The `git@` is mandatory — `git+ssh://github.com/...` (without it) fails. If `pipx` warns about PATH, run `pipx ensurepath` once after the install.

### Verify the install

```bash
beril-adversarial --version    # should print "beril-adversarial-skill 0.7.0.2"
beril-adversarial --help       # lists subcommands: install-skill, configure, review
```

### Updating

```bash
pipx upgrade beril-adversarial-skill
# OR for explicit version pin:
pipx install --force git+https://github.com/ArkinLaboratory/beril-adversarial-skill.git@v0.7.0.2
```

After any update, **re-run `beril-adversarial install-skill <BERIL_ROOT>`** so the deployed skill files in your BERIL fork pick up the new version's prompts, tools, and SKILL.md.

---

## 4. Skill deployment into BERIL

`beril-adversarial` is a Claude Code skill — beyond the CLI, it ships a "skill subtree" (prompts, orchestrator script, SKILL.md, slash command definitions) that must be deployed into your BERIL fork's `.claude/skills/` directory for Claude Code to discover it.

### Deploy

From the BERIL fork's root directory (the directory containing `projects/` and `.claude/`):

```bash
cd /path/to/your/beril-fork
beril-adversarial install-skill .
```

Or specify the path explicitly from anywhere:

```bash
beril-adversarial install-skill /path/to/your/beril-fork
```

### What gets deployed

The skill subtree lands at:

```
<BERIL_ROOT>/.claude/skills/beril-adversarial/
├── SKILL.md                  ← Read by the in-hub Claude Code agent
├── commands/                 ← Slash command definitions
│   ├── beril-adversarial.md
│   └── beril-adversarial-configure.md
├── prompts/                  ← Reviewer system prompts
│   ├── adversarial_paper.v3.md
│   ├── adversarial_presentation.v3.md
│   ├── adversarial_plan.v1.md
│   └── adversarial_project.v1.md
├── references/               ← Background / checklist material
├── tools/                    ← The orchestrator + validator
│   ├── adversarial_review.sh
│   └── validate_presentation_review.py
└── state/                    ← Persistent state (preserved across re-installs)
```

### Idempotency and state preservation

`install-skill` is **idempotent**: re-running it overwrites every shipped file with the current package version. The `state/` directory is the only thing it preserves — never overwritten or deleted. State persists across re-installs so accumulated review history and learned patterns aren't lost when you upgrade.

### Verify deployment

```bash
beril-adversarial install-skill <BERIL_ROOT>      # should print "Skill files installed to: ..."
beril-adversarial configure                        # should report claude (and optionally codex) detected
```

The `configure` command runs a smoke test that checks:
- `claude` CLI is on PATH
- `codex` CLI (optional) is on PATH
- The deployed skill subtree is at the expected location
- Tool versions are compatible

---

## 5. Configuration

The skill has **no runtime configuration files** — it reads everything from CLI flags, environment, and the deployed prompts. This minimizes surprise, but a few environment-level details matter.

### Required: `claude` CLI

The orchestrator shells out to `claude -p` for review invocation. The skill reports `[OK] claude — <path>` from `beril-adversarial configure` when it's discoverable. If you see `[FAIL]`, ensure Claude Code is installed and on PATH (`which claude`).

### Optional: `codex` CLI for fusion mode

If `codex` is on PATH, `configure` reports `[OK] codex — <path> (enables --reviewer codex/claude,codex)`. Fusion mode runs both reviewers in parallel and merges findings (via a fusion prompt) — useful when you want blind-spot diversity. **Note:** as of v0.7.0.x, fusion is supported only for legacy modes (`--type plan|project`); paper and presentation v3 are single-reviewer. Fusion for paper/presentation v3 ships in v0.7.1.

### Optional: model override

The default model is `claude-sonnet-4-6`. Override per-invocation:

```bash
beril-adversarial review --type paper <draft> --model claude-opus-4-x
```

### Optional: `BERIL_ROOT` env var

Both the Python CLI and the bash orchestrator auto-detect BERIL_ROOT (cwd-walk + script install path). For programmatic invocation from another skill's orchestrator, you can set `BERIL_ROOT=/abs/path` in the environment to override.

### Per-project override

For per-project tuning (e.g., a specific model for one project's reviews), pass flags explicitly per invocation. There's deliberately no per-project config file; this avoids the "where is the config; is it being read?" debugging cycle.

---

## 6. Testing the skill

### Unit tests (fast, no LLM cost)

Clone the repo if you don't have it, install dev dependencies, and run pytest:

```bash
git clone https://github.com/ArkinLaboratory/beril-adversarial-skill.git
cd beril-adversarial-skill
pip install -e ".[dev]"     # or `pip install -e ".[dev]" --break-system-packages` if PEP 668-locked
pytest tests/ -v
```

Expected: 193 tests pass in ~3 seconds. Tests cover:
- Validator behavior (schema acceptance, D1/D2/D6 enforcement, deprecation warnings, auto-correction)
- Prompt structural integrity (all classes named, schema_version pinned, anti-pattern guidance present)
- Discovery (BERIL_ROOT resolution from cwd, env, explicit)
- CLI migration hint (v0.5.x-shape invocation detection)
- Cross-skill interop (paper-writer integration shape; both v2 deprecated and v3 current)

### Cross-skill integration smoke

If you want to verify the producer-side integration shape:

```bash
pytest tests/integration/test_paper_writer_interop.py -v
```

This builds synthetic paper-writer-shaped inputs and runs the full review pipeline end-to-end against the validator. Useful when bumping a major version to confirm consumer-facing fields haven't drifted.

### Live test against a real draft (LLM cost ~$0.50–$1)

The most realistic confidence check. Pick a real BERDL paper or presentation draft you have and run:

```bash
# Paper review against an existing draft:
beril-adversarial review --type paper \
  /abs/path/to/papers/draft_X \
  --beril-root /abs/path/to/beril-fork

# Presentation review:
beril-adversarial review --type presentation \
  /abs/path/to/talks/draft_X \
  --beril-root /abs/path/to/beril-fork
```

Verify after the run:
- Exit code 0 (or 2 if validator auto-corrected — both are success).
- `audit/adversarial_review.md` and `audit/adversarial_review.json` both exist.
- The JSON parses; `schema_version` matches `adversarial-review-{paper|presentation}.v3`.
- Findings array is non-empty (a 5000-word paper or 20-slide deck with zero findings means the LLM under-fired; re-run).
- Exactly one `info`-severity finding with class `central_objection` (the killshot).

---

## 7. Operation inside BERIL workflow

### Two surfaces

The same review functionality is exposed through two interfaces with **functionally equivalent behavior** but **slightly different syntax**:

| | Slash command | Python CLI subcommand |
|---|---|---|
| Invocation | `/beril-adversarial` | `beril-adversarial` |
| Subcommand keyword | NONE — target follows directly | **`review`** required |
| Full shape | `/beril-adversarial <target> --type X` | `beril-adversarial review <target> --type X` |
| Where it runs | Claude Code agent inside a BERIL deployment | Any shell with the pipx install |
| Best for | Interactive use by a researcher | Programmatic invocation from another skill or CI |

Both delegate to the same `tools/adversarial_review.sh` orchestrator and produce identical output. Pick whichever fits your context.

### Project resolution

When invoked, the skill figures out which project you mean using a 4-signal resolution tree (in priority order):

1. **Explicit argument.** If you typed a target after the slash command or CLI verb, that's used directly.
2. **Git branch.** The hub uses `projects/<id>` as the branch-naming convention. If your current branch matches that pattern, the agent infers the project from it. **Strongest signal on the hub** because users typically stay at BERIL_ROOT in cwd.
3. **cwd.** If you `cd`-ed into `projects/<id>/`, that's the project.
4. **Ask you.** If none of the above resolve, the agent lists projects (`ls projects/`) and asks you to pick.

The agent **always confirms** before invoking the review when project resolution comes from a signal other than your explicit argument.

### Draft auto-detection (paper/presentation only)

For `--type paper` and `--type presentation`, after resolving the project the agent picks a draft:

- If you supplied a full path, that's the draft.
- Otherwise: lists `papers/` (or `talks/`), proposes the **highest-numbered `draft_N`** as default, asks you to confirm or pick another.

### Output paths

For paper and presentation v3 modes:

```
<BERIL_ROOT>/projects/<id>/papers/draft_<N>/audit/adversarial_review.{md,json}
<BERIL_ROOT>/projects/<id>/talks/draft_<N>/audit/adversarial_review.{md,json}
```

For legacy plan/project modes:

```
<BERIL_ROOT>/projects/<id>/ADVERSARIAL_REVIEW_<N>.md         (auto-numbered, .md only)
<BERIL_ROOT>/projects/<id>/ADVERSARIAL_PLAN_REVIEW_<N>.md
```

Use `--output <basename>` to override the default filename for paper/presentation modes. The output still lands in `<draft_dir>/audit/` but with your basename instead of the canonical `adversarial_review`.

### Iteration patterns

Two supported patterns for running the reviewer multiple times per draft:

**Pattern A — `--output` flag (preferred since v0.7.0):**

```bash
beril-adversarial review --type paper draft_3 --output review-pre-fix
# ... apply fixes ...
beril-adversarial review --type paper draft_3 --output review-post-fix
```

Both reviews coexist in `audit/`.

**Pattern B — rename `audit/` between runs:**

```bash
beril-adversarial review --type paper draft_3
mv draft_3/audit draft_3/audit-pre-fix
# ... apply fixes ...
beril-adversarial review --type paper draft_3
```

Pattern A is cleaner; Pattern B is fine for ad-hoc workflows.

---

## 8. The four review modes

### `--type project` — comprehensive project audit

**When:** before submitting a project, after a major analysis cycle, or any time you want a top-to-bottom skeptical pass.

**Input:** `<project_id>` (directory under `projects/`).

**Output:** auto-numbered `ADVERSARIAL_REVIEW_<N>.md` at `projects/<id>/`.

**Schema:** legacy markdown (no JSON). Severity vocabulary: `Critical` / `Important` / `Suggested`.

**What it checks:** scientific rigor, hypothesis vetting, biological-claim verification against literature, statistical-rigor critique, data support, issues from prior reviews, comprehensive REPORT.md cross-referencing.

**Special:** supports `--reviewer claude,codex` fusion. Supports `--consolidate` to synthesize all numbered reviews into a `FINAL_REVIEW.md` canonical file.

### `--type plan` — pre-data-collection plan review

**When:** before investing analysis time, after you've drafted a `RESEARCH_PLAN.md`. Catches design holes before they become wasted weeks.

**Input:** `<project_id>` (project must contain `RESEARCH_PLAN.md`).

**Output:** auto-numbered `ADVERSARIAL_PLAN_REVIEW_<N>.md` at `projects/<id>/`.

**Schema:** legacy markdown. Severity vocabulary same as `--type project`.

**What it checks:** plan feasibility, statistical pre-registration concerns, scope-creep risk, missing controls, missing comparators, hypothesis specificity.

**Special:** supports `--reviewer claude,codex` fusion. Supports `--consolidate`.

### `--type paper` — paper draft review (v3 schema)

**When:** before sending a paper draft to coauthors, before submission, or after each paper-writer revision pass.

**Input:** `<draft_dir>` — absolute path to `papers/draft_<N>/` (paper-writer v0.6+ per-draft layout).

**Required input files:** `manuscript.md`, `00_throughline.md`, `references.md`, `citation_map.md`, plus `<project>/REPORT.md`. Optional: `reframing_log.md`, `methods_provenance.md`, `figures_inventory.md`, `tables_inventory.md`.

**Output:** `<draft_dir>/audit/adversarial_review.{md,json}` (or your `--output` basename).

**Schema:** `adversarial-review-paper.v3`. Single `findings[]` array. Severity: `P0` / `P1` / `P2` / `info`.

**Detection classes (10):** `claim_evidence`, `unbacked_quantitative`, `register_drift`, `central_objection`, `throughline`, `missing_section`, `section_arc`, `citation_reality`, `report_drift`, `abstract_body_mismatch`.

**What it catches that a casual reviewer misses:** numbers in the paper that don't appear verbatim in REPORT (P0), citations that exist in references.md but don't actually support the specific claim they're pinned to (P1 drift; P0 if fabricated), abstract claims the body doesn't support (P0 overclaim), Discussion claims that silently differ from REPORT without acknowledgment in `reframing_log.md` (P0 silent drift), the single biggest peer-reviewer objection the paper hasn't preempted (info, `central_objection`).

### `--type presentation` — presentation deck review (v3 schema)

**When:** before presenting publicly, before sending a deck to coauthors, after each presentation-maker revision pass.

**Input:** `<draft_dir>` — absolute path to `talks/draft_<N>/`.

**Output:** `<draft_dir>/audit/adversarial_review.{md,json}`.

**Schema:** `adversarial-review-presentation.v3`. Single `findings[]` array. Severity: same as paper.

**Detection classes (8):** `claim_evidence`, `unbacked_quantitative`, `register_drift`, `central_objection`, `throughline`, `missing_slide`, `substory_arc`, `qa_softball`, `citation_reality`.

**What it catches:** numbers on slides that don't trace to REPORT (P0), tier-language drift between deck and REPORT register (P1 over-claiming, P0 if STRONG-tier deck uses confident verbs for marginal evidence), Q&A anti-strawman (Q&A slides that frame easy questions while ducking sharp ones — P1 `qa_softball`), substory arc issues (climax buried; methods after evidence — P1), missing slides the throughline promised (P0/P1), citations on slide footers / `provenance_pin` / in-text markers that are fabricated, miscited, or don't support the slide's claim (P0/P1 `citation_reality`).

---

## 9. Adversarial review's specific role

### Two-tools-two-purposes architecture

`beril-adversarial` is one of two complementary reviewers in the BERIL ecosystem:

| | beril-adversarial (canonical) | paper-writer's `fallback_reviewer.v1.md` |
|---|---|---|
| Detection classes | 10 (paper) / 8 (presentation) | 3 (paper only) |
| Time per review | 5–10 minutes | ~30 seconds |
| Cost per review | ~$0.50–$1 | ~$0.05 |
| When to use | Pre-ship audit; thorough scientific critique | In-loop revision triage; fast convergence |
| Where it lives | This skill | Inside `beril-paper-writer` |
| Output | `<draft_dir>/audit/adversarial_review.{md,json}` (v3) | Inline review attached to revision pipeline |

Both reviewers are stable equilibrium — they have different scopes and different costs. The fallback reviewer triages obvious errors during paper-writer's revise loop; the canonical adversarial is what you run before you hand the draft to a human.

### Hands-off design

The skill **produces files; it does not produce chat output**. The Markdown report and JSON file are the artifacts. The review is delivered ONLY by the `Write` tool inside the LLM invocation — if the LLM tries to print the review as chat output, the orchestrator catches the missing files and retries (up to 3 attempts).

This design choice has consequences:

- **You read the .md;** consumer skills parse the .json. The .md is meant for humans.
- **The .json is the consumer contract** — see [`CONTRACT.md`](CONTRACT.md) for field semantics, schema version policy, and consumer migration guidance.
- **Auto-correction is in code, not chat.** If the LLM emits a summary count that doesn't match the findings array (a known LLM arithmetic-on-self-output failure mode), the validator rewrites the JSON in-place from the findings array (which is ground truth) and writes the original to a sidecar file for forensics. Exit 2 (warn-only); the .json is consumer-safe.

### What it isn't

- **Not a copy-edit tool.** It flags scientific issues, not wording preferences.
- **Not a balanced critique.** It does not balance criticism with praise. Use `/berdl-review` for that.
- **Not infallible.** It is a reviewer, not an oracle. Read findings critically; some will be wrong. The `confidence: high|medium|low` field on each finding helps you triage.
- **Not a replacement for human review.** It is a first pass that catches the issues a peer reviewer would catch on a careful reading. Your coauthors and reviewers will catch others.

---

## 10. Cross-skill integration

### For consumers (`beril-paper-writer`, `beril-presentation-maker`, others)

The interop contract is documented in [`CONTRACT.md`](CONTRACT.md). Key pieces:

**Invocation:** call `beril-adversarial review <target> --type X --beril-root <path>` from your orchestrator. The Python CLI propagates exit codes; trust them (0 = clean, 1 = user error, 2 = warn-only including auto-correct, 3 = config error).

**Output paths:** for `--type paper|presentation`, output is at `<draft_dir>/audit/adversarial_review.{md,json}` (or `<basename>.{md,json}` if you pass `--output`). Read both. If you pass `--output`, audit your assumptions — pre-v0.7.0 the flag was silently ignored.

**Schema version:** the JSON has a `schema_version` field. Pin against `adversarial-review-paper.v3` or `adversarial-review-presentation.v3` (current as of v0.7.0). v2 docs continue to be readable but emit a deprecation warning.

**Class enum:** dispatch on the `class` field. The `central_objection` class (renamed from v2's `narrative_weakness` at v0.7.0) is the deck/paper-wide synthesis finding, severity always `info`. v3 docs containing the dead name `narrative_weakness` are HARD-REJECTED by the validator — update your code to use `central_objection`.

**Required field for `citation_reality`:** the `citation_id` field is required and non-empty when class is `citation_reality`. May be a bibtex key, DOI, or REPORT.md section reference.

### For producers (this skill)

`beril-adversarial` produces output that other skills consume. We do not publish events or webhooks; consumers either invoke us synchronously (preferred) or poll for the audit file.

**Recommended consumer-side smoke test** (per the recurring cross-skill drift pattern):

```python
import json, subprocess
result = subprocess.run(
    ["beril-adversarial", "review", "--type", "paper", str(draft_dir),
     "--beril-root", str(beril_root)],
    capture_output=True, text=True, timeout=900,
)
assert result.returncode == 0, f"adversarial review failed: {result.stderr}"
audit = draft_dir / "audit" / "adversarial_review.json"
assert audit.is_file(), "audit JSON missing"
doc = json.loads(audit.read_text())
assert doc["schema_version"] == "adversarial-review-paper.v3", \
    f"unexpected schema_version: {doc['schema_version']}"
assert isinstance(doc.get("findings"), list), "findings array missing"
```

This catches the failure mode where an upstream change to our CLI surface produces argparse usage errors that get captured silently as "the review file."

---

## 11. Troubleshooting

### `beril-adversarial: command not found`

`pipx`'s bin directory isn't on your PATH. Run `pipx ensurepath`, then start a new shell.

### `beril-adversarial install-skill` fails: "BERIL_ROOT does not contain .claude/skills/"

You're not in a BERIL fork, or the path you passed isn't one. Verify with `ls <BERIL_ROOT>/.claude/skills/` — if missing, the fork is incomplete or you have the wrong path.

### `beril-adversarial configure` reports `[FAIL] claude — not on PATH`

Claude Code isn't installed or isn't on PATH. Install Claude Code separately; verify with `which claude`. The skill cannot run reviews without it.

### `Error: paper system prompt not found: ..../adversarial_paper.v3.md`

The deployed skill is stale (from an older release that didn't have the v3 prompt). Refresh:

```bash
pipx install --force git+https://github.com/ArkinLaboratory/beril-adversarial-skill.git
beril-adversarial install-skill <BERIL_ROOT>
```

### `beril-adversarial CLI changed in v0.6.0` migration hint appears

You're invoking the CLI with the pre-v0.6.0 shape (`beril-adversarial --type X <pos>`). The current shape is `beril-adversarial review --type X <target>`. The hint message gives the exact migration; see [`CONTRACT.md`](CONTRACT.md) for full migration guidance.

### `JSON VALIDATION FAILED — non-correctable error(s)`

The LLM produced JSON the validator can't auto-fix (schema violation, invalid enum value, duplicate IDs, central_objection invariant violation, fabricated `narrative_weakness` class in v3). The .md report may still be useful, but the .json is not consumer-safe. Re-run the review — many of these are stochastic prompt-discipline failures.

### Review produces 0 P0 findings on a real paper / 20+ slide deck

The reviewer under-fired. The prompt's self-skepticism pass should have caught this; re-run. If it persists, check that the input files are actually present (`manuscript.md`, `REPORT.md`, etc.) — empty/missing inputs lead to empty reviews.

### Wrong project_id detected

The agent inferred from your branch but you wanted a different project. Override by passing the project_id (or draft_dir) explicitly as the first argument. The agent honors explicit arguments over branch / cwd inference.

### Auto-correction warning appears (exit 2)

Not a problem. The validator caught a summary count mismatch in the LLM's output and rewrote the summary from the findings array (ground truth). The original miscount is preserved at `<output>.original-summary.json` for forensics. The .json file is consumer-safe.

### Live test passes but cross-skill consumer breaks

Run the consumer-side smoke test (above). The most common cause is consumer code dispatching on `class == "narrative_weakness"` against v3 output where the class is `central_objection`. Rename in your dispatch or accept both classes during transition.

---

## 12. Where to read more

- **[`README.md`](README.md)** — repo overview, quick-start examples, architectural summary.
- **[`CONTRACT.md`](CONTRACT.md)** — durable interop surface for downstream consumers; schema family compatibility matrix; severity vocabulary mapping; v0.7.0 migration section. **Read this if you're a consumer.**
- **[`SCHEMA_V3_DECISIONS.md`](SCHEMA_V3_DECISIONS.md)** — design intent for the current v3 schema; Tier C/D/G implementation contracts; rationale for class rename and citation_reality addition.
- **[`SKILL.md`](src/beril_adversarial/skill/SKILL.md)** — the deployed skill's own documentation, what the in-hub Claude Code agent reads.
- **[`RELEASE_NOTES.md`](RELEASE_NOTES.md)** — full v0.4.x → v0.7.x changelog with migration notes per release.
- **[`SCHEMA_V2_DECISIONS.md`](SCHEMA_V2_DECISIONS.md) and [`SCHEMA_V2_PAPER_DECISIONS.md`](SCHEMA_V2_PAPER_DECISIONS.md)** — historical (v0.5/v0.6 design); preserved for archaeological context.
- **[`SPEC_TYPE_PRESENTATION.md`](SPEC_TYPE_PRESENTATION.md)** — historical (original v0.4 spec for presentation mode); the v3 prompt has evolved well past it but the spec captures the original design intent.
- **Per-mode prompt files** — `src/beril_adversarial/skill/prompts/adversarial_*.{v1,v3}.md` — the actual reviewer system prompts. Read these to understand exactly what the reviewer is told to look for.
- **Validator source** — `src/beril_adversarial/skill/tools/validate_presentation_review.py` — the schema-acceptance and auto-correction logic.

---

## Document version

This guide tracks `beril-adversarial-skill v0.7.0.2`. Keep this header in sync with `pyproject.toml`'s version string when major changes ship. Update at every minor release; refresh examples and counts at every major. For the cross-skill release cadence and consumer migration coordination, see [`CONTRACT.md`](CONTRACT.md) §"v2 deprecation policy."
