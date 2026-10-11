# PR 387 post-ready refresh source correction

Inline finding `4241534049` on `b17eaa758a21f44f035128aeb4450dd9ebb42e12`
identified a gap after a successful `advanced: false` response: the handler
awaited `refresh()` before starting shared-status polling. A failed refresh
therefore reached `finally` with neither polling nor status-retry enabled,
allowing another advance POST while the shared calendar might have moved.

The handler now captures week and season at click entry and starts
`pollForAdvance(prevWeek, prevSeason)` before awaiting `refresh()`.
Polling owns the disabled control before that read can fail, and retains the
original calendar even if the refresh observes a rollover. A later successful poll observes calendar movement
or cleared readiness using the existing branches; a failed poll exposes the
existing status-only Retry action. The refresh cannot independently enable
the control while polling remains active, because `finally` checks `mpPolling`.
No additional advance request is introduced. The default season argument keeps
ready-seat reload polling anchored to its freshly loaded state.

Retry clearing also moves from the generic copy painter into `refresh()`
after its successful status read. When both post-ready refresh and a subsequent
poll fail, cached `you_ready: false` can no longer erase the newly set retry
flag. The resulting Retry click invokes polling only, even if another manager
advanced while status was unavailable. A successful fresh read or the existing
successful poll branches still resolve calendar movement or canceled readiness.

This is a source-only correction to the handler, polling calendar argument,
and placement of retry clearing. All earlier historical proofs, receipts, runtime metadata,
CSV rows and integration qualifications remain dated at their original heads,
including the b17 integration evidence. No historical acceptance is claimed
for this correction.

No local tests, syntax/Node/native checks, simulations, gates, analytics
commands, browser acceptance or game were launched under the explicit user
override. Fresh exact-head remote CI and independent root review of all seven
inline dispositions remain required before merge. The primary checkout and
port 8421 were untouched; no merge was performed.
