#!/usr/bin/env python3
"""Da Homi harness: the safety vetter (v2, lighter build).

This is a TRIPWIRE, not a clearance. It statically scans a fetched repo
before anything in it runs and flags known hostile shapes. A CLEAN verdict
means the tripwire found nothing. It does not mean the code is safe.

Deliberately NOT done here, because it would cost more good tools than bad
ones: no AST pass, no file-level shape blocking. Network plus write plus
permission change is what legitimate installers, downloaders, and build
tools do. Shape blocking would reject the very tools Da Homi exists to
fetch. The real safety boundary stays where it belongs: the host's approval
rules before anything runs, sends, spends, publishes, or deletes, plus a
human reading every REVIEW verdict before execution.

HARD patterns block the run outright. SOFT patterns mark the repo REVIEW:
a human reads those spots before executing. REVIEW is its own exit code
now, so no automation can mistake it for CLEAN.

Inert status comes only from a tests, docs, examples, or fixtures
directory in the path, or from a documentation extension. Never from a
filename: v1 let any file starting with "test" downgrade a HARD flag, so
a payload named test_setup.py walked through. That bypass is closed.

Large files and files outside the text extension list are NOT scanned and
are NOT silently skipped either: they are listed as SKIPPED, visible in
both text and JSON output, so the human knows what the tripwire did not see.

Usage:
    python3 vet.py <directory> [--json]
Exit: 0 = CLEAN, 3 = REVIEW, 1 = BLOCKED, 2 = usage.
"""
import argparse, json, os, re, sys

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
INERT_DIRS = {"tests", "test", "docs", "examples", "fixtures"}
DOC_EXT = {".md", ".rst", ".txt"}
MAX_SCAN = 1_000_000

SELF = os.path.abspath(__file__)


def is_inert(path):
    parts = [p.lower() for p in path.replace(os.sep, "/").split("/")]
    if any(d in parts for d in INERT_DIRS):
        return True
    return os.path.splitext(path)[1].lower() in DOC_EXT


def scan(root):
    hard, soft, skipped = [], [], []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            p = os.path.join(dirpath, fn)
            if os.path.abspath(p) == SELF:
                continue  # the vetter never scans itself: its pattern table is not code under review
            ext = os.path.splitext(fn)[1].lower()
            if ext not in TEXT_EXT or os.path.getsize(p) > MAX_SCAN:
                skipped.append(f"SKIPPED (not scanned): {p}")
                continue
            try:
                with open(p, encoding="utf-8", errors="ignore") as f:
                    lines = f.read().splitlines()
            except Exception:
                skipped.append(f"SKIPPED (unreadable): {p}")
                continue
            inert = is_inert(p)
            for i, line in enumerate(lines, 1):
                for pat, label in HARD:
                    if re.search(pat, line):
                        tag = "HARD-INERT" if inert else "HARD"
                        hard.append(f"{tag} {label}: {p}:{i}: {line.strip()[:120]}")
                for pat, label in SOFT:
                    if re.search(pat, line):
                        soft.append(f"soft {label}: {p}:{i}: {line.strip()[:120]}")
    return hard, soft, skipped


def verdict(hard, soft):
    hard_exec = [h for h in hard if h.startswith("HARD ")]
    hard_inert = [h for h in hard if h.startswith("HARD-INERT")]
    if hard_exec:
        return "BLOCKED", 1
    if hard_inert or soft:
        return "REVIEW", 3
    return "CLEAN", 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("directory", nargs="?")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    if not args.directory:
        print(__doc__)
        sys.exit(2)
    hard, soft, skipped = scan(args.directory)
    word, code = verdict(hard, soft)
    if args.json:
        print(json.dumps({"verdict": word, "exit": code, "hard": hard,
                          "soft": soft[:100], "skipped": skipped}, indent=2))
        sys.exit(code)
    for h in hard:
        print(h)
    for s in soft[:40]:
        print(s)
    for s in skipped:
        print(s)
    if word == "BLOCKED":
        print(f"VERDICT: BLOCKED ({len([h for h in hard if h.startswith('HARD ')])} hard flags in executable code). Do not run this code.")
    elif word == "REVIEW":
        print(f"VERDICT: REVIEW ({len(hard)} hard flags in tests/docs, {len(soft)} soft). "
              "A human reads the flagged spots before anything in this fetch runs. This is not CLEAN.")
    else:
        print("VERDICT: CLEAN (tripwire found nothing; this is not clearance).")
    sys.exit(code)
