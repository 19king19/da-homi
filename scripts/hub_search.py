#!/usr/bin/env python3
"""Da Homi hub search: search GitHub repositories and rank candidates.

Standalone (stdlib only). Uses `gh` if available on PATH for authenticated
search; falls back to the unauthenticated GitHub API.

Usage:
    python3 hub_search.py "llm model router" [--limit 10] [--json]

Scoring favors: actually matching the query, then GitHub's own relevance
order as the base, stars (log scale), recent activity, a real license, and
penalizes forks. V1 sorted by stars, which replaced relevance with
popularity and let a famous repo that mentions the words beat a niche tool
that does the task. That sort is gone.

This ranks; it does not vet. Vetting is step 4 of the Da Homi loop and
is done by vet.py plus a human reading every REVIEW before anything runs.
"""
import argparse, json, math, os, re, subprocess, sys, urllib.parse, urllib.request
from datetime import datetime, timezone

API = "https://api.github.com/search/repositories"


def gh_token():
    try:
        r = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    except Exception:
        pass
    return os.environ.get("GITHUB_TOKEN", "")


def search(query, limit):
    # No sort parameter: GitHub's default is best match (relevance).
    q = urllib.parse.quote(query)
    url = f"{API}?q={q}&per_page={min(limit * 3, 100)}"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                                "User-Agent": "da-homi-hub-search"})
    tok = gh_token()
    if tok:
        req.add_header("Authorization", f"Bearer {tok}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8")).get("items", [])


def score(item, query="", position=0):
    stars = item.get("stargazers_count", 0)
    # Stars are a signal, not the decision: capped, so relevance can win.
    s = min(50.0, math.log10(stars + 1) * 20)
    pushed = item.get("pushed_at") or ""
    try:
        age_days = (datetime.now(timezone.utc) - datetime.fromisoformat(pushed.replace("Z", "+00:00"))).days
    except Exception:
        age_days = 9999
    if age_days <= 30:
        s += 25
    elif age_days <= 180:
        s += 15
    elif age_days <= 365:
        s += 5
    else:
        s -= 10
    if item.get("license"):
        s += 10
    if item.get("fork"):
        s -= 30
    if (item.get("description") or "").strip():
        s += 5
    # Relevance position bonus: earlier in GitHub's best-match order scores higher.
    s += max(0, 30 - position * 3)
    # Query term overlap bonus: does it actually talk about the task?
    terms = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) >= 3]
    if terms:
        hay = ((item.get("full_name") or "") + " " + (item.get("description") or "")).lower()
        s += min(45, 15 * sum(1 for t in terms if t in hay))
    return round(s, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    try:
        items = search(args.query, args.limit)
    except Exception as e:
        print(f"SEARCH FAILED: {e}", file=sys.stderr)
        return 1
    ranked = sorted(enumerate(items), key=lambda p: score(p[1], args.query, p[0]), reverse=True)[: args.limit]
    rows = [{
        "repo": it["full_name"],
        "url": it["html_url"],
        "stars": it.get("stargazers_count", 0),
        "license": (it.get("license") or {}).get("spdx_id"),
        "pushed_at": (it.get("pushed_at") or "")[:10],
        "fork": bool(it.get("fork")),
        "score": score(it, args.query, position),
        "description": (it.get("description") or "").strip(),
    } for position, it in ranked]
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        for r in rows:
            print(f"{r['score']:>6}  {r['repo']}  ★{r['stars']}  {r['license'] or 'no license'}  pushed {r['pushed_at']}")
            if r["description"]:
                print(f"        {r['description'][:140]}")
            print(f"        {r['url']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
