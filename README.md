# jev-skill-router

A `muse` plugin that picks relevant skills per user prompt instead of
enabling all skills at startup.

## How it works

1. `scripts/jev-route.py "<prompt>"` prefilters the skill catalog by
   keyword overlap (default backend, no API key).
2. With `--backend jev` and `OPENROUTER_API_KEY` set, it asks the
   `typesafe/jev-1.13` decision model to score the shortlisted
   candidates. The Decisions payload shape is experimental -- dump it
   with `--print-request` and verify against the official TypeSafe docs
   before trusting live scores. Failures fall back to the heuristic.
3. Read only the recommended `SKILL.md` files. Skill activation toggles
   apply from the next run, so per-prompt routing reads files instead
   of flipping flags.

## Use

```
/jev-route review this PR diff
```

## Verify

```bash
python3 plugins/jev-skill-router/scripts/test_router.py
muse plugins validate plugins/jev-skill-router
```
