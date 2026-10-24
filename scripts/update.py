"""Da Homi automatic updates (v2.2).

An installed copy checks a version manifest, and when a newer version is
published it downloads the gated package and swaps its own files. This is
how a private, Hub-gated skill updates without going public: the manifest
and the download live behind the Hub's member gate, and the updater proves
who it is with a member token. Public is not what makes updates work.
Authentication is.

Manifest format (JSON, published at one stable URL by the Hub operator):

    {
      "version": "2.2",
      "download_url": "https://hub.19keys.com/da-homi/da-homi-2.2.zip",
      "sha256": "<sha256 of that zip>",
      "notes": "What changed, in one line."
    }

Rules that never change, whatever the source:
- The manifest and the download may be a local path, a file:// URL, or an
  https:// URL. A token, when given, travels only as an Authorization
  header (or not at all for local files) and is never printed or logged.
- A download whose sha256 does not match the manifest is refused and
  nothing in the install changes.
- A download with no sha256 in the manifest is refused unless
  --allow-unsigned is passed explicitly, and that allowance is printed.
- The live DA_HOMI_MEMORY.md is never overwritten by an update. The
  package ships only a blank template, and the updater skips any
  DA_HOMI_MEMORY.md the package contains. A live memory file is saved
  aside and restored after the swap.
- The da-homi-cache/ directory is never touched by an update: receipts,
  fetches, and manifests stay where they are.
- Every apply makes a full backup beside the install first, named
  <target>.backup-<timestamp>, and prints the restore command.
- The target must look like a Da Homi install (SKILL.md plus
  scripts/da_homi.py) or the updater refuses to touch it.

Usage:
    python3 update.py check --manifest <url-or-path> [--token <token>]
    python3 update.py apply --manifest <url-or-path> [--target <dir>]
        [--token <token>] [--allow-unsigned]

The token may also come from the DA_HOMI_UPDATE_TOKEN environment
variable. --target defaults to the skill folder this script lives in.

Exit codes, check: 0 = up to date, 3 = update available, 2 = usage or
error. Exit codes, apply: 0 = updated (or already up to date, nothing
changed), 1 = refused or failed (nothing changed), 2 = usage or error.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)


def parse_version(text):
    """Dotted version as a tuple of ints, so 2.10 beats 2.2. Junk parts read as 0."""
    parts = []
    for piece in str(text or "").strip().split("."):
        digits = ""
        for ch in piece:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits) if digits else 0)
    return tuple(parts) if parts else (0,)


def compare_versions(a, b):
    """-1 when a < b, 0 when equal, 1 when a > b."""
    pa, pb = parse_version(a), parse_version(b)
    length = max(len(pa), len(pb))
    pa += (0,) * (length - len(pa))
    pb += (0,) * (length - len(pb))
    return (pa > pb) - (pa < pb)


def local_version(target):
    path = os.path.join(target, "VERSION")
    if os.path.exists(path):
        with open(path) as f:
            return f.read().strip()
    return "0"


def fetch_bytes(source, token):
    """Bytes for a source: an existing local path, a file:// URL, or https://."""
    if source.startswith("file://"):
        with open(source[len("file://"):], "rb") as f:
            return f.read()
    if os.path.exists(source):
        with open(source, "rb") as f:
            return f.read()
    if source.startswith("https://"):
        req = urllib.request.Request(source, headers={"User-Agent": "da-homi-update"})
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()
    raise ValueError(f"update.py: cannot fetch source: {source}")


def load_manifest(source, token):
    try:
        data = json.loads(fetch_bytes(source, token).decode("utf-8"))
    except Exception as e:
        raise ValueError(f"update.py: cannot read manifest {source}: {e}")
    if not isinstance(data, dict) or not data.get("version"):
        raise ValueError("update.py: manifest has no version field")
    return data


def is_dahomi_install(target):
    return (os.path.isfile(os.path.join(target, "SKILL.md"))
            and os.path.isfile(os.path.join(target, "scripts", "da_homi.py")))


def package_root(extract_dir):
    """The folder inside an extracted zip that holds SKILL.md, or None."""
    if os.path.isfile(os.path.join(extract_dir, "SKILL.md")):
        return extract_dir
    for name in sorted(os.listdir(extract_dir)):
        candidate = os.path.join(extract_dir, name)
        if os.path.isdir(candidate) and os.path.isfile(os.path.join(candidate, "SKILL.md")):
            return candidate
    return None


def check(manifest_source, token, target):
    manifest = load_manifest(manifest_source, token)
    current, latest = local_version(target), str(manifest["version"]).strip()
    cmp = compare_versions(latest, current)
    print(f"CURRENT: {current}")
    print(f"LATEST: {latest}")
    if manifest.get("notes"):
        print(f"NOTES: {manifest['notes']}")
    if cmp > 0:
        print("UPDATE AVAILABLE")
        return 3
    print("UP TO DATE")
    return 0


def apply_update(manifest_source, token, target, allow_unsigned):
    if not is_dahomi_install(target):
        print(f"update.py: REFUSED. {target} does not look like a Da Homi install "
              "(needs SKILL.md and scripts/da_homi.py).", file=sys.stderr)
        return 1
    try:
        manifest = load_manifest(manifest_source, token)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2
    current, latest = local_version(target), str(manifest["version"]).strip()
    if compare_versions(latest, current) <= 0:
        print(f"UP TO DATE: installed {current}, latest {latest}. Nothing changed.")
        return 0
    if not manifest.get("download_url"):
        print("update.py: REFUSED. Manifest has no download_url.", file=sys.stderr)
        return 1
    try:
        blob = fetch_bytes(str(manifest["download_url"]), token)
    except Exception as e:
        print(f"update.py: download failed: {e}", file=sys.stderr)
        return 1
    expected = manifest.get("sha256")
    if expected:
        actual = hashlib.sha256(blob).hexdigest()
        if actual.lower() != str(expected).lower():
            print(f"update.py: REFUSED. sha256 mismatch: manifest {expected}, "
                  f"downloaded {actual}. Nothing changed.", file=sys.stderr)
            return 1
    elif not allow_unsigned:
        print("update.py: REFUSED. Manifest gives no sha256. Pass --allow-unsigned "
              "explicitly to accept an unsigned package, or publish a sha256.",
              file=sys.stderr)
        return 1
    else:
        print("UPDATE: unsigned package accepted because --allow-unsigned was passed.")
    tmp = tempfile.mkdtemp(prefix="da-homi-update-")
    try:
        zip_path = os.path.join(tmp, "package.zip")
        with open(zip_path, "wb") as f:
            f.write(blob)
        extract_dir = os.path.join(tmp, "extracted")
        try:
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(extract_dir)
        except zipfile.BadZipFile as e:
            print(f"update.py: REFUSED. Download is not a zip: {e}", file=sys.stderr)
            return 1
        root = package_root(extract_dir)
        if root is None:
            print("update.py: REFUSED. Package has no SKILL.md. Nothing changed.",
                  file=sys.stderr)
            return 1
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = f"{target.rstrip(os.sep)}.backup-{stamp}"
        shutil.copytree(target, backup, ignore=shutil.ignore_patterns(
            "da-homi-cache", "__pycache__"))
        memory_path = os.path.join(target, "DA_HOMI_MEMORY.md")
        memory_bytes = None
        if os.path.exists(memory_path):
            with open(memory_path, "rb") as f:
                memory_bytes = f.read()
        for name in os.listdir(target):
            if name == "da-homi-cache":
                continue
            path = os.path.join(target, name)
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
        for name in os.listdir(root):
            if name == "DA_HOMI_MEMORY.md" or name == "__pycache__":
                continue
            src = os.path.join(root, name)
            dst = os.path.join(target, name)
            if os.path.isdir(src):
                shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__"))
            else:
                shutil.copy2(src, dst)
        if memory_bytes is not None:
            with open(memory_path, "wb") as f:
                f.write(memory_bytes)
        print(f"UPDATED: {current} -> {latest}")
        print(f"BACKUP: {backup}")
        print(f"RESTORE: rm -rf {target} && mv {backup} {target}")
        print("PRESERVED: DA_HOMI_MEMORY.md and da-homi-cache/ were left untouched.")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Da Homi automatic updates.")
    sub = ap.add_subparsers(dest="command", required=True)
    for name in ("check", "apply"):
        p = sub.add_parser(name)
        p.add_argument("--manifest", required=True,
                       help="Manifest URL or path (Hub stable URL, file path, or file://).")
        p.add_argument("--target", default=SKILL_ROOT,
                       help="Installed skill folder (default: this skill's folder).")
        p.add_argument("--token", default=os.environ.get("DA_HOMI_UPDATE_TOKEN", ""),
                       help="Member token for a gated manifest/download. "
                            "Also read from DA_HOMI_UPDATE_TOKEN. Never printed.")
    sub.choices["apply"].add_argument("--allow-unsigned", action="store_true",
                                      help="Accept a package whose manifest gives no sha256.")
    args = ap.parse_args(argv)
    try:
        if args.command == "check":
            return check(args.manifest, args.token, args.target)
        return apply_update(args.manifest, args.token, args.target, args.allow_unsigned)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
