"""Talk module — one 1:1 conversation per week.

The topic is read off the player's actual state (their biggest problem
first); the manager picks one of three approaches; the outcome depends on
the player's personality tags with a deterministic roll from the campaign
seed. Small numbers on purpose: a talk is a nudge, not a lever you crank.

Voice follows docs/game-voice.md: professional room language, no melodrama.
"""

from __future__ import annotations

from dataclasses import dataclass

from esports_sim.manager.state import GameState
from esports_sim.rng.tree import RngTree
from esports_sim.schemas import Player

RISKY_TAGS = {"hot_head", "volatile", "perfectionist"}
STEADY_TAGS = {"calm", "veteran", "reliable", "team_player"}
YOUNG_TAGS = {"rookie", "underrated"}


@dataclass
class TalkOption:
    id: str
    label: str


@dataclass
class Topic:
    id: str
    text: str
    options: list[TalkOption]


def week_key(gs: GameState) -> str:
    return f"s{gs.season}w{gs.week}"


def can_talk(gs: GameState, pid: str) -> tuple[bool, str]:
    if pid not in gs.teams[gs.acting_team_id].player_ids:
        return False, "not on your roster"
    if gs.talked_week == week_key(gs):
        return False, "you already held this week's 1:1"
    return True, ""


def topic_for(gs: GameState, pid: str) -> Topic:
    """The player's most pressing issue, by priority."""
    p = gs.players[pid]
    from esports_sim.manager import transfer_requests

    if transfer_requests.active(gs, pid, gs.acting_team_id):
        return Topic(
            "transfer_request",
            f"{p.handle} has asked to leave. Morale is {p.morale:.0f}; this is "
            "now about whether any trust can be repaired.",
            [
                TalkOption("accept_exit", "Accept the request and promise a fair exit"),
                TalkOption("repair_trust", "Own the damage and offer one last reset"),
                TalkOption("refuse_exit", "Refuse - the contract still belongs to the club"),
            ],
        )
    if p.morale <= 20:
        return Topic(
            "crisis",
            f"{p.handle} asks for an urgent meeting. Morale has hit {p.morale:.0f}; "
            "one wrong answer could end their time at the club.",
            [
                TalkOption("take_responsibility", "Take responsibility and ask what must change"),
                TalkOption("listen_then_plan", "Listen, then agree a concrete two-week reset"),
                TalkOption("public_challenge", "Challenge them to answer the criticism publicly"),
                TalkOption("bench_ultimatum", "Tell them to accept the bench or find another club"),
            ],
        )
    if p.morale < 50:
        return Topic(
            "morale",
            f"{p.handle} has been quiet all week. Morale is low "
            f"({p.morale:.0f}) and it's starting to show in reviews.",
            [
                TalkOption("reassure", "Back them publicly — the slump isn't on them"),
                TalkOption("challenge", "Be blunt — the level isn't good enough"),
                TalkOption("listen", "Ask what's actually going on and listen"),
                TalkOption("promise_playtime", "Promise starting play time for the next 3 weeks"),
            ],
        )
    if 0 < p.contract_weeks_left <= 8:
        return Topic(
            "contract",
            f"{p.handle}'s deal runs out in {p.contract_weeks_left} weeks "
            f"and they know it. The agent has started calling.",
            [
                TalkOption("commit", "Promise renewal talks start this week"),
                TalkOption("honest", "Be honest — no decision until the season ends"),
                TalkOption("deflect", "Keep it light and change the subject"),
            ],
        )
    if p.stamina < 40:
        return Topic(
            "workload",
            f"{p.handle} is running on fumes ({p.stamina:.0f} stamina). "
            f"Another full week and something gives.",
            [
                TalkOption("rest", "Pull them from parts of practice this week"),
                TalkOption("push", "Ask for one more hard week before a break"),
                TalkOption("routine", "Bring in a routine review instead"),
            ],
        )
    if p.form < 45:
        return Topic(
            "form",
            f"{p.handle}'s numbers have dipped ({p.form:.0f} form). "
            f"They've noticed the bench conversation online.",
            [
                TalkOption("film", "Do a film session together on the losses"),
                TalkOption("back", "Tell them the spot is safe regardless"),
                TalkOption("bench_threat", "Make clear the spot has to be earned"),
                TalkOption("promise_playtime", "Promise starting play time for the next 3 weeks"),
            ],
        )
    return Topic(
        "check_in",
        f"Nothing is on fire with {p.handle}. A regular check-in.",
        [
            TalkOption("praise", "Call out what they've done well lately"),
            TalkOption("goals", "Set a concrete goal for the next block"),
            TalkOption("banter", "Keep it social — no shop talk"),
            TalkOption("promise_captain", "Promise they will be captain within 4 weeks"),
        ],
    )


def _tags(p: Player) -> set[str]:
    return set(p.personality_tags)


def resolve(gs: GameState, pid: str, option_id: str) -> tuple[bool, str, dict]:
    """Apply the chosen approach. Returns (ok, message, effects)."""
    ok, why = can_talk(gs, pid)
    if not ok:
        return False, why, {}
    p = gs.players[pid]
    topic = topic_for(gs, pid)
    if option_id not in {o.id for o in topic.options}:
        return False, "that approach doesn't fit this conversation", {}

    rng = RngTree(gs.seed).derive("talk", gs.season, gs.week, pid, option_id)
    tags = _tags(p)
    steady = tags & STEADY_TAGS
    young = tags & YOUNG_TAGS
    # The continuous layer under the tags: how criticism lands rides
    # resilience/ego, not a binary "risky" flag — anyone can bristle on a
    # bad day (base 25%), a brittle or big-ego player far more often.
    from esports_sim.manager import memories, personality

    bristle_p = min(
        0.9,
        max(
            0.05,
            0.25
            + 0.5 * max(0.0, -personality.dev(p, "resilience"))
            + 0.25 * max(0.0, personality.dev(p, "ego")),
        ),
    )
    # History with THIS org tilts the room (a debut given, a release
    # survived): a nudge, never a lever.
    loyalty = memories.loyalty_bias(gs, pid, gs.acting_team_id)

    d_morale = 0.0
    d_form = 0.0
    d_chem = 0.0
    msg = ""
    transfer_requested = False

    if topic.id == "crisis":
        from esports_sim.manager import transfer_requests

        if option_id == "take_responsibility":
            d_morale = 7.0 + max(0.0, loyalty) * 0.1
            d_chem = 1.0
            msg = f"{p.handle} stays in the room. The reset has a chance."
        elif option_id == "listen_then_plan":
            d_morale = 5.0
            d_form = 1.0
            msg = f"{p.handle} agrees to a two-week reset before deciding anything."
        elif option_id == "public_challenge":
            axes = personality.axes(p)
            request_p = min(
                0.95,
                max(
                    0.25,
                    0.55
                    + (axes["ego"] - 50.0) / 160.0
                    + (50.0 - axes["resilience"]) / 200.0,
                ),
            )
            if rng.random() < request_p:
                d_morale = -6.0
                d_chem = -2.0
                transfer_requests.issue(gs, pid, "manager escalated a morale crisis publicly")
                transfer_requested = True
                msg = f"{p.handle} ends the meeting and submits a transfer request."
            else:
                d_morale = 1.0
                d_form = 2.0
                msg = f"{p.handle} accepts the challenge, narrowly."
        else:  # bench_ultimatum
            d_morale = -8.0
            d_chem = -3.0
            transfer_requests.issue(gs, pid, "manager issued a bench ultimatum")
            transfer_requested = True
            msg = f"{p.handle} asks to leave immediately."
    elif topic.id == "transfer_request":
        from esports_sim.manager import transfer_requests

        if option_id == "accept_exit":
            d_morale = 2.0
            msg = f"{p.handle} appreciates the straight answer. The request remains active."
        elif option_id == "repair_trust":
            axes = personality.axes(p)
            repair_p = min(
                0.8,
                max(
                    0.15,
                    0.35
                    + max(0.0, loyalty) / 50.0
                    + (axes["resilience"] - 50.0) / 250.0,
                ),
            )
            if rng.random() < repair_p:
                transfer_requests.withdraw(gs, pid)
                # F3 SEAM B: repairing a transfer request is a deterministic
                # play-time reset promise doorway (surfaced as an inbox item +
                # Locker Room badge). Lazy import mirrors the market.py seam.
                from esports_sim.manager import promises
                promises.offer_from_transfer_reset(gs, gs.acting_team_id, pid)
                d_morale = 8.0
                d_chem = 1.0
                msg = f"{p.handle} withdraws the request and agrees to the reset."
            else:
                d_morale = -2.0
                msg = f"{p.handle} hears the apology but keeps the request in."
        else:  # refuse_exit
            d_morale = -5.0
            d_chem = -1.0
            msg = f"{p.handle} leaves angry. The transfer request remains active."
    elif option_id in ("reassure", "back", "commit", "praise"):
        d_morale = 4.0 + (1.5 if young else 0.0) + loyalty * 0.15
        if steady:
            d_morale -= 1.0  # veterans don't need the pep talk
        msg = f"{p.handle} takes it well."
        if loyalty >= 5.0:
            msg = f"{p.handle} takes it well. This club means something to them."
        
        if option_id == "commit":
            from esports_sim.schemas.promise import ManagerPromise
            import hashlib
            promise_type = "renew_contract"
            key = f"{gs.season}|{gs.week}|{pid}|{promise_type}"
            promise_id = f"promise_{hashlib.blake2b(key.encode('utf-8'), digest_size=8).hexdigest()}"
            promise = ManagerPromise(
                id=promise_id,
                team_id=gs.acting_team_id,
                player_id=pid,
                promise_type=promise_type,
                weeks_left=4,
                created_week=gs.week,
                created_season=gs.season,
                status="active"
            )
            gs.promises = [pr for pr in gs.promises if not (pr.player_id == pid and pr.promise_type == promise_type and pr.status == "active")]
            gs.promises.append(promise)

    elif option_id == "promise_playtime":
        d_morale = 5.0
        msg = f"{p.handle} is pleased with the promise of playtime."
        from esports_sim.schemas.promise import ManagerPromise
        import hashlib
        promise_type = "play_time"
        key = f"{gs.season}|{gs.week}|{pid}|{promise_type}"
        promise_id = f"promise_{hashlib.blake2b(key.encode('utf-8'), digest_size=8).hexdigest()}"
        promise = ManagerPromise(
            id=promise_id,
            team_id=gs.acting_team_id,
            player_id=pid,
            promise_type=promise_type,
            weeks_left=3,
            created_week=gs.week,
            created_season=gs.season,
            status="active"
        )
        gs.promises = [pr for pr in gs.promises if not (pr.player_id == pid and pr.promise_type == promise_type and pr.status == "active")]
        gs.promises.append(promise)

    elif option_id == "promise_captain":
        d_morale = 8.0
        msg = f"{p.handle} is excited about the prospect of leading the team."
        from esports_sim.schemas.promise import ManagerPromise
        import hashlib
        promise_type = "make_captain"
        key = f"{gs.season}|{gs.week}|{pid}|{promise_type}"
        promise_id = f"promise_{hashlib.blake2b(key.encode('utf-8'), digest_size=8).hexdigest()}"
        promise = ManagerPromise(
            id=promise_id,
            team_id=gs.acting_team_id,
            player_id=pid,
            promise_type=promise_type,
            weeks_left=4,
            created_week=gs.week,
            created_season=gs.season,
            status="active"
        )
        gs.promises = [pr for pr in gs.promises if not (pr.player_id == pid and pr.promise_type == promise_type and pr.status == "active")]
        gs.promises.append(promise)

    elif option_id in ("challenge", "bench_threat", "push"):
        if rng.random() < bristle_p:
            d_morale = -5.0
            d_chem = -1.0
            msg = f"{p.handle} bristles. That landed badly."
        else:
            d_morale = 2.0
            d_form = 3.0
            msg = f"{p.handle} answers the challenge."
    elif option_id in ("listen", "film", "goals", "routine"):
        d_morale = 2.5
        d_form = 1.5 if option_id == "film" else 0.5
        if steady:
            d_morale += 1.0
        msg = f"Solid conversation. {p.handle} leaves with a plan."
    elif option_id == "rest":
        p.stamina = min(100.0, p.stamina + 10.0)
        d_morale = 3.0
        d_form = -1.0
        msg = f"{p.handle} gets a lighter week."
    elif option_id == "honest":
        if steady:
            d_morale = 1.5
            msg = f"{p.handle} respects the straight answer."
        else:
            d_morale = -2.0
            msg = f"{p.handle} wanted more than that."
    elif option_id in ("deflect", "banter"):
        d_morale = 1.0 if rng.random() < 0.7 else -1.0
        msg = f"Nothing settled, nothing broken."

    p.morale = round(min(100.0, max(0.0, p.morale + d_morale)), 1)
    p.form = round(min(100.0, max(0.0, p.form + d_form)), 1)
    team = gs.teams[gs.acting_team_id]
    team.chemistry = round(min(100.0, max(0.0, team.chemistry + d_chem)), 1)

    # The 1:1 also colours how the player sees the captain running these
    # meetings: a talk that lands bonds them, one that backfires sours it.
    from esports_sim.manager import relationships

    captain = team.captain_id
    if captain and captain != pid and captain in gs.players:
        if d_chem < 0 or d_morale < 0:
            relationships.nudge(gs, pid, captain, -3.0)
        elif d_form > 0 or d_morale >= 3.0:
            relationships.nudge(gs, pid, captain, 2.0)

    gs.talked_week = week_key(gs)
    if abs(d_morale) >= 4.0:
        gs.push_news(f"1:1 with {p.handle}: {msg}")
    effects = {
        "morale": d_morale,
        "form": d_form,
        "chemistry": d_chem,
        "transfer_request": 1.0 if transfer_requested else 0.0,
    }
    return True, msg, effects


# ---------------------------------------------------------------------------
# Streaming: the manager can spend the week's 1:1 asking a player to cut back
# on streaming and put the hours into practice. It buys back development (the
# load drops, so training.py's growth penalty eases) at the cost of org
# streaming revenue and morale — you're telling someone to step away from
# something they enjoy and profit from. Shares the one-per-week 1:1 gate
# (can_talk): this week you address their morale, their contract, OR their
# streaming — one real conversation. Deterministic (no rng).

REIN_CHUNK = 30.0       # how far a single talk pushes stream_load down
REIN_MORALE_BASE = 4.0  # baseline morale cost of the conversation


def can_rein_streaming(gs: GameState, pid: str) -> tuple[bool, str]:
    """Whether a 'rein in the streaming' 1:1 is available for this player:
    on the acting roster, the weekly 1:1 unspent, and actually streaming
    enough to be worth the conversation."""
    from esports_sim.manager import social

    ok, why = can_talk(gs, pid)
    if not ok:
        return False, why
    p = gs.players[pid]
    if p.stream_load <= social.STREAM_LOAD_MIN + 1.0:
        return False, f"{p.handle} barely streams — nothing to rein in"
    return True, ""


def rein_in_streaming(gs: GameState, pid: str) -> tuple[bool, str, dict]:
    """Spend the week's 1:1 telling a player to stream less and grind. Lowers
    their streaming load (more practice per training.py, less revenue per
    economy.py) at a morale cost that's steeper for a heavier streamer and for
    a player who bristles at direction (big ego / thin resilience). The load
    drifts back toward its follower baseline over the following weeks
    (social.stream_load_tick), so this is a recurring lever, not a one-off fix."""
    from esports_sim.manager import personality, social

    ok, why = can_rein_streaming(gs, pid)
    if not ok:
        return False, why, {}
    p = gs.players[pid]
    before = p.stream_load
    p.stream_load = round(max(social.STREAM_LOAD_MIN, before - REIN_CHUNK), 1)
    dropped = round(before - p.stream_load, 1)
    # Morale cost: bigger the more they stream (more to give up), and bigger
    # for a big ego / thin resilience (dislikes being told what to do).
    ego = max(0.0, personality.dev(p, "ego"))
    resil = max(0.0, -personality.dev(p, "resilience"))
    cost = REIN_MORALE_BASE * (0.5 + before / 100.0) * (1.0 + 0.6 * ego + 0.4 * resil)
    d_morale = -round(cost, 1)
    p.morale = round(min(100.0, max(0.0, p.morale + d_morale)), 1)
    gs.talked_week = week_key(gs)
    gs.push_news(
        f"1:1 with {p.handle}: asked to cut the streaming and focus on the game. "
        + ("They take it on the chin." if d_morale > -5.0 else "They aren't happy.")
    )
    return True, (
        f"{p.handle} will stream less and practice more "
        f"(load {before:.0f} -> {p.stream_load:.0f})."
    ), {"stream_load": -dropped, "morale": d_morale}
