#!/usr/bin/env python3
"""Da Homi harness: the excuse gate (v2, lighter build).

The coded form of the law: "I can't" is a search query. This gate scans a
draft response for limitation claims.

Two rules that v1 got wrong, fixed here:

1. Capability, not authority. An authority or policy decline ("I won't send
   this without your approval", "this needs your go") is not a capability
   claim and passes without a receipt. Only capability claims ("there is no
   tool for this") route to the hunt. The excuse phrase list itself is
   unchanged on purpose: a gate that gets better at suppressing an agent's
   "I won't" would fight the host's own approval rules.
2. Receipts are bound to the task. A claim passes only with a fresh (24h)
   receipt whose outcome is terminal AND whose task query overlaps the
   task at hand. A receipt showing candidates found returns CONTINUE: the
   agent goes back and finishes the loop, it does not get to report a
   blocker. Receipts from v1 have no outcome field and are ignored as
   LEGACY: re-run the hunt with the v2 script.

Usage:
    python3 excuse_gate.py --text "draft response text" [--task "the task"]
    python3 excuse_gate.py --file draft.txt [--task "the task"]
Exit: 0 = PASS, 1 = BLOCKED (including CONTINUE receipts).
"""
import argparse, glob, json, os, re, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
RUNS = os.path.join(HERE, "..", "da-homi-cache", "runs")

# Unchanged from v1, on purpose. See the module docstring.
EXCUSES = [
    r"i can'?t", r"i cannot", r"i'?m unable", r"unable to", r"not possible",
    r"i don'?t have (access|a way|the ability)", r"i do not have (access|a way|the ability)",
    r"no way to", r"beyond my (capabilities|ability)", r"i'?m not able",
    r"there is no way", r"it'?s impossible",
]

# Authority and policy declines. These are not capability claims.
AUTHORITY = [
    r"without your (approval|go|permission|ok)",
    r"need(s)? your (approval|go|permission)",
    r"needs your (approval|go|permission)",
    r"waiting for your (approval|go)",
    r"i won'?t (send|spend|publish|delete)",
    r"not authorized", r"i don'?t have permission",
    r"requires? your (approval|permission)",
    r"before i (send|spend|publish|delete)",
]

TERMINAL = {"no_candidates", "search_failed", "all_blocked", "fetch_failed", "test_failed"}

STOPWORDS = {"the", "and", "for", "with", "from", "that", "this", "what", "does",
             "your", "you", "are", "can", "how", "into", "over", "under", "about"}


def tokens(text):
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {w for w in words if len(w) >= 4 and w not in STOPWORDS}


def split_sentences(text):
    return [s.strip() for s in re.split(r"[.!?\n]+", text or "") if s.strip()]


def capability_sentences(text):
    """Sentences carrying a capability claim: an excuse phrase, no authority phrase."""
    out = []
    for s in split_sentences(text):
        low = s.lower()
        if any(re.search(p, low) for p in EXCUSES) and not any(re.search(p, low) for p in AUTHORITY):
            out.append(s)
    return out


def task_matches(receipt_query, task_text):
    rq, tq = tokens(receipt_query), tokens(task_text)
    if not rq or not tq:
        return False
    shared = rq & tq
    if len(shared) >= 2:
        return True
    if len(shared) == 1 and len(rq) <= 3:
        return True
    return False


def matching_receipt(task_text, runs_dir=None):
    """Newest fresh receipt that is terminal AND bound to this task.

    Returns (path, receipt, status) where status is one of PASS, CONTINUE,
    LEGACY, or NONE. CONTINUE and LEGACY are reported, not passed.
    """
    directory = runs_dir or RUNS
    files = sorted(glob.glob(os.path.join(directory, "*.json")), key=os.path.getmtime, reverse=True)
    saw_legacy = False
    for f in files:
        try:
            r = json.load(open(f))
        except Exception:
            continue
        if time.time() - os.path.getmtime(f) >= 24 * 3600:
            continue
        outcome = r.get("outcome")
        if outcome is None:
            saw_legacy = True
            continue
        if not task_matches(r.get("task_query", ""), task_text):
            continue
        if outcome in TERMINAL:
            return f, r, "PASS"
        if outcome == "CONTINUE":
            return f, r, "CONTINUE"
    if saw_legacy:
        return None, None, "LEGACY"
    return None, None, "NONE"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", default="")
    ap.add_argument("--file", default="")
    ap.add_argument("--task", default="")
    args = ap.parse_args()
    text = open(args.file).read() if args.file else args.text
    claims = capability_sentences(text)
    if not claims:
        print("PASS: no capability claim in this response (authority declines pass without a receipt).")
        sys.exit(0)
    task_text = args.task or text
    path, receipt, status = matching_receipt(task_text)
    if status == "PASS":
        print(f"PASS: capability claim backed by terminal receipt {path} "
              f"(outcome {receipt.get('outcome')} for '{receipt.get('task_query')}').")
        sys.exit(0)
    if status == "CONTINUE":
        print(f"CONTINUE: receipt {path} shows candidates found for '{receipt.get('task_query')}'. "
              "Finish the loop: vet, fetch, test. Do not report a blocker yet.")
        sys.exit(1)
    if status == "LEGACY":
        print("BLOCKED: only v1 receipts found (no outcome field). Re-run the hunt with the v2 script.")
        sys.exit(1)
    print(f"BLOCKED: capability claim ({claims[0][:120]}) with no fresh terminal receipt bound to this task. "
          "Run the loop first: python3 da_homi.py hunt \"<the missing capability>\", "
          "then vet, fetch, test. If the loop truly fails, its terminal receipt is what makes the blocker reportable.")
    sys.exit(1)
