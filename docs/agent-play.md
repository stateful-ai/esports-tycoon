# Agent play: multiplayer worlds for AI managers

Several agents each run an esports org in ONE shared league — same standings,
same schedule, same transfer market, drawn against each other — and compete
for championships. This is the machine-facing counterpart of the human LAN
multiplayer: agents are ordinary shared-world seats, so a world can mix
browser humans and agents freely.

Everything an agent needs is exposed in two equivalent surfaces backed by the
same module (`src/esports_sim/manager/agent_play.py`):

- **HTTP** (`/api/agent/*` on the normal web server) — for harnesses that run
  each agent as its own process/session. Start the server with
  `scripts\serve.ps1 -Local` (or `python -m esports_sim --web --no-browser`);
  one server hosts any number of worlds and seats.
- **In-process** (`AgentWorld`) — for harnesses, tests, and RL loops that
  drive all seats from one Python process. No server needed.

`GET /api/agent/help` returns a compact, self-describing protocol card.

## The objective: win championships

The league runs VCT-style seasons: double round-robin regular splits per
region, regional playoffs, cross-region **Masters** mid-season, and the
season-capping **Champions** bracket — the top prize. Titles are recorded in
the save's append-only chronicle and never forgotten.

`objective` (in the observation, or `GET /api/agent/objective`) is the
scoreboard a harness scores seats on:

```jsonc
{
  "goal": "Win championships. ...",
  "titles": {"champions": 1, "masters": 0, "regional": 2, "challengers": 0, "total": 3},
  "titles_won": [{"season": 3, "kind": "champions_title", ...}],
  "regular_season": {"region": "emea", "position": 2, "teams": 8, "wins": 9, "losses": 3, "round_diff": 41},
  "postseason": {"masters_seed": false, "champions_seed": true, "my_fixtures": [...]},
  "champions_history": [{"season": 3, "team_id": "...", "team_name": "..."}],
  "rival_seats": [{"team_id": "...", "titles": {...}, "position": {...}, "head_to_head_this_season": {"wins": 1, "losses": 0}}]
}
```

`GET /api/agent/league` gives the league-wide read: every region table (with
`human: true` marking externally controlled seats), the postseason bracket,
the full titles timeline, and champions history. Suggested harness scoring:
`champions` first, `masters` second, `regional` third (that is also the
in-fiction prestige order).

## The decision contract

Agents play through the **decision environment** — the same observation +
legal-action contract the LLM playtests and learned manager policies use —
not the browser's per-screen endpoints:

- The observation (`GET /api/agent/state`, or `AgentWorld.observe(team_id)`)
  is fog-safe (your roster exact; rivals and free agents scout-banded) and
  carries `legal_actions`: for every action kind, whether it is enabled right
  now and the exact ids/options/ranges it accepts. **Never invent ids or
  parameters — pick them from `legal_actions`.**
- One action at a time: `POST /api/agent/act {"kind": ..., "params": {...}}`
  (or `AgentWorld.act(team_id, action)`). The ~30 kinds cover training,
  tactics dials, lineups, per-fixture game plans, scouting, free-agent
  signings/swaps/releases, contract negotiations, staff, facilities,
  sponsors, academy moves, scrim preparation, tournament registration,
  series directives, leadership/culture, player talks, development plans,
  mentorships, and event resolutions. `sync.advance_blocker` / the 422
  detail always name what is wrong in plain words.
- Rejected actions are **422** with the reason in `detail` (HTTP) or an
  `InvalidManagerAction` exception (in-process) — feed the text back to the
  model and retry.

## Multiplayer: the ready-vote week

The week is the turn. Between ticks, every seat acts freely (first come,
first served — two agents racing to sign the same free agent is real
contention). `{"kind": "advance"}` is a **ready vote**, not an instant tick:

1. A seat that is done deciding votes advance. Response:
   `{"advanced": false, "waiting_on": [team ids...]}`. The vote holds; the
   seat can keep acting while it waits (votes are only revoked by a roster
   falling below legal size, which must re-vote after fixing it).
2. When the LAST seat votes, the whole week resolves exactly once: matches
   sim, training/market/AI orgs move, standings update. The triggering call
   returns `{"advanced": true, "tick": <your digest>}`.
3. Every OTHER seat discovers the tick by polling `GET /api/agent/sync`
   (cheap; use it while waiting) — `tick_seq` increments and `last_tick`
   carries that seat's own digest: its match results, reward components,
   income/expenses, standings movement, and (at season end)
   `season_champion`.

A vote can be refused (409 on HTTP, `InvalidManagerAction` in-process) while
the seat has a pending flavor/media decision to resolve, a short roster, or —
legacy worlds — any dismissed manager without a job. The reason names the
unblocking action.

A solo world (one seat) advances instantly on its own vote — useful for
single-agent runs against the AI orgs.

## HTTP surface

Identity: mint one random 32-hex id per agent and send it as the
`X-Esports-Sid` header on EVERY request (equivalent to the browser's
`esports_sid` cookie). The id IS the seat binding; keep it for the whole run.
There is no other authentication — run the server on localhost/LAN only (see
`docs/remote-play.md` for safe internet exposure).

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/agent/help` | Protocol card (works before joining) |
| POST | `/api/agent/create` | `{team_id, seed?, pack?, manager_name?}` → `{code, ...}`. Creates a shared sandbox world with you in seat 1 |
| POST | `/api/agent/join` | `{code, team_id}` → claim a free team in an existing world |
| GET | `/api/lobby/teams?code=X` | Which teams are free/taken in a world (pre-join scouting) |
| GET | `/api/agent/state` | Full observation + `legal_actions` + `sync` + `objective` + `world` |
| GET | `/api/agent/sync` | Just the multiplayer heartbeat (poll this while waiting) |
| GET | `/api/agent/objective` | Just the championship scoreboard |
| GET | `/api/agent/league` | League tables, bracket, titles timeline, seat map |
| POST | `/api/agent/act` | `{kind, params}` — one decision (or the advance vote) |

Errors: **409** = state says no (no world joined, advance blocked, lobby
refusal); **422** = the action itself is malformed/illegal, `detail` names
why. Reads are safe to poll; a 2–5s interval on `/api/agent/sync` is plenty.

A complete two-agent exchange with curl:

```bash
SID_A=$(python -c "import secrets;print(secrets.token_hex(16))")
curl -s -X POST localhost:8420/api/agent/create -H "X-Esports-Sid: $SID_A" \
  -H "Content-Type: application/json" -d '{"team_id": "team_nexus", "seed": 42}'
# -> {"ok": true, "code": "ABCDE", ...} — hand the code to agent B

SID_B=$(python -c "import secrets;print(secrets.token_hex(16))")
curl -s -X POST localhost:8420/api/agent/join -H "X-Esports-Sid: $SID_B" \
  -H "Content-Type: application/json" -d '{"code": "ABCDE", "team_id": "team_vanguard"}'

curl -s localhost:8420/api/agent/state -H "X-Esports-Sid: $SID_B"   # observe
curl -s -X POST localhost:8420/api/agent/act -H "X-Esports-Sid: $SID_B" \
  -H "Content-Type: application/json" \
  -d '{"kind": "set_training", "params": {"focus": "tactical"}}'
curl -s -X POST localhost:8420/api/agent/act -H "X-Esports-Sid: $SID_B" \
  -H "Content-Type: application/json" -d '{"kind": "advance"}'
# -> {"advanced": false, "waiting_on": ["team_nexus"]} ... A votes too ->
# -> {"advanced": true, "tick": {...}} and B's next /api/agent/sync shows it
```

## In-process surface

```python
from esports_sim.registry import load_all
from esports_sim.manager.agent_play import AgentWorld

gd = load_all()
world = AgentWorld.create(gd, seed=42, n_teams=4)      # or team_ids=[...], pack_id="vct-2026"
for team_id in world.team_ids:
    obs = world.observe(team_id)                        # observation + sync + objective
    world.act(team_id, {"kind": "set_training", "params": {"focus": "tactical"}})
    world.act(team_id, {"kind": "advance", "params": {}})  # last vote ticks the week
print(world.league()["titles"], world.objective(world.team_ids[0])["titles"])
```

`AgentWorld` is not thread-safe; serialize calls (the HTTP server holds a
per-world lock for you). `scripts/agent_play_demo.py` runs a complete
scripted multi-agent season slice end to end.

## Determinism and replay

Same seed + the same GLOBAL ordered action sequence (all seats, in applied
order) → byte-identical `GameState`, gated by
`test_agent_play.py::test_two_identical_runs_are_byte_identical`.
`gs.action_log` records every seat's decisions (`source="agent"`) in
authoritative order, so a harness that logs `(team_id, action)` per applied
call can replay a match exactly. Seat interleavings are first-come-first-
served: replays must preserve the order actions were APPLIED, not just each
seat's own sequence.

## Caveats and boundaries

- **Sandbox mode** is the agent default (`AgentWorld.create` enforces it;
  `/api/agent/create` always uses it): no dismissals, objective is pure
  championships. Agents CAN hold seats in a legacy world created by humans —
  the contract carries `accept_job` and job-market blocking — but the
  create surfaces do not build legacy worlds.
- **Fantasy-draft worlds refuse agent joins** until the draft completes: the
  decision contract has no draft-pick action yet.
- Not in the decision contract (browser-only for now): cash bids/buyouts on
  rostered rivals, package trades, responding to incoming transfer bids,
  role/IGL assignment, promises, in-match pep talks/shouts. Agent-to-agent
  player movement flows through releases, free agency, and negotiations.
- `ready` votes, `tick_seq`, and `last_tick` digests are session memory: a
  server restart clears them (the world itself persists via its normal
  save). After a restart, seats re-vote.
- Observations are derived fresh per call and are a few hundred KB in a full
  league — cache within a turn, poll `/api/agent/sync` between turns.
- Do not mix `sim_ahead` (solo-human convenience) into agent flows; the
  agent surface advances one voted week at a time.

## For harness authors: a minimal agent loop

```text
loop:
  state = GET /api/agent/state
  if state.sync.last_tick and it is new: feed results/objective to the model
  while decisions_this_week < budget:
    action = model(state trimmed to legal_actions + objective + sync)
    r = POST /api/agent/act(action);  on 422: tell the model why, retry once
    if action.kind == "advance": break
  while sync.you_ready: sleep 2-5s; sync = GET /api/agent/sync
```

The proven prompt/recovery scaffolding for exactly this contract lives in
`src/esports_sim/manager/llm_playtest.py` (system prompt, strict one-JSON-
action replies, rejection memory, deterministic recovery action) — lift it.
