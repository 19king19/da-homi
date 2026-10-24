#!/usr/bin/env python3
"""Da Homi harness: the excuse gate.

The coded form of the law: "I can't" is a search query. This gate scans a
draft response for limitation claims. A claim is allowed ONLY with a run
receipt from da_homi.py proving the loop ran (search executed, candidates
scored) within the last 24 hours. Otherwise the response is BLOCKED and the
agent is sent back to run the loop.

Usage:
    python3 excuse_gate.py --text "draft response text"
    python3 excuse_gate.py --file draft.txt
Exit: 0 = PASS, 1 = BLOCKED.
"""
import argparse, glob, json, os, re, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(HERE, "..", "da-homi-cache", "runs")

EXCUSES = [
    r"i can'?t", r"i cannot", r"i'?m unable", r"unable to", r"not possible",
    r"i don'?t have (access|a way|the ability)", r"i do not have (access|a way|the ability)",
    r"no way to", r"beyond my (capabilities|ability)", r"i'?m not able",
    r"there is no way", r"it'?s impossible",
]


def find_excuses(text):
    low = text.lower()
    return [p for p in EXCUSES if re.search(p, low)]


def fresh_receipt():
    files = sorted(glob.glob(os.path.join(RUNS, "*.json")), key=os.path.getmtime, reverse=True)
    for f in files:
        try:
            r = json.load(open(f))
        except Exception:
            continue
        if r.get("loop_completed") and time.time() - os.path.getmtime(f) < 24 * 3600:
            return f, r
    return None, None


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", default="")
    ap.add_argument("--file", default="")
    args = ap.parse_args()
    text = open(args.file).read() if args.file else args.text
    hits = find_excuses(text)
    if not hits:
        print("PASS: no limitation claim in this response.")
        sys.exit(0)
    path, receipt = fresh_receipt()
    if receipt:
        print(f"PASS: limitation claim backed by run receipt {path} "
              f"({len(receipt.get('candidates', []))} candidates scored for '{receipt.get('task_query')}').")
        sys.exit(0)
    print(f"BLOCKED: limitation claim ({hits[0]}) with no Da Homi run receipt. "
          "Run the loop first: python3 da_homi.py hunt \"<the missing capability>\", "
          "then vet, fetch, test. If the loop truly fails, its receipt is what makes the blocker reportable.")
    sys.exit(1)
