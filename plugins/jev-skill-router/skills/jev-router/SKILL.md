---
name: jev-router
description: Pick relevant muse skills for one user prompt. Use when the prompt could match several skills, before enabling more skills, or when startup cost matters. Prefilters the catalog, optionally asks a decision model, then reads only the chosen SKILL.md files.
---

# jev-router

Recommend skills per prompt instead of enabling everything at startup.

## Procedure

1. Run the router (no API key needed for the default backend):
   `python3 scripts/jev-route.py "<user prompt>" --top 5`
2. Read the `SKILL.md` of each recommended skill id only. Do not read the rest.
3. Do not toggle skill activation per prompt: activation changes apply
   from the next run, so routing means reading files, not switching flags.

## Decision model backend

- Default `--backend heuristic` is local keyword overlap. Good enough
  for exact skill names (`plantuml`, `review`, `jira`).
- `--backend jev` POSTs an OpenRouter Decisions request and needs
  `OPENROUTER_API_KEY`. The payload shape is experimental: dump it with
  `--print-request` and check it against the official TypeSafe docs
  before trusting live scores. Any failure falls back to the heuristic.
