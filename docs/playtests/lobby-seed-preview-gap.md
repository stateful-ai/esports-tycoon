# Lobby seed preview gap and candidate fix

Origin: root player session `2026-10-11-match-prep-root`, on source commit
`83cd64d1d15b066c17cb392c483f21b870356831` (tree
`4bcc0ca59c7dbc121d3a0feecb0665ebd943af81`). Observation runtime model and
effort: `unknown (not exposed)`. This report copies public DOM excerpts from
that session; the implementation agent did not reproduce gameplay or mutate
the test world. The existing intent/outcome history remains authoritative.

The root reported entering seed 2040 after an initial seed of 6163 and pressing
Tab. The organisation grid retained its earlier metadata. These safe excerpts
are copied from `step1-lobby-after-seed-dom.txt`:

```text
- paragraph: Pick your organisation. Seed controls the generated league.
- spinbutton "Seed": "2040"
- generic: EMEA
- button "Phantom Core PHC rep 56.6 · 227,100 cr"
```

EMEA is the group heading containing the Phantom Core card; other cards between
the heading and this card are omitted. After selecting the displayed Phantom
Core option, `step1-created-dom.txt` contains:

```text
- generic: Season 1 · Week 1 · Regular — Phantom Core
- generic: 246,900 cr
- generic: Pacific League
```

These excerpts support a visible preview/created-world mismatch. They do not
establish which browser input events fired or the order of preview responses.
No private saves, authentication, page identifiers, or world identifiers are
included here.

Source inspection finds that seed refresh listened only to `change`; previews
and offers could render without checking request freshness; card callbacks
read mutable settings and creation independently reread the seed field. Draft
interviews likewise awaited server responses without checking whether their
seed/settings context was still active. These gaps permit a displayed offer to
outlive its seed or be replaced by an older response.

The candidate clears choices immediately on input and refreshes after 200 ms
(or immediately on change). Each rendered pick belongs to a captured seed,
pack, mode, shared setting, draft setting, lobby visit, and request revision.
Only the current response can render and only its picks can create a campaign.
Creation submits that captured seed. Invalid or empty seeds show guidance and
cannot select an organisation; zero and negative whole-number seeds no longer
silently fall back to 2026. Seed handling accepts JavaScript safe integers.
Roster packs keep their existing server-supplied static metadata; scenarios
remain server-applied at creation. Generated league data, manager logic,
deterministic campaign state and API contracts are unchanged.

Coverage authored in `tests/lobby_seed_preview_check.cjs`, exposed through the
web-marked pytest wrapper, exercises input/change refresh, immediately stale
picks, reversed response order, stale errors, current errors, invalid and zero/
negative seeds, pack/scenario creation, career offers, shared creation, draft
context replacement, join navigation, lobby re-entry, both awaited draft
endpoints, and draft joins without a create-lobby seed.

Validation: **UNRUN by explicit user override**. No local tests, validators,
syntax checks, simulation runs, gates, or analytics commands were executed.
The authored coverage is not passing-test evidence. Candidate acceptance in a
real browser and root review remain pending; the supplied observations precede
this candidate and are not evidence that the fix works.
