# Future management-sim feature ideas

Recorded after the July 2026 club-depth pass. These are intentionally not
committed roadmap scope; each needs playtest evidence before promotion.

## Decision journal and counterfactual review

Turn the existing action log, market-decision ledger, Chronicle, and match
reviews into a season-end causal review: what the manager knew, what they
changed, and what followed. A later research extension can run deterministic
counterfactuals (for example, keep a player instead of selling) without
pretending the alternate history is canonical.

## Delegation policies â€” implemented 2026-07-12

Let managers define bounded staff rules: automatically scout players matching
a profile, renew rotation players inside a salary band, or alert only when a
prospect crosses a readiness threshold. Depth should not require repetitive
weekly clicks. The shipped policy uses the same renewal salary calculation and
single-scout capacity as manual play, records each run and its exceptions, and
supports profile-based prospect alerts without exposing hidden ability.

## Dynamic league governance

Long careers could vote on controlled offseason changes: regional expansion,
format adjustments, roster-rule changes, and Tier-2 promotion pathways. Rules
must be deterministic, versioned on GameState, and understood by schedule,
market, AI, and headless-policy layers before they affect a live save.

## High-stakes media choices â€” implemented 2026-07-12

Occasional grounded choices—defend a rookie, cool a transfer rumor, set derby
expectations—could feed existing sentiment, sponsor, memory, and relationship
systems. The shipped layer is contextual, has a six-week cooldown, never
stacks with a flavor prompt, and applies deterministic player-trust, sponsor,
and sentiment consequences. Derby expectations settle from the real result.

## Wider career formats

International/regional selection jobs, create-an-organization starts, and
multi-squad ownership remain attractive long-horizon variants. They are much
larger than ordinary features because they change schedule ownership, player
availability, finances, and the manager-seat contract.

## Presentation polish

Viewer camera follow/zoom, animated office characters, and fuller season-end
ceremony remain useful independent presentation projects. They should consume
existing state and event logs and introduce no simulation state in JavaScript.
