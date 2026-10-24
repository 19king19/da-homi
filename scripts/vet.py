#!/usr/bin/env python3
"""Da Homi harness: the safety vetter.

Static scan of a fetched repo before anything in it runs. HARD patterns block
the run outright. SOFT patterns mark the repo REVIEW: a human or the agent
reads those spots before executing.

Usage:
    python3 vet.py <directory>
Exit: 0 = CLEAN or REVIEW, 1 = BLOCKED.
"""
import os, re, sys

HARD = [
    (r"curl[^\n|]*\|\s*(sudo\s+)?(sh|bash)", "pipe-to-shell install"),
    (r"wget[^\n|]*\|\s*(sudo\s+)?(sh|bash)", "pipe-to-shell install"),
    (r"eval\s*\(\s*base64", "base64 eval payload"),
    (r"~/.ssh|id_rsa|id_ed25519", "touches SSH keys"),
    (r"/etc/passwd|/etc/shadow", "reads system credential files"),
    (r"AWS_SECRET_ACCESS_KEY|GITHUB_TOKEN[^\n]{0,40}(post|send|upload)", "credential exfiltration shape"),
]
SOFT = [
    (r"subprocess|os\.system|child_process|execSync", "shells out"),
    (r"requests\.post|urllib\.request|fetch\(|axios", "network calls"),
    (r"os\.environ|process\.env", "reads environment"),
    (r"socket\.|createConnection", "raw sockets"),
    (r"chmod\s+\+x|sudo\s", "permission changes / sudo"),
]
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv"}
TEXT_EXT = {".py", ".js", ".ts", ".sh", ".bash", ".rb", ".pl", ".php", ".json", ".yml", ".yaml", ".toml", ".md", ""}


SELF = os.path.abspath(__file__)


def scan(root):
    hard, soft = [], []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            p = os.path.join(dirpath, fn)
            if os.path.abspath(p) == SELF:
                continue  # the vetter never scans itself: its pattern table is not code under review
            if os.path.splitext(fn)[1].lower() not in TEXT_EXT or os.path.getsize(p) > 1_000_000:
                continue
            try:
                lines = open(p, encoding="utf-8", errors="ignore").read().splitlines()
            except Exception:
                continue
            base = os.path.basename(p)
            inert = (".test." in base or ".spec." in base or base.startswith("test")
                     or "/tests/" in p or os.path.splitext(fn)[1].lower() == ".md")
            for i, line in enumerate(lines, 1):
                for pat, label in HARD:
                    if re.search(pat, line):
                        tag = "HARD-INERT" if inert else "HARD"
                        hard.append(f"{tag} {label}: {p}:{i}: {line.strip()[:120]}")
                for pat, label in SOFT:
                    if re.search(pat, line):
                        soft.append(f"soft {label}: {p}:{i}: {line.strip()[:120]}")
    return hard, soft


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    hard, soft = scan(sys.argv[1])
    for h in hard:
        print(h)
    for s in soft[:40]:
        print(s)
    hard_exec = [h for h in hard if h.startswith("HARD ")]
    hard_inert = [h for h in hard if h.startswith("HARD-INERT")]
    if hard_exec:
        print(f"VERDICT: BLOCKED ({len(hard_exec)} hard flags in executable code, "
              f"{len(hard_inert)} in tests/docs, {len(soft)} soft). Do not run this code.")
        sys.exit(1)
    if hard_inert:
        print(f"VERDICT: REVIEW (hard patterns appear only in tests/docs: {len(hard_inert)}; "
              f"{len(soft)} soft). Read those spots, then decide.")
    elif soft:
        print(f"VERDICT: REVIEW (0 hard flags, {len(soft)} soft). Read the flagged spots before running.")
    else:
        print("VERDICT: CLEAN (no flags).")
    sys.exit(0)
