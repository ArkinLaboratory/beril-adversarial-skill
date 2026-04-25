---
description: Run a harsh adversarial review of a BERDL project, plan, or paper. Supports multi-model fusion, depth tiers, and provenance-tracked consolidation.
argument-hint: [<project_id>] [--type plan|project|paper] [--reviewer claude|codex|claude,codex] [--model <model_id>] [--depth quick|standard|deep] [--no-stream] [--no-critic] [--consolidate]
allowed-tools: Bash, Read, Write
---

# /beril-adversarial

Run an adversarial review of the project, plan, or paper draft at
`projects/<project_id>/`. Harsher and more detail-oriented than
`/berdl-review`. Supports multi-model fusion and consolidation across
rounds.

## Step 1 — Verify the package is installed

Run in a Bash block:

    beril-adversarial --version

If the command is not found, tell the user:

> The `beril-adversarial` package isn't on your PATH. Install it with:
>
>     pipx install --force git+https://github.com/ArkinLaboratory/beril-adversarial-skill.git
>
> If you have an SSH key registered with GitHub you can also use the
> SSH URL — note the explicit `git@`, which is required:
>
>     pipx install --force git+ssh://git@github.com/ArkinLaboratory/beril-adversarial-skill.git
>
> Then run `beril-adversarial install-skill .` from your BERIL root,
> followed by `/beril-adversarial-configure`.

Stop here if the command is missing. Do not try fallback installs.

## Step 2 — Resolve the project

If the user passed `<project_id>` explicitly, use it.

Otherwise, check if cwd is inside `projects/<id>/` and auto-detect.
If neither: ask the user via AskUserQuestion which project to review.

Validate that `projects/<project_id>/` exists. If not, stop with an
error.

For `--type paper`: also confirm `projects/<project_id>/papers/`
contains at least one `draft{N}.md`. If not, tell the user the paper
directory is empty and stop.

## Step 3 — Invoke the reviewer

**Run the bash command in the FOREGROUND. Do not background it.** A
standard-depth review takes 5–10 minutes and a deep review can take
20+ minutes; that is normal and expected. If the bash tool warns about
a long-running command, wait for it. Backgrounding the call breaks
the user's ability to see the end-of-run summary in the natural
turn-completion flow, and creates ambiguity if the user wants to
abort.

From BERIL_ROOT:

    bash .claude/skills/beril-adversarial/tools/adversarial_review.sh \
        <project_id> \
        --type <type> \
        --reviewer <reviewer> \
        --depth <depth> \
        [--model <model_id>] \
        [--consolidate]

- Omit `--type` if `project` (default).
- Omit `--reviewer` if `claude` (default). Use `codex` for an
  alternative perspective. Use `claude,codex` for parallel reviews
  with fusion.
- Omit `--depth` if `standard` (default; ~5-10 minutes). Pass `quick`
  (~1-2 minutes, skips subagents) for fast iteration during
  development. Pass `deep` (~15-25 minutes) for thorough
  pre-publication review.
- Omit `--model` to use the per-reviewer default.
- Pass `--consolidate` to skip review and synthesize numbered reviews
  into a canonical file.

The script auto-numbers output files race-safely. Multi-reviewer
fusion runs both backends in parallel and produces three artifacts:
intermediate `*_claude.md`, intermediate `*_codex.md`, and the unified
numbered file.

## Step 4 — Verify completion

After the script returns:

1. Check the output file exists and is non-empty.
2. Confirm it has YAML frontmatter (`grep -q '^---' <file>`).
3. If validation fails, tell the user and stop.

## Step 5 — Present summary

Read the output file's frontmatter and Summary section. Present a
brief summary to the user:

- Overall verdict (1–2 sentences from Summary)
- Severity counts: critical / important / suggested
- Biological claims checked / flagged (for project and paper types)
- Churn from prior reviews if applicable: how many issues addressed
  vs. still open
- Pointer to the output file
- **Cumulative run cost** from the review file's `## Run Metadata`
  section at the end (elapsed, tokens, $cost, pipeline labels).
  This is the canonical record. Optionally also quote the per-call
  summary lines that appeared in the bash output (e.g.,
  `Adversarial review: 06:58 · input=... output=... ~$0.163`) for
  per-stage transparency.
- **Compliance critic outcome** — surface this verbatim from the
  bash output. One of:
    - `Compliance critic: PASS` (review compliant on first try)
    - `Compliance critic: N violation(s) — running fix pass...`
      followed by `Compliance critic (post-fix): PASS` (fix worked)
    - `Compliance critic (post-fix): N violation(s) remain.` (fix
      didn't fully land; audit log preserved at `<output>.audit2.md`)

## Step 6 — Guidance

Branch on review outcome:

**No critical issues:**

> The review found no critical issues. The project looks clean from an
> adversarial standpoint. Note that adversarial reviews persist across
> `/submit` cycles — they accumulate as audit trail. Run
> `/beril-adversarial --consolidate` when you want a canonical
> consolidated view across all rounds.

**Critical issues present:**

> The review flagged {N} critical issues:
> 1. {C1 title} — {location}
> 2. {C2 title} — {location}
> ...
>
> Want me to help address these? Re-run `/beril-adversarial` after
> fixes to verify resolution.

**Multi-model fusion run:**

> Fusion reviewed by Claude ({claude-model}) and Codex ({codex-model}).
> {N} issues raised by both; {M} by Claude only; {K} by Codex only.
> {disagreement_count} reviewer disagreements surfaced.

## Step 7 (consolidate path only) — Highlight history

If `--consolidate` was passed:

> Consolidated {N} numbered reviews into canonical
> `<canonical_path>`. Numbered source files preserved as audit trail.
> Persistent open issues: {C} critical, {I} important, {S} suggested.
> Trajectory: {improving | stable | degrading} based on per-round
> severity counts.

## Notes for the agent

- Numbered review files are append-only across the project lifecycle.
  `/submit` does NOT clear them (unlike `REVIEW_*.md`).
- For `--type paper`: the script picks the highest-numbered
  `draft{N}.md` automatically. Output is co-located with the draft as
  `papers/draft{N}-review.md`.
- The shell script handles all error paths (missing project, invalid
  type, script-not-installed, reviewer subprocess failure) and exits
  non-zero with a diagnostic. Surface stderr verbatim if the script
  fails.
- This command never edits project files. All output goes to numbered
  review files or canonical review files in the project directory.
- If WebSearch is unavailable, biological-claim verification will be
  skipped silently; the review will note this in its Summary.

## Pitfall detection

When you encounter errors during this skill — script failures, missing
prompts, unexpected reviewer output — follow the pitfall-capture
protocol. Read `.claude/skills/pitfall-capture/SKILL.md` and follow its
instructions.
