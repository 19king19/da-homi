#!/usr/bin/env python3
"""Da Homi harness: keyword classifier and routing log. It does NOT call a
model. It maps a task to a model tier by keyword class, so Da Homi never
overspends: cheapest tier that can plausibly succeed. Escalation is manual
until a failure counter is coded: the escalation rule lives as prose in
routing.json, with no failure counter behind it.

Reads scripts/routing.json (tiers, task classes, gateway plan), classifies
the task, prints the routing decision, and logs it to
da-homi-cache/routing/ for spend audits.

Usage:
    python3 route.py "search github for a video editor"
    python3 route.py --class strategy "the funnel relaunch"
"""
import argparse, json, os, sys, time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "routing.json")
LOGDIR = os.path.join(HERE, "..", "da-homi-cache", "routing")


def classify(text, cfg):
    low = " " + text.lower() + " "
    best, best_hits = None, 0
    for cls, words in cfg["keywords"].items():
        hits = sum(1 for w in words if w in low)
        if hits > best_hits:
            best, best_hits = cls, hits
    return best or "summarize"  # default mid: unknown work is making, not fetching


def decide(text, forced_class=None):
    cfg = json.load(open(CONFIG))
    cls = forced_class or classify(text, cfg)
    tier = cfg["task_classes"].get(cls, "builder")
    decision = {
        "homi": "da-homi/routing-decision",
        "at": datetime.now(timezone.utc).isoformat(),
        "task": text,
        "task_class": cls,
        "tier": tier,
        "tier_purpose": cfg["tiers"][tier]["purpose"],
        "models": cfg["tiers"][tier]["models"],
        "escalation": cfg["escalation"],
        "gateway": cfg["gateways"]["primary"].split(":")[0],
        "judge": cfg["gateways"]["judge"].split(":")[0],
    }
    os.makedirs(LOGDIR, exist_ok=True)
    with open(os.path.join(LOGDIR, f"{int(time.time())}.json"), "w") as f:
        json.dump(decision, f, indent=2)
    return decision


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("task")
    ap.add_argument("--class", dest="cls", default=None)
    args = ap.parse_args()
    d = decide(args.task, args.cls)
    print(f"task class: {d['task_class']}  ->  tier: {d['tier'].upper()} ({d['models']})")
    print(f"why: {d['tier_purpose']}")
    print(f"route: {d['gateway']} serves it; {d['judge']} judges the ambiguous ones")
