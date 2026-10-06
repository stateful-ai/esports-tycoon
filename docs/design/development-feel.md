# Development that responds to decisions and performances

Training choices shape the player's actual match-engine attributes. The
Development tab names the skills targeted by each individual plan and explains
recent progress using measured practice, match, bench-scrim and event gains.
Hovering a source shows the individual skill changes. These are recorded at the
point of mutation, rather than inferred from an overall-rating increase.

## Decisions and feedback

- A pinned focus overrides the team's category. Training the skills used in
  this week's matches provides a 25% practice-transfer bonus.
- Match impact is normalized per round and relative to opponent ability.
  Assists, trades, objectives, survival and clutches count alongside kills.
  First deaths alone no longer produce positioning XP.
- A player's match-performance trend updates once per week, rather than once
  per map. The trend changes practice absorption by at most 30% in either
  direction. Poor performances still teach skills; they are not a blanket
  development lock. Bye/bench weeks gently fade the trend without inventing
  match evidence.
- Intensity still buys more reps at a condition cost. Fatigue now gradually
  reduces learning instead of applying only below the old 35-condition cliff.
  Rest pauses practice and retains any match learning earned that week.
- Coaches, mentorship, facilities, scouting guidance and streaming retain their
  existing effects. The latest-week report explains the applicable practice
  factors. Other campaign effects, such as aging and badges, remain visible in
  the broader season skill deltas.

## Surprise careers

Most careers retain their existing growth curve. For unauthored careers, a
stable hidden response produces a small exceptional-learning group (6%) and a
group that struggles to translate projected upside into skills (8%). The latter
has much slower absorption and lower reachable headroom, without changing
opening ability or the scout's initial headline forecast. Authored career
volatility scales both the frequency and size of these tails; zero volatility
keeps its authored response.

After at least four played weeks, sustained positive performances plus completed
practice in reasonable condition can rarely trigger a career breakthrough. A
player at the current forecast can still earn new headroom. It gives a small gain
in the skills actually practiced and persistent extra room to develop. Sustained
underperformance plus practice can rarely produce a stalled path, reducing
future headroom without removing skills already earned. Neither event fires on
a recovery/bye/bench week. Six-week cooldowns and a lifetime headroom adjustment
bounded to +/-6 prevent unlimited compounding. A player can recover from a
stall; a negative shift is not an irreversible bust label.

Every club uses the same growth, performance and career-event rules. The
manager's choice of individual plans remains the existing human-controlled
lever; AI coaches still select roster-aware team practice. Events appear in the
owning manager's private inbox and latest-week development report. The browser
receives observed gains and qualitative feedback, never the hidden response or
exact ceiling shift.

## Persistence and validation

Save v36 adds a defaulted player development-progress object. Old saves start
with no trend or measured weekly history, preserving existing attributes.
The latest report is replaced each week, so save size stays bounded. Career
randomness uses a dedicated campaign/season/week/player RNG path and sorted
iteration. Match-engine rules and neutral golden fixtures are unchanged.

`tests/test_development_path.py` covers same-player counterfactuals, focus
transfer, support impact, fatigue, first-death farming, career tails, rare
turning points, recovery, old-save loading and campaign replay determinism.
Run the full pytest suite and `scripts/snowball_report.py` to check regressions
and multi-season competitiveness.
