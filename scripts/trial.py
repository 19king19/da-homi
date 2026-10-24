#!/usr/bin/env python3
"""Da Homi harness: the trial runner (v2, lighter build).

Runs the smallest end-to-end test that proves a fetched tool works, with
a timeout and a written record. It does not sandbox the run by default:
legitimate tools need their environment, their auth, and network to prove
they work, and scrubbing all three would false fail them. Pass --fresh-home
for a clean HOME when the test does not need the real one.

Install hooks are the one thing this script refuses by default. A trial
command containing pip install, npm install, a setup.py install, or a
pipe-to-shell install is refused unless --allow-install is passed
explicitly, and the allowance is recorded in the trial record. That keeps
install hooks disabled without human-gating every install: the agent
reads the install path first, then passes the flag on purpose.

Usage:
    python3 trial.py <dir> -- <command...> [--timeout 60] [--record <path>] [--fresh-home] [--allow-install]

Exit: 0 = test passed, 1 = test failed or install refused, 3 = timeout, 2 = usage.
"""
import argparse, json, os, subprocess, sys, tempfile, time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "..", "da-homi-cache", "trials")

INSTALL_SHAPES = ["pip install", "npm install", "setup.py install", "curl |", "wget |", "| sh", "| bash"]


if __name__ == "__main__":
    # Options go before the "--", the test command goes after it. argparse
    # REMAINDER would swallow the options, so split on "--" first.
    argv = sys.argv[1:]
    if "--" in argv:
        opt_argv, cmd = argv[:argv.index("--")], argv[argv.index("--") + 1:]
    else:
        opt_argv, cmd = argv, []
    ap = argparse.ArgumentParser()
    ap.add_argument("directory")
    ap.add_argument("--timeout", type=int, default=60)
    ap.add_argument("--record", default="")
    ap.add_argument("--fresh-home", action="store_true")
    ap.add_argument("--allow-install", action="store_true")
    args = ap.parse_args(opt_argv)
    if not cmd or not os.path.isdir(args.directory):
        print(__doc__)
        sys.exit(2)
    joined = " ".join(cmd)
    install_shape = any(s in joined for s in INSTALL_SHAPES)
    if install_shape and not args.allow_install:
        print("trial.py: REFUSED. Trial command looks like an install. Read the install path first, "
              "then pass --allow-install explicitly if it is safe.")
        sys.exit(1)
    env = dict(os.environ)
    tmp_home = None
    if args.fresh_home:
        tmp_home = tempfile.mkdtemp(prefix="da-homi-home-")
        env["HOME"] = tmp_home
    started = time.time()
    try:
        r = subprocess.run(cmd, cwd=args.directory, env=env, capture_output=True, text=True, timeout=args.timeout)
        outcome, code = ("passed" if r.returncode == 0 else "failed"), (0 if r.returncode == 0 else 1)
        stdout, stderr = r.stdout[-4000:], r.stderr[-4000:]
    except subprocess.TimeoutExpired as e:
        outcome, code = "timeout", 3
        stdout, stderr = (e.stdout or b"").decode(errors="ignore")[-4000:] if isinstance(e.stdout, bytes) else (e.stdout or "")[-4000:], ""
    except FileNotFoundError as e:
        outcome, code = "failed", 1
        stdout, stderr = "", f"command not found: {e.filename}"
    record = {
        "homi": "da-homi/trial-record",
        "directory": args.directory,
        "command": cmd,
        "outcome": outcome,
        "exit": code,
        "timeout_seconds": args.timeout,
        "fresh_home": bool(tmp_home),
        "allow_install": bool(args.allow_install),
        "duration_seconds": round(time.time() - started, 2),
        "at": datetime.now(timezone.utc).isoformat(),
        "stdout": stdout,
        "stderr": stderr,
    }
    os.makedirs(CACHE, exist_ok=True)
    path = args.record or os.path.join(CACHE, f"{int(time.time())}.json")
    with open(path, "w") as f:
        json.dump(record, f, indent=2)
    print(f"TRIAL: {outcome} (exit {code})")
    print(f"RECORD: {path}")
    if stdout:
        print(stdout[-1000:])
    sys.exit(code)
