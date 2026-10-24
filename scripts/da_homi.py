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
    python3 da_homi.py hunt "the missing capability in plain words"

Exit: 0 = CONTINUE (candidates found), 3 = terminal (reportable blocker).
"""
import json, os, sys, time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hub_search  # noqa: E402

CACHE = os.path.join(HERE, "..", "da-homi-cache", "runs")

TERMINAL = {"no_candidates", "search_failed", "all_blocked", "fetch_failed", "test_failed"}


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


def hunt(query, cache_dir=None):
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
    } for position, it in ranked]
    if candidates:
        outcome = "CONTINUE"
    elif any("error" not in t for t in tried):
        outcome = "no_candidates"
    else:
        outcome = "search_failed"
    receipt = {
        "homi": "da-homi/run-receipt",
        "version": 2,
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
        print(f"{c['score']:>6}  {c['repo']}  ★{c['stars']}  {c['license'] or 'no license'}  pushed {c['pushed_at']}")
        if c["description"]:
            print(f"        {c['description'][:140]}")
    if outcome != "CONTINUE":
        print(f"{outcome.upper()}. The loop ran; report the blocker with this receipt.")
    return 0 if outcome == "CONTINUE" else 3


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "hunt":
        sys.exit(hunt(" ".join(sys.argv[2:])))
    print(__doc__)
    sys.exit(2)
