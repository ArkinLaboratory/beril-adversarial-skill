#!/usr/bin/env bash
# adversarial_review.sh — invoke the BERIL adversarial reviewer.
#
# Usage:
#   adversarial_review.sh <project_id> [--type plan|project|paper] \
#     [--reviewer claude|codex|claude,codex] [--model <model_id>] \
#     [--beril-root <path>] [--consolidate] [--output <path>]
#
# Mirrors BERIL's tools/review.sh. Differences:
#   - Three review types (plan, project, paper) instead of two.
#   - Multi-reviewer fusion when --reviewer claude,codex: runs both in
#     parallel, then a third fusion call produces the unified review.
#   - --consolidate path: synthesize all numbered reviews of the matching
#     type into a canonical file with revision history.
#   - Skill-dir-based discovery: the script locates BERIL_ROOT and
#     prompts relative to its own install path
#     (<BERIL_ROOT>/.claude/skills/beril-adversarial/tools/).
#   - Richer --allowedTools grant for the claude subprocess:
#     Read,Write,Bash,Grep,Glob,WebSearch,Agent.

set -euo pipefail

# --- Defaults ---
REVIEWER="claude"
MODEL=""
PROJECT_ID=""
REVIEW_TYPE="project"
OUTPUT_FILE=""
BERIL_ROOT_OVERRIDE=""
CONSOLIDATE=0
DEPTH="standard"
# Stream parsing (Write verification + cost summary at end) is the default.
# Set NO_STREAM=1 (via --no-stream) to opt out.
NO_STREAM=0
# Compliance critic (post-review audit + targeted fix pass) is the default.
# Set NO_CRITIC=1 (via --no-critic) to opt out.
NO_CRITIC=0
# Citation verification gate (programmatic check against Crossref + PubMed)
# is the default. Set NO_VERIFY_CITATIONS=1 (via --no-verify-citations) to
# opt out. The gate is independent of the LLM-based critic and adds zero
# token cost (just HTTP calls to free registries).
NO_VERIFY_CITATIONS=0

CLAUDE_DEFAULT_MODEL="claude-sonnet-4-20250514"
CODEX_DEFAULT_MODEL="gpt-5.4"

CLAUDE_TOOLS="Read,Write,Bash,Grep,Glob,WebSearch,Agent,ToolSearch"

# --- Usage ---
usage() {
  local exit_code="${1:-0}"
  cat <<EOF
Usage: adversarial_review.sh <project_id> [options]

Arguments:
  project_id                  Project directory name under projects/
                              (optional if cwd is inside projects/<id>/)

Options:
  --type plan|project|paper   Review type (default: project)
  --reviewer R                claude | codex | claude,codex
                              (claude,codex runs both in parallel and
                              fuses the results; default: claude)
  --model <model_id>          Model override (default: claude-sonnet-4-20250514
                              for claude; gpt-5.4 for codex)
  --beril-root <path>         BERIL repository root (default: auto-detect)
  --consolidate               Skip review; synthesize all numbered
                              reviews of matching --type into a canonical
                              file with revision history
  --depth quick|standard|deep Review thoroughness (default: standard).
                              quick: ~1-2m, skip subagents, top-level only.
                              standard: ~5-10m, full subagent flow.
                              deep: ~15-25m, expanded subagents + sensitivity.
  --no-stream                 Disable the stream-json parser pipe (turns off
                              programmatic Write verification, retry on
                              silent failure, end-of-run summary, and the
                              sidecar .stream.log). Default: parser is on.
  --no-critic                 Disable the post-review compliance critic.
                              Default: critic runs after main review and
                              triggers a targeted fix pass on violations.
  --no-verify-citations       Disable the citation verification gate.
                              Default: gate runs after the compliance
                              critic loop. Every 9-field citation block
                              is verified against Crossref (DOI) and
                              NCBI PubMed (PMID); fabricated citations
                              are marked inline and listed in a Citation
                              Verification section appended to the
                              review.
  --output <path>             Override output file path (default: auto-numbered)
  --help                      Show this message

Examples:
  adversarial_review.sh my_project
  adversarial_review.sh my_project --type plan
  adversarial_review.sh my_project --depth quick           # fast iteration
  adversarial_review.sh my_project --depth deep            # thorough
  adversarial_review.sh my_project --type paper --reviewer claude,codex
  adversarial_review.sh my_project --consolidate
EOF
  exit "$exit_code"
}

# --- Parse arguments ---
while [[ $# -gt 0 ]]; do
  case "$1" in
    --type)
      [[ -z "${2:-}" ]] && { echo "Error: --type requires a value" >&2; usage 1; }
      REVIEW_TYPE="$2"
      shift 2
      ;;
    --reviewer)
      [[ -z "${2:-}" ]] && { echo "Error: --reviewer requires a value" >&2; usage 1; }
      REVIEWER="$2"
      shift 2
      ;;
    --model)
      [[ -z "${2:-}" ]] && { echo "Error: --model requires a value" >&2; usage 1; }
      MODEL="$2"
      shift 2
      ;;
    --beril-root)
      [[ -z "${2:-}" ]] && { echo "Error: --beril-root requires a value" >&2; usage 1; }
      BERIL_ROOT_OVERRIDE="$2"
      shift 2
      ;;
    --output)
      [[ -z "${2:-}" ]] && { echo "Error: --output requires a value" >&2; usage 1; }
      OUTPUT_FILE="$2"
      shift 2
      ;;
    --consolidate)
      CONSOLIDATE=1
      shift
      ;;
    --depth)
      [[ -z "${2:-}" ]] && { echo "Error: --depth requires a value" >&2; usage 1; }
      DEPTH="$2"
      shift 2
      ;;
    --verbose)
      # Backward compat: --verbose used to enable streaming. Now streaming
      # is the default; --verbose is a no-op for users who still pass it.
      shift
      ;;
    --no-stream)
      NO_STREAM=1
      shift
      ;;
    --no-critic)
      NO_CRITIC=1
      shift
      ;;
    --no-verify-citations)
      NO_VERIFY_CITATIONS=1
      shift
      ;;
    --help)
      usage
      ;;
    -*)
      echo "Error: Unknown option $1" >&2
      usage 1
      ;;
    *)
      if [[ -z "$PROJECT_ID" ]]; then
        PROJECT_ID="$1"
      else
        echo "Error: Unexpected argument $1" >&2
        usage 1
      fi
      shift
      ;;
  esac
done

# --- Validate --type ---
if [[ "$REVIEW_TYPE" != "plan" && "$REVIEW_TYPE" != "project" && "$REVIEW_TYPE" != "paper" ]]; then
  echo "Error: --type must be plan|project|paper, got '$REVIEW_TYPE'" >&2
  exit 1
fi

# --- Validate --reviewer ---
if [[ "$REVIEWER" != "claude" && "$REVIEWER" != "codex" && "$REVIEWER" != "claude,codex" ]]; then
  echo "Error: --reviewer must be claude|codex|claude,codex, got '$REVIEWER'" >&2
  exit 1
fi

# --- Validate --depth ---
if [[ "$DEPTH" != "quick" && "$DEPTH" != "standard" && "$DEPTH" != "deep" ]]; then
  echo "Error: --depth must be quick|standard|deep, got '$DEPTH'" >&2
  exit 1
fi

# --- Resolve BERIL_ROOT ---
# Priority: --beril-root flag → $BERIL_ROOT env → derive from script path
# (since this script lives at <BERIL>/.claude/skills/beril-adversarial/tools/).
if [[ -n "$BERIL_ROOT_OVERRIDE" ]]; then
  BERIL_ROOT="$(cd "$BERIL_ROOT_OVERRIDE" && pwd)"
elif [[ -n "${BERIL_ROOT:-}" ]]; then
  BERIL_ROOT="$(cd "$BERIL_ROOT" && pwd)"
else
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
  # tools/ → beril-adversarial/ → skills/ → .claude/ → BERIL_ROOT
  # Use pwd -P to resolve symlinks; protects against symlink-traversal
  # if the skill dir is symlinked.
  BERIL_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd -P)"
fi

# Sanity-check the resolution.
if [[ ! -d "$BERIL_ROOT/.claude/skills" ]]; then
  echo "Error: resolved BERIL_ROOT=$BERIL_ROOT does not contain .claude/skills/" >&2
  echo "Pass --beril-root explicitly or set BERIL_ROOT env var." >&2
  exit 1
fi

SKILL_DIR="$BERIL_ROOT/.claude/skills/beril-adversarial"
PROMPTS_DIR="$SKILL_DIR/prompts"
STATE_DIR="$SKILL_DIR/state"

if [[ ! -d "$PROMPTS_DIR" ]]; then
  echo "Error: prompts directory missing at $PROMPTS_DIR" >&2
  echo "Run 'beril-adversarial install-skill $BERIL_ROOT' first." >&2
  exit 1
fi

# Ensure state/ exists (for learned-patterns.md).
mkdir -p "$STATE_DIR"

# --- Resolve PROJECT_ID ---
if [[ -z "$PROJECT_ID" ]]; then
  # Auto-detect from cwd if inside projects/<id>/...
  CWD="$(pwd)"
  if [[ "$CWD" == "$BERIL_ROOT/projects/"* ]]; then
    REL="${CWD#"$BERIL_ROOT/projects/"}"
    PROJECT_ID="${REL%%/*}"
  else
    echo "Error: project_id is required (or cd into projects/<id>/)" >&2
    usage 1
  fi
fi

PROJECT_DIR="$BERIL_ROOT/projects/$PROJECT_ID"
if [[ ! -d "$PROJECT_DIR" ]]; then
  echo "Error: project directory not found: $PROJECT_DIR" >&2
  exit 1
fi

# Change cwd to BERIL_ROOT for consistent relative paths in prompts.
cd "$BERIL_ROOT"

# ==============================================================================
# Helpers
# ==============================================================================

# Pick the next available numbered filename for a given prefix+dir.
# Usage: next_numbered_file <dir> <prefix>
#   -> echoes the path of the next available file (race-safe via noclobber)
#
# The race-safety story: walk up from N=1 until we find a non-existent
# slot, then atomically claim it via `set -C` (noclobber). If two
# concurrent invocations both pick the same N, the first to atomically
# claim wins; the second gets EEXIST and falls through to N+1.
next_numbered_file() {
  local dir="$1"
  local prefix="$2"
  local n=1
  while true; do
    local target="$dir/${prefix}_${n}.md"
    if [[ -f "$target" ]]; then
      n=$((n + 1))
      continue
    fi
    # Atomically claim via noclobber. Fails (returns nonzero) if
    # another process created the file between the -f test and now.
    if (set -C; : > "$target") 2>/dev/null; then
      echo "$target"
      return 0
    fi
    # Lost the race; try next number.
    n=$((n + 1))
    # Hard cap to prevent infinite loops if the directory is somehow
    # write-protected.
    if [[ $n -gt 9999 ]]; then
      echo "Error: cannot claim a numbered file under $dir/${prefix}_*" >&2
      return 1
    fi
  done
}

# Write a placeholder into a file to claim it race-safely.
# Usage: claim_file <path> <reviewer_label> <model>
claim_file() {
  local path="$1"
  local label="$2"
  local model="$3"
  echo "<!-- Review in progress by ${label} (${model}) — started $(date -u +%Y-%m-%dT%H:%M:%SZ) -->" > "$path"
}

# Invoke a claude subprocess with a system prompt file and a review prompt.
# Usage:
#   invoke_claude <sys_prompt_file> <review_prompt> <model>
#                 [expected_write_path] [metadata_path]
#
# Default behavior: pipe claude through stream_progress.py for programmatic
# Write-tool verification + end-of-run summary (tokens, cost, tool counts).
# Falls back to direct claude invocation if NO_STREAM=1, python3 missing,
# or parser script missing.
#
# metadata_path: where the parser writes per-call metadata JSON. If empty,
# defaults to "${expected_write_path}.metadata.json". The shell pipeline
# aggregates all per-call metadata at end of run.
invoke_claude() {
  local sys_prompt_file="$1"
  local review_prompt="$2"
  local model="$3"
  local expected_write_path="${4:-}"
  local metadata_path="${5:-}"
  if [[ -z "$metadata_path" && -n "$expected_write_path" ]]; then
    metadata_path="${expected_write_path}.metadata.json"
  fi

  if ! command -v claude &>/dev/null; then
    echo "Error: 'claude' CLI is not installed or not in PATH" >&2
    return 1
  fi

  local sys_prompt
  sys_prompt="$(cat "$sys_prompt_file")"

  # Decide whether to use the parser-pipe path
  local use_parser=1
  if [[ "$NO_STREAM" == "1" ]]; then
    use_parser=0
  elif [[ -z "$expected_write_path" ]]; then
    # No expected path → no Write verification value; skip parser
    use_parser=0
  elif ! command -v python3 &>/dev/null; then
    echo "Warning: python3 not on PATH; running without stream parser" >&2
    use_parser=0
  elif [[ ! -f "$SKILL_DIR/tools/stream_progress.py" ]]; then
    echo "Warning: parser script missing; running without stream parser" >&2
    use_parser=0
  fi

  if [[ "$use_parser" == "1" ]]; then
    local log_file="${expected_write_path}.stream.log"
    set -o pipefail
    CLAUDECODE= claude -p \
      --model "$model" \
      --system-prompt "$sys_prompt" \
      --allowedTools "$CLAUDE_TOOLS" \
      --dangerously-skip-permissions \
      --output-format stream-json \
      --verbose \
      "$review_prompt" \
      < /dev/null \
      | python3 "$SKILL_DIR/tools/stream_progress.py" \
          --expected-write-path "$expected_write_path" \
          --log "$log_file" \
          --model "$model" \
          --metadata-out "$metadata_path" \
          > /dev/null
    local parser_rc=$?
    # On success: remove the stream log (keep on failure for diagnostics).
    if [[ $parser_rc -eq 0 ]]; then
      rm -f "$log_file"
    fi
    return $parser_rc
  else
    CLAUDECODE= claude -p \
      --model "$model" \
      --system-prompt "$sys_prompt" \
      --allowedTools "$CLAUDE_TOOLS" \
      --dangerously-skip-permissions \
      "$review_prompt" \
      < /dev/null
  fi
}

# Invoke a codex subprocess.
# Usage: invoke_codex <system_prompt_file> <review_prompt> <model>
invoke_codex() {
  local sys_prompt_file="$1"
  local review_prompt="$2"
  local model="$3"

  if ! command -v codex &>/dev/null; then
    echo "Error: 'codex' CLI is not installed or not in PATH" >&2
    return 1
  fi

  local sys_prompt
  sys_prompt="$(cat "$sys_prompt_file")"
  local full_prompt="${sys_prompt}

---

${review_prompt}"

  codex exec \
    --model "$model" \
    --sandbox workspace-write \
    --ephemeral \
    "$full_prompt" \
    < /dev/null
}

# Invoke claude with retry on detected silent-failure (Write not invoked).
# Args:
#   $1  system_prompt_file
#   $2  base_review_prompt   (will be wrapped with retry escalation on attempt > 1)
#   $3  model
#   $4  expected_write_path  (passed to parser for programmatic Write verification)
#   $5  label                (for diagnostics, e.g., "Claude reviewer", "fusion step")
#   $6  metadata_path        (optional; where parser writes per-call metadata JSON)
#
# Returns 0 on success, 1 on hard failure (after MAX_ATTEMPTS or non-retryable error).
# Each attempt re-claims the placeholder; on success the placeholder has been
# overwritten by the actual review via the Write tool.
#
# Retry only fires on parser exit-code 2 (Write tool never invoked), which
# is the stochastic failure mode worth retrying. Exit-code 3 (Write on wrong
# path) and other non-zero codes are non-retryable.
invoke_claude_with_retry() {
  local sys_prompt_file="$1"
  local base_prompt="$2"
  local model="$3"
  local expected_path="$4"
  local label="${5:-reviewer}"
  local metadata_path="${6:-}"

  local MAX_ATTEMPTS=3
  local attempt=1
  local attempt_prompt rc

  while [[ $attempt -le $MAX_ATTEMPTS ]]; do
    if [[ $attempt -gt 1 ]]; then
      echo "Retry $attempt/$MAX_ATTEMPTS for $label (previous attempt did not invoke Write)" >&2
      attempt_prompt="ATTEMPT $attempt OF $MAX_ATTEMPTS — the previous attempt produced \
output but did not call the Write tool. The review was lost. THIS \
ATTEMPT MUST CALL THE Write TOOL. Do not produce the review as a chat \
response under any circumstance. Invoke Write with the full markdown.

${base_prompt}"
    else
      attempt_prompt="$base_prompt"
    fi

    # Re-claim placeholder (file may have been deleted on prior attempt).
    claim_file "$expected_path" "$label" "$model"

    invoke_claude "$sys_prompt_file" "$attempt_prompt" "$model" \
        "$expected_path" "$metadata_path"
    rc=$?

    if [[ $rc -eq 0 ]]; then
      return 0
    elif [[ $rc -eq 2 ]]; then
      # Silent-failure — retry
      rm -f "$expected_path"
      attempt=$((attempt + 1))
    elif [[ $rc -eq 3 ]]; then
      echo "Error: $label invoked Write on the wrong path (not retryable)" >&2
      rm -f "$expected_path"
      return 1
    else
      echo "Error: $label failed (exit $rc)" >&2
      rm -f "$expected_path"
      return 1
    fi
  done

  echo "Error: $label failed to invoke Write across $MAX_ATTEMPTS attempts." >&2
  echo "  Stream log preserved at: ${expected_path}.stream.log (last attempt only)." >&2
  echo "  This is a known stochastic failure mode of claude -p with rich tool grants." >&2
  return 1
}

# Run the compliance critic against a completed review file.
# Args:
#   $1  review_file_path  (absolute)
#   $2  model
#   $3  audit_output_path (where the critic writes PASS or VIOLATIONS_FOUND)
#   $4  metadata_path     (optional; per-call metadata JSON for aggregation)
# Returns 0 if critic ran (regardless of outcome), nonzero on hard error.
invoke_critic() {
  local review_file="$1"
  local model="$2"
  local audit_file="$3"
  local metadata_path="${4:-}"

  local critic_sys="$PROMPTS_DIR/compliance_critic.v1.md"
  if [[ ! -f "$critic_sys" ]]; then
    echo "Warning: compliance critic prompt missing at $critic_sys; skipping" >&2
    return 1
  fi

  local critic_prompt="Audit the adversarial review at this absolute path:
${review_file}

Read it, check it against the format/discipline rules in your system \
prompt, and write your audit verdict to this absolute path:
${audit_file}

If the review fully complies with all rules, write only the line:
  STATUS: PASS

If violations exist, write the structured VIOLATIONS_FOUND report \
described in your system prompt. Do NOT modify the review itself; \
only write your audit verdict to the audit_file path.

Use the Write tool with the absolute audit_file path above."

  echo "Running compliance critic..." >&2
  invoke_claude_with_retry \
    "$critic_sys" "$critic_prompt" "$model" \
    "$audit_file" "compliance critic" "$metadata_path"
}

# Run a fix pass: re-invoke the original reviewer with the critic's
# violation list and a corrected version of the review.
#
# IMPORTANT — this function MUST inline the original review content into
# the fix prompt. The retry helper's claim_file step truncates the
# review_file to a placeholder BEFORE the fix-pass model runs, which
# means the model cannot recover the original content from disk. We
# capture the content first, inline it into the prompt, and the model
# writes a corrected version from its prompt context.
#
# We also backup the original to .pre-fix.bak so finalize_review can
# restore it if the fix pass produces invalid/truncated output.
#
# Args:
#   $1  review_file_path  (absolute, the file to fix)
#   $2  audit_file_path   (absolute, contains the violation list)
#   $3  system_prompt_file (the original system prompt — we reuse it
#                            so the model knows what compliant output
#                            looks like)
#   $4  model
#   $5  metadata_path     (optional; per-call metadata JSON for aggregation)
invoke_fix_pass() {
  local review_file="$1"
  local audit_file="$2"
  local sys_prompt_file="$3"
  local model="$4"
  local metadata_path="${5:-}"

  if [[ ! -s "$review_file" ]]; then
    echo "Error: cannot run fix pass on empty/missing review file: $review_file" >&2
    return 1
  fi

  # Capture original BEFORE invoke_claude_with_retry's claim_file call
  # destroys it. Inline it into the prompt so the model can produce a
  # corrected version from prompt context (it cannot read from disk —
  # the disk version will be a placeholder by the time the model runs).
  local original_content
  original_content="$(cat "$review_file")"

  local violations
  violations="$(cat "$audit_file" 2>/dev/null || echo '(audit file unreadable)')"

  local fix_prompt="The adversarial review below failed compliance review. \
Your job is to produce a corrected version with the listed violations \
fixed, preserving all substantive content verbatim.

ORIGINAL REVIEW CONTENT (verbatim — preserve all substantive content \
including claims, severity assessments, hypothesis vetting, biological \
claims, data support, prior-review handling):

\`\`\`markdown
${original_content}
\`\`\`

VIOLATIONS FOUND BY THE COMPLIANCE CRITIC:

${violations}

YOUR JOB: write a corrected version of the review to this absolute \
path via the Write tool:
${review_file}

Rules for the fix:
- Preserve ALL substantive content from the original above. Do NOT \
  drop sections, do NOT summarize, do NOT rewrite for style. Only \
  change what the listed violations require.
- The corrected file should have a similar length to the original \
  (within ~10-20%). If you find yourself producing a much shorter \
  file, you are dropping content you should be preserving.
- For 'Sources/References at end' violations: remove the trailing \
  orphan list section, but keep all inline citations and the \
  surrounding text intact.
- For 'vague citation' violations: either upgrade to the full 9-field \
  block format (verify via WebSearch first if needed), or remove the \
  vague reference and the sentence that depended on it. Do NOT just \
  delete a citation while leaving a half-sentence behind.
- For 'vague missing-citation' violations: either provide the strict \
  citation block (verify the paper exists via WebSearch), or rewrite \
  the suggestion to be method/concept-based instead of paper-based.

The corrected review is delivered ONLY by invoking the Write tool with \
the absolute path above. Producing the corrected review as a chat \
response means it is lost. Before responding, verify Write was \
actually invoked in this turn."

  echo "Running compliance fix pass..." >&2
  invoke_claude_with_retry \
    "$sys_prompt_file" "$fix_prompt" "$model" \
    "$review_file" "compliance fix pass" "$metadata_path"
}

# Compute the forensic-artifacts directory for a review file.
# Usage: debug_dir_for <review_file_path>
#   echoes <project>/.adversarial-debug/<review-basename-without-ext>/
# Does not create the directory; caller decides.
debug_dir_for() {
  local review_file="$1"
  local dir base
  dir="$(dirname "$review_file")"
  base="$(basename "$review_file" .md)"
  echo "$dir/.adversarial-debug/$base"
}

# Finalize a review: run compliance critic + fix pass if violations,
# re-critic to confirm, then aggregate per-call metadata into a Run Metadata
# section appended to the review file.
#
# Args:
#   $1  output_file      (the canonical review file to audit)
#   $2  sys_prompt_file  (the original review system prompt — for fix pass)
#   $3  model
#
# Reads/mutates script-level globals:
#   META_FILES   array of per-call metadata JSON paths (caller appends to this)
#   CALL_LABELS  array of human labels matching META_FILES (caller appends)
#
# Side effects:
#   - May append additional metadata files / labels for critic, fix, re-critic
#   - On success, calls aggregate_metadata.py to inject Run Metadata section
#   - Cleans up metadata JSON files after aggregation
#
# Returns 0 on success (review may still have unfixable violations), nonzero
# only on hard error in the helper itself.
finalize_review() {
  local output_file="$1"
  local sys_prompt_file="$2"
  local model="$3"

  # Forensic artifacts (audit logs, fix attempts, pre-fix backup) live in
  # a debug subdirectory so they don't litter the project root. We wipe
  # this subdir at start of each finalize_review call: only the most
  # recent run's forensics ever persist (auto-prune).
  local debug_dir
  debug_dir="$(debug_dir_for "$output_file")"
  rm -rf "$debug_dir"
  mkdir -p "$debug_dir"

  # Compliance critic + fix pass (skipped if NO_CRITIC=1 or codex-only path)
  if [[ "$NO_CRITIC" != "1" ]]; then
    local audit_file="$debug_dir/audit.md"
    local meta_critic="${output_file}.metadata.critic.json"
    if invoke_critic "$output_file" "$model" "$audit_file" "$meta_critic"; then
      META_FILES+=( "$meta_critic" )
      CALL_LABELS+=( "critic" )

      if grep -q "^STATUS: PASS" "$audit_file" 2>/dev/null; then
        echo "Compliance critic: PASS" >&2
        rm -f "$audit_file"
      elif grep -q "^STATUS: VIOLATIONS_FOUND" "$audit_file" 2>/dev/null; then
        local v_count
        v_count=$(grep -c "^### " "$audit_file" 2>/dev/null || echo "?")
        echo "Compliance critic: ${v_count} violation(s) — running fix pass..." >&2
        local meta_fix="${output_file}.metadata.fix.json"

        # Backup the original review BEFORE fix pass. The retry helper's
        # claim_file step truncates output_file to a placeholder before the
        # fix-pass model runs; if the model produces invalid/corrupted output
        # (or the helper fails entirely after retries), we lose the original.
        # The pre-fix.bak (in debug_dir) lets us restore on any failure mode.
        local fix_backup="$debug_dir/pre-fix.bak"
        local original_lines
        cp "$output_file" "$fix_backup"
        original_lines=$(wc -l < "$fix_backup")

        local fix_rc=0
        invoke_fix_pass "$output_file" "$audit_file" "$sys_prompt_file" \
                        "$model" "$meta_fix" || fix_rc=$?

        # Validate the post-fix file: must have YAML frontmatter and at
        # least 60% of the original line count (catches drastic truncation
        # like the model writing a STATUS stub instead of a corrected
        # review).
        local fix_valid=1
        local post_fix_lines=0
        if [[ -f "$output_file" ]]; then
          post_fix_lines=$(wc -l < "$output_file")
        fi
        if [[ $fix_rc -ne 0 ]]; then
          fix_valid=0
        elif ! validate_output "$output_file" 2>/dev/null; then
          fix_valid=0
        elif [[ $original_lines -gt 0 ]] \
             && (( post_fix_lines * 100 < original_lines * 60 )); then
          fix_valid=0
          echo "Warning: post-fix review is ${post_fix_lines} lines vs ${original_lines} original (drastic truncation)" >&2
        fi

        if [[ $fix_valid -eq 1 ]]; then
          # Fix landed. Discard backup, record metadata, run re-critic.
          rm -f "$fix_backup"
          META_FILES+=( "$meta_fix" )
          CALL_LABELS+=( "fix" )

          local audit_file2="$debug_dir/audit2.md"
          local meta_recritic="${output_file}.metadata.recritic.json"
          if invoke_critic "$output_file" "$model" "$audit_file2" "$meta_recritic"; then
            META_FILES+=( "$meta_recritic" )
            CALL_LABELS+=( "re-critic" )
            if grep -q "^STATUS: PASS" "$audit_file2" 2>/dev/null; then
              echo "Compliance critic (post-fix): PASS" >&2
              rm -f "$audit_file" "$audit_file2"
            else
              local r_count
              r_count=$(grep -c "^### " "$audit_file2" 2>/dev/null || echo "?")
              echo "Compliance critic (post-fix): ${r_count} violation(s) remain. Audit at $audit_file2" >&2
              rm -f "$audit_file"
            fi
          else
            # Re-critic invocation hard-failed (subprocess error, not just
            # a violations result). Don't leak the audit files — we have
            # no signal on whether the fix landed cleanly, but the user's
            # review is at least intact.
            echo "Warning: re-critic invocation failed; cannot verify fix landed" >&2
            rm -f "$audit_file" "$audit_file2"
          fi
        else
          # Fix pass produced invalid output. Preserve the corrupt attempt
          # for inspection, then restore the original review from backup.
          local fix_attempt="$debug_dir/fix-attempt.md"
          if [[ -f "$output_file" ]]; then
            mv "$output_file" "$fix_attempt"
          fi
          mv "$fix_backup" "$output_file"
          # Don't record metadata for a failed fix — the fix call's tokens
          # were spent but the work was discarded; aggregating it would
          # mislead users into thinking the fix landed.
          rm -f "$meta_fix"
          echo "Error: fix pass produced invalid output; original review restored." >&2
          echo "  Corrupted fix attempt preserved at: $fix_attempt" >&2
          echo "  Original violations remain. Critic audit at: $audit_file" >&2
        fi
      else
        echo "Compliance critic: unexpected output. Audit at $audit_file" >&2
      fi
    else
      echo "Warning: compliance critic invocation failed; skipping audit" >&2
      rm -f "$audit_file"
    fi
  fi

  # Citation verification gate. Programmatically verifies every 9-field
  # citation block against Crossref (DOI) and NCBI PubMed (PMID).
  # Fabricated citations are marked inline in the review and listed in a
  # Citation Verification section appended to the review file.
  #
  # The gate uses HTTP calls to free registries (no LLM tokens), so cost
  # is negligible. We do not aggregate this into the cumulative Run
  # Metadata token cost — it's reported as a separate end-of-run line.
  if [[ "$NO_VERIFY_CITATIONS" != "1" \
        && -f "$SKILL_DIR/tools/verify_citations.py" \
        && -f "$output_file" ]] \
     && command -v python3 &>/dev/null; then
    local verify_meta="$debug_dir/citation_verification.json"
    mkdir -p "$debug_dir"
    local verify_rc=0
    python3 "$SKILL_DIR/tools/verify_citations.py" "$output_file" \
        --metadata-out "$verify_meta" 2>&1 || verify_rc=$?
    case $verify_rc in
      0)
        # Pass (or pass with caveats — verifier already logged details)
        rm -f "$verify_meta"
        ;;
      2)
        echo "" >&2
        echo "================================================================" >&2
        echo "CITATION VERIFICATION: FABRICATIONS FOUND" >&2
        echo "================================================================" >&2
        echo "  The review contains one or more fabricated citations." >&2
        echo "  Inline warnings inserted; full report appended to:" >&2
        echo "    $output_file" >&2
        echo "  Look for the 'Citation Verification' section." >&2
        echo "================================================================" >&2
        echo "" >&2
        rm -f "$verify_meta"
        ;;
      *)
        echo "Warning: citation verifier failed (exit $verify_rc); review unchanged" >&2
        rm -f "$verify_meta"
        ;;
    esac
  fi

  # If the debug dir is empty (clean run, no forensics preserved), remove
  # it entirely so the project root has zero adversarial-skill residue.
  # Also try to remove the parent .adversarial-debug/ if it's now empty
  # (e.g., this was the only review in the project, or all peer reviews
  # are also clean).
  rmdir "$debug_dir" 2>/dev/null || true
  rmdir "$(dirname "$debug_dir")" 2>/dev/null || true

  # Aggregate per-call metadata into one cumulative Run Metadata section
  if [[ ${#META_FILES[@]} -gt 0 && -f "$SKILL_DIR/tools/aggregate_metadata.py" ]]; then
    python3 "$SKILL_DIR/tools/aggregate_metadata.py" \
        --review-file "$output_file" \
        --metadata-files "${META_FILES[@]}" \
        --call-labels "${CALL_LABELS[@]}" \
        2>&1 || echo "Warning: metadata aggregation failed; review file untouched" >&2
    rm -f "${META_FILES[@]}"
  fi
}

# Validate that a written output file has real content (frontmatter + body).
# Usage: validate_output <path>
validate_output() {
  local path="$1"
  if [[ ! -s "$path" ]]; then
    echo "Error: output file is empty: $path" >&2
    return 1
  fi
  if ! grep -q '^---' "$path"; then
    # Might be just the placeholder
    if grep -q '<!-- Review in progress' "$path" && [[ $(wc -l < "$path") -le 2 ]]; then
      echo "Error: reviewer did not write to $path (placeholder remains)" >&2
      return 1
    fi
    echo "Error: output file missing YAML frontmatter: $path" >&2
    return 1
  fi
  return 0
}

# ==============================================================================
# Consolidation path
# ==============================================================================
if [[ $CONSOLIDATE -eq 1 ]]; then
  case "$REVIEW_TYPE" in
    plan)
      NUMBERED_GLOB="$PROJECT_DIR/ADVERSARIAL_PLAN_REVIEW_*.md"
      CANONICAL_OUT="$PROJECT_DIR/ADVERSARIAL_PLAN_REVIEW.md"
      CURRENT_ARTIFACT="$PROJECT_DIR/RESEARCH_PLAN.md"
      ;;
    project)
      NUMBERED_GLOB="$PROJECT_DIR/ADVERSARIAL_REVIEW_*.md"
      CANONICAL_OUT="$PROJECT_DIR/ADVERSARIAL_REVIEW.md"
      CURRENT_ARTIFACT="$PROJECT_DIR/REPORT.md"
      ;;
    paper)
      NUMBERED_GLOB="$PROJECT_DIR/papers/draft*-review.md"
      CANONICAL_OUT="$PROJECT_DIR/papers/FINAL_REVIEW.md"
      # current_artifact: highest-numbered draft
      LATEST_DRAFT="$(ls -1 "$PROJECT_DIR/papers/"draft*.md 2>/dev/null \
        | grep -E 'draft[0-9]+\.md$' \
        | sort -V \
        | tail -n 1 || true)"
      if [[ -z "$LATEST_DRAFT" ]]; then
        echo "Error: no papers/draft{N}.md found for --type paper consolidation" >&2
        exit 1
      fi
      CURRENT_ARTIFACT="$LATEST_DRAFT"
      ;;
  esac

  # Enumerate numbered review files (filename globbing; skip canonical itself).
  # shellcheck disable=SC2206
  NUMBERED_FILES=( $NUMBERED_GLOB )
  if [[ ${#NUMBERED_FILES[@]} -eq 0 || ! -f "${NUMBERED_FILES[0]}" ]]; then
    echo "Error: no numbered reviews found matching $NUMBERED_GLOB" >&2
    exit 1
  fi

  # Exclude canonical if it was matched by the glob (e.g., papers/FINAL_REVIEW.md
  # wouldn't match, but guard anyway).
  FILTERED=()
  for f in "${NUMBERED_FILES[@]}"; do
    if [[ "$f" != "$CANONICAL_OUT" ]]; then
      FILTERED+=( "$f" )
    fi
  done
  NUMBERED_FILES=( "${FILTERED[@]}" )

  if [[ ${#NUMBERED_FILES[@]} -eq 0 ]]; then
    echo "Error: no numbered reviews to consolidate" >&2
    exit 1
  fi

  # Build the review prompt listing all numbered files + current artifact.
  # All paths are ABSOLUTE — relative paths cause the model to resolve
  # against unexpected directories and the file lands in the wrong place.
  NUMBERED_LIST=""
  for f in "${NUMBERED_FILES[@]}"; do
    NUMBERED_LIST+="  - ${f}
"
  done

  CONSOLIDATE_PROMPT="Consolidate the following numbered adversarial reviews \
of project '${PROJECT_ID}' (type: ${REVIEW_TYPE}) into a canonical review \
with revision history.

Numbered review files — ABSOLUTE paths, read ALL of them in order:
${NUMBERED_LIST}
Current artifact for disposition check (absolute path): ${CURRENT_ARTIFACT}

YOUR JOB: produce the consolidated review markdown and save it via the \
Write tool.

Target path (absolute — use exactly this path): ${CANONICAL_OUT}

The consolidated review is delivered ONLY by invoking Write with the \
ABSOLUTE path above. Producing it as a chat response means it is \
lost. Before responding, verify Write was actually invoked in this \
turn — if you cannot point to a Write call you made, invoke it now.

Preserve per-round dated provenance. Cite each issue's source round-file \
with model and date inline in square brackets. Follow the consolidation \
protocol in the system prompt exactly."

  SYSTEM_PROMPT_FILE="$PROMPTS_DIR/consolidation.v1.md"
  if [[ ! -f "$SYSTEM_PROMPT_FILE" ]]; then
    echo "Error: consolidation system prompt not found: $SYSTEM_PROMPT_FILE" >&2
    exit 1
  fi

  # Default to claude for consolidation unless --reviewer codex explicit.
  CONSOL_REVIEWER="$REVIEWER"
  if [[ "$CONSOL_REVIEWER" == "claude,codex" ]]; then
    # Fusion on consolidation is not supported; prefer claude for single-model synthesis.
    echo "Note: --reviewer claude,codex is ignored during --consolidate; using claude." >&2
    CONSOL_REVIEWER="claude"
  fi
  [[ -z "$MODEL" ]] && {
    if [[ "$CONSOL_REVIEWER" == "claude" ]]; then
      MODEL="$CLAUDE_DEFAULT_MODEL"
    else
      MODEL="$CODEX_DEFAULT_MODEL"
    fi
  }

  echo "Consolidating ${#NUMBERED_FILES[@]} review(s) → ${CANONICAL_OUT}"

  # Per-call metadata aggregator: track all claude calls made during
  # consolidation (synthesis, optional critic, optional fix pass, re-critic).
  META_FILES=()
  CALL_LABELS=()

  if [[ "$CONSOL_REVIEWER" == "claude" ]]; then
    META_CONSOL="${CANONICAL_OUT}.metadata.consolidation.json"
    invoke_claude_with_retry \
      "$SYSTEM_PROMPT_FILE" "$CONSOLIDATE_PROMPT" "$MODEL" \
      "$CANONICAL_OUT" "consolidation step" \
      "$META_CONSOL" \
      || exit 1
    META_FILES+=( "$META_CONSOL" )
    CALL_LABELS+=( "consolidation" )
  else
    claim_file "$CANONICAL_OUT" "Consolidator" "$MODEL"
    invoke_codex "$SYSTEM_PROMPT_FILE" "$CONSOLIDATE_PROMPT" "$MODEL" || {
      echo "Error: consolidation failed" >&2
      rm -f "$CANONICAL_OUT"
      exit 1
    }
  fi

  # Compliance critic + fix pass + cumulative metadata aggregation.
  # Skip for codex-only path (no programmatic Write detection on codex).
  if [[ "$CONSOL_REVIEWER" == "claude" ]]; then
    finalize_review "$CANONICAL_OUT" "$SYSTEM_PROMPT_FILE" "$MODEL"
  fi

  if ! validate_output "$CANONICAL_OUT"; then
    rm -f "$CANONICAL_OUT"
    exit 1
  fi

  echo "Consolidated review written to: ${CANONICAL_OUT}"
  exit 0
fi

# ==============================================================================
# Standard review path
# ==============================================================================

# --- Resolve paper draft (if --type paper) ---
PAPER_DRAFT=""
if [[ "$REVIEW_TYPE" == "paper" ]]; then
  if [[ ! -d "$PROJECT_DIR/papers" ]]; then
    echo "Error: --type paper requires $PROJECT_DIR/papers/ directory" >&2
    exit 1
  fi
  PAPER_DRAFT="$(ls -1 "$PROJECT_DIR/papers/"draft*.md 2>/dev/null \
    | grep -E 'draft[0-9]+\.md$' \
    | sort -V \
    | tail -n 1 || true)"
  if [[ -z "$PAPER_DRAFT" ]]; then
    echo "Error: no papers/draft{N}.md found for --type paper" >&2
    exit 1
  fi
  # Extract the draft number for output filename.
  DRAFT_BASENAME="$(basename "$PAPER_DRAFT")"
  DRAFT_NUMBER="${DRAFT_BASENAME#draft}"
  DRAFT_NUMBER="${DRAFT_NUMBER%.md}"
fi

# --- Resolve output path ---
if [[ -z "$OUTPUT_FILE" ]]; then
  case "$REVIEW_TYPE" in
    plan)
      OUTPUT_FILE="$(next_numbered_file "$PROJECT_DIR" "ADVERSARIAL_PLAN_REVIEW")"
      ;;
    project)
      OUTPUT_FILE="$(next_numbered_file "$PROJECT_DIR" "ADVERSARIAL_REVIEW")"
      ;;
    paper)
      OUTPUT_FILE="$PROJECT_DIR/papers/draft${DRAFT_NUMBER}-review.md"
      # For paper: if already exists, auto-version as draftN-review_v2.md, _v3.md, ...
      if [[ -f "$OUTPUT_FILE" ]]; then
        v=2
        while [[ -f "$PROJECT_DIR/papers/draft${DRAFT_NUMBER}-review_v${v}.md" ]]; do
          v=$((v + 1))
        done
        OUTPUT_FILE="$PROJECT_DIR/papers/draft${DRAFT_NUMBER}-review_v${v}.md"
      fi
      ;;
  esac
fi

# --- Validate OUTPUT_FILE is under PROJECT_DIR ---
# Defense against --output /etc/passwd or similar path-traversal attempts.
# Resolve to absolute paths and confirm OUTPUT_FILE is contained in PROJECT_DIR.
OUTPUT_FILE_ABS="$(cd "$(dirname "$OUTPUT_FILE")" 2>/dev/null && pwd -P)/$(basename "$OUTPUT_FILE")"
PROJECT_DIR_ABS="$(cd "$PROJECT_DIR" && pwd -P)"
if [[ "$OUTPUT_FILE_ABS" != "$PROJECT_DIR_ABS"/* ]]; then
  echo "Error: output path must be under project directory" >&2
  echo "  Resolved output path: $OUTPUT_FILE_ABS" >&2
  echo "  Project directory:    $PROJECT_DIR_ABS" >&2
  exit 1
fi

# --- Load system prompt ---
SYSTEM_PROMPT_FILE="$PROMPTS_DIR/adversarial_${REVIEW_TYPE}.v1.md"
if [[ ! -f "$SYSTEM_PROMPT_FILE" ]]; then
  echo "Error: system prompt not found: $SYSTEM_PROMPT_FILE" >&2
  exit 1
fi
if [[ ! -r "$SYSTEM_PROMPT_FILE" ]]; then
  echo "Error: system prompt not readable (permission denied?): $SYSTEM_PROMPT_FILE" >&2
  exit 1
fi

# --- Build depth instructions ---
case "$DEPTH" in
  quick)
    DEPTH_INSTRUCTIONS="DEPTH MODE: quick (~1-2 minute target).
- SKIP the literature-scan subagent. Use the project's existing
  references.md and your training knowledge only. Do not WebSearch
  for new literature.
- SKIP biological-claim WebSearch verification. Mark such claims
  with status 'not-verified-in-quick-mode' rather than producing
  citations.
- SKIP per-hypothesis structured vetting; produce a single-paragraph
  hypothesis assessment covering the project's main hypothesis or
  framing.
- DO use Tier 1 calculations (closed-form on reported numbers) when
  high-value — those are cheap.
- DO read all canonical artifacts (README, RESEARCH_PLAN, REPORT,
  prior reviews).
- Focus output on the highest-value 3-5 issues. Do not aim for
  comprehensive coverage. A short, sharp review is the goal."
    ;;
  standard)
    DEPTH_INSTRUCTIONS="DEPTH MODE: standard (~5-10 minute target).
This is the default — apply the system prompt's full instructions.
- DO spawn the literature-scan subagent.
- DO verify biological claims via WebSearch with strict citation
  format.
- DO produce per-hypothesis structured vetting.
- DO Tier 1 calculations as warranted.
- Aim for 5-15 substantive issues with precise citations and fixes."
    ;;
  deep)
    DEPTH_INSTRUCTIONS="DEPTH MODE: deep (~15-25 minute target).
- EXPAND the literature-scan subagent: target 30-50 papers including
  citation snowballing on top results. Read full text of top 5-10
  most relevant via PMC where available.
- VERIFY each biological claim against multiple primary sources;
  prefer 2-3 independent confirmations or one strong contradiction.
- EXHAUSTIVE per-hypothesis vetting including implicit hypotheses
  and sub-claims that the report's narrative depends on.
- TIER 1 calculations including sensitivity analyses on key results
  (e.g., recompute with different multiple-testing thresholds, or
  with alternative effect-size definitions).
- SPAWN context-reset subagents liberally for unbiased assessment of
  statistical rigor, hypothesis plausibility, biological-claim
  groups.
- Aim for 15-25 substantive issues. Coverage matters at this depth."
    ;;
esac

# --- Build review prompt ---
case "$REVIEW_TYPE" in
  plan)
    TARGET_DESC="the research plan at projects/${PROJECT_ID}/"
    READ_HINT="Read RESEARCH_PLAN.md, README.md, references.md. Also scan \
docs/pitfalls.md, docs/schemas/, and other projects/*/README.md for prior \
art."
    ;;
  project)
    TARGET_DESC="the project at projects/${PROJECT_ID}/"
    READ_HINT="Read all canonical artifacts (README, RESEARCH_PLAN, REPORT, \
existing REVIEW_*.md and ADVERSARIAL_REVIEW_*.md, notebooks, figures, \
references.md, data/). Also docs/pitfalls.md and \
.claude/skills/beril-adversarial/state/learned-patterns.md if present."
    ;;
  paper)
    TARGET_DESC="the paper draft at ${PAPER_DRAFT#$BERIL_ROOT/}"
    READ_HINT="Read the draft, papers/THROUGHLINE.md, papers/bibliography.bib, \
papers/citation-map.md, and cross-check against projects/${PROJECT_ID}/REPORT.md \
plus figures/. Also .claude/skills/beril-adversarial/state/learned-patterns.md \
if present. Prior paper reviews in papers/draft*-review*.md are context."
    ;;
esac

# ==============================================================================
# Single-reviewer path (claude OR codex)
# ==============================================================================
if [[ "$REVIEWER" != "claude,codex" ]]; then
  [[ -z "$MODEL" ]] && {
    if [[ "$REVIEWER" == "claude" ]]; then
      MODEL="$CLAUDE_DEFAULT_MODEL"
    else
      MODEL="$CODEX_DEFAULT_MODEL"
    fi
  }

  if [[ "$REVIEWER" == "claude" ]]; then
    REVIEWER_LABEL="Claude"
  else
    REVIEWER_LABEL="Codex"
  fi

  REVIEW_PROMPT="Adversarially review ${TARGET_DESC}. ${READ_HINT}

${DEPTH_INSTRUCTIONS}

YOUR JOB: produce the adversarial review markdown and save it via the \
Write tool.

Target path (absolute — use exactly this path, do not rewrite to a \
relative form): ${OUTPUT_FILE}

The review is delivered ONLY by invoking the Write tool with the full \
markdown content as the file_text argument and the ABSOLUTE path above \
as file_path. Producing the review as a chat response without invoking \
Write means the review is lost.

Before producing your final response, verify in your own reasoning that \
the Write tool was actually invoked in this turn with the absolute path \
above. If you cannot point to a Write tool call you made, you have not \
completed the task — invoke Write now.

In the YAML frontmatter, set reviewer to: \
BERIL Adversarial Review (${REVIEWER_LABEL}, ${MODEL}). Set \
prompt_version to: adversarial_${REVIEW_TYPE}.v1 (depth=${DEPTH}). \
Follow the system prompt structure exactly."

  claim_file "$OUTPUT_FILE" "$REVIEWER_LABEL" "$MODEL"

  echo "Invoking ${REVIEWER_LABEL} ${REVIEW_TYPE} reviewer (model: ${MODEL}) for '${PROJECT_ID}'..."
  echo "Output: ${OUTPUT_FILE}"

  # Per-call metadata aggregator: track all claude calls made for this review.
  META_FILES=()
  CALL_LABELS=()
  META_MAIN="${OUTPUT_FILE}.metadata.main.json"

  if [[ "$REVIEWER" == "claude" ]]; then
    invoke_claude_with_retry \
      "$SYSTEM_PROMPT_FILE" \
      "$REVIEW_PROMPT" \
      "$MODEL" \
      "$OUTPUT_FILE" \
      "Claude $REVIEW_TYPE reviewer" \
      "$META_MAIN" \
      || exit 1
    META_FILES+=( "$META_MAIN" )
    CALL_LABELS+=( "main" )
  else
    invoke_codex "$SYSTEM_PROMPT_FILE" "$REVIEW_PROMPT" "$MODEL" || {
      echo "Error: reviewer failed" >&2
      rm -f "$OUTPUT_FILE"
      exit 1
    }
  fi

  # Compliance critic + fix pass + cumulative metadata aggregation.
  # Skip for codex-only path (no programmatic Write detection on codex).
  if [[ "$REVIEWER" == "claude" ]]; then
    finalize_review "$OUTPUT_FILE" "$SYSTEM_PROMPT_FILE" "$MODEL"
  fi

  if ! validate_output "$OUTPUT_FILE"; then
    rm -f "$OUTPUT_FILE"
    exit 1
  fi

  echo "Review written to: $OUTPUT_FILE"
  exit 0
fi

# ==============================================================================
# Fusion path (claude,codex)
# ==============================================================================

# For fusion, determine two intermediate paths + the fused output.
case "$REVIEW_TYPE" in
  plan|project)
    # Derive N from OUTPUT_FILE's numeric suffix.
    N_SUFFIX="$(basename "$OUTPUT_FILE" | sed -E 's/.*_([0-9]+)\.md$/\1/')"
    BASENAME_ROOT="$(basename "$OUTPUT_FILE" .md)"  # e.g. ADVERSARIAL_REVIEW_3
    CLAUDE_INT="$PROJECT_DIR/${BASENAME_ROOT}_claude.md"
    CODEX_INT="$PROJECT_DIR/${BASENAME_ROOT}_codex.md"
    FUSED_OUT="$OUTPUT_FILE"
    ;;
  paper)
    # draft{N}-review.md → draft{N}-review_claude.md, _codex.md
    BASENAME_ROOT="$(basename "$OUTPUT_FILE" .md)"
    CLAUDE_INT="$PROJECT_DIR/papers/${BASENAME_ROOT}_claude.md"
    CODEX_INT="$PROJECT_DIR/papers/${BASENAME_ROOT}_codex.md"
    FUSED_OUT="$OUTPUT_FILE"
    ;;
esac

CLAUDE_MODEL="${MODEL:-$CLAUDE_DEFAULT_MODEL}"
CODEX_MODEL="${MODEL:-$CODEX_DEFAULT_MODEL}"
# If both defaults are needed (user didn't pass --model), use per-reviewer defaults.
if [[ -z "$MODEL" ]]; then
  CLAUDE_MODEL="$CLAUDE_DEFAULT_MODEL"
  CODEX_MODEL="$CODEX_DEFAULT_MODEL"
fi

CLAUDE_REVIEW_PROMPT="Adversarially review ${TARGET_DESC}. ${READ_HINT}

${DEPTH_INSTRUCTIONS}

YOUR JOB: produce the adversarial review markdown and save it via the \
Write tool.

Target path (absolute — use exactly this path): ${CLAUDE_INT}

The review is delivered ONLY by invoking Write with the full markdown \
content and the ABSOLUTE path above as file_path. Producing the review \
as a chat response means it is lost. Before responding, verify Write \
was actually invoked in this turn with that absolute path.

In the YAML frontmatter, set reviewer to: BERIL Adversarial Review \
(Claude, ${CLAUDE_MODEL}). Set prompt_version to: \
adversarial_${REVIEW_TYPE}.v1 (depth=${DEPTH})."

CODEX_REVIEW_PROMPT="Adversarially review ${TARGET_DESC}. ${READ_HINT}

${DEPTH_INSTRUCTIONS}

YOUR JOB: produce the adversarial review markdown and save it to disk.

Target path (absolute): ${CODEX_INT}

The review is delivered ONLY by saving the full markdown to the \
absolute path above. Producing the review as a chat response means \
it is lost.

In the YAML frontmatter, set reviewer to: BERIL Adversarial Review \
(Codex, ${CODEX_MODEL}). Set prompt_version to: \
adversarial_${REVIEW_TYPE}.v1 (depth=${DEPTH})."

claim_file "$CLAUDE_INT" "Claude" "$CLAUDE_MODEL"
claim_file "$CODEX_INT" "Codex" "$CODEX_MODEL"

echo "Fusion review: running Claude (${CLAUDE_MODEL}) and Codex (${CODEX_MODEL}) in parallel..."

# Per-call metadata aggregator: track all claude calls made during the
# fusion pipeline. Codex calls don't generate metadata (no stream parser).
META_FILES=()
CALL_LABELS=()
META_CLAUDE_INT="${CLAUDE_INT}.metadata.json"
META_FUSION="${FUSED_OUT}.metadata.fusion.json"

# Run both in parallel; capture PIDs and rc's.
# Claude side uses retry helper (silent-failure detection + retry).
# Codex side has no programmatic Write detection so no retry.
(
  invoke_claude_with_retry \
    "$SYSTEM_PROMPT_FILE" "$CLAUDE_REVIEW_PROMPT" "$CLAUDE_MODEL" \
    "$CLAUDE_INT" "Claude reviewer (fusion)" "$META_CLAUDE_INT" >/dev/null
) &
CLAUDE_PID=$!

(
  invoke_codex "$SYSTEM_PROMPT_FILE" "$CODEX_REVIEW_PROMPT" "$CODEX_MODEL" >/dev/null
) &
CODEX_PID=$!

CLAUDE_RC=0; CODEX_RC=0
wait "$CLAUDE_PID" || CLAUDE_RC=$?
wait "$CODEX_PID" || CODEX_RC=$?

if [[ $CLAUDE_RC -ne 0 || $CODEX_RC -ne 0 ]]; then
  echo "Error: parallel review step failed (claude_rc=$CLAUDE_RC codex_rc=$CODEX_RC)" >&2
  [[ $CLAUDE_RC -ne 0 ]] && rm -f "$CLAUDE_INT"
  [[ $CODEX_RC -ne 0 ]] && rm -f "$CODEX_INT"
  exit 1
fi

validate_output "$CLAUDE_INT" || { rm -f "$CLAUDE_INT" "$CODEX_INT"; exit 1; }
validate_output "$CODEX_INT" || { rm -f "$CLAUDE_INT" "$CODEX_INT"; exit 1; }

# Both intermediate reviews succeeded; the claude side wrote per-call
# metadata (codex didn't — no parser).
if [[ -f "$META_CLAUDE_INT" ]]; then
  META_FILES+=( "$META_CLAUDE_INT" )
  CALL_LABELS+=( "claude-intermediate" )
fi

echo "Both source reviews complete. Fusing..."

# Fusion step: a third claude call with fusion.v1.md as system prompt.
FUSION_SYS="$PROMPTS_DIR/fusion.v1.md"
if [[ ! -f "$FUSION_SYS" ]]; then
  echo "Error: fusion system prompt not found: $FUSION_SYS" >&2
  exit 1
fi

FUSION_PROMPT="Fuse the two adversarial reviews of ${TARGET_DESC}:
  - Claude review (absolute path): ${CLAUDE_INT}
  - Codex review (absolute path): ${CODEX_INT}

Target path for the fused review (absolute — use exactly this): ${FUSED_OUT}

Save the fused review via the Write tool with the absolute path above. \
Every issue must carry an inline citation with source file, model, and \
date in square brackets as specified in the fusion system prompt. Never \
silently drop an issue."

FUSION_MODEL="${CLAUDE_MODEL}"  # Use claude for fusion step.

invoke_claude_with_retry \
  "$FUSION_SYS" "$FUSION_PROMPT" "$FUSION_MODEL" \
  "$FUSED_OUT" "fusion step" \
  "$META_FUSION" \
  || exit 1
META_FILES+=( "$META_FUSION" )
CALL_LABELS+=( "fusion" )

# Compliance critic + fix pass + cumulative metadata aggregation against
# the fused review. The fused review uses the original review-type system
# prompt for the fix pass (so the fixer knows what compliant output looks
# like for the underlying review type, not for fusion synthesis).
finalize_review "$FUSED_OUT" "$SYSTEM_PROMPT_FILE" "$FUSION_MODEL"

if ! validate_output "$FUSED_OUT"; then
  rm -f "$FUSED_OUT"
  exit 1
fi

echo "Fused review written to: $FUSED_OUT"
echo "Intermediate reviews preserved at:"
echo "  - $CLAUDE_INT"
echo "  - $CODEX_INT"
exit 0
