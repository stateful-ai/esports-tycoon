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

## Relationship arcs

Turn existing chemistry, loyalty, mentorship, trust, culture, and Chronicle
signals into scarce readable mentor-bond, friction, and grudge arcs. Surface
them in profiles and occasional inbox moments; use bounded effects on renewal,
development, or confidence rather than another detached meter.

## Sponsor lifecycle

Add a Finances commitments timeline for accepted demands: deadline fixture,
reward/risk, outcome, and the resulting brand-relation change. Show known
commitments only; do not reveal hidden demand-generation odds.

## Maintenance: roadmap reconciliation

Development milestones already have Chronicle detection and Inbox surfacing.
Remove that stale open item from the roadmap, then keep this document aligned
as the remaining polish work ships.
