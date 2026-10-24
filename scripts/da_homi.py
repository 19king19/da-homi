#!/usr/bin/env python3
"""Da Homi harness: the hunt runner.

Runs the search leg of the Da Homi loop mechanically and writes a RUN RECEIPT
into da-homi-cache/runs/. The excuse gate (excuse_gate.py) only accepts a
limitation claim when a receipt proves the loop actually ran.

Usage:
    python3 da_homi.py hunt "the missing capability in plain words"
"""
import json, os, sys, time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hub_search  # noqa: E402

CACHE = os.path.join(HERE, "..", "da-homi-cache", "runs")


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


def hunt(query):
    os.makedirs(CACHE, exist_ok=True)
    tried, pool = [], {}
    for v in variants(query):
        try:
            items = hub_search.search(v, 10)
        except Exception as e:
            tried.append({"query": v, "error": str(e)})
            continue
        tried.append({"query": v, "results": len(items)})
        for it in items:
            pool[it["full_name"]] = it
    ranked = sorted(pool.values(), key=hub_search.score, reverse=True)[:10]
    receipt = {
        "homi": "da-homi/run-receipt",
        "task_query": query,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "queries_tried": tried,
        "candidates": [{
            "repo": it["full_name"], "url": it["html_url"],
            "stars": it.get("stargazers_count", 0),
            "license": (it.get("license") or {}).get("spdx_id"),
            "pushed_at": (it.get("pushed_at") or "")[:10],
            "score": hub_search.score(it),
            "description": (it.get("description") or "").strip(),
        } for it in ranked],
        "loop_completed": len(ranked) > 0,
        "next_step": "vet the winner (vet.py) before anything runs, then fetch, test, finish the task",
    }
    slug = "".join(c if c.isalnum() else "-" for c in query.lower())[:40].strip("-")
    path = os.path.join(CACHE, f"{int(time.time())}-{slug}.json")
    with open(path, "w") as f:
        json.dump(receipt, f, indent=2)
    print(f"RECEIPT: {path}")
    for c in receipt["candidates"]:
        print(f"{c['score']:>6}  {c['repo']}  ★{c['stars']}  {c['license'] or 'no license'}  pushed {c['pushed_at']}")
        if c["description"]:
            print(f"        {c['description'][:140]}")
    if not receipt["loop_completed"]:
        print("NO CANDIDATES FOUND. The loop ran; report the blocker with this receipt.")
    return 0 if receipt["loop_completed"] else 3


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "hunt":
        sys.exit(hunt(" ".join(sys.argv[2:])))
    print(__doc__)
    sys.exit(2)
