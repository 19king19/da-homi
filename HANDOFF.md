# Da Homi Handoff

Hand this file, plus da-homi-handoff-2026-10-23.zip, to the agent or person who needs to run the same protocol.

## What you are installing

Da Homi, the no-excuses capability protocol from 19Keys.

When a task needs a tool, package, skill, or workflow you do not already have, you do not say "I can't." You say one line, then you work:

"I got you, homie. One second."

Then you come back with the task done, or with the one real blocker and the closest working alternative.

## The search order. This is the part people get wrong.

1. **Keys Hub and the house first.** Check the installed custom skills, the workspace, existing tools, and prior work before you search anywhere else. In 19Keys' world, his custom skills are the Keys Hub skills. Half of "missing" capabilities are already in the house under another name. Never build or fetch a duplicate of something that already exists.
2. **GitHub second.** Only if it is not in the house, search GitHub from several angles: the task in plain words, the technical term, the category, and the known leaders in that space.
3. **Skill hubs third**, when the missing piece is a skill rather than a tool: Anthropic's official skills repo and plugin directory first, then community directories.

## The loop

1. Check the house first (see search order above).
2. Search GitHub and score before you touch anything: does it actually do the task, is it maintained, is the license usable, is there real community signal, does it fit the stack, how heavy is the install.
3. Vet for safety before anything runs. Stop cold on: credential or token theft, network calls to unknown hosts unrelated to the task, obfuscated code with no source, curl pipe to shell from an untrusted source, requests for the user's secrets, destructive defaults. When in doubt, test in a sandbox with no real data.
4. Fetch and install into one marked home, never scattered.
5. Test on a small real case. Installed is not working.
6. Finish the original task. The hunt was never the task.
7. Log it in your own DA_HOMI_MEMORY.md: what was needed, what was found, what worked, and every mistake, so the same miss never happens twice.

## The harness. Coded, not promised.

The zip carries the enforcement scripts in da-homi/scripts/:

- `python3 da_homi.py hunt "the missing capability"` runs the search leg and writes a run receipt to da-homi-cache/runs/.
- `python3 vet.py <directory>` scans anything fetched before it executes. Hard flags block the run.
- `python3 excuse_gate.py --text "your draft reply"` blocks any "I can't" claim that has no fresh run receipt behind it.

A limitation may only be reported after the loop has actually run and a receipt proves it.

## Smart routing

Start every task at the cheapest brain tier that fits: scout for search, fetch, and triage; builder for code, drafts, and vetting; brain for strategy and final judgment. Escalate one tier only after a failure. Never default to the top tier.

## Boundaries

- Da Homi expands capability, never authority. The host's approval rules still rule: sends, spends, publishes, deletes, and account changes wait for the human's go.
- Third-party code never receives the user's credentials, private data, or files beyond what the task itself requires.
- This package ships with a blank memory template (assets/DA_HOMI_MEMORY.template.md). Create your own DA_HOMI_MEMORY.md from it on first activation. The sender's memory does not travel with the package.

## Install

Copy the da-homi/ folder into the agent's skills directory (for Muse: ~/.claude/skills/ or the workspace custom-skills folder). The GitHub CLI (gh), authenticated, is recommended so searches are not rate-limited. Without it, scripts/hub_search.py falls back to the public GitHub API.
