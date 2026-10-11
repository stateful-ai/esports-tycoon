# Collapsed Inbox controls exposed to accessibility navigation

Origin: root CUA browser session on PR #415 candidate `27a2ea2f` (tree
`943144e`), fresh owned Sandbox world REWKH, seed 2039, Season 1 Week 2.
This observation was on a candidate build, not remote main. Runtime model
and effort were `unknown (not exposed)`. The root preserves the original
step 8 blocked intent and its outcome in the separate fresh-campaign history;
this report does not rewrite that expectation or claim a new player session.
Publication of that origin history was still pending when this fix was prepared.

The original attempt clicked the enabled Open Roster control for Apex's
contract deadline, but remained on Inbox. Fresh read-only DOM inspection
showed that both Open Roster and Open Tactics were children of
`.inbox-body.collapsed`, with opacity 0, max-height 0px, pointer-events none,
and no inert or aria-hidden attributes. The accessibility snapshot exposed
the body text and enabled buttons anyway. See the copied
[DOM attributes](inbox-collapsed-controls.json) and
[blocked snapshot](inbox-open-roster-noop-dom.txt).

Source inspection of both the candidate and verified remote main
`b9ec161f85d8dcca1152fd3d1b874c1afec77980` found the existing roster shortcut
already maps to Club/Squad and clicks its real top navigation button. This
fix addresses collapsed-control exposure and the absent keyboard expander;
it leaves route aliases, offer listeners, usage hooks, and decision semantics
in place. It makes collapsed bodies inert and hidden from accessibility
navigation, exposes each message header as a keyboard-operable disclosure,
and updates its expanded state through the existing open/close path.

Root subsequently expanded Apex's message through its visible header and
clicked Open Roster. The original candidate correctly reached Club/Squad,
showing Apex's current 10,400/wk contract with 57 weeks remaining. Root step
12 preserves this correction to the initial route suspicion. See the
[expanded controls](inbox-expanded-controls.json) and
[Club destination](expanded-route-club-dom.txt). This confirms the existing
route on the original candidate; it is not acceptance of the new accessibility
change. The historical reminder's old terms are not diagnosed as a new defect.

The authored frontend regression case covers collapsed/expanded attributes,
Enter/Space operation, digest expansion, and the actual expanded roster
shortcut callback selecting Squad before the Club click. It has not run.
All local tests, syntax checks, gates, simulations, and analytics reports
were skipped at the user's explicit instruction. No fixed-head browser
acceptance or runtime pass is claimed here; root review and CUA acceptance
remain required. Read-only navigation is not an accepted campaign decision.
