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

provenance(item) (v2.1) reports where a candidate comes from (age, last
push, owner type, fork, archive, license, stars, forks, description) and
raises plain flags from those facts. Flags inform the reader. They never
refuse anything and never feed score(), which is unchanged.
"""
import argparse, json, math, os, re, subprocess, sys, urllib.parse, urllib.request
from datetime import datetime, timedelta, timezone

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


YOUNG_DAYS, STALE_DAYS = 90, 365


def _when(value):
    """A GitHub timestamp as an aware datetime, or None when missing or unparseable."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        when = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def provenance(item, now=None):
    """Provenance facts for one search item, plus sorted flags. Flags only."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    owner = item.get("owner") if isinstance(item.get("owner"), dict) else {}
    lic = item.get("license") if isinstance(item.get("license"), dict) else {}
    info = {
        "created_at": item.get("created_at"),
        "pushed_at": item.get("pushed_at"),
        "owner_type": owner.get("type"),
        "fork": bool(item.get("fork")),
        "archived": bool(item.get("archived")),
        "license": lic.get("spdx_id"),
        "stars": item.get("stargazers_count") or 0,
        "forks": item.get("forks_count") or 0,
        "description_present": bool((item.get("description") or "").strip()),
    }
    flags = set()
    created, pushed = _when(info["created_at"]), _when(info["pushed_at"])
    if created is None or pushed is None:
        flags.add("dates_unknown")  # never guess an age
    if created is not None and now - created < timedelta(days=YOUNG_DAYS):
        flags.add("young")
    if pushed is not None and now - pushed > timedelta(days=STALE_DAYS):
        flags.add("stale")
    if info["fork"]:
        flags.add("fork")
    if info["archived"]:
        flags.add("archived")
    if info["license"] is None:
        flags.add("no_license")
    if info["stars"] < 10 and info["forks"] < 3:
        flags.add("thin")
    if info["owner_type"] == "User":
        flags.add("personal_account")
    if not info["description_present"]:
        flags.add("no_description")
    info["flags"] = sorted(flags)
    return info


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
