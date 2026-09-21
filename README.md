# jev-skill-router

Stop paying startup tax for skills you won't use this session.

Measured on a real catalog of 528 `muse` skills:

| Setup | Startup tokens |
|---|---|
| All 528 skills on | ~56,300 |
| 85 curated skills on | ~9,300 |
| Router only | ~104 |

That is a 99.8% cut. Turn everything off, route per prompt, read only
what scores.

Per-prompt cost: the default heuristic backend is free and needs no API
key. A 12-candidate `jev` call measured 1,156 in / 255 out tokens,
about $0.00005, in ~1s.

## How it works

1. `scripts/jev-route.py "<prompt>"` prefilters the skill catalog by
   keyword overlap (default backend, no API key).
2. With `--backend jev` and `OPENROUTER_API_KEY` set, it asks the
   `typesafe/jev-1.13` decision model to score the shortlisted
   candidates. Failures fall back to the heuristic.
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

## Install from the marketplace

```bash
muse plugins marketplace add jev-router https://github.com/zereight/muse-jev-skill-router
muse plugins install jev-skill-router@jev-router
```

## Releasing a new version

`marketplace.json` carries the binary-computed `package_sha256`.
After changing anything under `plugins/jev-skill-router`, reinstall
from the local path, copy the fresh `package_sha256` out of
`~/.local/share/muse/plugins/installed.json` (key `plugins.jev-skill-router`)
into `marketplace.json`, then commit and push. Never hand-compute it.
