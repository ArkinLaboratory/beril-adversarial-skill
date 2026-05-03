# adversarial-review schema v3 — design decisions (paper + presentation)

**Status:** Decisions for v0.7.0 implementation. Author: Claude (this session, 2026-05-03). Adam-review gate before any prompt or code work begins.

This doc consolidates v3 changes for BOTH paper and presentation schemas. Replaces the per-format pattern of `SCHEMA_V2_DECISIONS.md` (presentation) + `SCHEMA_V2_PAPER_DECISIONS.md` (paper). Bundling avoids doc proliferation now that the two schemas have a shared evolution story.

## Why v3 exists

Three breaking changes have accumulated since v2 shipped:

1. **Class rename** — `narrative_weakness` → `central_objection`. Label issue flagged by paper-writer team's taxonomy review (2026-05-03). The function (single deck/paper-wide synthesis finding, severity=info, "the biggest objection a hostile reviewer would raise") didn't change; the name was being misread as "the deck has a weak narrative" rather than "here is the central thing to defend against."
2. **Class addition (presentation only)** — add `citation_reality` to presentation v3. Currently paper-only. Presentation-maker team requested parity (2026-05-02): slide footers and provenance pinning to REPORT.md sections are de-facto citations, and citation drift / fabrication does happen at presentation level (slide cites paper claiming X; paper says Y).
3. **CLI surface** — `--output` flag honored for `--type paper|presentation` (currently silently ignored per CONTRACT.md v0.6.5 honesty fix). Surfaced by paper-writer team's draft_9 live review (2026-05-03).

Bundling these into one schema bump saves consumers (paper-writer's fallback_reviewer.v1, paper-writer's review-rewrite loop, presentation-maker's revise_loop) one re-pin migration instead of three sequential ones.

## Why bundled, not sequenced

Three sequential schema bumps cost consumers:
- 3× re-pin cycles
- 3× CONTRACT.md migration sections to read
- 3× cross-skill smoke updates
- N (consumers) × 3 deprecation-window calendar coordination

One bundled v3 costs:
- 1× re-pin cycle
- 1 CONTRACT.md migration section
- 1× cross-skill smoke update
- N × 1 deprecation-window coordination

Adam endorsed the bundle 2026-05-03.

## What's NOT in v3 (explicit out-of-scope)

- **`subkind` field on `missing_section`** (deferred — paper-writer team to provide one more data point on whether per-finding recommendation text is already steering remediation correctly; if so, skip).
- **Splitting `missing_section` into `rendering_failure` / `methods_gap` / `compliance_gap`** (deferred — same data point as above; preference is `subkind` enum if needed at all, since reviewer's job is the same in all three sub-cases).
- **`--auto-number` flag** (deferred — pending paper-writer team's interest signal; orthogonal to schema).
- **Phase 4 graphic design reviewer** (vision-LLM; tracked as #19; not part of v3).

## Class taxonomy — v3 vs v2

### Presentation v3 (8 classes; net +1 from v2's 7)

| Class | v2 | v3 | Notes |
|---|---|---|---|
| `claim_evidence` | ✓ | ✓ | unchanged |
| `unbacked_quantitative` | ✓ | ✓ | unchanged |
| `register_drift` | ✓ | ✓ | unchanged |
| `narrative_weakness` | ✓ | — | renamed → `central_objection` |
| `central_objection` | — | ✓ | renamed from `narrative_weakness`; same role (1 per review, severity=info) |
| `throughline` | ✓ | ✓ | unchanged |
| `missing_slide` | ✓ | ✓ | unchanged |
| `substory_arc` | ✓ | ✓ | unchanged |
| `qa_softball` | ✓ | ✓ | unchanged |
| `citation_reality` | — | ✓ | NEW; parity with paper v2 |

### Paper v3 (10 classes; rename only, no net change)

| Class | v2 | v3 | Notes |
|---|---|---|---|
| `claim_evidence` | ✓ | ✓ | unchanged |
| `unbacked_quantitative` | ✓ | ✓ | unchanged |
| `register_drift` | ✓ | ✓ | unchanged |
| `narrative_weakness` | ✓ | — | renamed → `central_objection` |
| `central_objection` | — | ✓ | renamed from `narrative_weakness`; same role (1 per review, severity=info) |
| `throughline` | ✓ | ✓ | unchanged |
| `missing_section` | ✓ | ✓ | unchanged (subkind deferred) |
| `section_arc` | ✓ | ✓ | unchanged |
| `citation_reality` | ✓ | ✓ | unchanged |
| `report_drift` | ✓ | ✓ | unchanged |
| `abstract_body_mismatch` | ✓ | ✓ | unchanged |

### Cross-format intersection v3 (vs v2's 5)

| Class | presentation v3 | paper v3 |
|---|---|---|
| claim_evidence | ✓ | ✓ |
| unbacked_quantitative | ✓ | ✓ |
| register_drift | ✓ | ✓ |
| central_objection | ✓ | ✓ |
| throughline | ✓ | ✓ |
| citation_reality | ✓ | ✓ |
| missing_slide / missing_section | parallel-renamed | parallel-renamed |
| substory_arc / section_arc | parallel-renamed | parallel-renamed |
| qa_softball | ✓ (presentation only) | — |
| report_drift | — | ✓ (paper only) |
| abstract_body_mismatch | — | ✓ (paper only) |

**v3 intersection: 6 classes identical** (75% of presentation, 60% of paper) — up from v2's 5/62%/50%.

## Per-finding fields — unchanged from v2

No field additions, removals, or renames. v3 inherits v2's:
- Universal required fields (`id`, `class`, `severity`, `confidence`, `issue`, `fix_target`, `fix_hint`).
- Format-specific optional fields (presentation: `slide_id`, `title_quote`, `report_evidence`; paper: `section`, `line_range`, `paragraph_quote`, `citation_id`, `bibliography_evidence`).
- Class-conditional `paragraph_quote` / `title_quote` requirements (preserved exactly; `central_objection` follows the same rule `narrative_weakness` did — optional, since deck/paper-wide).

## `citation_reality` on presentation v3 — class definition

Adopting paper v2's `citation_reality` semantics with presentation-appropriate locus:

**Detection:** A slide cites a source (paper, REPORT.md section, dataset DOI, etc.) where the citation is fabricated, miscited, or doesn't support the specific claim it's pinned to.

**Locus:** slide-level (`slide_id` present). The cited source is identified via the slide footer, an in-text citation, or the slide's `provenance_pin` block (presentation-maker layout convention).

**Required fields when present:**
- `slide_id`, `title_quote` (per existing presentation v3 patterns)
- `citation_id` (NEW for presentation v3; was paper-only) — bibtex key, DOI, or REPORT.md section reference being flagged
- `report_evidence` for any P0/P1 (per existing rule for evidence-class findings)

**fix_target conventions:**
- `slide_compose.v1.md` — for citation drift in slide content
- `provenance.v1.md` (if presentation-maker has one) — for provenance-pin issues
- Otherwise the per-slide draft prompt name

**Worked example (Tier B2 will write the full version):** Slide footer reads "Smith et al. 2023 — n=120 healthy controls"; the cited Smith 2023 paper has n=120 patients (not controls). Reviewer flags `citation_reality` with `confidence=high` if it can verify from REPORT.md or provenance; `medium` otherwise.

## `central_objection` rename — semantic spec

Function unchanged from v2's `narrative_weakness`. Spec updated to make the role unambiguous:

> Identify the single biggest objection a hostile expert reviewer would raise against this deck/paper. Exactly ONE finding per review. Severity always `info`. Optional fields (`slide_id`/`section`, quote fields) typically OMITTED — this is a deck/paper-wide synthesis. The finding answers: "If this work were challenged at peer review, what's the strongest attack?"

Rename rationale: "narrative_weakness" was being misread as "the deck has a weak narrative" (a quality judgment). "Central objection" reflects the actual function: the central thing the work needs to defend against, regardless of overall quality.

Validator: where v2 routed `narrative_weakness`, v3 routes `central_objection`. v2 docs continue to validate (deprecation window).

## `--output` flag behavior change

Per CONTRACT.md v0.6.5: in v0.6.x, `--output` is silently ignored for `--type paper|presentation`; output lands at canonical `<draft_dir>/audit/adversarial_review.{md,json}`.

In v0.7.0:
- Without `--output`: behavior unchanged (canonical paths).
- With `--output <basename>`: writes to `<draft_dir>/audit/<basename>.{md,json}`. Iteration without renaming `audit/` is now possible.

This is **operator surface, not schema surface** — the output JSON shape is unchanged. Bundled with v3 for release coordination, not because it depends on v3.

Backwards-compat for consumers: v2 callers that pass `--output` and assume it's ignored will start getting outputs at the basename they specified. That's technically a behavior change. Mitigation: document prominently in CONTRACT.md migration section. Consumers that don't pass `--output` see no difference.

## Validator behavior in v0.7.0

`validate_review.py` accepts:
- `adversarial-review-presentation.v1` (deprecated since v0.5.0; warning continues)
- `adversarial-review-presentation.v2` (deprecated as of v0.7.0; warning added)
- `adversarial-review-presentation.v3` (current)
- `adversarial-review-paper.v2` (deprecated as of v0.7.0; warning added)
- `adversarial-review-paper.v3` (current)

**v2 deprecation policy:** v2 acceptance remains until consumers (paper-writer, presentation-maker) have migrated and confirmed. Removal is event-driven, not calendar-driven — the next release after both consumers report v3 adoption is the one that yanks v2 acceptance. No fixed window. Adam coordinates the migrate-now signal with each consumer team.

**Per-version validation:**
- v3 docs MUST use `central_objection` not `narrative_weakness`. Validator rejects v3 docs containing `narrative_weakness` with a clear error pointing at the rename.
- v3 presentation docs MAY use `citation_reality`. Validator routes per-class field requirements identically to paper.
- All other validation (compute_correct_summary auto-correction, class-conditional paragraph_quote/title_quote, etc.) unchanged.

**Compute_correct_summary** generic across v1/v2/v3 — counts findings, derives by_severity/by_class.

### Validator implementation contract (Tier D prerequisites)

These are explicit requirements the Tier D implementation must honor. The
v3 prompts assume them; if Tier D doesn't enforce them, the prompts
become aspirational instead of contractual.

**D1. Hard-reject v3 docs containing `narrative_weakness`.** When
`schema_version` matches `adversarial-review-{paper|presentation}.v3` AND
any finding's `class` is `"narrative_weakness"`, the validator MUST
reject (exit 1, not auto-correct) with an error like:
`"v3 schema renamed narrative_weakness → central_objection. See SCHEMA_V3_DECISIONS.md for migration."`
This is NOT the auto-correction path — it's a contract violation. Without
this enforcement, an LLM occasional emission of the old name (likely on
retry after an earlier run) produces JSON that consumers parse-by-class
will silently misroute, AND the auto-corrected summary's `by_class`
tally will include the dead class name → JSON internally inconsistent.

**D2. Class-conditional `citation_id` enforcement on `citation_reality`.**
For v3 docs (paper or presentation), when a finding has
`class == "citation_reality"`, the validator MUST require `citation_id`
to be present and non-empty. Reject if missing. The prompts both specify
this requirement (presentation.v3.md table; paper.v3.md table); the
validator must mirror.

**D3. Class-conditional `report_evidence` for `citation_reality` —
fabrication carve-out.** For v3 docs with a `citation_reality` finding
at severity P0 or P1, `report_evidence` is required UNLESS the finding
represents fabrication (the `issue` text describes a missing bibliography
entry / fabricated citation marker; the `citation_id` references a
non-existent source). The validator's enforcement should accept either
shape: with `report_evidence` (drift / pin-drift subclasses) OR without
(fabrication subclass). Tier D should NOT try to mechanically detect
fabrication-vs-drift — accept either shape and let the LLM's class
selection govern.

**D4. Class-conditional `paragraph_quote` / `title_quote` per the
per-finding-fields table.** Both prompts' per-finding-fields tables list
which classes have these fields as REQUIRED vs OPTIONAL. The validator
MUST enforce per-class rather than universal:
- Paper: `paragraph_quote` required IFF `section` present, EXCEPT
  optional for `central_objection`, `missing_section`, `throughline`,
  `section_arc`, `abstract_body_mismatch`, `citation_reality`.
- Presentation: `title_quote` required IFF `slide_id` present, EXCEPT
  optional for `central_objection`, `missing_slide`, `substory_arc`,
  `throughline`, `citation_reality`.

**D5. `prompt_version` field passing.** The prompts emit
`prompt_version: adversarial_{paper|presentation}.v3` in their JSON. The
orchestrator passes the version string into the user-prompt body via a
template variable substitution (see Tier C contract below). The
validator does NOT enforce `prompt_version` content (it's a forensic
field, optional in the schema), but it should accept the field if
present and surface it in summary output.

**D6. Schema-aware deprecation warnings.** The validator MUST emit a
deprecation warning for v2 docs (and continue v1 deprecation warning).
Format: `"WARNING: schema_version v2 is deprecated as of v0.7.0; v3 is current. v2 docs continue to be readable for forensic inspection."`. Warning to stderr, exit code unchanged from current behavior.

### Orchestrator implementation contract (Tier C prerequisites)

**C1. `--output` flag honored for `--type paper|presentation`.** Without
`--output`: behavior unchanged (canonical `<draft_dir>/audit/adversarial_review.{md,json}` paths). With `--output <basename>`:
write to `<draft_dir>/audit/<basename>.{md,json}`. Iteration without
renaming `audit/` is now possible. **CONSUMER-VISIBLE BEHAVIOR CHANGE:**
v2 callers passing `--output` thinking it's a no-op (per CONTRACT.md
v0.6.5 honesty fix) will start getting outputs at the basename they
specified. Tier G must add a CONTRACT.md migration callout flagging this.

**C2. `prompt_version` template substitution.** The orchestrator MUST
substitute `{PROMPT_VERSION}` in the user-prompt template before invoking
the LLM. The substitution value is `adversarial_paper.v3` or
`adversarial_presentation.v3` per the loaded prompt. Without this, the
LLM will emit `prompt_version: {PROMPT_VERSION}` literal (or worse, a
guess) in the JSON, and consumers checking the field for forensic
version-pinning will see garbage.

**C3. Load `.v3.md` prompts.** When `--type paper` is invoked, load
`adversarial_paper.v3.md`. Same for `--type presentation`. The current
orchestrator loads `.v2.md`; this is the swap-over point.

### Release prep contract (Tier G prerequisites)

**G1. CONTRACT.md migration section.** A new "v0.7.0 migration" section
explicitly flags the `--output` behavior change as visible (consumers
passing `--output` thinking it's a no-op WILL see new file paths). Lists
the class rename (narrative_weakness → central_objection), the new
class for presentation (citation_reality), and the asymmetric class
renumbering note (see G2).

**G2. Asymmetric class renumbering note.** The class renumbering is
asymmetric across schemas: paper.v3 keeps the same class numbers as
paper.v2 (the rename is in-place; central_objection remains Class 10).
Presentation.v3 inserts citation_reality as Class 6, bumping
missing_slide 6→7 and central_objection 7→8. Class numbers are
documentation-internal (the `class` field is the canonical identifier),
but worked-example references and self-skepticism per-class checks use
the numbers, so consumers reading prompts to understand reviewer
behavior need to know.

**G3. Cross-consumer coordination policy.** CONTRACT.md should define:
"v2 schema acceptance by the validator will be removed in the release
AFTER BOTH paper-writer and presentation-maker teams confirm v3
adoption in production. The beril-adversarial skill owner coordinates
with each consumer team before tagging the release that yanks v2
acceptance."

**G4. `citation_id` semantic note for presentation.** Add to CONTRACT.md
or the v3 prompt description: "Presentation v3 `citation_id` may hold
REPORT.md section references (e.g., `'REPORT§Finding 7'`), DOIs, or
bibtex keys — any string identifier of the cited source. Consumers
parsing presentation v3 JSON should not assume `citation_id` is a
bibtex key."

**G5. RELEASE_NOTES forensic-compat note.** v0.6.x audit files containing
`narrative_weakness` (v2 schema) remain readable by v0.7.0 validator.
The rename applies only to v3 schema. Users re-processing old audit
files don't need to update them.

## Reviewer behavior in v0.7.0

Each prompt emits exactly ONE schema:
- `adversarial_paper.v3.md` emits `adversarial-review-paper.v3` only.
- `adversarial_presentation.v3.md` emits `adversarial-review-presentation.v3` only.

v2 prompts (`adversarial_paper.v2.md`, `adversarial_presentation.v2.md`) are deleted in v0.7.0 — no dual-emit. The validator's continued v2 acceptance is for forensic purposes only (inspecting old draft audit JSONs).

## Consumer migration

### paper-writer

Consumer code in paper-writer (`fallback_reviewer.v1` and the planned review-rewrite loop) needs three changes:

1. **Class enum:** wherever paper-writer's code matches on `class == "narrative_weakness"`, switch to `class == "central_objection"`. If paper-writer wants to handle the deprecation window, accept both for one minor cycle.
2. **`--output` flag:** if paper-writer's orchestrator was passing `--output` thinking it was a no-op, remove that assumption. Either drop the flag (canonical paths) or use it intentionally for non-default basenames.
3. **No field changes** required — all v2 fields remain.

(Plus the orthogonal v0.6.0+ CLI shape fix for `paper_writer.sh 0.6.3` documented in v0.6.5 cross-team message.)

### presentation-maker

Consumer code in presentation-maker (`revise_loop.py`) needs four changes:

1. **Class enum:** `narrative_weakness` → `central_objection` (same as paper-writer).
2. **New class handling:** route `citation_reality` findings somewhere — likely surface to user for review (citation issues need human verification, not auto-revision).
3. **`--output` flag:** if presentation-maker's orchestrator passes it, audit assumptions same as paper-writer.
4. **No field changes** required — `citation_reality` reuses existing optional fields (`citation_id`, `report_evidence`).

### Both consumers — recommended consumer-side smoke

Per v0.6.5 cross-skill drift lesson: each consumer SHOULD add a smoke test asserting:
- The CLI invocation it issues exits 0.
- The output file exists, parses as JSON, contains a `findings` array.
- `schema_version` matches what the consumer expects (v2 or v3).

Producer (us) cannot enforce this; consumer-side responsibility.

## Files changed in v0.7.0

| File | Change |
|---|---|
| `prompts/adversarial_paper.v2.md` | Delete (forensic-only access via deprecated validator) |
| `prompts/adversarial_paper.v3.md` | New; rename `narrative_weakness` → `central_objection` in taxonomy + worked examples + self-skepticism pass; carry forward all v0.6.x JSON-validity hardening; update prompt_version field |
| `prompts/adversarial_presentation.v2.md` | Delete |
| `prompts/adversarial_presentation.v3.md` | New; rename `narrative_weakness` → `central_objection`; ADD `citation_reality` as 8th class with worked example + class-conditional field rules; carry forward JSON-validity hardening; update prompt_version |
| `tools/validate_review.py` | Accept v3 schemas; emit deprecation warning for v2; reject v3 docs containing `narrative_weakness` (rename enforcement); route `citation_reality` on presentation v3 |
| `tools/adversarial_review.sh` | Honor `--output` flag for `--type paper\|presentation`; load `.v3.md` prompts; user-prompt sets v3 schema/prompt versions; argparse migration hint for v0.5.x-shape invocations |
| `src/beril_adversarial/cli.py` | Fusion: `--reviewer claude\|codex\|claude,codex` flag (Tier E) |
| `src/beril_adversarial/commands/review.py` | Fusion plumbing; --output passthrough |
| `src/beril_adversarial/commands/fusion.py` (NEW) | Merge/dedupe logic for dual-reviewer output |
| `tests/unit/test_validate_review.py` | v3 schema tests; deprecation warning tests; rename-enforcement tests; citation_reality on presentation v3 tests |
| `tests/unit/test_paper_review.py` + `test_presentation_review.py` | Update prompt path expectations to v3 |
| `tests/unit/test_fusion.py` (NEW) | Merge/dedupe unit tests |
| `tests/integration/test_paper_writer_interop.py` | Updated for v3 shape; verifies central_objection in output; verifies --output flag works |
| `pyproject.toml` + `src/beril_adversarial/__init__.py` | 0.6.5 → 0.7.0 |
| `RELEASE_NOTES.md` | v0.7.0 entry: schema bump migration guide, fusion intro, --output behavior change, argparse hint |
| `CONTRACT.md` | New section: v3 migration; --output behavior change; fusion usage examples; schema version policy (deprecation cadence) |
| `SCHEMA_V2_DECISIONS.md` + `SCHEMA_V2_PAPER_DECISIONS.md` | Mark as historical (front-matter banner pointing at this doc); keep for archaeology |
| `.commit-message-v0_7_0.txt` | Staged for `git commit -F` |

## Decisions (Adam-review gate cleared 2026-05-03)

1. **`citation_reality` field name on presentation.** Keep `citation_id` for cross-format consistency. The field holds any string identifier — bibtex key, DOI, REPORT.md section reference — not just bibliographic IDs.

2. **v2 deprecation policy.** Event-driven, not calendar-driven. v2 acceptance stays until consumers confirm v3 migration; removal lands in the next release after both confirm. No fixed deadline. (Reflected in "Validator behavior" section above.)

3. **`--output` behavior change.** Bundled with v3, no separate version bump. Prominent CONTRACT.md migration callout flags the consumer-visible behavior change ("if your orchestrator passes `--output` thinking it's a no-op, audit assumptions").

4. **Fusion default reviewer set.** `--reviewer claude` remains the default (back-compat, deterministic, no surprise costs). Fusion is opt-in via `--reviewer claude,codex` even when both CLIs are detected at configure-time.

5. **`citation_reality` emission gate on presentation.** Silent absence of citation/provenance is NOT a `citation_reality` finding. Class triggers ONLY when a citation is present and questionable. Slides without any provenance pin / footer citation are not flagged by this class (other classes may flag the absence under different framings — `claim_evidence` or `unbacked_quantitative` typically).

6. **Migration script for older audit JSONs.** Not provided. Historical audit files stay at v2; validator continues to read them. v3 is for new runs only.

Tier A complete. B1/B2/C/D/E/F unblocked.
