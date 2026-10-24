#!/usr/bin/env python3
"""Da Homi harness: the hunt runner (v2, lighter build).

Runs the search leg of the Da Homi loop mechanically and writes a RUN RECEIPT
into da-homi-cache/runs/. The receipt carries an explicit outcome, not just
a boolean. Only terminal outcomes license a limitation claim at the excuse
gate. A receipt showing candidates found means CONTINUE: the agent goes back
and finishes the loop instead of reporting a blocker.

Outcomes:
    CONTINUE      candidates found, keep working the loop
    no_candidates every query succeeded and found nothing
    search_failed every query errored
    all_blocked   candidates were found but every one was vet BLOCKED
                  (written by fetch.py, not by this search leg)
    fetch_failed  a fetch failed (written by fetch.py)
    test_failed   a trial failed (written by trial.py)

Usage:
    python3 da_homi.py hunt "the missing capability in plain words" [--deep]

v2.1: every candidate carries provenance (hub_search.provenance) and its
flags print in brackets on the candidate line. --deep adds a releases and
a contributors check for the top 5 candidates. Flags inform the reader:
they never refuse anything, never change a score, and never change the
exit code. The receipt stays version 2 and lists its "features".

Exit: 0 = CONTINUE (candidates found), 3 = terminal (reportable blocker).
"""
import json, os, sys, time, urllib.request
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hub_search  # noqa: E402

CACHE = os.path.join(HERE, "..", "da-homi-cache", "runs")

TERMINAL = {"no_candidates", "search_failed", "all_blocked", "fetch_failed", "test_failed"}

DEEP_TOP = 5
API_REPOS = "https://api.github.com/repos"


def variants(query):
    q = query.strip()
    out = [q]
    if not q.lower().startswith(("ai ", "llm ")):
        out.append(q + " tool")
    out.append(q + " github")
    seen, res = set(), []
    for v in out:
        if v.lower() not in seen:
            seen.add(v.lower())
            res.append(v)
    return res[:3]


def github_get(url, token):
    # Same headers and token lookup as hub_search.search.
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": "da-homi-hub-search"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8").strip()
    return json.loads(body) if body else []  # an empty repo's contributors come back 204, no body


def deep_provenance(candidates, top=DEEP_TOP):
    """--deep: releases and contributors for the top candidates, kept in the
    same provenance dict. A failed request flags deep_unavailable and moves on."""
    token = hub_search.gh_token()
    for c in candidates[:top]:
        prov, deep = c["provenance"], {}
        flags = set(prov["flags"])
        for key, query in (("releases", "releases?per_page=1"),
                           ("contributors", "contributors?per_page=2&anon=0")):
            try:
                data = github_get(f"{API_REPOS}/{c['repo']}/{query}", token)
                if not isinstance(data, list):
                    raise ValueError(f"unexpected {key} response")
                deep[key] = len(data)
            except Exception as e:
                deep[key] = None
                deep.setdefault("errors", []).append(f"{key}: {e}"[:200])
                flags.add("deep_unavailable")
        if deep["releases"] == 0:
            flags.add("no_releases")
        if deep["contributors"] == 1:
            flags.add("single_contributor")
        prov["deep"] = deep
        prov["flags"] = sorted(flags)


def hunt(query, cache_dir=None, deep=False):
    cache = cache_dir or CACHE
    os.makedirs(cache, exist_ok=True)
    tried, pool = [], {}
    for v in variants(query):
        try:
            items = hub_search.search(v, 10)
        except Exception as e:
            tried.append({"query": v, "error": str(e)})
            continue
        tried.append({"query": v, "results": len(items)})
        for position, it in enumerate(items):
            pool[it["full_name"]] = (position, it)
    ranked = sorted(pool.values(), key=lambda p: hub_search.score(p[1], query, p[0]), reverse=True)[:10]
    candidates = [{
        "repo": it["full_name"], "url": it["html_url"],
        "stars": it.get("stargazers_count", 0),
        "license": (it.get("license") or {}).get("spdx_id"),
        "pushed_at": (it.get("pushed_at") or "")[:10],
        "score": hub_search.score(it, query, position),
        "description": (it.get("description") or "").strip(),
        "provenance": hub_search.provenance(it),
    } for position, it in ranked]
    if deep:
        deep_provenance(candidates)
    if candidates:
        outcome = "CONTINUE"
    elif any("error" not in t for t in tried):
        outcome = "no_candidates"
    else:
        outcome = "search_failed"
    receipt = {
        "homi": "da-homi/run-receipt",
        "version": 2,
        "features": ["provenance", "deep_provenance"] if deep else ["provenance"],
        "task_query": query,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "queries_tried": tried,
        "candidates": candidates,
        "outcome": outcome,
        # Kept for readers that still look at it. It means the search leg
        # completed, not that a blocker is licensed. The gate reads outcome.
        "loop_completed": True,
        "next_step": ("vet the winner (vet.py) before anything runs, then fetch, test, finish the task"
                      if outcome == "CONTINUE" else "report the blocker with this receipt"),
    }
    slug = "".join(c if c.isalnum() else "-" for c in query.lower())[:40].strip("-")
    path = os.path.join(cache, f"{int(time.time())}-{slug}.json")
    with open(path, "w") as f:
        json.dump(receipt, f, indent=2)
    print(f"RECEIPT: {path}")
    print(f"OUTCOME: {outcome}")
    for c in candidates:
        flags = c["provenance"]["flags"]
        print(f"{c['score']:>6}  {c['repo']}  ★{c['stars']}  {c['license'] or 'no license'}  pushed {c['pushed_at']}"
              + (f"  [{', '.join(flags)}]" if flags else ""))
        if c["description"]:
            print(f"        {c['description'][:140]}")
    if outcome != "CONTINUE":
        print(f"{outcome.upper()}. The loop ran; report the blocker with this receipt.")
    return 0 if outcome == "CONTINUE" else 3


def hunt_args(argv):
    """Split hunt's arguments: --deep may sit anywhere and never joins the query."""
    return " ".join(a for a in argv if a != "--deep").strip(), "--deep" in argv


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "hunt":
        query, deep = hunt_args(sys.argv[2:])
        if query:
            sys.exit(hunt(query, deep=deep))
    print(__doc__)
    sys.exit(2)
