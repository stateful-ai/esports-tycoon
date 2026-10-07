# Local UI usage

The browser writes best-effort usage events to `saves/usage/usage.0.jsonl`.
This sidecar never changes GameState, decision logs, random streams or saves.
No external analytics service is contacted. Request bodies, queries, entity
IDs, cookies, error text and freeform input are excluded.

Schema version 1 records a hashed cookie-plus-page session identifier,
server receipt time (`received_at`), and server-resolved world/team/season/week.
The browser's random page ID is a correlation token, never a credential or
seat claim. Membership comes from the real session cookie. Each page load
starts a new usage session; this is not a unique-person count.

Events: session start/end; tab/subtab view; visible-time slices; mutation
attempt/result pairs; read-request failures; replay open/close/play/pause,
round selection, seek and speed. Results distinguish success, HTTP error,
transport/JSON error, and HTTP-200 `ok:false` rejection. Success means API
success, not proof of a changed setting or achievement of player intent.
Request IDs pair concurrent or reordered results. Routes are coarse buckets:
actions retain their verb; other API routes retain the first resource segment.
Replay fixture/player identifiers are not captured.

Visible time uses the browser monotonic clock, excludes hidden-tab intervals,
and emits every 15 seconds or on view/visibility transitions. Each slice is
capped at 60 seconds to limit timer suspension distortion. It is visible-page
time, not evidence of attention. A hidden replay does not accumulate visible
time. `received_at` is ingestion time, not an exact click timestamp. Lifecycle
mutations drain queued events and their attempt before changing membership;
the result belongs to the new context. Pairing works across that boundary.

Limits: 32 events/request, 16 KiB request body, 128 queued events per page,
four rotating segments of at most 2 MiB each. Payload validation rejects
unknown fields, targets, routes and excessive values. Disk failures return
`accepted:false`; network errors/timeouts drop batches without retries. Each
send has a 500 ms deadline, including lifecycle drains. Gameplay continues
when telemetry is unavailable. Abrupt exits, busy queues, retention rotation,
multiple server processes, or failed sends can lose events or split pairs.
Use one server process for this local sidecar. Counts are retained best-effort
observations, not complete funnels, exact total sessions, or causal evidence.

Read-only report: `python scripts/ui_usage_report.py [saves/usage]`, or
`GET /api/usage/report` from the host machine only. It reports event counts,
visible milliseconds by view (including the replay overlay), outcome counts,
retained event counts by world, per-session receipt-span proxies, attempts/paired results,
unmatched attempts/orphan results, and malformed lines. Rotation may explain
unmatched records. It does not expose raw records or inspect hidden game state.
Inspect the sidecar alongside deterministic `action_log` for decision evidence;
usage attempt parameters are intentionally unavailable.
