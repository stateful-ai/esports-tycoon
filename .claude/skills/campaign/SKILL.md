---
name: campaign
description: Add or extend a campaign-layer (manager/) feature — weekly-tick systems, market, economy, development, narrative, inbox — with campaign determinism, save migration, and the snowball gate. Use for any change under src/esports_sim/manager/.
---

# Campaign — manager-layer feature workflow

Campaign features (weekly tick, market, economy, development, staff,
talks, relationships, narrative, inbox) never run inside the match gates,
so they're free of the neutral-safe tactics rule — but they carry their
own invariants.

## Campaign determinism (same seed → byte-identical GameState)

- Every draw through `RngTree` labels or blake2 of stable ids. NEVER
  `hash()` (salted per process), never wall-clock, never set/dict
  iteration order — sort every iterable whose order can reach state.
- New weekly phases run in a FIXED position in `campaign.py`'s tick order;
  inserting a phase reorders downstream draws, which is a deliberate,
  test-visible change — not a refactor.
- Verify: run `--auto N --seed S --team T` twice, diff the saves. A
  dedicated determinism test should cover any new subsystem with RNG.

## Save compatibility

`state.py` carries `schema_version` + a migration hook. If you add/rename
a persisted field: bump the version, write the migration, and make the
serializer emit the field with a default so old saves load. Never let a
new field crash an existing `saves/campaign.json`.

## Balance across seasons

Anything touching results-to-condition feedback (form, morale, economy,
development, market strength) can snowball into 13–0 leagues over
multiple seasons — single-match testing won't show it. Gate:
`.venv-win\Scripts\python.exe scripts\snowball_report.py` → exit 0.

## Surfacing to the player

- **Inbox**: weekly-important events belong in `manager/inbox.py`'s
  digest. If the item is actionable (an offer), do NOT store actions on
  the item — derive them live from current state in `actions_for`, so a
  stale message can't fire a dead offer.
- **Narrative**: recaps are templated and grounded — every fact resolves
  to a real event/log entry; phrasing seeded per event; silence beats
  invented drama. Dry, no-hype voice (docs/salvage/tone_and_cast_lock.md).
- **Profiles/stats**: derived views read stored fixture lines and the
  event log; they never write campaign state.

## AI parity

Whatever lever you give the player, decide explicitly what the AI orgs do
with it (they train, poach, adapt tactics, work the market). An
unanswered player-only lever is a difficulty leak; document it if
intentional.

## Checklist before /ship

1. Full pytest green (campaign tests + API contract tests).
2. Double-run seed diff (byte-identical saves).
3. `snowball_report.py` if condition/economy/market feedback changed.
4. Old-save load check if anything persisted changed.
5. ASCII-only in any CLI/console output (cp1252 consoles).
