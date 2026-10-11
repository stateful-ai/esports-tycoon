# Dashboard competition-tier correction

The observed player session used source commit
`754f525ce5f13636034a951a43e6da7346953df9` (main plus the standing-scouting
Dashboard change). At season 1, week 3, seed 2071, Azure Vanta's Dashboard
showed the EMEA top division, including Nova Rift and Mumbai Meteors. Season's
EMEA Challengers table placed Azure Vanta fifth of six at 0-2 with -17 round
differential; the weekly recap correctly said fifth of six.

The Dashboard chose the regional `rows` from `/api/standings`, which represents
Tier 1. Its `/api/state` fallback also used the default Tier 1 standings.
The recap already ordered the team's own region and tier.

The fix shares that server ordering with a read-only `competition_table`
snapshot in `/api/state`. The snapshot identifies region, tier and competition,
and includes all rows. The Dashboard keeps server order and shows the top four
plus the manager's row and preceding row. The status tile also identifies the
same competition. Season's full tables retain both divisions and navigation.
No simulation, scheduling, save schema or campaign outcomes change.

Old saves receive the normal Team tier default. Empty tables show an explicit
empty state; an absent snapshot does not substitute an unrelated division.
Active drafts retain their short state response and dismissed legacy managers
retain their job-market screen.

Regression coverage was authored for Tier 1/Tier 2, sandbox/legacy acting
managers, full-table agreement with recap and Season, read purity, a missing
team, empty standings, a missing legacy tier field and active drafts. The
frontend regression exercises the actual card-rendering source with a
fifth-place manager, distracting Tier 1 data, empty or absent snapshots and
the Full table navigation.

All local tests, checks, validators, syntax checks, simulations, gates,
reports and commit/push hooks are **UNRUN under the user's explicit waiver**.
The observations above establish the defect on the observed commit; they are
not browser acceptance evidence for this change's new head.
