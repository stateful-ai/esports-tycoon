"""The deterministic match resolver: ``run(state, decisions, seed) -> WhyRecord``.

This is rule #1 of the architecture made literal. The resolver is **pure and
headless**: it takes the already-loaded :class:`~esports_tycoon.schema.WorldState`,
the manager's structured :class:`~esports_tycoon.schema.Decisions`, and a seed
(defaulting to the save's own ``state.seed`` — the seed-in-save contract), and
returns a structured :class:`~esports_tycoon.schema.WhyRecord` that the narrator
consumes verbatim. The bridge between the scoreboard and the story is *data, not
vibes* — there is no LLM, no clock, no entropy beyond the seed, no file or network
I/O, and nothing under ``content/`` is imported. The only inputs are the three
arguments; the only randomness is a local ``random.Random(seed)``.

The result is also not arbitrary. A coin-flip resolver would be deterministic
but tell no story. Outcomes here are *grounded in the canned world* so the drama
is earned:

* **Skill** comes from each starter's traits (the cast was authored to differ).
* **Form** comes from the sentiment of their most recent memories — a player on
  a bad run plays worse. This is the "memory compounds" thesis reaching the
  scoreboard.
* **Map comfort** comes from memories tagged with the map being played.
* **Tilt** comes from tilt-prone traits *and* from the explicit clash pairs:
  field two people who are feuding and the more combustible one is likelier to
  come apart.
* **Difficulty** comes from the opposing org's archetype (the Dynasty is a wall;
  the Chaos Agents are a coin you can't read).

Same ``state`` + ``decisions`` + ``seed`` always yields an identical record;
different seeds explore the distribution those inputs define.
"""

from __future__ import annotations

import math
from random import Random
from typing import Optional

from esports_tycoon.schema import (
    Decisions,
    KeyMoment,
    Player,
    PracticeFocus,
    RecallTag,
    Role,
    RoundResult,
    TacticalStance,
    WhyRecord,
    WorldState,
)

__all__ = ["run", "KIND_TO_RECALL_TAG"]


#: Mapping from the resolver's narrator-facing :attr:`KeyMoment.kind` to the
#: frozen recall vocabulary (:data:`~esports_tycoon.schema.RecallTag`). Kinds
#: that do not rhyme with any recall tag (e.g. ``"ace"``) deliberately have no
#: entry — the beat is still narrated, but it contributes no tag-overlap signal
#: to the deterministic precedent recall (which is what "fails closed on
#: off-vocabulary tags" means in practice). The mapping is *one-way*: the wider
#: ``kind`` vocabulary stays unconstrained for the templated copy pack, while
#: the recall plane stays small and typed.
KIND_TO_RECALL_TAG: dict[str, RecallTag] = {
    "choke": "choke",
    "clutch": "clutch",
    "comeback": "clutch",
    "dominant": "clutch",
    "closeout": "clutch",
    "blowout": "tilt",
    "match_point": "tilt",
}

# --------------------------------------------------------------------------- #
# Tuning. All grounding lives in these tables, so the model is auditable at a
# glance and a new trait simply scores 0 until someone gives it weight.
# --------------------------------------------------------------------------- #
_BASE_SKILL = 5.0

#: How much each authored trait moves a player's per-round skill.
_SKILL_TRAITS: dict[str, float] = {
    "mechanically-gifted": 3.0,
    "veteran": 2.0,
    "reliable": 2.0,
    "anchor": 2.0,
    "info-savant": 2.0,
    "hotshot": 2.0,
    "structure-first": 1.0,
    "patient": 1.0,
    "lurker": 1.0,
    "stoic": 1.0,
    "control-freak": 1.0,
    "impulsive": -1.0,
    "oversharer": -1.0,
    "aging-out": -2.0,
}

#: How prone each trait makes a player to tilting (coming apart under pressure).
#: Positive = more fragile, negative = steadier.
_TILT_TRAITS: dict[str, float] = {
    "impulsive": 3.0,
    "clout-chasing": 2.0,
    "defensive": 2.0,
    "grudge-holder": 2.0,
    "hotshot": 1.0,
    "oversharer": 1.0,
    "stoic": -3.0,
    "deadpan": -2.0,
    "patient": -2.0,
    "reliable": -2.0,
    "low-ego": -2.0,
    "veteran": -1.0,
    "anchor": -1.0,
    "structure-first": -1.0,
}

#: A practice block lifts (+2 skill) the roles it suits. "rest" trains no skill
#: but settles nerves (see ``_tilt_for``).
_PRACTICE_ROLES: dict[PracticeFocus, frozenset[Role]] = {
    "aim": frozenset({Role.DUELIST}),
    "comms": frozenset({Role.IGL, Role.INITIATOR}),
    "defaults": frozenset({Role.IGL, Role.CONTROLLER}),
    "anti_strat": frozenset({Role.SENTINEL, Role.CONTROLLER}),
    "rest": frozenset(),
}
_PRACTICE_SKILL_BONUS = 2.0

#: Per-player-equivalent strength of an opposing org, keyed by its archetype.
#: The opponent has no canned roster in M0, so the archetype carries the weight.
_ARCHETYPE_STRENGTH: dict[str, float] = {
    "The Dynasty": 8.5,
    "The Wunderkind / Heir": 8.0,
    "The Ex-Teammate": 7.5,
    "The Chaos Agents": 6.5,
    "The Rising Underdog": 6.0,
    "The Fallen Star": 6.0,
}
_DEFAULT_ARCHETYPE_STRENGTH = 7.0

#: The Chaos Agents play off-meta: each round their effective edge jitters, so
#: the series is far harder to predict (and to grind out) than its mean implies.
_CHAOS_ARCHETYPE = "The Chaos Agents"
_CHAOS_ROUND_JITTER = 0.15

#: Logistic scale turning a (team - opponent) strength gap into a round-win
#: probability. Larger = flatter (gaps matter less).
_ROUND_SCALE = 8.0

# First-to-13, win by 2 (overtime). The cap is a safety net for the vanishingly
# unlikely endless-overtime draw; real series terminate in well under it.
_ROUNDS_TO_WIN = 13
_WIN_BY = 2
_MAX_ROUNDS = 60

# Per-round narrative-event probabilities (all drawn from the seeded RNG).
_ACE_PROB = 0.06
_CLUTCH_PROB = 0.55
_CONSOLATION_PROB = 0.22
_BACK_FOOT_LOSSES = 2  # consecutive lost rounds that make the next win a clutch

# A run of this many rounds of lead that then evaporates / is overturned earns a
# "choke" / "comeback" key moment.
_SWING_THRESHOLD = 6
_BLOWOUT_MARGIN = 6  # final margin that reads as dominant / one-sided

# Morale arithmetic, clamped to keep one match from swinging a season.
_MORALE_WIN = 2
_MORALE_LOSS = -2
_MORALE_MVP = 2
_MORALE_CARRY = 1
_MORALE_TILT = -3
_MORALE_CLAMP = 5

# Tilt accounting.
_CLASH_TILT = 2.0
_LOSS_TILT = 2.0
_ZERO_IMPACT_TILT = 2.0
_AGGRESSIVE_TILT_TRAITS = frozenset({"impulsive", "hotshot", "clout-chasing"})
_TILT_THRESHOLD = 4.0
_MAX_TILTED = 3
_MAX_CARRIERS = 3
_MAX_KEY_MOMENTS = 6
_RECENT_MEMORIES = 3  # how many of a player's latest memories set their form


# --------------------------------------------------------------------------- #
# Pure helpers. Each takes only its arguments — no module or RNG state.
# --------------------------------------------------------------------------- #
def _logistic(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _form(player: Player) -> float:
    """Recent-memory sentiment as a small skill swing.

    The player's latest few memories (by week then day) vote: +1 positive, -1
    negative, 0 neutral. A losing streak in the log literally drags their play.
    """
    recent = sorted(player.memory_log, key=lambda m: (m.week, m.day))[-_RECENT_MEMORIES:]
    score = 0
    for entry in recent:
        if entry.sentiment == "positive":
            score += 1
        elif entry.sentiment == "negative":
            score -= 1
    return float(score)


def _map_affinity(player: Player, map_name: str) -> float:
    """Comfort on this map, read from memories tagged with it.

    Clamped to ±2 so one storied map can't dominate raw skill.
    """
    needle = map_name.strip().lower()
    if not needle:
        return 0.0
    score = 0
    for entry in player.memory_log:
        if needle in (tag.lower() for tag in entry.tags):
            score += 1 if entry.sentiment == "positive" else -1 if entry.sentiment == "negative" else 0
    return float(max(-2, min(2, score)))


def _skill_for(player: Player, decisions: Decisions) -> float:
    """A player's effective per-round skill for this match (always ≥ 0.5)."""
    skill = _BASE_SKILL
    skill += sum(_SKILL_TRAITS.get(trait, 0.0) for trait in player.traits)
    skill += _form(player)
    skill += _map_affinity(player, decisions.map)
    if player.role in _PRACTICE_ROLES[decisions.practice_focus]:
        skill += _PRACTICE_SKILL_BONUS
    return max(0.5, skill)


def _base_tilt(player: Player) -> float:
    """Trait-only tilt proneness, before clashes and match circumstance."""
    return sum(_TILT_TRAITS.get(trait, 0.0) for trait in player.traits)


def _opponent_strength(world: WorldState, opponent_id: str) -> float:
    """Per-player-equivalent strength of the scheduled opponent.

    Raises ``ValueError`` (pure, no I/O) if the opponent is not a known rival.
    """
    for rival in world.rivals:
        if rival.id == opponent_id:
            return _ARCHETYPE_STRENGTH.get(rival.archetype, _DEFAULT_ARCHETYPE_STRENGTH)
    known = ", ".join(sorted(r.id for r in world.rivals))
    raise ValueError(f"unknown opponent {opponent_id!r}; known rivals: {known}")


def _resolve_lineup(world: WorldState, decisions: Decisions) -> list[Player]:
    """The five starters to field, validated.

    An empty ``decisions.lineup`` defaults to the managed team's roster in save
    order; anything else must be exactly five distinct ids drawn from that roster.
    """
    by_id = {p.id: p for p in world.roster}
    if not decisions.lineup:
        return list(world.roster)

    seen: set[str] = set()
    lineup: list[Player] = []
    for pid in decisions.lineup:
        if pid not in by_id:
            known = ", ".join(sorted(by_id))
            raise ValueError(f"unknown starter {pid!r} in lineup; known starters: {known}")
        if pid in seen:
            raise ValueError(f"duplicate starter {pid!r} in lineup")
        seen.add(pid)
        lineup.append(by_id[pid])
    if len(lineup) != 5:
        raise ValueError(f"lineup must field exactly 5 starters, got {len(lineup)}")
    return lineup


def _weighted_pick(rng: Random, ids: list[str], weights: list[float]) -> str:
    """Deterministically pick one id with probability proportional to its weight.

    Draws exactly one value from ``rng``; ``ids`` is iterated in its given (fixed)
    order so the choice is reproducible.
    """
    total = sum(weights)
    if total <= 0:
        return ids[rng.randrange(len(ids))]
    threshold = rng.random() * total
    cumulative = 0.0
    for pid, weight in zip(ids, weights):
        cumulative += weight
        if threshold < cumulative:
            return pid
    return ids[-1]


def _stance_team_bonus(stance: TacticalStance, lineup: list[Player]) -> float:
    """Team-strength swing from the tactical stance.

    Aggression buys raw pressure; discipline only pays off when a structure-first
    caller is on the server to enforce it.
    """
    if stance == "aggressive":
        return 2.0
    if stance == "disciplined":
        has_structure_igl = any(
            p.role is Role.IGL and "structure-first" in p.traits for p in lineup
        )
        return 1.0 if has_structure_igl else 0.0
    return 0.0


def _tilt_for(
    player: Player,
    base_tilt: float,
    decisions: Decisions,
    clash_tilt: float,
    lost_match: bool,
    impact: int,
) -> float:
    """Final tilt pressure on a player after the match is known.

    Combines authored fragility, seeded clashes, the stance/practice mood, the
    sting of a loss and a quiet game, minus whatever they actually contributed.
    """
    tilt = base_tilt + clash_tilt
    if decisions.tactical_stance == "aggressive" and (
        _AGGRESSIVE_TILT_TRAITS & set(player.traits)
    ):
        tilt += 1.0
    if decisions.tactical_stance == "disciplined":
        tilt -= 1.0
    if decisions.practice_focus == "rest":
        tilt -= 1.0
    if lost_match:
        tilt += _LOSS_TILT
    if impact == 0:
        tilt += _ZERO_IMPACT_TILT
    tilt -= impact
    return tilt


def _clash_tilt_by_player(world: WorldState, lineup: list[Player]) -> dict[str, float]:
    """Extra tilt pushed onto the more combustible side of each live intra-team clash.

    Only clashes whose *both* members are fielded count — a feud you bench can't
    blow up. The steadier member absorbs it; the more tilt-prone one carries it.
    """
    fielded = {p.id: p for p in lineup}
    base = {p.id: _base_tilt(p) for p in lineup}
    extra = {p.id: 0.0 for p in lineup}
    for clash in world.clash_pairs:
        if clash.cross_team:
            continue
        if clash.a in fielded and clash.b in fielded:
            # Tie-break on id so the assignment is stable.
            target = max((clash.a, clash.b), key=lambda pid: (base[pid], pid))
            extra[target] += _CLASH_TILT
    return extra


# --------------------------------------------------------------------------- #
# The resolver.
# --------------------------------------------------------------------------- #
def run(state: WorldState, decisions: Decisions, seed: Optional[int] = None) -> WhyRecord:
    """Resolve one match into a structured :class:`WhyRecord`.

    Pure and deterministic: identical ``state``/``decisions``/``seed`` always
    produce an identical record. ``state`` and ``decisions`` are read, never
    mutated.

    ``seed`` defaults to the save's own ``state.seed`` (the seed-in-save
    contract): with no explicit seed, the match's randomness is anchored in the
    loaded save, so the same save always replays to the same week. Passing an
    explicit ``seed`` overrides it to explore the distribution those inputs
    define — the seed is still threaded into the one local generator and echoed
    back on the record, so the result remains fully reproducible either way.
    """
    if seed is None:
        seed = state.seed
    rng = Random(seed)

    lineup = _resolve_lineup(state, decisions)
    lineup_ids = [p.id for p in lineup]
    opponent_id = decisions.opponent

    skill = {p.id: _skill_for(p, decisions) for p in lineup}
    weights = [skill[pid] for pid in lineup_ids]
    team_strength = sum(weights) + _stance_team_bonus(decisions.tactical_stance, lineup)
    opponent_strength = _opponent_strength(state, opponent_id) * len(lineup)

    is_chaos = any(
        r.id == opponent_id and r.archetype == _CHAOS_ARCHETYPE for r in state.rivals
    )
    base_round_p = _logistic((team_strength - opponent_strength) / _ROUND_SCALE)

    impact = {pid: 0 for pid in lineup_ids}
    round_log: list[RoundResult] = []
    key_moments: list[KeyMoment] = []
    star_by_round: dict[int, str] = {}

    overcast = 0
    opponent = 0
    recent_results: list[bool] = []  # True = Overcast won that round
    peak_ovc_lead = 0
    peak_ovc_lead_round = 1
    peak_opp_lead = 0
    peak_opp_lead_round = 1

    rounds_played = 0
    while rounds_played < _MAX_ROUNDS:
        rounds_played += 1
        rnd = rounds_played

        # Round win probability. Draw the chaos jitter first (only against the
        # Chaos Agents) so the RNG sequence is identical for a given matchup.
        p = base_round_p
        if is_chaos:
            p = min(0.95, max(0.05, p + rng.uniform(-_CHAOS_ROUND_JITTER, _CHAOS_ROUND_JITTER)))
        overcast_won = rng.random() < p

        if overcast_won:
            overcast += 1
            star = _weighted_pick(rng, lineup_ids, weights)
            star_by_round[rnd] = star
            impact[star] += 1

            if rng.random() < _ACE_PROB:
                impact[star] += 2
                key_moments.append(
                    KeyMoment(
                        round=rnd,
                        kind="ace",
                        actors=[star],
                        descriptor="5k",
                        tag=KIND_TO_RECALL_TAG.get("ace"),
                        actor_ref=star,
                    )
                )
            elif (
                len(recent_results) >= _BACK_FOOT_LOSSES
                and not any(recent_results[-_BACK_FOOT_LOSSES:])
                and rng.random() < _CLUTCH_PROB
            ):
                impact[star] += 1
                key_moments.append(
                    KeyMoment(
                        round=rnd,
                        kind="clutch",
                        actors=[star],
                        descriptor="won it off the back foot",
                        tag=KIND_TO_RECALL_TAG.get("clutch"),
                        actor_ref=star,
                    )
                )
        else:
            opponent += 1
            # Even in a lost round someone can make a play worth a morale point.
            if rng.random() < _CONSOLATION_PROB:
                impact[_weighted_pick(rng, lineup_ids, weights)] += 1

        winner = state.team.id if overcast_won else opponent_id
        round_log.append(
            RoundResult(round=rnd, winner=winner, summary=f"{overcast}-{opponent}")
        )
        recent_results.append(overcast_won)

        lead = overcast - opponent
        if lead > peak_ovc_lead:
            peak_ovc_lead, peak_ovc_lead_round = lead, rnd
        if -lead > peak_opp_lead:
            peak_opp_lead, peak_opp_lead_round = -lead, rnd

        if max(overcast, opponent) >= _ROUNDS_TO_WIN and abs(overcast - opponent) >= _WIN_BY:
            break

    final_round = rounds_played
    won_match = overcast > opponent

    # --- Standout players -------------------------------------------------- #
    ranked = sorted(lineup_ids, key=lambda pid: (-impact[pid], pid))
    top_impact = impact[ranked[0]]
    if top_impact > 0:
        mvp = ranked[0]
        carry_floor = max(2, math.ceil(0.6 * top_impact))
        who_carried = [pid for pid in ranked if impact[pid] >= carry_floor][:_MAX_CARRIERS]
    else:
        # A win with no tracked plays is impossible, but a loss can leave nobody
        # standing out — fall back to the strongest performer so MVP is always set.
        mvp = sorted(lineup_ids, key=lambda pid: (-skill[pid], pid))[0]
        who_carried = []

    # --- Who came apart ---------------------------------------------------- #
    clash_tilt = _clash_tilt_by_player(state, lineup)
    carried = set(who_carried) | {mvp}
    tilt_scores: list[tuple[float, str]] = []
    for player in lineup:
        if player.id in carried:
            continue  # a carrier didn't tilt, whatever their wiring
        score = _tilt_for(
            player,
            _base_tilt(player),
            decisions,
            clash_tilt[player.id],
            lost_match=not won_match,
            impact=impact[player.id],
        )
        if score >= _TILT_THRESHOLD:
            tilt_scores.append((score, player.id))
    tilt_scores.sort(key=lambda item: (-item[0], item[1]))
    who_tilted = [pid for _, pid in tilt_scores[:_MAX_TILTED]]

    # --- Macro key moments ------------------------------------------------- #
    closeout_star = star_by_round.get(final_round, mvp)
    if won_match and peak_opp_lead >= _SWING_THRESHOLD:
        actors = who_carried or [mvp]
        key_moments.append(
            KeyMoment(
                round=peak_opp_lead_round,
                kind="comeback",
                actors=actors,
                descriptor=f"clawed back from {peak_opp_lead} down",
                tag=KIND_TO_RECALL_TAG.get("comeback"),
                actor_ref=actors[0],
            )
        )
    if (not won_match) and peak_ovc_lead >= _SWING_THRESHOLD:
        choke_actor = _igl_id(lineup) or mvp
        key_moments.append(
            KeyMoment(
                round=peak_ovc_lead_round,
                kind="choke",
                actors=[choke_actor],
                descriptor=f"threw a {peak_ovc_lead}-round lead",
                tag=KIND_TO_RECALL_TAG.get("choke"),
                actor_ref=choke_actor,
            )
        )
    if abs(overcast - opponent) >= _BLOWOUT_MARGIN:
        blowout_actors = who_carried or [mvp]
        key_moments.append(
            KeyMoment(
                round=final_round,
                kind="dominant" if won_match else "blowout",
                actors=blowout_actors,
                descriptor=f"{overcast}-{opponent}",
                tag="clutch" if won_match else "tilt",
                actor_ref=blowout_actors[0],
            )
        )
    # The decisive round is always worth narrating, so reserve it a slot and let
    # the cap fall on the earlier colour instead of the closeout itself.
    closeout = KeyMoment(
        round=final_round,
        kind="closeout" if won_match else "match_point",
        actors=[closeout_star],
        descriptor=f"{overcast}-{opponent}",
        tag="clutch" if won_match else "tilt",
        actor_ref=closeout_star,
    )
    key_moments.sort(key=lambda m: (m.round, m.kind))
    key_moments = key_moments[: _MAX_KEY_MOMENTS - 1] + [closeout]
    key_moments.sort(key=lambda m: (m.round, m.kind))

    # --- Morale ------------------------------------------------------------ #
    tilted = set(who_tilted)
    morale_deltas: dict[str, int] = {}
    for pid in lineup_ids:
        delta = _MORALE_WIN if won_match else _MORALE_LOSS
        if pid == mvp:
            delta += _MORALE_MVP
        if pid in carried:
            delta += _MORALE_CARRY
        if pid in tilted:
            delta += _MORALE_TILT
        morale_deltas[pid] = max(-_MORALE_CLAMP, min(_MORALE_CLAMP, delta))

    return WhyRecord(
        scoreline=(overcast, opponent),
        mvp=mvp,
        key_moments=key_moments,
        who_carried=who_carried,
        who_tilted=who_tilted,
        morale_deltas=morale_deltas,
        seed=seed,
        round_log=round_log,
    )


def _igl_id(lineup: list[Player]) -> Optional[str]:
    """The fielded in-game leader, if any — they own a choke."""
    for player in lineup:
        if player.role is Role.IGL:
            return player.id
    return None
