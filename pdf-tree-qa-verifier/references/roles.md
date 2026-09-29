# Roles and models for a QA review

A QA review has two AI roles plus the human reviewer. The split is the same for every
provider; only the models change.

| Role | Responsibility | Claude Code | OpenAI (Codex) |
|---|---|---|---|
| **Lead** (jefe) | Prepares batches, dispatches reviewers, re-runs `validate_agent_result.py` and `verify_claims.py`, spot-checks CONTRADICTED / SEVERITY / Critical / High rows, registers drafts, consolidates | **Opus** (`.claude/agents/pdf-tree-qa-lead.md`, `model: opus`) | **GPT-6.1-Sol** (`gpt-6.1-sol`) or **GPT-6-Sol** (`gpt-6-sol`); no `gpt-6-terra` is available in this installation |
| **Reviewer** | Reviews one batch visually and writes only its `output/findings_result.json` | **Sonnet** (`.claude/agents/pdf-tree-qa-reviewer.md`, `model: sonnet`) | **GPT-6-Luna** (`gpt-6-luna`), reasoning effort **high** |
| **Human reviewer** | Approves, edits or rejects every draft in Streamlit page 7 and finalizes the version | Assigned in `version_manifest.json` | Same |

## How to run it

**Claude Code**
- Start the lead as the main agent so it runs on Opus:
  `claude --agent pdf-tree-qa-lead` (from the `pdf_tree/` root), or ask the main
  session (on Opus) to "use the pdf-tree-qa-lead agent".
- The lead spawns one `pdf-tree-qa-reviewer` per batch; the reviewer's model is fixed
  to Sonnet in its definition.

**OpenAI (Codex)**
- Run the lead with one of the confirmed model ids and this skill:
  `codex exec --model gpt-6.1-sol -C /Users/j/Documents/Dataclever/pdf_tree \
  'Use $pdf-tree-qa-verifier as the lead: prepare batches, verify drafts, and register \
  proposals; do not approve findings.'`
  `gpt-6-sol` is also available as a Sol lead id. The CLI model catalog has no
  `gpt-6-terra` entry, so Terra cannot be pinned to a GPT-6 id here.
- Run each reviewer on one batch with Luna and high reasoning effort:
  `codex exec --model gpt-6-luna -c model_reasoning_effort=high \
  -C /Users/j/Documents/Dataclever/pdf_tree \
  'Use $pdf-tree-qa-verifier in draft mode for this batch: <batch-directory>. Write only \
  <batch-directory>/output/findings_result.json.'`
  The reviewer also receives the provider-neutral rules from
  `.claude/agents/pdf-tree-qa-reviewer.md`.
- `model_reasoning_effort` is the Codex configuration key; this CLI has no separate
  `--reasoning-effort` flag. The commands above pin the model and the reviewer effort
  for each invocation.

### Optional Codex profiles (proposal only)

This Codex installation uses v2 profiles as separate files named
`$CODEX_HOME/<profile>.config.toml`, selected with `--profile`; it does not use an
inline `[profiles.<name>]` block in `~/.codex/config.toml`. If desired, create these
files manually (this repository change does not apply them):

`~/.codex/pdf-tree-qa-lead.config.toml`:

```toml
model = "gpt-6.1-sol"
```

`~/.codex/pdf-tree-qa-reviewer.config.toml`:

```toml
model = "gpt-6-luna"
model_reasoning_effort = "high"
```

Launch them with `codex exec --profile pdf-tree-qa-lead -C /Users/j/Documents/Dataclever/pdf_tree
...` and `codex exec --profile pdf-tree-qa-reviewer -C /Users/j/Documents/Dataclever/pdf_tree
...`, respectively. `gpt-6-terra` was not present in `codex debug models`, so the lead
profile uses `gpt-6.1-sol`.

## Invariants (all providers)

- AI output is always a draft; only the human reviewer approves.
- Reviewers never edit files outside their batch's `output/`.
- Every draft passes `validate_agent_result.py` and `verify_claims.py` before the lead
  registers it; the lead records the provider/model in the draft's `provider` field.
