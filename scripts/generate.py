#!/usr/bin/env python3
"""Generate the highlighted profile section using an LLM (DeepSeek).

Reads:
  - data/persona.md            AI persona (system prompt)
  - data/news.md               hand-written personal news fodder
  - data/cache/repos.json      GitHub repos
  - data/cache/commits.json    recent commits
  - data/cache/stars.json      recently starred repos
  - templates/highlight.html   the HTML shell with a {{CONTENT}} slot

Writes the fully-rendered section to data/cache/highlight.html.
"""

import json
import os
import sys
import textwrap
from datetime import datetime, timezone

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
CACHE = os.path.join(DATA, "cache")

PERSONA_PATH = os.path.join(DATA, "persona.md")
NEWS_PATH = os.path.join(DATA, "news.md")
TEMPLATE_PATH = os.path.join(ROOT, "templates", "highlight.html")
REPOS_PATH = os.path.join(CACHE, "repos.json")
COMMITS_PATH = os.path.join(CACHE, "commits.json")
STARS_PATH = os.path.join(CACHE, "stars.json")
OUT_PATH = os.path.join(CACHE, "highlight.html")

ENDPOINT = os.environ.get("DEEPSEEK_ENDPOINT", "https://api.deepseek.com/chat/completions")
MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")


def _read(path, default=""):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


def _load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _summarize_repos(repos, commits):
    lines = []
    for r in repos[:10]:
        c = commits.get(r["name"], {})
        desc = (r.get("description") or "").strip()
        parts = [f"- {r['name']} (lang: {r.get('language') or '?'}, stars: {r['stars']})"]
        if desc:
            parts.append(f"  description: {desc}")
        if c:
            parts.append(f"  last commit: {c.get('commit_date', '')[:10]} — {c.get('commit_message', '')}")
        else:
            parts.append(f"  last push: {str(r.get('pushed_at', ''))[:10]}")
        lines.append("\n".join(parts))
    return "\n".join(lines)


def _summarize_stars(stars):
    lines = []
    for s in stars[:10]:
        desc = (s.get("description") or "").strip()
        lines.append(f"- {s['name']} (stars: {s['stars']})" + (f" — {desc}" if desc else ""))
    return "\n".join(lines) or "(none)"


def build_prompt():
    repos = _load_json(REPOS_PATH, {}).get("repos", [])
    commits = _load_json(COMMITS_PATH, {}).get("commits", {})
    stars = _load_json(STARS_PATH, {}).get("stars", [])
    news = _read(NEWS_PATH, "")

    return textwrap.dedent(
        f"""\
        Today is {datetime.now(timezone.utc).strftime('%Y-%m-%d')}.

        === RECENT REPOSITORIES ===
        {_summarize_repos(repos, commits)}

        === RECENTLY STARRED ===
        {_summarize_stars(stars)}

        === PERSONAL NEWS (raw, hand-written) ===
        {news or "(none)"}

        === TASK ===
        Produce ONE fragment (CONTENT): a short first-person narrative of my
        recent activity, written as 1-2 natural prose paragraphs (HTML <p>
        tags), in the same tone as the rest of my profile README. Weave in
        2-4 concrete things: recent pushes, new projects, maintenance — for
        each repo, say what it is for and what problem it solves, linking to
        it. If PERSONAL NEWS has content, work it naturally into the
        narrative; if it is empty or "(none)", just don't mention news.
        NO bullet lists — flowing prose only, GitHub-native HTML (p, a, b, i;
        no inline styles, no CSS classes, no images). Keep it short and
        honest.

        Output format — output exactly this, nothing else, no code fences:

        <!-- CONTENT:START -->
        <p>...</p>
        <!-- CONTENT:END -->
        """
    )


def _extract(text, marker):
    start = f"<!-- {marker}:START -->"
    end = f"<!-- {marker}:END -->"
    if start not in text or end not in text:
        raise RuntimeError(f"model output missing {marker} markers")
    return text.split(start, 1)[1].split(end, 1)[0].strip()


def call_llm(system, user):
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is not set")

    resp = requests.post(
        ENDPOINT,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL,
            "temperature": 0.7,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def main():
    persona = _read(PERSONA_PATH)
    if not persona:
        print("[generate] warn: persona.md is empty", file=sys.stderr)

    prompt = build_prompt()
    raw = call_llm(persona, prompt)

    content = _extract(raw, "CONTENT")

    template = _read(TEMPLATE_PATH)
    if "{{CONTENT}}" not in template:
        raise RuntimeError("template missing {{CONTENT}} placeholder")

    html = template.replace("{{CONTENT}}", content)

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[generate] ok -> {os.path.relpath(OUT_PATH, ROOT)}")


if __name__ == "__main__":
    main()