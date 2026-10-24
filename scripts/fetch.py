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

v2.1 adds two rules, both additive:
4. Pinning. --pin <ref> takes a tag, a full 40 hex SHA, or a short SHA
   (7 to 39 hex). A tag is cloned with --branch <tag> and matches when
   that tag names the commit checked out. A full SHA is fetched exactly
   (git init, fetch --depth 1 origin <sha>, checkout --detach FETCH_HEAD)
   and must equal HEAD. A short SHA clones the default branch shallow and
   must prefix its tip. A mismatch renames dest to <dest>.pin-mismatch,
   writes the manifest anyway with matched false, and exits 1. --verify
   checks an existing dest against --pin by the same rules, never clones.
   An unpinned fetch works as before and prints the SHA to pin next time.
5. Provenance. The candidate's provenance flags are copied from the
   receipt, git ls-remote --tags counts the remote's tags (no_tags at 0),
   and both go in the manifest. Flags are recorded, never enforced: they
   never refuse a fetch and never change the exit code.

Usage:
    python3 fetch.py owner/repo [--dest <dir>] [--receipt <receipt.json>] [--no-receipt] [--url <git-url>] [--pin <ref>]
    python3 fetch.py owner/repo --pin <ref> --verify [--dest <dir>]
    --url exists for local testing with a file path or local git repo.

Exit: 0 = fetched (CLEAN or REVIEW), 1 = BLOCKED, quarantined, or refused, 2 = usage.
      1 also = PIN MISMATCH. With --verify: 0 = PIN OK, 1 = PIN DRIFT, 2 = no dest to verify.
"""
import hashlib, json, os, re, subprocess, sys, time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "..", "da-homi-cache")
MANIFESTS = os.path.join(CACHE, "manifests")


def run(cmd, cwd=None, timeout=120):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)


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


def pin_kind(ref):
    """tag, sha (40 hex), or short_sha (7 to 39 hex). An all hex ref reads as a SHA."""
    if re.fullmatch(r"[0-9a-fA-F]{40}", ref):
        return "sha"
    if re.fullmatch(r"[0-9a-fA-F]{7,39}", ref):
        return "short_sha"
    return "tag"


def resolve_head(dest):
    """The commit checked out in dest, or "" when HEAD does not resolve."""
    r = run(["git", "-C", dest, "rev-parse", "HEAD"])
    sha = r.stdout.strip()
    return sha if r.returncode == 0 and re.fullmatch(r"[0-9a-f]{40,64}", sha) else ""


def tag_commit(dest, tag):
    r = run(["git", "-C", dest, "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}^{{commit}}"])
    return r.stdout.strip() if r.returncode == 0 else ""


def pin_matches(kind, ref, resolved, dest):
    """One rule set, used after a clone and by --verify."""
    if not resolved:
        return False
    if kind == "sha":
        return resolved == ref.lower()
    if kind == "short_sha":
        return resolved.startswith(ref.lower())
    # A tag matches when that tag names the commit checked out, so a branch
    # name passed as --pin cannot pass for a pin, and --verify means something.
    return tag_commit(dest, ref) == resolved


def remote_tag_count(url):
    """Tags on the remote, or None when ls-remote fails. Tolerated, never a refusal."""
    try:
        r = run(["git", "ls-remote", "--tags", url], timeout=60)
    except Exception:
        return None
    if r.returncode != 0:
        return None
    # An annotated tag is listed twice: the tag, then its peeled <tag>^{} line.
    return sum(1 for line in r.stdout.splitlines() if "\t" in line and not line.endswith("^{}"))


def manifest_for(dest, repo, commit, verdict, receipt, no_receipt, pin=None, provenance=None):
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
        "pin": pin,
        "provenance": provenance,
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
    ap.add_argument("--pin", default="")
    ap.add_argument("--verify", action="store_true")
    args = ap.parse_args()
    repo = args.repo
    if "/" not in repo:
        print("fetch.py: repo must look like owner/name", file=sys.stderr)
        sys.exit(2)
    pin = args.pin.strip()
    kind = pin_kind(pin) if pin else None
    if args.verify and not pin:
        print("fetch.py: --verify needs --pin <ref> to compare against.", file=sys.stderr)
        sys.exit(2)
    dest = args.dest or os.path.join(CACHE, "fetches", repo.replace("/", "_"))
    if args.verify:
        # Rule 4, checked in place: never clones, never touches the network.
        if not os.path.exists(dest):
            print(f"fetch.py: nothing to verify, dest does not exist: {dest}", file=sys.stderr)
            sys.exit(2)
        commit = resolve_head(dest)
        ok = pin_matches(kind, pin, commit, dest)
        note = f"; tag {pin} names {tag_commit(dest, pin) or 'no commit in dest'}" if kind == "tag" else ""
        print(f"{'PIN OK' if ok else 'PIN DRIFT'}: requested {kind} {pin}, resolved {commit or 'none'} in {dest}{note}")
        sys.exit(0 if ok else 1)
    if os.path.exists(dest):
        print(f"fetch.py: dest already exists: {dest}. Reuse it, do not refetch.", file=sys.stderr)
        sys.exit(2)
    # Rule 1: receipt bound, unless explicitly skipped.
    receipt_candidates, receipt_entry = [], {}
    if args.receipt:
        try:
            entries = json.load(open(args.receipt)).get("candidates", [])
            receipt_candidates = [c.get("repo") for c in entries]
        except Exception as e:
            print(f"fetch.py: cannot read receipt: {e}", file=sys.stderr)
            sys.exit(2)
        if repo not in receipt_candidates:
            print(f"fetch.py: REFUSED. {repo} is not in receipt {args.receipt}. Hunt and score it first.", file=sys.stderr)
            sys.exit(1)
        receipt_entry = entries[receipt_candidates.index(repo)]
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
    note = ""
    if kind == "sha":
        # Rule 4: fetch exactly that commit. GitHub serves reachable SHAs; a
        # local fixture needs uploadpack.allowAnySHA1InWant. A failed fetch
        # leaves HEAD unresolved, which reads as PIN MISMATCH below.
        r = run(["git", "init", dest])
        if r.returncode == 0:
            r = run(["git", "-C", dest, "remote", "add", "origin", url])
        if r.returncode != 0:
            print(f"fetch.py: clone failed: {r.stderr.strip()[:300]}", file=sys.stderr)
            sys.exit(1)
        r = run(["git", "-C", dest, "fetch", "--depth", "1", "origin", pin.lower()])
        if r.returncode == 0:
            r = run(["git", "-C", dest, "checkout", "--detach", "FETCH_HEAD"])
        if r.returncode != 0:
            note = f" (the pinned commit could not be fetched: {' '.join(r.stderr.split())[:200]})"
    else:
        r = run(["git", "clone", "--depth", "1", *(["--branch", pin] if kind == "tag" else []), url, dest])
        if r.returncode != 0:
            print(f"fetch.py: clone failed: {r.stderr.strip()[:300]}", file=sys.stderr)
            sys.exit(1)
    commit = resolve_head(dest)
    matched = pin_matches(kind, pin, commit, dest) if kind else None
    if matched is False and kind == "tag":
        note = f" (tag {pin} names {tag_commit(dest, pin) or 'no commit in the fetch'})"
    # Rule 5: provenance flags ride along from the receipt. Recorded, never enforced.
    prov = receipt_entry.get("provenance")
    from_receipt = isinstance(prov, dict) and isinstance(prov.get("flags"), list)
    flags = {str(f) for f in prov["flags"]} if from_receipt else set()
    remote_tags = remote_tag_count(url)
    if remote_tags == 0:
        flags.add("no_tags")
    provenance = {"flags": sorted(flags), "source": "receipt" if from_receipt else "none",
                  "remote_tags": remote_tags}
    # Rule 3: vet automatically. Never executes anything in the repo.
    vet = run([sys.executable, os.path.join(HERE, "vet.py"), dest, "--json"])
    try:
        verdict = json.loads(vet.stdout).get("verdict", "UNKNOWN")
    except Exception:
        verdict = "UNKNOWN"
    os.makedirs(MANIFESTS, exist_ok=True)
    slug = repo.replace("/", "_")
    manifest_path = os.path.join(MANIFESTS, f"{int(time.time())}-{slug}.json")
    pin_record = {"requested": pin or None, "kind": kind, "resolved": commit or None, "matched": matched}
    manifest = manifest_for(dest, repo, commit, verdict, args.receipt, args.no_receipt,
                            pin=pin_record, provenance=provenance)
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
    if matched is False:
        print(f"PIN MISMATCH: requested {kind} {pin}, resolved {commit or 'none'}{note}")
    else:
        print(f"FETCHED: {repo} @ {commit[:12]} -> {dest}")
        if kind:
            print(f"PIN: {kind} {pin} resolved {commit[:12]} MATCH")
        else:
            print(f"PIN: none (unpinned fetch; reproduce it next time with --pin {commit[:12] or '<sha>'})")
    print(f"PROVENANCE: {', '.join(provenance['flags']) or 'none flagged'}")
    print(f"VET: {verdict}")
    print(f"MANIFEST: {manifest_path}")
    if matched is False:
        # Rule 4: not the pinned commit, so it moves off the path like a quarantine.
        aside = dest + ".pin-mismatch"
        if os.path.exists(aside):
            aside += f".{int(time.time())}"
        os.rename(dest, aside)
        print(f"MOVED ASIDE: renamed to {aside}. It is not the pinned commit; nothing at the original path can be run.")
        sys.exit(1)
    if verdict == "BLOCKED":
        quarantined = dest + ".quarantined"
        os.rename(dest, quarantined)
        print(f"QUARANTINED: renamed to {quarantined}. Nothing at the original path can be run.")
        sys.exit(1)
    if verdict == "REVIEW":
        print("REVIEW: a human reads the flagged spots before anything in this fetch runs.")
    sys.exit(0)
