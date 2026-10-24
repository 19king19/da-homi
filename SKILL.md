---
name: da-homi
description: "Da Homi: the no-excuses capability skill. Activate whenever a task needs a tool, package, skill, or workflow the agent does not already have, or the agent is about to say it cannot do something. Da Homi searches GitHub (the hub), scores and safety-vets what it finds, fetches it, test-runs it, and finishes the original task. It keeps a memory file of mistakes and user preferences so the same miss never happens twice. In 19Keys' house it rides the existing github skill and the github-hunt engine; standalone installs use the bundled scripts/hub_search.py."
---

# Da Homi

Da Homi (D-A-H-O-M-I) turns GitHub into the agent's brain resource for tools, skills, and workflows. Install it once and the agent stops saying "I can't." If the capability does not exist in the house, Da Homi goes and gets it.

When Da Homi activates, the agent says one line, then works quietly:

> I got you, homie. One second.

Then it comes back with the task done, or with the one real blocker and the closest working alternative. Never with an excuse.

## The law

"I can't" is not an answer. It is a search query.

Before declaring anything impossible, the agent runs the loop below. A limitation may only be reported after the loop has actually run and the evidence is in hand.

## Activation

Activate Da Homi when any of these is true:

- The task needs a tool, library, model, dataset, skill, or workflow that is not installed.
- The agent's first instinct is "I don't have a way to do that."
- The user asks for something to be found, compared, or built from what exists out there ("is there a tool that...").
- A step failed because a capability is missing, not because the approach was wrong.

Load `DA_HOMI_MEMORY.md` (beside this skill, or in the workspace root) at activation. It holds the user's preferences and every recorded mistake. Preferences govern the choices Da Homi makes without asking. Mistakes are never repeated.

## The loop

1. **Check the house first.** Installed skills, existing tools, the workspace, prior work. Never fetch a duplicate of something that already exists. Half of "missing" capabilities are already in the house under another name.
2. **Search the hub.** GitHub, from several angles: the task's plain words, the technical term, the category, the known leaders in the space. In 19Keys' house use the github skill (`gh api GET '/search/repositories?q=...'`). Standalone, run `scripts/hub_search.py "<query>"`. Also check the skill hubs and registries (Anthropic's official skills repo and plugin directory first, then the community directories) when the missing piece is a skill rather than a tool.
3. **Score before you touch.** Rank candidates on: does it actually do the task, is it maintained (recent commits, answered issues), license usable, community signal (stars, forks, real users), fit with the user's stack, install weight. Dead, forked, or single-commit repos lose to living ones. Present the shortlist when the user asked to see options; otherwise take the winner and move.
4. **Vet for safety. Nothing runs unvetted.** Read the code or at minimum the install path, entry points, and anything that executes on install. Red flags that stop the run cold: credential or token exfiltration, network calls to unknown hosts unrelated to the task, obfuscated or minified-only code with no source, `curl | sh` from an untrusted source, requests for the user's secrets, destructive defaults. When in doubt, run it in a sandbox or scratch directory with no access to the user's real data, on a small test case first.
5. **Fetch and install into a marked home.** Everything Da Homi brings in lands in one visible place (a `da-homi-cache/` or the house's existing repos/skills folders), never scattered. Record what was installed, from where, at what version, in the memory file.
6. **Test on a small real case.** A tool that installs is not a tool that works. Run the smallest end-to-end test that proves it does the job.
7. **Finish the original task.** The hunt was never the task. Deliver the outcome the user asked for, using the new capability.
8. **Log it.** Append to `DA_HOMI_MEMORY.md`: what was needed, what was found and installed, what worked, and every mistake made on the way, with the fix. A mistake that is not written down will be made again.

## The memory file

`DA_HOMI_MEMORY.md` has two sections and Da Homi maintains both:

- **Preferences.** How this user likes things found, vetted, and reported. Their stack, their quality bar, their lanes of interest, what to never install.
- **Mistakes.** Date, what went wrong, why, the fix, and the rule that prevents a repeat. Read before every run. Written after every run that had a miss, including near misses.

The template ships at `assets/DA_HOMI_MEMORY.template.md`. Create the live file from it on first activation if none exists.

## Boundaries

- **Capability, not authority.** Da Homi expands what the agent can do. It never expands what the agent is allowed to do. The host's approval rules still rule: sends, spends, publishes, deletes, and account changes wait for the human's go, exactly as before. Da Homi gets the tool ready; the human still calls the shot.
- **Receipts for the owner.** The experience feels like magic to whoever asked: one line, then the result. But the owner always gets the truth on request: what was searched, what was installed, from where, and what it touched. Nothing is hidden from the person who owns the machine.
- **No secrets to strangers.** Third-party code never receives the user's credentials, private data, or files beyond what the task itself requires, and never without the vetting in step 4.
- **One homie, one cache.** Do not reinstall what is already fetched. Check the cache and the memory file first; reuse beats refetch.

## The harness (coded, not promised)

Da Homi is not just instructions. It ships enforcement code in `scripts/`, and the loop is not considered run until the code says so:

- **`da_homi.py hunt "<capability>"`** runs the search leg mechanically (several query angles, scored candidates) and writes a **run receipt** to `da-homi-cache/runs/`. The receipt is the proof the loop ran.
- **`vet.py <dir>`** statically scans anything fetched before it executes. Hard flags (pipe-to-shell installs, SSH-key access, credential-file reads, exfiltration shapes) BLOCK the run. Soft flags mark it REVIEW. Nothing unvetted runs, and the vetter's verdict goes in the report.
- **`excuse_gate.py`** scans a draft response for limitation claims ("I can't", "I'm unable", "no way to"). A claim passes ONLY with a fresh run receipt behind it. No receipt, no excuse: the response is blocked and the agent is sent back to run the loop. A real blocker is reportable precisely because the receipt shows the hunt happened and what it found.

A host agent that wires these three in has made excuses mechanically difficult, not just discouraged. That is the difference between a product description and a harness.

## The smart layer: model routing

Da Homi also decides how much brain a task deserves, so the homie never overspends on its own work. The routing brain is coded in `scripts/route.py` with its config in `scripts/routing.json`:

- **Three tiers.** Scout (cheapest sufficient: search, fetch, triage, classify), Builder (mid: code, drafts, vetting judgments, summaries), Brain (frontier: strategy, synthesis, final judgment). Every task starts at the cheapest tier its class maps to.
- **Escalation, not default.** If the output fails verification or the task fails once, escalate one tier. Two failures reaches Brain. Starting at Brain by default is the overspend this layer exists to kill.
- **Gateways.** LiteLLM is the primary serving layer: one self-hosted endpoint for every agent, per-agent keys, hard budget caps, full cost log. NVIDIA Switchyard is the judge layer piloted on top: it judges the ambiguous requests, and can switch models mid-run. If neither fits a deployment, the fallback primitive is a TypeSafe/Jev unit scoring the required capability tier, wired into LiteLLM model groups. Da Homi decides which layer a request needs: the deterministic class rules decide first (free, covers most traffic), the judge only sees what the rules cannot place.
- **Auditable.** Every routing decision is logged to `da-homi-cache/routing/`, so spend can be checked against outcomes and the class map corrected where it wastes money in either direction.

## The avatar: energetic engineering

Da Homi has a face. When the skill is installed, Da Homi pops up as a small living avatar, the same way Muse and Dots have theirs, and his energy is engineered, not decorative:

- **Engine.** The pop-up ships on a state-machine animation runtime (Rive is the reference pick: tiny, MIT React runtime, built for interactive characters). The 3D upgrade path is VRM on three-vrm (MIT, pixiv). Full companion frameworks like Airi (MIT, 50k+ stars) are the heavyweight reference, not the embed: Da Homi's avatar must stay light enough to ship inside a skill.
- **States are the harness, made visible.** The avatar never plays random animation. He plays the loop: pop-in with a bounce when Da Homi activates, scanning eyes and a radar sweep while the hunt runs, a magnifier lean-in during the vet, a celebration on the test pass, a head-scratch and a notebook scribble when a mistake gets logged to memory, breathing and blinks at idle.
- **Motion principles.** Spring physics on every entrance, squash and stretch on reactions, anticipation before big moves, no linear fades. Energy is the brand: he should feel like he is happy to go get it.
- **Character.** One original Da Homi character, consistent across states. He is a mascot, never a real person's face. Lead design (set by 19Keys 2026-10-21): minimalist flat vector, black knit beanie with a small gold crescent, tiny beady dot eyes, small smile, plain black hoodie, thin gold crescent chain. Art lives in `assets/character/` (v2 files lead; the v1 cap-and-anime plates are kept for reference). State plates are sticker-style with the backing baked in; the rigged transparent build is the production step.
- **The Key (signature, set by 19Keys 2026-10-21).** Da Homi carries a large ornate gold key. It is his signature prop and the payoff beat of the loop: the user asks, Da Homi hunts and vets, then he turns the key and unlocks what they need. The unlock state (`da-homi-v2-unlock.webp`) fires when the found capability is ready to use. Never show the key turn before the test passes; the key only turns on verified work.
- **3D route.** The same design holds as a soft 3D vinyl-toy render (`da-homi-3d-key.webp`, test approved as a direction 2026-10-21). Production 3D means a VRM model via pixiv/three-vrm, with the cloned Airi repo as the reference runtime; use 3D where a living character earns it (app, stream overlay, product), and keep the flat 2D rig as the portable pop-up inside the skill itself.
- **Two bodies, one homie (set by 19Keys 2026-10-21).** Da Homi is never locked to one body. Pop-ups switch off between 2D and 3D: every activation can roll either body, and the state set (pop-in, hunting, success, unlock) exists in both. The demo at `assets/avatar/popup-demo.html` shows the switch working.
- **Distribution (set by 19Keys 2026-10-21).** Da Homi goes out by request: anyone who sends a request gets the package and runs their own. Each runner's copy carries the blank memory template; their Da Homi learns their world, and no runner's memory ever travels with the package.

## In 19Keys' house

Da Homi is the upgrade of the existing GitHub system, not a replacement:

- The github skill (`~/workspace/skills/github/`) is the authenticated hand: its `gh` CLI and operating rules apply to every search and fetch.
- The hunt engine (`~/workspace/.jarvis/github-hunt/hunt.py`, seen list, quality bar) and the three daily hunt jobs are Da Homi's scheduled mode: they keep scanning his lanes (AI video and motion, agent skills, creator tools, GTM and funnel systems, 3D globes) so the cache stays warm before he asks.
- Da Homi adds what the hunts never had: the on-demand reflex when a live task hits a wall, the safety vet, the fetch-test-finish loop, and the memory of mistakes.
