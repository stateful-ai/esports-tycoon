---
type: stream_doc
title: playtest_m0_1
stream: esports-tycoon
updated: '2026-05-25T21:30:00Z'
summary: Fresh-clone Week-6 playtest verdict for the M0.1 zero-API slice. PASS
  with one fix logged (Chirper posts not conditioned on per-player match outcome).
---

# Playtest gate — M0.1 zero-API slice

**Verdict: PASS (with 1 fix logged).** The milestone closes.

The fresh-clone playthrough confirms what M0.1 is supposed to prove: from a
fresh checkout, with no API key, no network, and no GPU, a tester reaches a
screenshot-ready recap in which **the game cites a real precedent memory by
ID** for every reaction it surfaces. The "remembered me" beat lands.

## How it was played

- Clone: `git clone <this repo> /tmp/esports-tycoon-playtest`
- Branch: `task/task_20260525T203300Z_3835b7` @ `f7d50eb` (WorldState referential-integrity)
- Install: `pip install -e .[web]` — Python 3.12.3 — clean.
- Engine: templated mode (default; `ESPORTS_TYCOON_CONTENT_BACKEND` unset).
- Network during the slice: **none.** No outbound connections observed.

Two paths were exercised end-to-end:

1. **Headless runner**, two distinct decision branches:
   - `--practice defaults --stance default` → slice `wk6-6dbefcb76d21`
   - `--practice comms    --stance disciplined` → slice `wk6-010d83545e46`
   Each wrote `recap.md`, `feed.snapshot.html`, and `events.jsonl` under `runs/<slice_id>/`.
2. **Web app** (`python -m esports_tycoon play --port 8769`), driven via cookie-jar:
   `/` → `/practice` (POST `defaults`) → `/prematch` (POST team talk) →
   `/match` → `/fallout` (POST fallout post) → `/recap`, `/feed`, `/healthz`
   (`{"backend":"templated","status":"ok"}`). All 200/302 as expected.

## Coherence — what works

- **The "game remembered" beat lands.** The recap's *What the room remembered*
  section closes the loop: 6/6 cited memories resolve back to entries in the
  canned log (`mem:rook:echo_mind_games_w4`, `mem:coyote:needs_silence_w4`,
  `mem:pixie:coyote_silence_feud_w4`, etc.). Grounding rate: **100% (6/6)**.
- **Cast voices survive across decision branches.** Rook reads as a stoic IGL
  (`"that's on me. we go again."`), Vex blame-shifts in character
  (`"hard to win a round that's lost before i get there. but sure."`), Sable is
  one syllable (`"next."`), Pixie performs for the camera, Coyote broods. Same
  voices in both branches — the tone-and-cast lock is paying off in actual
  play.
- **Decisions surface and route.** Practice-focus + tactical stance change
  the MVP, the came-apart line, and the morale deltas. The team-talk text
  surfaces in the half-time IGL ack via stance routing. The fallout post
  surfaces as the team handle's Chirper line.
- **Recap is screenshot-shaped.** Tight one-page layout: fixture → your week →
  the match → standouts → morale → Chirper → *What the room remembered*. A
  founder can hand this to someone and they will read it top-to-bottom.
- **Determinism contract holds.** `slice_id` is content-addressed; the headless
  rerun against the same inputs lands the same `wk6-…` folder.

## Coherence — friction observed

1. **(Fix logged.)** Player Chirper posts are conditioned only on the *team*
   win/loss boolean, not on the *player's own performance this match*. After a
   close loss in which Pixie clutches and is named MVP, her post is still a
   loss-mode line (`"that one stings but i love this team…"`). The grounded
   precedent attached to the post is sentiment-correct for the team result, but
   the player's *voice in this specific match* is not. Source:
   `esports_tycoon/content/templated.py:218` (`_CHIRPER_LINES[(register, won)]`).
   See **Fix #1** below.
2. **(Observation, not a fix.)** In both branches against `apex_foundry` on
   Helix the result was 6–13. The decision surface changed the *texture* of
   the match (who carried, who came apart, what was remembered) but not the
   W/L. Reading the rivals file this looks intentional — apex_foundry is the
   "Wunderkind" archetype on a must-win — and the slice's stated taste-target
   is the reactions, not the W/L. Worth surfacing only because a first-time
   founder might read the second playthrough as "my choice didn't matter."
   No action; flag in the playtest brief if it lands that way again with a
   second tester.
3. **(Cosmetic.)** Narration uses full names ("Mariana and Aurelie came
   apart") while the standouts row uses nicknames ("Came apart: Vex and
   Pixie"). Minor naming inconsistency in the same recap. No action.

## Would I keep playing?

**Yes — for a second slice.** The "remembered me" beat is exactly the hook
M0 was scoped around, and it lands on the very first read. The cast feels
like a cast, not five interchangeable IDs, and the recap is something I
actually wanted to read to the end. The honest caveat is the one captured in
Fix #1: on the second consecutive loss, the player posts read as a stock
choir rather than five distinct reactions to *this* match, and that's the
edge where the loop would start to feel hollow if I played four weeks in a
row without it. As a one-week vertical slice it sells the pitch; as the
shape of a 40-hour loop it needs Fix #1 before another round of playtests.

## Fix logged

### Fix #1 — Chirper reactions should condition on the player's own match outcome

- **Where:** `esports_tycoon/content/templated.py:218` —
  `_CHIRPER_LINES[(register, won)]` keys reactions on a team-level
  win/loss boolean.
- **What:** A player who personally MVP'd or carried in a team *loss*
  delivers a loss-mode line; a player who came apart in a team *win*
  delivers a win-mode line. The player's local outcome doesn't reach the
  selector.
- **Why it matters:** The slice's promised beat is *"the game remembered
  something about me, specifically."* Per-player reactions are the most
  visible surface where that promise either lands or doesn't — and they
  currently regress to a team-shaped reaction on the second look.
- **Shape of the fix:** Pass the per-player local outcome through the
  `GenerationContext` for `chirper_post` (one of `mvp` | `carried` |
  `came_apart` | `neutral`), expand `_CHIRPER_LINES` to key on
  `(register, local_outcome)` instead of `(register, won)`, and have the
  templated picker fall back to the existing `(register, won)` table when
  `local_outcome == neutral`. Keep the same memory-grounding seam (the
  picker still grounds in one of the author's own memories matching mood);
  only the line set changes.
- **Scope:** templated-mode only for M0. The vLLM-mode prompt already gets
  the full `WhyRecord`; that path can lift the same local-outcome field
  into its system message in M0.2.
- **Tests:** Extend `tests/test_templated_adapter.py` with a case that
  asserts a `mvp` player in a team loss is *not* served a loss-mode line,
  and a `came_apart` player in a team win is *not* served a win-mode line.

This is the only fix that blocks the loop from feeling alive past a single
playthrough. It is scoped, behind one seam, and does not unfreeze any of
the 9 hardening tickets the founder brief left parked.

## Artifacts

Both run folders are available under
`/tmp/esports-tycoon-playtest/runs/wk6-6dbefcb76d21/` and
`…/wk6-010d83545e46/` — `recap.md`, `feed.snapshot.html`, `events.jsonl`
each. The first is the canonical screenshot surface for the gate.

## Gate status

- Acceptance: founder-or-tester plays Week-6 decision → match → recap from
  a fresh clone ✅
- Written verdict on coherence + "would I keep playing" ✅
- ≥1 fix logged ✅ (Fix #1 above)
- **Milestone close: cleared.** M0.1 closes; M0.2 is unblocked.
