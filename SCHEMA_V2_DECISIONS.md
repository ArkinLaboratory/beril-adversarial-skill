# adversarial-review-presentation schema v2 — design decisions

**Status:** Decisions for v0.5.0 implementation. Author: Claude (this session, 2026-04-29).

## Why v2 exists

v1 had two arrays: `findings[]` (slide-level) + `deck_level_findings[]`
(non-slide-locus findings like missing_slide and narrative_weakness).
The LLM repeatedly placed deck-level findings into `findings[]` because
prompt-level instruction wasn't load-bearing. Schema v1's dual-array
structure created an entire class of failure modes (wrong-array placement)
that adding more prompt instructions or validator patches couldn't
reliably eliminate.

v2 collapses to a single `findings[]` array. Deck-level findings are
identified by absence of `slide_id`. The LLM cannot put findings in the
wrong array because there is only one array.

## Schema differences

### Top-level structure

**v1:**
```json
{
  "schema_version": "adversarial-review-presentation.v1",
  ...
  "findings": [...],            // slide-level only
  "deck_level_findings": [...]  // narrative_weakness, missing_slide, etc.
}
```

**v2:**
```json
{
  "schema_version": "adversarial-review-presentation.v2",
  ...
  "findings": [...]             // ALL findings, slide-level and deck-level
}
```

`deck_level_findings` field is REMOVED in v2. Validator rejects v2 docs
that include it.

### Per-finding fields

**v2 required fields (all findings):**
- `id` (string, F### sequential)
- `class` (enum)
- `severity` (enum)
- `confidence` (enum: high|medium|low)
- `issue` (string)
- `fix_target` (string)
- `fix_hint` (string)

**v2 optional fields (slide-level findings have these; deck-level findings omit them):**
- `slide_id` (int) — presence-of indicates slide-level
- `slide_position` (int)
- `slide_layout` (string)
- `title_quote` (string)
- `substory_id` (string|null)
- `report_evidence` (array of {section, quote})

**Migration:**
- v1 finding in `findings[]` → v2 finding with `slide_id` (unchanged)
- v1 finding in `deck_level_findings[]` → v2 finding without `slide_id`
- ID prefixes: v1 used `F###` for slide-level and `DL###` for deck-level.
  v2 uses `F###` for ALL findings (sequential, single namespace).

### Summary block

Unchanged shape. v2's `summary.total_findings` = `len(findings)` (single
array) instead of v1's `len(findings) + len(deck_level_findings)`.

## Validator behavior

The validator accepts BOTH v1 and v2 for forensic compatibility:

- **v1 docs** (existing draft_9 / draft_10 / earlier audit files):
  validator validates per v1 rules; emits a deprecation note on stderr
  ("schema_version v1 is deprecated; new runs emit v2").
- **v2 docs** (new runs): validator validates per v2 rules; rejects
  docs that include the now-removed `deck_level_findings` field.
- **Auto-correction** of summary count mismatches works on both shapes.
- **`compute_correct_summary`** is the single source of truth and
  takes whichever array structure exists.

## Reviewer behavior (post-v0.5.0)

The presentation reviewer emits v2 ONLY. The prompt is renamed
`adversarial_presentation.v2.md` (file rename) and the user-prompt body
sets `schema_version: "adversarial-review-presentation.v2"` and
`prompt_version: "adversarial_presentation.v2"`.

## Why drop v1 emission cleanly (rather than dual-emit)

There are no real consumers of v1 yet. presentation-maker v0.3.0
review-rewrite loop is planned, not built. Dual-emit would be
deprecation-cycle theater for a contract no one depends on.

The validator's continued v1 *acceptance* is for FORENSIC purposes
only — Adam can still inspect old draft_9 / draft_10 audit files
without re-running the reviewer.

## Consumer migration (when presentation-maker v0.3.0 ships)

The consumer parses by:

```python
findings = doc["findings"]
slide_level = [f for f in findings if "slide_id" in f]
deck_level = [f for f in findings if "slide_id" not in f]

p0_findings = [f for f in findings if f["severity"] == "P0"]
narrative_weakness = next(
    (f for f in findings if f["class"] == "narrative_weakness"), None
)
```

For routing fix-targets (the consumer's main job):

```python
for f in findings:
    if f["severity"] == "P0":
        invoke_revise(f["fix_target"], f["slide_id"], f["fix_hint"])
```

`slide_id` lookup falls through naturally on deck-level findings — the
consumer either has slide-level routing or treats it as deck-wide.

## Files changed in v0.5.0

| File | Change |
|---|---|
| `prompts/adversarial_presentation.v1.md` | Renamed to `.v2.md`; output contract rewritten to single-array shape |
| `tools/validate_presentation_review.py` | Accepts v1 + v2; per-version validation paths; deprecation note for v1 |
| `tools/adversarial_review.sh` | Loads `.v2.md`; user-prompt sets v2 schema/prompt versions |
| `tests/unit/test_validate_presentation_review.py` | Default _make_doc emits v2; explicit v1 tests added; v2-only edge-case tests |
| `tests/unit/test_presentation_review.py` | Update prompt path expectation if filename grep is hard-coded |
| `pyproject.toml` + `src/beril_adversarial/__init__.py` | 0.4.1 → 0.5.0 |
| `RELEASE_NOTES.md` | v0.5.0 narrative + migration note |
| `.commit-message-v0_5_0.txt` | Staged for Adam's `git commit -F` |
