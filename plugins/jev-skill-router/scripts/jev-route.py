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


# Seed map: non-English stems users actually type -> English catalog tokens.
# Catalog descriptions are English, so a non-English-only prompt otherwise
# scores zero. Substring match on purpose (agglutination: 테스트를, レビューして).
# Small on purpose: cover frequent intents per language, extend as misses show up.
ALIASES = {
    # Korean
    "테스트": ["test", "testing"],
    "리뷰": ["review"],
    "네이밍": ["naming"],
    "구조": ["structure"],
    "다이어그램": ["diagram", "diagrams"],
    "시퀀스": ["sequence"],
    "순서도": ["flowchart", "diagram"],
    "그림": ["image", "images"],
    "지라": ["jira"],
    "이슈": ["issue", "issues"],
    "접근성": ["accessibility", "a11y"],
    "대비": ["contrast"],
    "명암": ["contrast"],
    "키보드": ["keyboard"],
    "스크린리더": ["screen", "reader"],
    "배포": ["deploy", "deployment", "release"],
    "빌드": ["build"],
    "에러": ["error", "errors"],
    "오류": ["error", "errors"],
    "성능": ["performance", "profiling"],
    "디버그": ["debug"],
    "번역": ["translation", "i18n"],
    # Japanese
    "テスト": ["test", "testing"],
    "レビュー": ["review"],
    "命名": ["naming"],
    "構造": ["structure"],
    "ダイアグラム": ["diagram", "diagrams"],
    "シーケンス": ["sequence"],
    "画像": ["image", "images"],
    "課題": ["issue", "issues"],
    "アクセシビリティ": ["accessibility", "a11y"],
    "コントラスト": ["contrast"],
    "キーボード": ["keyboard"],
    "デプロイ": ["deploy", "deployment", "release"],
    "ビルド": ["build"],
    "エラー": ["error", "errors"],
    "障害": ["error", "errors"],
    "性能": ["performance", "profiling"],
    "デバッグ": ["debug"],
    "翻訳": ["translation", "i18n"],
    # Chinese (simplified + traditional where they differ)
    "测试": ["test", "testing"],
    "測試": ["test", "testing"],
    "评审": ["review"],
    "審查": ["review"],
    "評審": ["review"],
    "命名": ["naming"],
    "结构": ["structure"],
    "結構": ["structure"],
    "图表": ["diagram", "diagrams"],
    "圖表": ["diagram", "diagrams"],
    "流程图": ["flowchart", "diagram"],
    "流程圖": ["flowchart", "diagram"],
    "图片": ["image", "images"],
    "圖片": ["image", "images"],
    "图像": ["image", "images"],
    "圖像": ["image", "images"],
    "问题": ["issue", "issues"],
    "問題": ["issue", "issues"],
    "无障碍": ["accessibility", "a11y"],
    "無障礙": ["accessibility", "a11y"],
    "对比度": ["contrast"],
    "對比度": ["contrast"],
    "键盘": ["keyboard"],
    "鍵盤": ["keyboard"],
    "部署": ["deploy", "deployment", "release"],
    "构建": ["build"],
    "構建": ["build"],
    "错误": ["error", "errors"],
    "錯誤": ["error", "errors"],
    "性能": ["performance", "profiling"],
    "效能": ["performance", "profiling"],
    "调试": ["debug"],
    "調試": ["debug"],
    "翻译": ["translation", "i18n"],
    "翻譯": ["translation", "i18n"],
    # Spanish
    "prueba": ["test", "testing"],
    "revis": ["review"],
    "diagrama": ["diagram", "diagrams"],
    "estructura": ["structure"],
    "nombr": ["naming"],
    "problema": ["issue", "issues"],
    "despliegue": ["deploy", "deployment", "release"],
    "compil": ["build"],
    "rendimiento": ["performance", "profiling"],
    "depur": ["debug"],
    "traducc": ["translation", "i18n"],
    # German (matched case-insensitively via lower())
    "prüf": ["review"],
    "diagramm": ["diagram", "diagrams"],
    "struktur": ["structure"],
    "benennung": ["naming"],
    "problem": ["issue", "issues"],
    "fehler": ["error", "errors"],
    "bereitstell": ["deploy", "deployment", "release"],
    "leistung": ["performance", "profiling"],
    # French
    "revue": ["review"],
    "révis": ["review"],
    "diagramme": ["diagram", "diagrams"],
    "nommage": ["naming"],
    "problème": ["issue", "issues"],
    "probleme": ["issue", "issues"],
    "erreur": ["error", "errors"],
    "déployer": ["deploy", "deployment", "release"],
    "deployer": ["deploy", "deployment", "release"],
    "rendement": ["performance", "profiling"],
}


def expand_aliases(prompt_low):
    extra = set()
    for native, en in ALIASES.items():
        if native in prompt_low or native.lower() in prompt_low:
            extra.update(en)
    return extra


def load_catalog(path=None):
    if path:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)["skills"]
    proc = subprocess.run(CATALOG_CMD, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError("muse skills list failed: " + proc.stderr.strip())
    return json.loads(proc.stdout)["skills"]


def resolve_skill_path(skill):
    """Resolve a catalog entry to a directly readable file path.

    read_skill refuses disabled skills, but the catalog path can be read
    as a plain file. plugin:// and bundled: entries have no direct file
    equivalent and are returned as-is.
    """
    raw = skill.get("path") or ""
    if raw.startswith("$HOME/"):
        return os.path.join(os.path.expanduser("~"), raw[len("$HOME/"):])
    if raw.startswith("~/"):
        return os.path.expanduser(raw)
    if raw.startswith("plugin://") or raw.startswith("bundled:"):
        return raw
    if os.path.isabs(raw):
        return raw
    return os.path.abspath(raw)


def score_skill(prompt, skill):
    prompt_low = prompt.lower()
    prompt_toks = set(tokens(prompt)) | expand_aliases(prompt_low)
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
    # Wire shape follows node-decision-model: questions is a map keyed by
    # id, each a typed noul question; answers come back under "answers".
    return {
        "model": JEV_MODEL,
        "state": prompt,
        "questions": {
            c["id"]: {
                "type": "noul",
                "instructions": "Is this skill relevant to the state? "
                + (c.get("description") or ""),
            }
            for c in candidates
        },
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
    answers = payload.get("answers") or {}
    ranked = []
    for c in candidates:
        ans = answers.get(c["id"], {})
        score = ans.get("noul", ans.get("probability", ans.get("score", 0)))
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
    parser.add_argument("--with-paths", action="store_true",
                        help="attach activation and resolved file path to each hit")
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
    if args.with_paths:
        by_id = {s["id"]: s for s in candidates}
        for r in ranked[: args.top]:
            src = by_id.get(r["id"], {})
            r["activation"] = src.get("activation")
            r["path"] = resolve_skill_path(src)
    print(json.dumps(ranked[: args.top], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
