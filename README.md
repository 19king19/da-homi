# Da Homi

**The no-excuses skill for AI agents.**

Install Da Homi and your AI stops saying "I can't." When a task needs a tool, package, skill, or workflow the agent does not have, Da Homi searches GitHub, scores what it finds, vets it for safety, fetches it, test-runs it, and finishes the task. It remembers every mistake and your preferences, so it gets sharper the longer it rides with you.

You say the word. It says: "I got you, homie. One second." Then the work comes back done.

## Install

Copy the `da-homi/` folder into your agent's skills directory (for Muse: `~/.claude/skills/` or your workspace custom-skills folder). On first activation it creates its memory file from `assets/DA_HOMI_MEMORY.template.md`.

Optional but recommended: the GitHub CLI (`gh`) authenticated, so searches are not rate-limited. Without it, `scripts/hub_search.py` falls back to the public API.

## What is inside

- `SKILL.md` — the loop, the law, the safety vet, the boundaries.
- `scripts/hub_search.py` — standalone GitHub search and ranking (stdlib only).
- `assets/DA_HOMI_MEMORY.template.md` — the mistakes and preferences memory it maintains.

## The boundary that matters

Da Homi expands capability, never authority. Your agent's approval rules for sending, spending, publishing, and deleting stay exactly as they were. Da Homi gets the tool ready. The human still calls the shot.
