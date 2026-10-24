# Da Homi

**The no-excuses skill for AI agents.**

Install Da Homi and your AI stops saying "I can't." When a task needs a tool, package, skill, or workflow the agent does not have, Da Homi searches GitHub, scores what it finds, vets it for safety, fetches it, test-runs it, and finishes the task. It remembers every mistake and your preferences, so it gets sharper the longer it rides with you.

You say the word. It says: "I got you, homie. One second." Then the work comes back done.

## Install

Copy the `da-homi/` folder into your agent's skills directory (for Muse: `~/.claude/skills/` or your workspace custom-skills folder). On first activation it creates its memory file from `assets/DA_HOMI_MEMORY.template.md`.

Optional but recommended: the GitHub CLI (`gh`) authenticated, so searches are not rate-limited. Without it, `scripts/hub_search.py` falls back to the public API.

## What is inside

- `SKILL.md` — the loop, the law, the safety vet, the boundaries. Operating instructions only.
- `HANDOFF.md` — the handoff: search order, loop, harness, boundaries, install.
- `scripts/da_homi.py` — the hunt runner. Writes a run receipt with an explicit outcome. Exit 0 is CONTINUE, exit 3 is a terminal, reportable blocker.
- `scripts/excuse_gate.py` — the excuse gate. Capability claims need a fresh terminal receipt bound to this task. Authority declines pass without a receipt. Exit 0 is PASS, exit 1 is BLOCKED.
- `scripts/vet.py` — the safety tripwire. Scans a fetched repo before anything runs. Exit 0 is CLEAN, exit 3 is REVIEW, exit 1 is BLOCKED, exit 2 is usage. Add `--json` for machine-readable output. A CLEAN verdict is not clearance.
- `scripts/hub_search.py` — standalone GitHub search and ranking (stdlib only). Relevance order, query term overlap, stars, recency, license, fork penalty.
- `scripts/fetch.py` — the fetcher. Clones shallow, records commit SHA and a sha256 manifest, vets automatically, quarantines BLOCKED fetches. Never installs or runs fetched code.
- `scripts/trial.py` — the trial runner. Runs the test with a timeout and a written record. Refuses install-shaped commands unless `--allow-install` is passed explicitly.
- `scripts/route.py` — keyword classifier and routing log. It does not call a model. Escalation is manual until a failure counter is coded.
- `scripts/routing.json` — tiers, task classes, gateway plan.
- `assets/DA_HOMI_MEMORY.template.md` — the mistakes and preferences memory it maintains. Cap: 200 lines.
- `assets/AVATAR.md` — avatar, states, and design.
- `assets/HOUSE.md` — in 19Keys' house: the github skill, hunt engine, and scheduled mode.
- `assets/avatar/popup-demo.html` — avatar pop-up demo.
- `assets/character/` — Da Homi character plates (2D and 3D, v2 lead).
- `tests/test_da_homi.py` — unittest suite for the gates, receipts, vet, scoring, fetch, and trial.

## The boundary that matters

Da Homi expands capability, never authority. Your agent's approval rules for sending, spending, publishing, and deleting stay exactly as they were. Da Homi gets the tool ready. The human still calls the shot.
