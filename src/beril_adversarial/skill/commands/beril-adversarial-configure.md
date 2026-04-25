---
description: Quick environment check for beril-adversarial-skill — verify the claude CLI is installed.
argument-hint: (no arguments)
allowed-tools: Bash, Read
---

# /beril-adversarial-configure

Quick environment check. Run once after `beril-adversarial install-skill .`,
or any time the toolchain changes.

## Step 1 — Run the check

```bash
beril-adversarial configure
```

Expected output if everything is fine:

```
beril-adversarial-skill v0.1.0
  BERIL_ROOT: /path/to/beril
  [OK]      claude — /path/to/claude
  [OK]      codex  — /path/to/codex  (enables --reviewer codex/claude,codex)
```

If `beril-adversarial: command not found`, install via:

```bash
pipx install --force git+https://github.com/ArkinLaboratory/beril-adversarial-skill.git
```

(SSH URL `git+ssh://git@github.com/ArkinLaboratory/beril-adversarial-skill.git`
also works if you have a GitHub SSH key registered.)

If `[MISSING] claude CLI not found`, install Claude Code from
https://docs.claude.com and ensure `claude` is on PATH.

If codex is `[absent]`, that's fine — the skill still works with
`--reviewer claude` (the default). Install the Codex CLI (e.g.,
`brew install --cask codex` on macOS) only if you want
`--reviewer codex` or `--reviewer claude,codex` (multi-model fusion).

## What this command does NOT check

WebSearch availability, MCP server health, model authentication.
Those surface with clear errors at first review run; pre-flighting
them adds latency without preventing real failures.
