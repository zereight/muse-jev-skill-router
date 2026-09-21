#!/usr/bin/env python3
"""Recommend muse skills for one user prompt.

Default backend is a local keyword heuristic and needs no API key.
The optional `jev` backend POSTs an OpenRouter Decisions request; its
payload shape is experimental -- dump it with --print-request and check
it against the official TypeSafe docs before trusting live results.
Any live-call failure falls back to the heuristic.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.request

CATALOG_CMD = ["muse", "skills", "list", "--source", "all", "--json"]
PREFILTER_CAP = 12
JEV_MODEL = os.environ.get("JEV_MODEL", "typesafe/jev-1.13")
DECISIONS_URL = os.environ.get(
    "OPENROUTER_DECISIONS_URL", "https://openrouter.ai/api/alpha/decisions"
)


def tokens(text):
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def load_catalog(path=None):
    if path:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)["skills"]
    proc = subprocess.run(CATALOG_CMD, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError("muse skills list failed: " + proc.stderr.strip())
    return json.loads(proc.stdout)["skills"]


def score_skill(prompt, skill):
    prompt_low = prompt.lower()
    prompt_toks = set(tokens(prompt))
    hay = skill["id"] + " " + (skill.get("description") or "")
    hay_toks = set(tokens(hay))
    overlap = prompt_toks & hay_toks
    substr = sum(1 for t in hay_toks if len(t) > 4 and t in prompt_low)
    return len(overlap) + substr


def prefilter(prompt, skills, cap=PREFILTER_CAP):
    ranked = sorted(skills, key=lambda s: -score_skill(prompt, s))
    return [s for s in ranked if score_skill(prompt, s) > 0][:cap]


def heuristic_rank(prompt, candidates):
    scored = [(score_skill(prompt, s), s) for s in candidates]
    top = max([n for n, _ in scored] or [1])
    return [
        {"id": s["id"], "score": round(n / top, 3), "backend": "heuristic"}
        for n, s in sorted(scored, key=lambda r: -r[0])
    ]


def jev_request(prompt, candidates):
    return {
        "model": JEV_MODEL,
        "state": prompt,
        "questions": [
            {
                "id": c["id"],
                "text": "Is this skill relevant to the state? "
                + (c.get("description") or ""),
                "choices": [{"id": "yes"}, {"id": "no"}],
            }
            for c in candidates
        ],
    }


def jev_rank(prompt, candidates):
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is not set")
    body = json.dumps(jev_request(prompt, candidates)).encode()
    req = urllib.request.Request(
        DECISIONS_URL,
        data=body,
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode())
    decisions = payload.get("decisions") or payload.get("results") or []
    by_id = {}
    for d in decisions:
        qid = d.get("id") or d.get("question_id")
        if qid:
            by_id[qid] = d
    ranked = []
    for c in candidates:
        d = by_id.get(c["id"], {})
        score = d.get("probability", d.get("confidence", d.get("score", 0)))
        ranked.append(
            {"id": c["id"], "score": float(score), "backend": "jev"}
        )
    ranked.sort(key=lambda r: -r["score"])
    return ranked


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt", nargs="?", help="user prompt (or stdin)")
    parser.add_argument("--catalog", default=None, help="cached skills JSON")
    parser.add_argument("--top", type=int, default=5)
    parser.add_argument("--backend", choices=["heuristic", "jev"], default="heuristic")
    parser.add_argument("--print-request", action="store_true")
    args = parser.parse_args(argv)

    prompt = args.prompt or sys.stdin.read().strip()
    if not prompt:
        parser.error("empty prompt")
    skills = load_catalog(args.catalog)
    candidates = prefilter(prompt, skills)
    if args.print_request:
        print(json.dumps(jev_request(prompt, candidates), indent=2))
        return 0
    try:
        ranked = jev_rank(prompt, candidates) if args.backend == "jev" else heuristic_rank(prompt, candidates)
    except Exception as exc:
        sys.stderr.write("judge failed (%s), heuristic fallback\n" % exc)
        ranked = heuristic_rank(prompt, candidates)
        for r in ranked:
            r["backend"] = "heuristic-fallback"
    print(json.dumps(ranked[: args.top], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
