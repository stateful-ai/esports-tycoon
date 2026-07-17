"""Named rival managers — persistent human antagonists for AI orgs.

Every AI-run tier-1 club has a named manager persona so a legacy career
is a rivalry between PEOPLE, not just logos. Identity is a pure function
of the persona id (region-flavoured name from gen.py's pools, personality
axes from personality.axes_for_id); only the employment facts persist on
GameState.rival_managers (see state.RivalManager, schema v32).

Determinism: every derivation is blake2 of stable ids — no rng stream is
ever consumed, so persona creation and replacement leave every other draw
in the campaign byte-identical. The offseason board review is rng-free
arithmetic over the final table.

Effects are presentation/narrative ONLY (owner call for this phase): the
team profile shows the manager, the dashboard spotlight names the
opposing manager, hirings/firings/tenure milestones enter the append-only
chronicle (and thus the movement feed + news). No match modifiers.
"""

from __future__ import annotations

import hashlib

from esports_sim.manager import chronicle, personality, rivalries
from esports_sim.manager.career import _ordinal as _place
from esports_sim.manager.gen import (
    _FIRST_NAMES,
    _LAST_NAMES,
    _REGION_FIRST_NAMES,
    _REGION_LAST_NAMES,
)
from esports_sim.manager.state import GameState, RivalManager
from esports_sim.schemas.common import Region

# -- board-style patience heuristic (documented dials, narrative-level) ------
PATIENCE_START_BASE = 62.0  # a fresh appointment starts at 62..78
PATIENCE_START_SPAN = 16.0
PATIENCE_TITLE = 25.0  # any title this season delights the board
PATIENCE_TOP_HALF = 8.0  # a top-half finish rebuilds trust
PATIENCE_BOTTOM_FLAT = 5.0  # ...while the bottom half drains it,
PATIENCE_PER_SLOT = 7.0  # harder the deeper the finish
FIRE_BAR = 25.0  # patience at/below this in the bottom of the table = sacked
MIN_SEASONS = 2  # every appointment gets two full seasons first
TENURE_MILESTONES = (5, 10, 15, 20)  # anniversaries worth a chronicle line

TITLE_KINDS = ("champions_title", "masters_title", "regional_title")

# Dominant personality axis -> the one-word identity shown in the UI.
_IDENTITY: dict[tuple[str, bool], str] = {
    ("ego", True): "Showman",
    ("ego", False): "Understated",
    ("resilience", True): "Unshakeable",
    ("resilience", False): "Combustible",
    ("sociability", True): "Connector",
    ("sociability", False): "Recluse",
    ("professionalism", True): "Technician",
    ("professionalism", False): "Maverick",
    ("ambition", True): "Climber",
    ("ambition", False): "Custodian",
}


def _u(*parts: object) -> float:
    """Stable uniform in [0, 1) from blake2 of the parts — draw-free."""
    b = hashlib.blake2b(
        "|".join(str(x) for x in parts).encode("utf-8"), digest_size=8
    )
    return int.from_bytes(b.digest(), "big") / 2**64


def persona_id(seed: int, team_id: str, stint: int) -> str:
    raw = hashlib.blake2b(
        f"rival-mgr|{seed}|{team_id}|{stint}".encode("utf-8"), digest_size=8
    ).hexdigest()
    return f"rm_{raw}"


def persona_name(seed: int, team_id: str, region: str, stint: int) -> str:
    """Region-flavoured full name from gen.py's pools — blake2-picked so
    the same (seed, org, stint) always meets the same person."""
    try:
        reg = Region(region)
    except ValueError:
        reg = None
    firsts = _REGION_FIRST_NAMES.get(reg, _FIRST_NAMES)
    lasts = _REGION_LAST_NAMES.get(reg, _LAST_NAMES)
    first = firsts[int(_u(seed, team_id, stint, "rm-first") * len(firsts))]
    last = lasts[int(_u(seed, team_id, stint, "rm-last") * len(lasts))]
    return f"{first} {last}"


def _persona_fields(
    seed: int, team_id: str, region: str, tenure_start: int, stint: int
) -> dict:
    """The raw persona dict — shared by build_persona and the v31->v32
    migration (which works on plain save data, no models)."""
    return {
        "id": persona_id(seed, team_id, stint),
        "name": persona_name(seed, team_id, region, stint),
        "team_id": team_id,
        "tenure_start": tenure_start,
        "stint": stint,
        "patience": round(
            PATIENCE_START_BASE
            + _u(seed, team_id, stint, "rm-patience") * PATIENCE_START_SPAN,
            1,
        ),
    }


def build_persona(
    seed: int, team_id: str, region: str, tenure_start: int, stint: int = 0
) -> RivalManager:
    return RivalManager(
        **_persona_fields(seed, team_id, region, tenure_start, stint)
    )


def migrate_backfill(data: dict) -> dict:
    """v31->v32: found a persona at every AI tier-1 org of an old save.
    Pure function of the save's stable ids. Tenure is back-dated a few
    seasons (blake2-jittered, clamped to season 1) so an old league does
    not read as 24 simultaneous day-one appointments."""
    seed = int(data.get("seed", 0))
    season = int(data.get("season", 1))
    humans = set(data.get("human_team_ids") or [])
    if not humans and not data.get("career_offers_by"):
        # Pre-multiplayer saves named their one human via user_team_id;
        # an empty list with offers pending means that org is AI-run now.
        uid = data.get("user_team_id")
        if uid:
            humans = {uid}
    personas: dict[str, dict] = {}
    teams = data.get("teams") or {}
    for tid in sorted(teams):
        t = teams[tid]
        if int(t.get("tier", 1)) != 1 or tid in humans:
            continue
        back = int(_u(seed, tid, "rm-backdate") * 8)
        personas[tid] = _persona_fields(
            seed,
            tid,
            str(t.get("region", "")),
            tenure_start=max(1, season - back),
            stint=0,
        )
    data["rival_managers"] = personas
    return data


# -- lifecycle ---------------------------------------------------------------


def _next_stint(gs: GameState, team_id: str) -> int:
    """How many managers (human or persona) this org has already been
    through — re-derived from the append-only chronicle so a persona
    created after a human era never reuses a predecessor's name."""
    return sum(
        1
        for e in gs.chronicle
        if e.kind == "appointment" and e.team_id == team_id
    )


def ensure_personas(gs: GameState, *, chronicle_new: bool = True) -> None:
    """Idempotent, rng-free reconciliation: every AI tier-1 org holds a
    persona; a human-run org never does (the human IS the manager — their
    appointment is already chronicled by career.create_seat/accept_offer).
    `chronicle_new=False` at new_campaign: founding managers simply exist,
    they are not 24 news stories."""
    for tid in sorted(gs.teams):
        t = gs.teams[tid]
        if t.tier != 1:
            continue
        if gs.is_human(tid):
            gs.rival_managers.pop(tid, None)
            continue
        if tid in gs.rival_managers:
            continue
        rm = build_persona(
            gs.seed, tid, str(t.region),
            tenure_start=gs.season, stint=_next_stint(gs, tid),
        )
        gs.rival_managers[tid] = rm
        if chronicle_new:
            chronicle.record(
                gs, "appointment",
                f"{rm.name} takes charge of {t.name}.",
                team_id=tid, importance=50.0, data={"rm": rm.id},
            )
            gs.push_news(f"{t.name} appoint {rm.name} as their new manager.")


def offseason_tick(gs: GameState) -> list[str]:
    """The AI boards' season review. Runs while the final table is still
    in state (before standings reset): patience follows the finish, a
    struggling org at the bottom of the table replaces its manager, and
    tenure anniversaries are chronicled. Deterministic and rng-free —
    plain arithmetic over the table plus blake2-derived successors.
    Returns the news lines pushed (for the caller's report)."""
    lines: list[str] = []
    for region in gs.league_regions:
        order = gs.standings_order(str(region), tier=1)
        n = len(order)
        if n == 0:
            continue
        bottom_from = n - max(2, n // 3)  # "the bottom of the table"
        for pos, tid in enumerate(order, start=1):
            rm = gs.rival_managers.get(tid)
            if rm is None:
                continue
            team = gs.teams[tid]
            titled = any(
                e.kind in TITLE_KINDS
                and e.team_id == tid
                and e.season == gs.season
                for e in gs.chronicle
            )
            if titled:
                delta = PATIENCE_TITLE
            elif pos <= n // 2:
                delta = PATIENCE_TOP_HALF
            else:
                delta = -(
                    PATIENCE_BOTTOM_FLAT + (pos - n // 2) * PATIENCE_PER_SLOT
                )
            rm.patience = round(min(100.0, max(0.0, rm.patience + delta)), 1)
            seasons_at = gs.season - rm.tenure_start + 1
            fired = (
                rm.patience <= FIRE_BAR
                and pos > bottom_from
                and seasons_at >= MIN_SEASONS
            )
            if fired:
                chronicle.record(
                    gs, "dismissal",
                    f"{team.name} part ways with manager {rm.name} "
                    f"after {seasons_at} seasons.",
                    team_id=tid, importance=55.0, data={"rm": rm.id},
                )
                successor = build_persona(
                    gs.seed, tid, str(team.region),
                    tenure_start=gs.season + 1,
                    stint=max(rm.stint + 1, _next_stint(gs, tid)),
                )
                gs.rival_managers[tid] = successor
                chronicle.record(
                    gs, "appointment",
                    f"{successor.name} takes charge of {team.name}.",
                    team_id=tid, importance=50.0, data={"rm": successor.id},
                )
                line = (
                    f"{team.name} sack {rm.name} after finishing "
                    f"{_place(pos)} of {n} and hand the reins to "
                    f"{successor.name}."
                )
                gs.push_news(line)
                lines.append(line)
            elif seasons_at in TENURE_MILESTONES:
                chronicle.record(
                    gs, "milestone",
                    f"{rm.name} marks {seasons_at} seasons in charge "
                    f"of {team.name}.",
                    team_id=tid, data={"rm": rm.id},
                )
                line = (
                    f"{rm.name} reaches {seasons_at} seasons at the helm "
                    f"of {team.name}."
                )
                gs.push_news(line)
                lines.append(line)
    return lines


# -- pure readers --------------------------------------------------------------


def identity_for_id(mid: str) -> str:
    """The one-word identity from the dominant personality axis — a pure
    function of the manager/persona/seat id, so it never drifts."""
    ax = personality.axes_for_id(mid)
    axis, val = sorted(
        ax.items(), key=lambda kv: (-abs(kv[1] - 50.0), kv[0])
    )[0]
    return _IDENTITY[(axis, val >= 50.0)]


def _titles_since(gs: GameState, team_id: str, since_season: int) -> int:
    return sum(
        1
        for e in gs.chronicle
        if e.kind in TITLE_KINDS
        and e.team_id == team_id
        and e.season >= since_season
    )


def _tenure_start_of(gs: GameState, team_id: str) -> int | None:
    """First season of the org's CURRENT manager: persona tenure for AI
    orgs, contract start for a legacy human seat (sandbox seats never
    move, so they date from season 1). None = no manager known."""
    rm = gs.rival_managers.get(team_id)
    if rm is not None and not gs.is_human(team_id):
        return rm.tenure_start
    seat = gs.manager_for(team_id)
    if seat is not None:
        return seat.contract.start_season if seat.contract else 1
    return None


def manager_heat(gs: GameState, a: str, b: str) -> float:
    """Manager-vs-manager heat: the orgs' existing rivalry pair heat
    (manager/rivalries.py — the single store of grudges) scaled by how
    long BOTH current managers have been in post while it burned. Three
    shared seasons carry the full org heat; a fresh hire inherits little.
    Pure read — nothing new is stored."""
    org = rivalries.get(gs, a, b)
    if org <= 0.0:
        return 0.0
    sa, sb = _tenure_start_of(gs, a), _tenure_start_of(gs, b)
    if sa is None or sb is None:
        return 0.0
    overlap = gs.season - max(sa, sb) + 1
    if overlap <= 0:
        return 0.0
    return round(org * min(1.0, overlap / 3.0), 1)


def career_line(gs: GameState, rm: RivalManager) -> str:
    """One grounded sentence from the chronicle — silence beats drama."""
    seasons_at = max(1, gs.season - rm.tenure_start + 1)
    titles = _titles_since(gs, rm.team_id, rm.tenure_start)
    line = f"Season {seasons_at} in charge"
    if titles:
        line += f"; {titles} title{'s' if titles != 1 else ''} in tenure"
    return line + "."


def profile_view(gs: GameState, team_id: str) -> dict | None:
    """The team-profile "manager" block — persona for AI orgs, the human
    seat for human orgs, one shape for both so the client renders one
    way. None for tier-2 orgs (they have no named manager layer)."""
    t = gs.teams.get(team_id)
    if t is None or t.tier != 1:
        return None
    rm = gs.rival_managers.get(team_id)
    if rm is not None and not gs.is_human(team_id):
        name, mid, since = rm.name, rm.id, rm.tenure_start
        human = False
    else:
        seat = gs.manager_for(team_id)
        if seat is None:
            return None
        name, mid = seat.name, seat.id
        since = (
            seat.contract.start_season if seat.contract is not None else 1
        )
        human = True
    heat = (
        manager_heat(gs, team_id, gs.acting_team_id)
        if team_id != gs.acting_team_id
        else 0.0
    )
    return {
        "name": name,
        "human": human,
        "identity": identity_for_id(mid),
        "since": since,
        "seasons": max(1, gs.season - since + 1),
        "honours": _titles_since(gs, team_id, since),
        "heat": heat if heat > 0.0 else None,
    }


def spotlight_view(gs: GameState, team_id: str) -> dict | None:
    """The dashboard spotlight's "who is across the aisle" line: just the
    name and the one-word identity (both public broadcast facts)."""
    view = profile_view(gs, team_id)
    if view is None:
        return None
    return {"name": view["name"], "identity": view["identity"]}
