#!/usr/bin/env python3
"""Da Homi harness: the fetcher (v2, lighter build).

Clones a candidate shallow, records what was fetched, vets it, and never
installs anything. Install is a separate step the agent takes after the
vet, with install hooks disabled (npm --ignore-scripts, and reading any
setup.py or build file before running it). Fetching is not installing,
and this script never runs code from the fetched repo.

Trusted-repo rules kept in, deliberately light:
1. Receipt bound. By default the repo must appear in a Da Homi run
   receipt's candidates, so the agent cannot pull a repo it never hunted
   and scored. Pass --no-receipt explicitly to skip this, and the skip
   is recorded in the manifest.
2. Never-install list. If the repo matches an entry under "Never install"
   in DA_HOMI_MEMORY.md, the fetch refuses.
3. Vet. BLOCKED fetches are quarantined by renaming the directory to
   <dest>.quarantined, so nothing at the original path can be run by
   accident. REVIEW fetches land normally, flagged: a human reads the
   flagged spots before anything in the fetch runs.

Manifest: commit SHA (git rev-parse HEAD), a sha256 digest per file, the
vet verdict, the receipt path, and the timestamp. Written to
da-homi-cache/manifests/<slug>.json and printed.

Usage:
    python3 fetch.py owner/repo [--dest <dir>] [--receipt <receipt.json>] [--no-receipt] [--url <git-url>]
    --url exists for local testing with a file path or local git repo.

Exit: 0 = fetched (CLEAN or REVIEW), 1 = BLOCKED, quarantined, or refused, 2 = usage.
"""
import hashlib, json, os, subprocess, sys, time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "..", "da-homi-cache")
MANIFESTS = os.path.join(CACHE, "manifests")


def run(cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=120)


def never_install_entries():
    entries = []
    for base in (os.path.join(HERE, ".."), os.getcwd()):
        path = os.path.join(base, "DA_HOMI_MEMORY.md")
        if not os.path.exists(path):
            continue
        try:
            text = open(path).read()
        except Exception:
            continue
        if "Never install" not in text:
            continue
        section = text.split("Never install", 1)[1].split("##", 1)[0]
        for line in section.splitlines():
            line = line.strip().lstrip("- ").strip()
            if line:
                entries.append(line.lower())
    return entries


def manifest_for(dest, repo, commit, verdict, receipt, no_receipt):
    files = {}
    for dirpath, dirnames, filenames in os.walk(dest):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for fn in filenames:
            p = os.path.join(dirpath, fn)
            rel = os.path.relpath(p, dest)
            try:
                h = hashlib.sha256()
                with open(p, "rb") as f:
                    for chunk in iter(lambda: f.read(65536), b""):
                        h.update(chunk)
                files[rel] = h.hexdigest()
            except Exception:
                files[rel] = "unreadable"
    return {
        "homi": "da-homi/fetch-manifest",
        "repo": repo,
        "commit": commit,
        "vet": verdict,
        "receipt": receipt,
        "receipt_skipped": bool(no_receipt),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "files": files,
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("--dest", default="")
    ap.add_argument("--receipt", default="")
    ap.add_argument("--no-receipt", action="store_true")
    ap.add_argument("--url", default="")
    args = ap.parse_args()
    repo = args.repo
    if "/" not in repo:
        print("fetch.py: repo must look like owner/name", file=sys.stderr)
        sys.exit(2)
    dest = args.dest or os.path.join(CACHE, "fetches", repo.replace("/", "_"))
    if os.path.exists(dest):
        print(f"fetch.py: dest already exists: {dest}. Reuse it, do not refetch.", file=sys.stderr)
        sys.exit(2)
    # Rule 1: receipt bound, unless explicitly skipped.
    receipt_candidates = []
    if args.receipt:
        try:
            receipt_candidates = [c.get("repo") for c in json.load(open(args.receipt)).get("candidates", [])]
        except Exception as e:
            print(f"fetch.py: cannot read receipt: {e}", file=sys.stderr)
            sys.exit(2)
        if repo not in receipt_candidates:
            print(f"fetch.py: REFUSED. {repo} is not in receipt {args.receipt}. Hunt and score it first.", file=sys.stderr)
            sys.exit(1)
    elif not args.no_receipt:
        print("fetch.py: REFUSED. No receipt given. Pass --receipt <receipt.json> or --no-receipt explicitly.", file=sys.stderr)
        sys.exit(1)
    # Rule 2: never-install list.
    for entry in never_install_entries():
        if entry and entry in repo.lower():
            print(f"fetch.py: REFUSED. {repo} matches a Never install entry: {entry}", file=sys.stderr)
            sys.exit(1)
    url = args.url or f"https://github.com/{repo}.git"
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    r = run(["git", "clone", "--depth", "1", url, dest])
    if r.returncode != 0:
        print(f"fetch.py: clone failed: {r.stderr.strip()[:300]}", file=sys.stderr)
        sys.exit(1)
    commit = run(["git", "-C", dest, "rev-parse", "HEAD"]).stdout.strip()
    # Rule 3: vet automatically. Never executes anything in the repo.
    vet = run([sys.executable, os.path.join(HERE, "vet.py"), dest, "--json"])
    try:
        verdict = json.loads(vet.stdout).get("verdict", "UNKNOWN")
    except Exception:
        verdict = "UNKNOWN"
    os.makedirs(MANIFESTS, exist_ok=True)
    slug = repo.replace("/", "_")
    manifest_path = os.path.join(MANIFESTS, f"{int(time.time())}-{slug}.json")
    manifest = manifest_for(dest, repo, commit, verdict, args.receipt, args.no_receipt)
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"FETCHED: {repo} @ {commit[:12]} -> {dest}")
    print(f"VET: {verdict}")
    print(f"MANIFEST: {manifest_path}")
    if verdict == "BLOCKED":
        quarantined = dest + ".quarantined"
        os.rename(dest, quarantined)
        print(f"QUARANTINED: renamed to {quarantined}. Nothing at the original path can be run.")
        sys.exit(1)
    if verdict == "REVIEW":
        print("REVIEW: a human reads the flagged spots before anything in this fetch runs.")
    sys.exit(0)
