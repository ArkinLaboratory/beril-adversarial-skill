# SPEC: `beril-adversarial --type presentation`

> **⚠️ HISTORICAL — pre-v0.5.0 design spec.** This document captures
> the original (April 2026) design for `--type presentation`, which
> shipped in v0.4.0 with the `adversarial-review-presentation.v1`
> dual-array schema. **The dual-array v1 schema has since been
> superseded.** v0.5.0 collapsed to a single `findings[]` array
> (`adversarial-review-presentation.v2`); v0.6.0 added the parallel
> `adversarial-review-paper.v2` schema for paper review.
>
> **For the current schemas, see `SCHEMA_V2_DECISIONS.md`
> (presentation) and `SCHEMA_V2_PAPER_DECISIONS.md` (paper).**
>
> **For the current cross-skill interop contract, see `CONTRACT.md`.**
>
> This file is preserved as historical context for the original
> design intent and the live-test rationale (`functional_dark_matter`
> draft_9 detection-class catalog) that drove v0.4.0. Concepts here
> map to v2 as follows:
> - "two arrays (findings + deck_level_findings)" → single
>   `findings[]` array; deck-level findings omit `slide_id`
> - `slide_id`/`title_quote` for presentation, `section`/
>   `paragraph_quote` for paper (parallel design)
> - Schema literal `adversarial-review-presentation.v1` → `.v2`
> - Severity vocabulary `Critical/Important/Suggested` → `P0/P1/P2`
>   (plus `info` for narrative_weakness)

**Status (original):** Spec for fresh-thread implementation. Author: Adam Arkin / Claude (this conversation, 2026-04-28).

**Goal:** Add `--type presentation` mode to `beril-adversarial-skill`. The reviewer takes a presentation-maker draft directory, harshly critiques the deck for scientific storytelling + claim-evidence load-bearing + Q&A sharpness + narrative arc, and emits a structured critique that downstream tooling (presentation-maker's review-rewrite loop, planned v0.3.0) can act on.

**Why this is needed:** Live test of presentation-maker v0.2.0 on `functional_dark_matter` shipped a 26-slide deck with content-level problems that no programmatic post-checker can detect (register drift on slide 9; "validates" overconfidence on slide 14; weight-sensitivity caveat buried in Q&A on slide 18; NMDC slide order inverted; experimental-roadmap climax buried; Q&A softballed real objections; missing top-N candidates slide). These are semantic alignment + narrative arc problems. Only LLM-in-the-loop semantic verification can catch them. This is the analog of `--type paper` for the presentation skill.

---

## 1. Scope

### In scope

- `--type presentation <draft_dir>` mode for `beril-adversarial-cli`.
- New prompt `prompts/adversarial_presentation.v1.md` — the harsh reviewer.
- Output: `<draft_dir>/audit/adversarial_review.md` (human-readable) + `<draft_dir>/audit/adversarial_review.json` (machine-readable; the consumer contract for presentation-maker's revise loop).
- Inputs: presentation-maker's standard draft artifacts (`slide_spec.json`, `00_throughline.md`, `02_substories.md`, REPORT.md, RESEARCH_PLAN.md).
- Severity grading per finding (P0/P1/P2).
- Per-finding fix hint that points at the responsible prompt or layer.

### Out of scope (for this spec)

- The review-rewrite loop in presentation-maker. That's a separate spec for `beril-presentation-maker-skill v0.3.0`. This spec is just the reviewer; the loop is a downstream consumer.
- Multi-model fusion (the adversarial-skill's `fusion.v1` pattern). v1 reviewer is single-pass; fusion is v2.
- Compliance-critic extension (the skill's `compliance_critic.v1`). Presentations don't have ICMJE/ICH-style compliance regimes the way papers do. Skip.
- Visual / format / KBase-brand review. That's the `walk_pptx.py`-based mechanical pass, not adversarial review. Keep it separate.

---

## 2. Input contract

The reviewer takes a single argument: `<draft_dir>` pointing at a presentation-maker draft directory. It reads:

| File | Purpose |
|---|---|
| `<draft_dir>/slide_spec.json` | The validated final spec for all slides (15-layout vocabulary; per-slide content). |
| `<draft_dir>/00_throughline.md` | The chosen narrative spine. Source for "does the deck honor the throughline?" |
| `<draft_dir>/02_substories.md` | Substory partition with punchlines. Source for "do substory boundaries make narrative sense?" |
| `<project_dir>/REPORT.md` | Project's authoritative findings doc. **The truth source for cross-checking quantitative claims.** |
| `<project_dir>/RESEARCH_PLAN.md` | Design intent. Source for "is this slide claiming something the plan didn't license?" |
| `<draft_dir>/03_slides/qa_anticipated.json` | Q&A fragment. Subject to the "softball check." |
| `<draft_dir>/04_speaker_notes/` (optional) | Speaker notes; check for caveats that should appear on the main slide. |

Where `<project_dir>` is `<draft_dir>/../..` (talks/draft_N → ../.. is project_dir).

The reviewer must NOT modify any of these files. Read-only.

---

## 3. Output contract

### `audit/adversarial_review.md` (human-readable)

Markdown report structured as:

```
# Adversarial Review — <project_id> draft_<N>

**Reviewer:** beril-adversarial --type presentation v1.0
**Reviewed at:** 2026-04-28T13:42:00Z
**Total findings:** 17 (3 P0, 9 P1, 5 P2)

## A. Throughline integrity
...

## B. Claim-evidence load-bearing
...

## C. Tier-language register
...

## D. Q&A anti-strawman check
...

## E. Substory→slide mapping coherence
...

## F. Missing-slide / coverage gaps
...

## G. The deck's biggest narrative weakness (single paragraph)
...

## Suggested fixes
For each finding: target prompt or layer, suggested action.
```

### `audit/adversarial_review.json` (machine-readable)

Schema:

```json
{
  "schema_version": "adversarial-review-presentation.v1",
  "draft_dir": "/abs/path/to/talks/draft_N/",
  "reviewed_at": "2026-04-28T13:42:00Z",
  "reviewer_model": "claude-sonnet-4-5-20250929",
  "tier": "STRONG",
  "summary": {
    "total_findings": 17,
    "by_severity": {"P0": 3, "P1": 9, "P2": 5},
    "by_class": {
      "throughline": 2,
      "claim_evidence": 5,
      "register_drift": 3,
      "qa_softball": 3,
      "substory_arc": 2,
      "missing_slide": 1,
      "unbacked_quantitative": 1
    }
  },
  "findings": [
    {
      "id": "F001",
      "class": "claim_evidence",
      "severity": "P0",
      "slide_id": 264,
      "slide_position": 9,
      "slide_layout": "data_figure",
      "title_quote": "Dark gene conservation spans diverse phylogenetic breadth with 30,756 clusters across 27,690 species",
      "issue": "Title claims 'diverse phylogenetic breadth' but REPORT.md §Finding 5 explicitly states '99.9% of clusters map to universal breadth — the classification does not discriminate among candidates.' The slide is making a claim the evidence actively undermines.",
      "report_evidence": [
        {"section": "§Finding 5", "lines": "142-148", "quote": "30,756 dark gene clusters mapped across 27,690 pangenome species, but 99.9% map to 'universal' breadth..."}
      ],
      "fix_target": "slide_compose.v1.md",
      "fix_hint": "Title should state the limitation, not bury it. Suggested: 'Phylogenetic breadth coarse: 99.9% of 30,756 clusters classify as universal; species-count metric needed for resolution.' Caption should reference fig07_phylo_breadth.png with the limitation explicit."
    },
    ...
  ],
  "deck_level_findings": [
    {
      "id": "DL001",
      "class": "narrative_arc",
      "severity": "P1",
      "issue": "S3 slide order obscures the experimental roadmap (the deck's climax). Slide 19 (10 RB-TnSeq experiments cover 45%) is presented as a figure caption mid-substory; quality metrics (slide 18) precede the roadmap when they should support it.",
      "fix_target": "substory_design.v1.md (climax marker) + slide_compose.v1.md (substory ordering)",
      "fix_hint": "Re-order S3: Methods → Roadmap-results → Dual-routes → Quality-metrics. Or: introduce a 'climax slide' marker in substory punchlines that slide_compose honors."
    },
    {
      "id": "DL002",
      "class": "missing_slide",
      "severity": "P0",
      "issue": "Deck never names the top 10 prioritized candidates with predicted functions. The whole talk is about prioritization but the audience never sees what gets prioritized.",
      "fix_target": "slide_compose.v1.md (coverage requirement) OR new layout 'top_candidates'",
      "fix_hint": "Add one slide between current 17 and 18: claim_evidence with bullets listing top 5-10 named candidates + predicted functions from REPORT.md §Finding 8."
    }
  ]
}
```

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Review completed; findings written to disk regardless of severity |
| 2 | Runtime error (missing inputs, claude CLI failed, etc.) |
| 3 | Config error (claude not on PATH) |

The presence of P0 findings is NOT an exit-code failure — that's the consumer's policy, not the reviewer's. The orchestrator decides whether to halt based on the JSON.

---

## 4. Failure-mode catalog

The reviewer must detect findings in seven classes. Each class has a per-class detection contract; the reviewer prompt is the operationalization.

### Class 1: throughline integrity

**Question to ask:** Does the throughline carry across all substories, or does the spine bend / break / get abandoned?

**Detection criteria:**
- For each substory, identify the substory's contribution to the throughline. If a substory makes a claim the throughline doesn't license, flag.
- For each substory punchline, decide: is it load-bearing or filler? A load-bearing punchline names a specific finding the substory established. A filler punchline is generic ("multi-source evidence converges").
- For the final-substory's last slide, check that it delivers the throughline's promised conclusion. If not, the deck has no climax.

**Severity:**
- P0 if any substory makes a claim the throughline doesn't license.
- P1 if any punchline is filler.
- P1 if the final substory doesn't deliver a climax.

### Class 2: claim-evidence load-bearing per slide

**Question to ask:** Does each content slide's title state a load-bearing claim that the bullets and figure actually evidence?

**Detection criteria per content slide (skip title/divider/acks/refs):**
- **Title load-bearing test:** Is the title a claim with a verb (e.g., "X demonstrates Y") or a topic label ("Methods: X")? Topic labels are P2. Method-summary slides legitimately use topic-label form, but most claim-evidence / data-figure slides should be claim-form.
- **Bullets-as-evidence test:** Do bullets evidence the title or restate it? Restatement is P1.
- **Quantitative grounding test:** For each number/percentage/ratio on the slide, search REPORT.md verbatim. Any number not appearing in REPORT.md is P0 ("unbacked quantitative claim"). Use string-match plus normalization for commas, percent vs decimal (24.9% ↔ 0.249), rounding to 2-3 sig figs.
- **Citation load-bearing test:** Are citations in `content.citations[]` actually about the claim being made? P1 if a citation supports a generic methodology rather than the specific claim.

**Severity:**
- P0 for unbacked numbers.
- P1 for bullet-restatement, citation drift.
- P2 for topic-label titles where claim-form was possible.

### Class 3: tier-language register

**Question to ask:** Does the slide's language match the deck's tier (STRONG / THIN / EXPLORATORY)?

**Detection criteria:**
- For each slide, compare the slide's main verbs and modifiers against REPORT.md's hedging for the same finding.
  - If REPORT says "marginal significance, p=0.072" or "post-hoc validation" or "coarse-grained" or "exploratory test," the slide CANNOT use confident verbs ("validates", "demonstrates", "establishes") for that finding.
  - If REPORT says "p<0.001, replicated, pre-registered" the slide CANNOT use over-hedged language ("may suggest", "could be consistent with") — that's STRONG-tier under-claiming.
- The reviewer must IDENTIFY which REPORT.md paragraph the slide is summarizing — this is the hard part, but the reviewer is reasoning over both texts so it can. Quote both.

**Severity:**
- P0 if a STRONG-tier deck uses confident verbs for findings REPORT explicitly hedges.
- P1 for milder register drift.
- P1 for STRONG-tier under-claiming.

### Class 4: Q&A anti-strawman check

**Question to ask:** Do the anticipated-Q&A slides preempt the SHARPEST objections, or are they softballs?

**Detection criteria:**
- For each Q&A slide, ask: would a hostile reviewer ACTUALLY ask this question, or is it a question whose answer hand-waves?
  - A real objection forces the speaker to concede a limitation. A softball lets the speaker pivot to a strength.
- For each Q&A slide, identify ONE objection NOT in the Q&A set that should be there (the reviewer should think adversarially: "what's the question this deck most needs to dodge?").
- Check: does the answer concede the limitation honestly or hand-wave?

**Severity:**
- P0 if Q&A actively avoids a sharp objection by inventing a softball.
- P1 if Q&A picks a real objection but the answer hand-waves.
- P1 for missing real objection.

### Class 5: substory→slide mapping coherence

**Question to ask:** Do substory boundaries make narrative sense? Does each substory have a clean arc?

**Detection criteria:**
- For each substory, check the slide order: motivation → methods → claim → evidence → punchline. Out-of-order or inverted ordering is a finding.
- Check whether the climax slide of each substory is positioned last (or near last). If the climax is buried mid-substory, flag.
- Check whether any slide belongs in a different substory (cross-cutting content).

**Severity:**
- P1 for substory-internal ordering issues (climax buried, evidence before claim).
- P1 for cross-cutting slides.

### Class 6: missing slides / coverage gaps

**Question to ask:** What's missing from the deck that the throughline promises?

**Detection criteria:**
- Read the throughline. List its load-bearing claims.
- For each load-bearing claim, check: is there a slide that delivers evidence for it?
- If the throughline says "we prioritize candidates" but no slide names the candidates, flag.
- If the throughline says "across N organisms" but no slide shows the organism breakdown, flag.

**Severity:**
- P0 for a missing slide that the throughline directly licenses.
- P1 for a missing slide that the throughline implies but doesn't directly license.

### Class 7: the deck's biggest narrative weakness

**Question to ask:** If a hostile reviewer in the audience asked the SINGLE question that lands hardest, what would it be? Does any slide preempt it?

**Detection criteria:**
- Single paragraph in the report identifying the weakness.
- This is the reviewer's "killshot" — the one objection the speaker most needs to be ready for.
- Always exactly one finding of this class; severity is informational (not P0/P1/P2).

---

## 5. Severity grades

| Grade | Meaning | Consumer policy (presentation-maker review-rewrite loop) |
|---|---|---|
| **P0** | Blocks ship. Slide makes a false / unbacked / over-confident claim a peer reviewer would catch. | Trigger revise loop: re-run targeted prompt for the slide(s); bounded retry. |
| **P1** | Visible quality regression. The deck is presentable but a careful reviewer finds the issue. | Surface in `next_actions.md`; user decides whether to revise. |
| **P2** | Polish. | Surface in `next_actions.md`; deferred. |

The reviewer must populate `severity` for every finding. The consumer (presentation-maker) decides which severity triggers the revise loop. Default policy: P0 → revise; P1 + P2 → next_actions.

---

## 6. Prompt structure

The prompt `adversarial_presentation.v1.md` follows the `_SKELETON.md` shape used across the skill family. Key sections:

```markdown
# Adversarial Presentation Reviewer

[Role and stakes - 200 words]

You are a hostile peer reviewer at a major scientific conference.
Your job is to find every weak claim, every register drift, every
hand-wave, every missing slide, every Q&A softball. Adam Arkin is
the speaker; he prefers harsh feedback over comfortable feedback.
Useful criticism over polite criticism.

Failures of nerve in this role:
- Calling something "minor" when it's load-bearing
- Citing a "good point" the deck makes (this is not a praise pass)
- Glossing over numbers without REPORT.md cross-check

## What you produce

Two artifacts:
1. <draft_dir>/audit/adversarial_review.md (human-readable)
2. <draft_dir>/audit/adversarial_review.json (machine-readable; schema below)

[JSON schema spec, exact match to §3 above]

## Inputs

[List of files to read, in order]

## Detection protocol

For each of the 7 classes (§4 in this spec), execute the detection criteria below.

[Per-class detailed criteria, expanded from §4]

## Worked example: register-drift detection

Suppose the slide title says "Lab-field concordance validates 61.7%
of dark gene phenotypes predict environmental distributions."

You must:
1. Identify which REPORT.md section is the source. Search REPORT.md
   for "lab-field" + "61.7" — finds §Finding 7.
2. Read §Finding 7 in full. It says: "binomial test against p=0.5
   yields p=0.072 (marginal significance)" plus "Fisher's combined
   p=0.031 (formal validation across multiple metrics)".
3. Decide: is "validates 61.7%" appropriate?
   - If only the binomial existed: NO. p=0.072 is not validation.
   - With Fisher combined p=0.031: BORDERLINE. Validation is
     defensible but the slide should cite the Fisher result, not
     just the 61.7% number alone.
4. Verdict: P1 register drift (over-confident on a borderline
   significance finding without citing the supporting Fisher result).
5. Fix hint: Either rephrase title ("Lab-field concordance: 61.7%
   directional agreement, Fisher's combined p=0.031") OR add
   "Fisher combined p=0.031" to the bullets so the validation
   verb is grounded.

## Anti-patterns

- Do not say "this is a good slide" or "well-supported." This is a
  critique pass; do not balance criticism with praise.
- Do not soften by hedging ("may consider", "perhaps"). Be direct.
- Do not invent objections that aren't in REPORT.md. Every objection
  must be grounded in the source materials.

## Output protocol

[Write order: read all inputs first; emit JSON via Write tool; emit
markdown via Write tool; close with closing-message template]
```

Estimated prompt length: 1500-2500 lines (mirrors `adversarial_paper.v1.md` shape from the existing skill).

---

## 7. Integration with `beril-adversarial-skill`

### CLI surface

```
beril-adversarial-cli --type presentation <draft_dir> [options]

Options:
  --model <model>      Override claude model (default: sonnet)
  --no-stream          Disable stream_progress.py wrapper
  --tier <STRONG|THIN|EXPLORATORY>
                       Override tier from spec (default: read from
                       slide_spec.json)
  --severity-floor <P0|P1|P2>
                       Don't report findings below this severity
                       (default: P2)
  --json-only          Skip the .md report; emit JSON only
```

### Orchestrator changes

`tools/adversarial_review.sh` adds a new dispatch path for `--type presentation`:

```bash
case "$TYPE" in
  paper)        run_paper_review ;;
  plan)         run_plan_review ;;
  project)      run_project_review ;;
  presentation) run_presentation_review ;;  # NEW
  *)            usage_die ;;
esac
```

The `run_presentation_review` function:
1. Validates `<draft_dir>/slide_spec.json` exists.
2. Resolves `<project_dir>` = `<draft_dir>/../..`. Validates `REPORT.md` + `RESEARCH_PLAN.md` exist there.
3. Builds the user prompt with all input paths.
4. Invokes `claude -p` with `prompts/adversarial_presentation.v1.md` + the user prompt + `--allowedTools Read,Write,Grep,Glob`.
5. Pipes through `stream_progress.py` for cost accounting.
6. Verifies the two output files were written; halts if not.
7. Logs findings count by severity to stderr.

### Tests

New tests in `tests/unit/test_presentation_review.py`:

- `test_presentation_review_against_synthetic_perfect_deck` — feed a deck where every slide claim grounds verbatim in a REPORT.md, every Q&A is sharp, no register drift. Expect 0 P0 findings.
- `test_presentation_review_catches_unbacked_number` — feed a deck with a number not in REPORT.md. Expect ≥1 P0 unbacked_quantitative finding pointing at the right slide.
- `test_presentation_review_catches_register_drift` — feed a deck with "validates" on a finding REPORT explicitly hedges. Expect ≥1 P0/P1 register_drift finding.
- `test_presentation_review_catches_qa_softball` — feed a deck where Q&A picks a question with an obvious hand-wave. Expect ≥1 P1 qa_softball finding.
- `test_presentation_review_writes_both_artifacts` — invoke against a real draft_dir, verify both .md and .json land.

Synthetic decks live under `tests/fixtures/adversarial_presentation/` as draft_dir-shaped trees with curated REPORT.md + slide_spec.json pairs.

---

## 8. Integration with `beril-presentation-maker` (downstream consumer; NOT in this spec)

For reference only — this is the v0.3.0 review-rewrite loop on the presentation-maker side, not part of this spec:

1. After `merge_and_assemble` in presentation-maker, optionally invoke `beril-adversarial-cli --type presentation <draft_dir>`.
2. Parse `<draft_dir>/audit/adversarial_review.json`.
3. For each P0 finding with `fix_target = slide_compose.v1.md`, invoke a `revise_slide.v1.md` prompt (analogous to `revise_throughline.v1.md` from paper-writer) targeting the named slide. Bounded retry (max 2 per slide; cap total cost via `--max-cost-usd`).
4. After revise pass, re-run validator + assemble.
5. Surface remaining (post-revise) findings in `next_actions.md`.

This loop is OUT OF SCOPE for this spec; it lives in presentation-maker v0.3.0.

---

## 9. Worked example: applying the reviewer to draft_9

To validate this spec, the implementer should run the reviewer against the existing
`spike/beril-extended/projects/functional_dark_matter/talks/draft_9/` directory and verify findings include AT LEAST these (already identified in this conversation by the storytelling reviewer):

| Class | Severity | Slide | Issue |
|---|---|---|---|
| claim_evidence | P0 | 9 | "diverse phylogenetic breadth" but REPORT §Finding 5 says 99.9% coarse |
| register_drift | P1 | 14 | "validates 61.7%" but binomial p=0.072 marginal (Fisher p=0.031 supports but uncited) |
| claim_evidence | P0 | 18 | weight-sensitivity (only 18/50 robust) absent from main slide; only in Q&A |
| substory_arc | P1 | 14-15 | NMDC validation order should follow lab-field, not precede |
| substory_arc | P1 | 17-19 | S3 climax (slide 19, 45% coverage) buried as figure caption |
| qa_softball | P1 | 22 | phylo bias question's answer doesn't land — Proteobacteria-centric prioritization not conceded |
| qa_softball | P1 | 23 | GapMind mechanism question avoided — only co-occurrence challenge raised |
| missing_slide | P0 | (after 17) | top 10 candidates with predicted functions never shown |

If the reviewer doesn't find ≥6 of these, the prompt is not sharp enough; iterate on the prompt before calling v1 done.

---

## 10. Open decisions

The implementer should make these calls early; mark them as decisions in `DECISIONS.md`:

1. **Which model for v1?** Sonnet is the cost default. For a hostile-reviewer task, an Opus pass might find sharper objections. Spec recommends Sonnet for cost; revisit after first 5 reviews.

2. **JSON schema versioning.** `adversarial-review-presentation.v1` is the spec'd version. Bump to .v2 if the schema changes; both must coexist for a deprecation cycle.

3. **WebSearch for citation cross-check?** The reviewer might want to verify that a citation actually supports the claim (not just exists in the pool). Out of scope for v1; defer unless a v1 review burns on a fabricated-citation issue.

4. **How does the reviewer signal confidence?** Each finding should include a `confidence: low|medium|high` field. High = "I'm certain this is wrong." Low = "I think this is wrong; might be defensible." Add to schema.

5. **Multi-pass review?** The hostile-reviewer task benefits from doing one pass for "obvious bugs," then a second pass for "deeper structural issues." v1 is single-pass; multi-pass is v2.

6. **Should the reviewer's findings cite specific REPORT.md line ranges?** Spec'd as yes (`report_evidence: [{section, lines, quote}]`). The reviewer must do real grep work, not synthesize.

---

## 11. Acceptance criteria for v0.4.0 of beril-adversarial-skill

The implementer should ship `--type presentation` as `beril-adversarial-skill v0.4.0` (current is v0.3.0 per pyproject; bumping major-minor for a new mode). Acceptance:

- [ ] `prompts/adversarial_presentation.v1.md` lands; ≥1500 lines; mirrors `adversarial_paper.v1.md` shape.
- [ ] `tools/adversarial_review.sh` adds `run_presentation_review` dispatch.
- [ ] `cli.py` adds `--type presentation` choice.
- [ ] `tests/unit/test_presentation_review.py` ≥5 tests, all pass.
- [ ] Live test against `draft_9/` finds ≥6 of the 8 issues listed in §9. Cost ≤ $1.50 on Sonnet.
- [ ] `audit/adversarial_review.md` is human-readable; `audit/adversarial_review.json` parses + matches schema.
- [ ] RELEASE_NOTES.md updated with v0.4.0 narrative.
- [ ] No breaking changes to `--type paper / plan / project` modes.

---

## 12. Briefing for the implementer thread

Hand this spec to a fresh Claude session as the load-bearing input. Brief the implementer:

> You are implementing `--type presentation` mode for `beril-adversarial-skill`. The spec is at `spike/beril-adversarial-skill-draft/SPEC_TYPE_PRESENTATION.md`. Read it in full before starting. The skill is at `spike/beril-adversarial-skill-draft/`. Existing `--type paper` is the closest precedent at `prompts/adversarial_paper.v1.md` and the `run_paper_review` function in `tools/adversarial_review.sh`. Mirror that shape. Validate against draft_9 at `spike/beril-extended/projects/functional_dark_matter/talks/draft_9/` per §9 of the spec. Bump version to v0.4.0. Write a punch list at `V0_4_0_PUNCH_LIST.md` before starting; tier as A (prompt) → B (orchestrator + CLI) → C (tests) → D (live validation) → E (commit + tag). Use the same tiered-with-deps + smoke-at-gates pattern that shipped paper-writer v0.1.0. The user (Adam Arkin) prefers harsh feedback over comfortable feedback; this includes self-criticism. Skip preamble; get to work.

---

## Appendix: why the regex post-checker approach was rejected

A separate proposal in the parent conversation suggested building `tools/check_register_drift.py` with regex-based hedge detection. That proposal was rejected because:

1. The verb is not the discriminator. "Validates" can be appropriate when REPORT has Fisher's combined p<0.05 even if binomial is p=0.072.
2. The hedge-regex catches noise. "Marginal" appears as marginal cost, marginal posterior, marginal improvement — multiple senses.
3. The slide→REPORT mapping is the actual hard problem. Regex can't know which REPORT paragraph a slide is summarizing.

Mechanical post-checkers work for STRUCTURAL invariants (citation pool keys exist, glyph cross-walks, path-shape rules, numeric verbatim grounding). They do NOT work for SEMANTIC alignment between two prose blocks. Register drift, caveat omission, slide ordering, Q&A softballing, missing-slide detection — these need LLM-in-the-loop semantic verification. That's why the adversarial reviewer is the architecturally correct answer for content control.

The one mechanical post-checker that's worth building separately: `check_quantitative_grounding.py` (number-grep against REPORT.md with normalization for commas, percent vs decimal, rounding). That one is deterministic; it's a v0.2.x deliverable for presentation-maker independent of this spec.
