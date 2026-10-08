# Replay participant identity follow-up

Continued the identified test world **26UHC**, seed2038, Team Nexus, S1 W2 on
clean **3ac34df**. Four timestamped rows use session
`2026-10-08-replay-roster`, with root model/effort `unknown (not exposed)`.
Inherited the ongoing run's flywheel findings and searched replay findings
after reopening the career, before inspecting its historical fixture.

The player question was why Sahara's replay roster and box score disagreed.
Dashboard news said Sahara released **Grimveil** and signed **Frostecho** after
the week-one match. Season → Fixtures → Played weeks reopened the 13–2 Lotus
replay without advancing. The replay roster listed Frostecho; its own box score
listed Grimveil (11 kills, 12 deaths). Event text used the generic
“Team Sahara Compass P1” for the departed player.

The [public replay identity audit](evidence/2026-10-08-replay-roster/identity-audit.json)
confirms the mismatch: `match.start.agents` contains
`team_sahara_compass_p1: jett`, but `players` omits that participant and includes
later signing `fa_7` instead. Grimveil's box-score `team_id` is null. This is a
replay identity defect caused by using the current roster. A dedicated
GPT-6.1-sol / medium gap agent is queued while the existing agents finish their
full validation gates.

Screenshot visually inspected:
`runs/playtests/2026-10-08-replay-roster/replay-identities.png`. The original
public response body is retained at `runs/playtests/2026-10-08-replay-roster/replay-response.json`;
the tracked audit contains the relevant identity fields without duplicating the
large match log. This was read-only inspection followed by Save; the seven
accepted decisions and one weekly snapshot are unchanged from the preceding
session. No new decision or fixture was produced.

The pre-open raw usage baseline contained 115 events from the prior session.
The end file preserved that prefix and added **26 events** for this new page
session, all world26UHC. [Isolated usage report](evidence/2026-10-08-replay-roster/usage-report.json)
and [raw events](evidence/2026-10-08-replay-roster/usage-events.jsonl) show
one paired Save request/success, replay open/close, six view events, start/end
and visibility slices. There are zero unmatched attempts, orphan results or
malformed lines. Four CSV rows have coarse browser evidence; opening Played
weeks and reading identities have no dedicated hook. Capture does not prove
attention or a complete click funnel.

The shared history now has **346 unique rows**, preserving its earlier prefix.
[Flywheel records](evidence/2026-10-08-replay-roster/flywheel.json) 0032/0033
retain two learnings, and0034 retains the identity pain-point. Confidence is
limited to this one fixture and the public response evidence.

The dedicated replay agent subsequently reproduced the same seed and match on
its isolated patched build. Four acceptance rows bring the shared history to
**350 unique rows**. Its [acceptance report](2026-10-08-replay-identity-fix.md)
and evidence show Grimveil/Jett, historical Sahara team identity and 11K/12D,
with Frostecho excluded. Five accepted decisions and seven browser request
pairs were reconciled independently; the four CSV rows retain their original
timestamps and expectations. Source review and the screenshot agree with
those results; the full gate and PR review remain pending at this append.
