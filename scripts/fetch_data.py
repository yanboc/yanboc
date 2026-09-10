#!/usr/bin/env python3
"""Fetch GitHub data for the profile highlight generator.

Reads:
  - repositories owned by the user (excluding forks)
  - recent commits for the top N recently-updated repos
  - recently starred repositories

Writes JSON to data/cache/. On any network error, falls back to the cached
files so the workflow never breaks due to transient failures.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone

import requests

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
USER = os.environ.get("GITHUB_USER", "yanboc")
TOP_N = int(os.environ.get("TOP_N", "8"))

BASE = "https://api.github.com"
CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "cache")

REPOS_PATH = os.path.join(CACHE_DIR, "repos.json")
COMMITS_PATH = os.path.join(CACHE_DIR, "commits.json")
STARS_PATH = os.path.join(CACHE_DIR, "stars.json")

HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
if GITHUB_TOKEN:
    HEADERS["Authorization"] = f"Bearer {GITHUB_TOKEN}"


def _get(url, params=None):
    resp = requests.get(url, headers=HEADERS, params=params, timeout=30)
    # Respect rate limits with a small wait on 403.
    if resp.status_code == 403:
        reset = resp.headers.get("X-RateLimit-Reset")
        if reset:
            wait = max(int(reset) - int(time.time()) + 1, 0)
            if 0 < wait <= 60:
                time.sleep(wait)
                return _get(url, params)
        resp.raise_for_status()
    resp.raise_for_status()
    return resp.json()


def _write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _load(path):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch_repos():
    repos = _get(f"{BASE}/users/{USER}/repos", {"sort": "updated", "per_page": 100})
    owned = [r for r in repos if not r.get("fork")]
    owned.sort(key=lambda r: r.get("pushed_at") or "", reverse=True)
    return [
        {
            "name": r["name"],
            "description": r.get("description"),
            "language": r.get("language"),
            "stars": r.get("stargazers_count", 0),
            "pushed_at": r.get("pushed_at"),
            "html_url": r.get("html_url"),
            "archived": r.get("archived", False),
        }
        for r in owned
    ]


def fetch_commits(repos):
    commits = {}
    for r in repos[:TOP_N]:
        try:
            data = _get(f"{BASE}/repos/{USER}/{r['name']}/commits", {"per_page": 1})
        except requests.HTTPError:
            continue
        if data:
            c = data[0]
            commits[r["name"]] = {
                "commit_message": c["commit"]["message"].splitlines()[0],
                "commit_date": c["commit"]["committer"]["date"],
                "html_url": c["html_url"],
            }
    return commits


def fetch_stars():
    stars = _get(f"{BASE}/users/{USER}/starred", {"per_page": 20, "sort": "created"})
    return [
        {
            "name": s["full_name"],
            "description": s.get("description"),
            "stars": s.get("stargazers_count", 0),
            "html_url": s.get("html_url"),
        }
        for s in stars[:20]
    ]


def main():
    meta = {"fetched_at": datetime.now(timezone.utc).isoformat()}

    try:
        repos = fetch_repos()
        _write(REPOS_PATH, {"meta": meta, "repos": repos})
        commits = fetch_commits(repos)
        _write(COMMITS_PATH, {"meta": meta, "commits": commits})
        stars = fetch_stars()
        _write(STARS_PATH, {"meta": meta, "stars": stars})
        print(f"[fetch] ok: {len(repos)} repos, {len(commits)} commit sets, {len(stars)} stars")
    except Exception as exc:  # noqa: BLE001 - fall back to cache
        print(f"[fetch] error: {exc}; falling back to cache", file=sys.stderr)
        if _load(REPOS_PATH) is None:
            sys.exit(1)


if __name__ == "__main__":
    main()