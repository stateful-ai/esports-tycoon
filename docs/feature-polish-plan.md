# Feature polish plan

This is the deferred companion to the LLM playtest harness. Work from the
evidence it produces; do not treat the order as a promise of scope.

## Shipped: match viewer spectator controls

The replay viewer carries a spectator camera layered as a pure presentation
transform (one outer scene group) over the untouched viewBox/backdrop
contract: cursor-anchored wheel zoom, pinch zoom, drag pan with edge
clamping, a Reframe reset, click-a-lineup-row player follow, and an
optional action-cam toggle that briefly auto-centers on kills and spike
plants before easing home. Audio cues are WebAudio-synthesized only (kill
tick, round-end stinger), muted by default, with the toggle persisted in
localStorage. The viewer remains a pure consumer of replay events — legacy
logs replay unchanged — and the guide->viewer transform authority is pinned
by tests/test_viewer_static.py.

## Shipped: AI organization planning parity

AI clubs book bounded opponent-specific game plans and bench rotations
through the same GamePlan/map_lineups seams humans use
(`campaign._book_ai_fixture_plans`): a small identity-anchored counter-dial
step scaled by the coach, a focus target read from public season stats only
(never fogged attributes), and a stamina-driven freshness substitution. The
prep read rolls per side on the dedicated "ai_plans" rng stream — better
coaches prep more often — while the freshness rotation stays a pure read.
Prep edge still flows only through the existing scouting/knowledge seam.
Snowball and dynasty gates verified in-band.

## Shipped: relationship arcs

`manager/arcs.py` derives at most three scarce arcs per team (grudge,
friction, mentor bond) as a pure read over stored state: pair chemistry
bars, broken promises and sustained benchings for org grudges, spotlight
friction between same-playstyle players trending down, and mentor bonds
for registered mentorships past the bar. Effects ride existing channels
only — a bounded renewal-demand bias in opened negotiations and a modest
mentorship ceiling-step multiplier — so hands-off sims are byte-identical.
Arcs surface as chips on own-club player/team profiles plus a rare inbox
talk item when an org grudge forms or cools.

## Shipped: sponsor lifecycle

The Finances commitments timeline (2026-07-23) lists accepted demands with
deadline fixture, reward/risk, outcome, and the resulting brand-relation
change. The relation deltas are single-sourced in `sponsors.RELATION_DELTAS`
— the resolver (`settle_demands`/`respond_demand`) and the view
(`commitment_views`) read the same table, so the timeline cannot drift from
what actually settled. Hidden demand-generation odds stay unserialized.

## Done: roadmap reconciliation

Reconciled 2026-07-23. The original slate is complete — new polish work now
comes from LLM-playtest evidence (`scripts/run_llm_playtest.py` critiques).

## Next evidence batch (2026-07-23 LLM playtest critique, seed 7001)

Shipped from this batch already: no-change feedback on repeated setters
(training/tactics/preparation/negotiation), blocker reasons that name the
unblocking action, and a prep-booking message that says when the payoff
lands. Still open, in critique order:

- **Development-plan progress feedback**: `set_dev_plan` gives no follow-up
  signal in the env observation or step messages; the web Development report
  has it, the headless contract does not. Surface a per-player growth line
  (last-window CA delta) in the roster observation.
- **Flavor-event outcome clarity**: several choices resolved to "the deal
  fades" with no mechanism named. Choices should carry coarse outcome hints
  (risk/safe framing) without leaking exact odds, mirroring the media-event
  copy standard.
- **Preparation impact attribution**: after a prepared fixture resolves, the
  week report/decision ledger should say what the prep edge contributed —
  the artifact exists server-side; the settle-side line is missing.
