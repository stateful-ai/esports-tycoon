# Synthetic players

A synthetic player is a language model with a browser, a persona, and a
notebook. It opens the shipped web UI, looks at the actual pixels, plays the
campaign by clicking, and files structured findings about what it experienced.

## Why this exists

The repo already had two agent-facing surfaces, and both are blind:

* `manager/decision_env.py` hands an agent a JSON observation and a legal-action
  mask. Perfect for RL. It cannot tell you that a screen is unreadable.
* `mcp/play_server.py` makes the whole campaign agent-playable over MCP. It
  routes through the same decision contract — so it, too, never touches the UI.

Everything a player actually complains about lives in the gap between those and
the pixels: jargon used before it is explained, a number with no units, a dial
whose effect is invisible, a modal that eats a click, a screen that renders
empty. No API test can see any of it.

The motivating example is in the repo history. `app.js` imported preact and htm
from `esm.sh` at page load. With no internet the module graph never resolved and
the game rendered as an empty shell — chrome and tabs painted, `#view` blank.
**Every API test in the suite passed.** A synthetic player finds that in one
step, because the first thing it does is look.

## The pieces

| Piece | What it is |
|---|---|
| `src/esports_sim/playtest/dom.py` | DOM snapshot → readable digest. Pure; unit-tested without a browser. |
| `src/esports_sim/playtest/session.py` | The body: boots the game, drives Chromium, screenshots every step. |
| `src/esports_sim/playtest/findings.py` | The notebook: append-only JSONL with a fixed severity/area vocabulary. |
| `src/esports_sim/playtest/personas.py` | The character sheets. |
| `src/esports_sim/playtest/control.py` | An HTTP control plane so one live browser survives across many short commands. |
| `scripts/playtest_daemon.py` | Start a session (game + browser + control port). |
| `scripts/play.py` | The agent's hands: one command per action. |
| `scripts/run_synthetic_players.py` | Launch a session and print the brief an agent plays under. |
| `scripts/playtest_report.py` | Merge every persona's findings into one prioritised report. |

## Running one

```bash
python scripts/run_synthetic_players.py --list
python scripts/run_synthetic_players.py --persona first-timer --start
```

That prints the control port and the brief. From there the agent plays:

```bash
python scripts/play.py --persona first-timer look
python scripts/play.py --persona first-timer tab club
python scripts/play.py --persona first-timer subtab "Development"
python scripts/play.py --persona first-timer advance --weeks 1
python scripts/play.py --persona first-timer note confusing club "Form has no scale" \
    --detail "Form shows 58 with no units and no indication whether high is good." \
    --repro "Club > Squad, look at the Form column."
python scripts/play.py --persona first-timer stop
```

Every command prints a digest **and** writes a screenshot the agent is expected
to open. Artifacts land under `runs/synthetic-players/<persona>/`:

```
screens/       one PNG per step
journal.jsonl  every action + the observation it produced
findings.jsonl the output
session.json   control port, game url, the brief
server.log     the game server's own output
```

Then merge:

```bash
python scripts/playtest_report.py --out runs/synthetic-players/report.md
python scripts/playtest_report.py --gate blocker   # exit 1 if a blocker survived
```

## Design rules

**Everything goes through the UI.** Driving the API would be faster and
steadier and would test a surface no human uses. `play.py api` exists only for
*cross-checking* what the UI was given — a finding is only real if it is
reachable by clicking.

**Every action returns an observation.** Act-then-look is one call, so an agent
cannot report on a screen it did not see.

**The harness never claims success it did not verify.** `new_campaign` waits for
the lobby to actually close; `advance_week` checks the week actually moved. An
early version reported `ok` while still sitting in the lobby, and that is worse
than a crash: an agent then attributes ten screens to a campaign that does not
exist.

**One visibility rule.** `dom.VISIBLE_JS` is injected everywhere. The closed
profile overlay is deliberately left at `display: flex; opacity: 0;
pointer-events: none` so it can fade out (`profile.css`), so a check that only
looks at `display` calls that closed modal "open" — blocking Advance Week and
hijacking the root for every later click. Both bugs happened during
development; `test_playtest_harness.py` pins the fix.

**Findings are append-only and never deduped at write time.** Two personas
hitting the same wall is the strongest signal in the file. `aggregate()` groups
on read instead, and reports the count and who hit it.

**Personas must disagree.** Five agents with the same watch-list are one
averaged reviewer. `test_personas_disagree_about_what_matters` asserts no two
personas share a watch-for item.

## Tests

| Lane | Command | Needs |
|---|---|---|
| Harness unit tests | `pytest -q tests/test_playtest_harness.py` | nothing |
| Frontend asset guard | `pytest -q tests/test_web_assets.py` | nothing |
| Browser integration | `pytest -q -m playtest` | Chromium |

The browser lane boots the real server, opens the real UI, and asserts every
tab renders with content, no tab raises a JavaScript error, nothing is fetched
from outside the page's own origin, and a week can be advanced end to end. It
is marked `slow` and skips itself when Chromium is missing, so it never breaks
a machine that cannot run it. Point `$PLAYTEST_CHROMIUM` at a binary to
override discovery.
