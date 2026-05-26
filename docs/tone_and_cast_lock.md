---
type: stream_doc
title: tone_and_cast_lock
stream: esports-tycoon
updated: '2026-05-25T15:12:38Z'
summary: >-
  M0.0 design lock. Pins the dry-mockumentary voice and the Vector Strike
  (Valorant-flavored) fiction, names the 5-starter cast with explicit clash
  pairs and 6 rival archetypes, and points at saves/week6.yaml as the canned
  Week-6-of-8 save. Goes to the founder as one batched approve/reject pass.
---

# Tone + Cast Lock — esports-tycoon M0 (Week 6 of 8)

This is the **1-pager that the whole slice builds on**. Prompts, templates, the
match resolver's narration, and the Chirper feed all inherit from here. Per the
red team, casting and tone are *hard prerequisites* — narration work does not
start until the founder approves this batch in one pass.

The cast, memory log, last-week scoreline, and last-week feed live in
[`saves/week6.yaml`](../saves/week6.yaml). This doc pins the *why*; that file is
the *what*.

---

## 1. Voice — dry mockumentary

Reference points: *The Office* / *Welcome to Wrexham* deadpan. The camera is
always on; everyone knows it; nobody admits how much they're performing for it.
Comedy comes from restraint and the gap between what's said and what's meant —
never from jokes, puns, or hype.

**Do**
- Flat, short, declarative lines. Let silence and understatement do the work.
- Talking-head energy: characters narrate their own drama to an unseen crew.
- Specific, mundane detail (a taped-up quote, a single-period tweet, a coat).
- Let the scoreboard and the memory log carry the stakes; the voice stays dry.
- Pettiness expressed in small actions (an unfollow, a read receipt) over speeches.

**Don't**
- No exclamation hype, no "GG EZ," no meme-speak from the narrator.
- No earnest inspirational arcs; this is deadpan, not *Ted Lasso*.
- No fourth-wall jokes about being an AI or a game.
- No slurs, real-person impersonation, or targeted harassment (see safety ticket).
- No emoji from the narrator. Characters may use them *in-character* on Chirper.

**Calibration lines** (the target — do not ship verbatim):
- Narration: "Overcast were up nine to three. They are no longer up nine to three."
- Rook (IGL): "We had a plan. It was a good plan. I'd like to think about something else now."
- Sable (Sentinel), full post-match interview: "Held. Won. Hungry."
- Chirper, the org account: "week 6: Helix. must-win. doors open at six. bring a coat."

Per-character voice prompts are pinned per player in `saves/week6.yaml`
(`persona_voice`). They are the contract the LLM mode and the templated mode both
honor, so the *shape* of recall is identical even when the templated voice is flatter.

---

## 2. Flavor — Vector Strike (Valorant-flavored)

A fictional 5v5 tactical shooter. **No real IP, players, orgs, or games.** All
names are invented. Glossary, so every ticket uses the same words:

- **The Vector** — the objective device attackers plant and defenders defuse.
- **Operatives** — the playable characters; each starter has a signature one.
- **Roles** — `IGL`, `DUELIST`, `CONTROLLER`, `SENTINEL`, `INITIATOR`. One per
  starter; the IGL is the in-game caller.
- **Maps** — Helix, Foundry, Terminus (used in last week's series; more exist).
- **Economy / play** — eco, force, full buy; entry, lurk, retake, clutch, ace.
- **League** — Vector Strike Pro League, Atlantic Division, an 8-week split;
  top 6 of 8 make playoffs.
- **Chirper** — the in-universe social feed (a fictional Twitter). The public
  surface where memory turns into drama.

---

## 3. The cast — 5 starters (org: Overcast, tag OVC)

Casting principle (red team): **every starter exists to clash with at least one
teammate or rival. Boring teams don't ship.** One player per role; combustible
on paper before any LLM runs.

| Player | Role | One-line | Primary clash |
|---|---|---|---|
| **Rook Tanaka** (`rook`) | IGL | 27-year-old captain, deadpan, structure-first, quietly afraid he's aged out. | Vex (his calls); Echo (the wunderkind). |
| **Vex Okonkwo** (`vex`) | Duelist | 19-year-old star, plays for the clip and the clout, right just often enough. | Rook (freelances his calls); Halo (Chirper beef). |
| **Sable Volkov** (`sable`) | Sentinel | The silent anchor; one-word interviews; petty in periods, not speeches. | Vex (steals his credit); Pixie (flashes his crosshair). |
| **Pixie Nardini** (`pixie`) | Initiator | The motormouth info engine; casters' darling, teammates' mute candidate. | Coyote (can't give him silence); Vex (flashed her in W5). |
| **Coyote Park** (`coyote`) | Controller | The lurker; wins rounds nobody claps for; revenge arc vs. his old org. | Bishop/Northwind (left on bad terms); Pixie (noise). |

### Explicit clash pairs

Authored in `saves/week6.yaml > clash_pairs`, each seeded by specific memory IDs:

1. **Rook ↔ Vex** — structure vs. freelance (intra-team, the central tension).
2. **Vex ↔ Sable** — spotlight vs. anchor (intra-team).
3. **Pixie ↔ Coyote** — noise vs. silence (intra-team).
4. **Vex ↔ Pixie** — blame vs. guilt, from the week-5 friendly flash (intra-team).
5. **Sable ↔ Pixie** — crosshair discipline (intra-team).
6. **Coyote ↔ Bishop** — ex-teammate grudge (cross-team, Northwind).
7. **Rook ↔ Echo** — veteran vs. wunderkind (cross-team, Apex Foundry).
8. **Vex ↔ Halo** — clout rivalry (cross-team, Sovereign).

Coverage: rook, vex, sable, pixie, coyote each appear in ≥1 pair. ✔

---

## 4. Rival archetypes — 6 orgs

Five-to-six per scope; six authored, each a distinct narrative pressure:

1. **Sovereign** (*The Dynasty*) — sterile champions; Halo is Vex's ceiling.
2. **Northwind** (*The Ex-Teammate*) — Coyote's old org; Bishop, the grudge.
3. **Apex Foundry** (*The Wunderkind / Heir*) — Echo, the prodigy IGL mirroring Rook.
4. **the Goblins** (*The Chaos Agents*) — off-meta meme team; humiliation risk.
5. **Tidewater** (*The Rising Underdog*) — "you used to be us"; Sable mentors their rookie.
6. **Last Light** (*The Fallen Star*) — Ghost, aging out in public; the cautionary tale.

---

## 5. The Week-6-of-8 situation

- **Standing.** Overcast are 2–3, sixth of eight — the last playoff spot, on a
  two-loss skid. Week 6 is must-win; they have to win out (6–8) to make playoffs.
- **Last week (week 5).** Lost the revenge series to **Northwind, 1–2**, after
  choking a **9–3 lead on Terminus**. Coyote's grudge match went the wrong way;
  Bishop taunted him; Vex and Pixie are crosswise over a friendly flash.
  Full scoreline + an 11-post Chirper feed are in `saves/week6.yaml > last_week`.
- **Why it's the on-ramp.** The founder walks into a locker room that already
  has history, grudges, and a public meltdown to clean up — exactly the state
  that makes "the game remembered me" land in one week of play.

---

## 6. Grounding contract (memory IDs)

Precedent is stored as memory entries with stable, opaque IDs:
**`mem:<player_id>:<event_slug>`** (lowercase, ascii, dash-snake slug). The
canonical example is `mem:rook:scrim_w5_choke`. `saves/week6.yaml` carries **37**
such entries across the five starters (≥30 required). The renderer resolves every
LLM cite against this log; unresolvable cites are regenerated then dropped. **No
hallucinated history** — the cast can only "remember" what's written here.

---

## 7. Approval — one batched pass

Per the locked decision (`mem_20260525T150603Z_b9788c`: cast batch-approval), the
founder reviews this **entire batch** — this 1-pager + `saves/week6.yaml` (cast,
clash pairs, rivals, ≥30 memories, last-week scoreline, last-week feed) — and
makes **one approve/reject decision over the whole thing**. No per-name
round-tripping.

The gate is mechanized in `esports_tycoon/cast_lock`:

```
python -m esports_tycoon.cast_lock review     # the one-screen batch summary
python -m esports_tycoon.cast_lock validate   # acceptance-bar checklist
python -m esports_tycoon.cast_lock approve --approver <founder> [--reason ...]
python -m esports_tycoon.cast_lock reject  --approver <founder>  --reason ...
python -m esports_tycoon.cast_lock status      # decision vs. current content
```

A batch that fails validation **cannot** be approved. The recorded decision is
bound to a content digest of both files, so any later edit invalidates the
approval until the gate is re-run — keeping the lock honest.
