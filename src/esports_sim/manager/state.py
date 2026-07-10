"""Campaign state — everything a save file needs.

Static registries (agents, weapons, maps, attribute definitions) are NOT
stored here; they reload from `data/` YAML. The save holds the mutable
world: teams, players, fixtures, standings, money, news.

Determinism: the campaign seed + (season, week, ...) labels drive every
stochastic step, and finished matches store the exact seed they were
simulated with — so a match can be re-simulated later to replay its full
event log (nothing but the box score is persisted).
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

from esports_sim.schemas import Player, Team
from esports_sim.schemas.common import Region

SCHEMA_VERSION = 5

# Save migrations, keyed by the schema_version they upgrade FROM. Each takes
# the raw parsed dict and returns it bumped one version forward. Add-a-field
# changes need nothing here (new fields carry defaults); this is for structural
# renames/moves a plain load couldn't absorb.


def _migrate_v1_to_v2(data: dict) -> dict:
    """v1 stored one human manager's private state as flat top-level fields.
    v2 makes the campaign multi-manager: that state moves under a per-team map
    keyed by team id, so several humans can share one world (LAN play) each
    with their own inbox/scouting/sponsors/staff/facilities. A v1 save has
    exactly one human — its `user_team_id` — so every old value slots in under
    that key. `extra="forbid"` means the old flat keys MUST be removed here."""
    uid = data.get("user_team_id")
    data["human_team_ids"] = [uid] if uid else []
    # (old flat field, new per-team storage field, default when absent)
    moves = [
        ("inbox", "inboxes", []),
        ("scout_target", "scout_targets", None),
        ("scout_progress", "scout_progress_by", {}),
        ("talked_week", "talked_weeks", ""),
        ("sponsor", "sponsor_by", None),
        ("sponsor_offer", "sponsor_offer_by", None),
        ("sponsor_slots", "sponsor_slots_by", {}),
        ("sponsor_slot_offers", "sponsor_slot_offers_by", {}),
        ("sponsor_market", "sponsor_market_by", {}),
        ("sponsor_relations", "sponsor_relations_by", {}),
        ("facilities", "facilities_by", {}),
        ("staff", "staff_by", {}),
        ("staff_candidates", "staff_candidates_by", {}),
    ]
    for old, new, default in moves:
        value = data.pop(old, default)
        data[new] = {uid: value} if uid else {}
    return data


def _migrate_v2_to_v3(data: dict) -> dict:
    """v2 kept a small per-manager staff candidate market (3 per role).
    v3 replaces it with one shared, world-level free-agent pool of staff
    (`staff_pool`) that every manager hires from. Old candidates fold into
    the pool (deduped by id); the per-manager field is removed. Missing
    v3 StaffMember fields (age/region/...) carry model defaults."""
    pool: list[dict] = []
    seen: set[str] = set()
    for market in (data.pop("staff_candidates_by", None) or {}).values():
        for members in (market or {}).values():
            for m in members or []:
                if m.get("id") and m["id"] not in seen:
                    seen.add(m["id"])
                    pool.append(m)
    data["staff_pool"] = pool
    return data


def _migrate_v3_to_v4(data: dict) -> dict:
    """v4 adds only new fields with defaults (game plans, meta patches,
    community sentiment) — a v3 save loads unchanged. The version bump
    exists so an OLDER build refuses a v4 save with the clean "update the
    game" message instead of an extra="forbid" validation stack trace."""
    return data


def _migrate_v4_to_v5(data: dict) -> dict:
    """v5 adds the career Chronicle (plus legacy-mode fields, all
    defaulted). Backfill a skeleton history from the record lists a v4
    save already keeps — champions, awards, retirements — so career
    views aren't empty on old saves. Weeks are unknown for past seasons;
    0 marks a backfilled entry."""
    import hashlib

    def eid(season: int, kind: str, *parts: object) -> str:
        key = "|".join(str(x) for x in (season, 0, kind, *parts))
        return hashlib.blake2b(key.encode("utf-8"), digest_size=8).hexdigest()

    chron: list[dict] = []
    for c in data.get("champions") or []:
        chron.append(
            {
                "id": eid(c["season"], "champions_title", c["team_id"], ""),
                "season": c["season"],
                "week": 0,
                "kind": "champions_title",
                "importance": 95.0,
                "team_id": c["team_id"],
                "player_id": "",
                "manager_id": "",
                "text": f"{c['team_name']} win Champions.",
                "data": {"title": f"S{c['season']} Champions"},
            }
        )
    for a in data.get("awards") or []:
        chron.append(
            {
                "id": eid(a["season"], "award", "", a["player_id"], a["award"]),
                "season": a["season"],
                "week": 0,
                "kind": "award",
                "importance": 60.0,
                "team_id": "",
                "player_id": a["player_id"],
                "manager_id": "",
                "text": f"{a['handle']} wins {a['award']} ({a['value']}).",
                "data": {"award": a["award"]},
            }
        )
    for r in data.get("retired") or []:
        chron.append(
            {
                "id": eid(r["season"], "retirement", "", r["handle"]),
                "season": r["season"],
                "week": 0,
                "kind": "retirement",
                "importance": 40.0,
                "team_id": "",
                "player_id": "",
                "manager_id": "",
                "text": f"{r['handle']} retires at {r['age']}.",
                "data": {},
            }
        )
    chron.sort(key=lambda e: (e["season"], e["week"], e["kind"], e["id"]))
    data["chronicle"] = chron
    return data


_MIGRATIONS: dict[int, "callable"] = {
    1: _migrate_v1_to_v2,
    2: _migrate_v2_to_v3,
    3: _migrate_v3_to_v4,
    4: _migrate_v4_to_v5,
}

REGULAR_PRIZES = [250_000, 180_000, 140_000, 110_000, 90_000, 70_000, 55_000, 45_000]
PRIZE_SEMI_LOSER = 60_000
PRIZE_FINAL_LOSER = 120_000
PRIZE_CHAMPION = 300_000


class PlayerLineSnap(BaseModel):
    """Per-map box-score line kept in the save (events are re-derivable)."""

    model_config = ConfigDict(extra="forbid")

    player_id: str
    kills: int
    deaths: int
    rating: float


class MapResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    map_id: str
    seed: int
    score_a: int
    score_b: int
    winner_id: str
    lines: list[PlayerLineSnap] = Field(default_factory=list)


class Fixture(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    week: int
    # regular | semi | final (regional) · masters_qf | masters_sf |
    # masters_final (international)
    stage: str = "regular"
    # "league" = intra-region, "masters" = cross-region. Default keeps
    # pre-VCT saves loading.
    bracket: str = "league"
    # 1 = franchised, 2 = Challengers (simmed, no replay capture).
    tier: int = 1
    best_of: int = 1
    team_a: str
    team_b: str
    maps: list[str] = Field(default_factory=list)  # planned map order
    # Human-readable veto log for BO3s, e.g. "NXS ban bind".
    veto: list[str] = Field(default_factory=list)
    played: bool = False
    results: list[MapResult] = Field(default_factory=list)
    winner_id: str | None = None

    @property
    def map_score(self) -> tuple[int, int]:
        a = sum(1 for r in self.results if r.winner_id == self.team_a)
        b = sum(1 for r in self.results if r.winner_id == self.team_b)
        return a, b


class TeamRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wins: int = 0
    losses: int = 0
    rounds_won: int = 0
    rounds_lost: int = 0

    @property
    def diff(self) -> int:
        return self.rounds_won - self.rounds_lost


class ChampionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    season: int
    team_id: str
    team_name: str


class PlayerSeasonStats(BaseModel):
    """Season-long aggregates, summed from per-map MatchStats at sim time.
    Reset (after awards) at season rollover."""

    model_config = ConfigDict(extra="forbid")

    maps: int = 0
    rounds: int = 0
    kills: int = 0
    deaths: int = 0
    first_kills: int = 0
    trade_kills: int = 0
    headshots: int = 0
    plants: int = 0
    defuses: int = 0
    # Richer highlight stats (default 0 keeps old saves loading).
    first_deaths: int = 0
    multikills: int = 0
    aces: int = 0
    clutches: int = 0  # legacy meaning: 1v2-or-worse round wins
    rating_sum: float = 0.0
    # Analytics-department depth (all default-0 so old saves load):
    assists: int = 0
    kast_rounds: int = 0  # rounds with a Kill, Assist, Survival or Trade
    combat_score: float = 0.0  # ACS points total; acs = per round
    clutch_1v1: int = 0
    clutch_1v2: int = 0
    clutch_1v3: int = 0  # 1v3 or worse
    pistol_kills: int = 0
    eco_kills: int = 0  # kills while the team was under-gunned
    save_kills: int = 0  # kills on a personal save loadout (sidearm round)
    kills_by_weapon: dict[str, int] = Field(default_factory=dict)

    @property
    def rating(self) -> float:
        return self.rating_sum / max(self.maps, 1)

    @property
    def kd(self) -> float:
        return self.kills / max(self.deaths, 1)

    @property
    def hs_pct(self) -> float:
        return 100.0 * self.headshots / max(self.kills, 1)

    @property
    def acs(self) -> float:
        return self.combat_score / max(self.rounds, 1)

    @property
    def kast_pct(self) -> float:
        return 100.0 * self.kast_rounds / max(self.rounds, 1)

    @property
    def fk_fd(self) -> float:
        return self.first_kills / max(self.first_deaths, 1)


class TeamSeasonStats(BaseModel):
    model_config = ConfigDict(extra="forbid")

    maps: int = 0
    atk_rounds: int = 0
    atk_won: int = 0
    def_rounds: int = 0
    def_won: int = 0
    pistols: int = 0
    pistols_won: int = 0


class TeamMapStats(BaseModel):
    """One team's season record on one map (keyed by map id)."""

    model_config = ConfigDict(extra="forbid")

    maps: int = 0
    wins: int = 0
    atk_rounds: int = 0
    atk_won: int = 0
    def_rounds: int = 0
    def_won: int = 0


class StatSnap(BaseModel):
    """One weekly point on a player's performance time-series (only weeks
    they actually played). Feeds the profile trend charts."""

    model_config = ConfigDict(extra="forbid")

    season: int
    week: int
    maps: int
    rating: float
    acs: float
    kd: float
    kast_pct: float
    kills: int
    deaths: int


class CareerStats(BaseModel):
    """Lifetime box-score totals, accumulated from each season's
    PlayerSeasonStats at rollover (before the per-season reset). The
    persistent counterpart to PlayerSeasonStats — titles/awards live in the
    chronicle, so only the raw counters that reset each season live here."""

    model_config = ConfigDict(extra="forbid")

    maps: int = 0
    rounds: int = 0
    kills: int = 0
    deaths: int = 0
    first_kills: int = 0
    clutches: int = 0
    seasons: int = 0  # seasons with at least one map played

    @property
    def kd(self) -> float:
        return self.kills / max(self.deaths, 1)


class DevSnap(BaseModel):
    """One weekly point on a player's development time-series (ability,
    confidence, condition, reach). Human rosters only — this is the
    manager's own longitudinal view, not league-wide telemetry."""

    model_config = ConfigDict(extra="forbid")

    season: int
    week: int
    ca: float  # current ability (mean attribute)
    confidence: float
    form: float
    morale: float
    followers: int


class SocialPost(BaseModel):
    """One entry in the social feed. Generated deterministically each week
    from real outcomes (results, stat lines, dev events) — the feed is
    flavor over facts, never a second source of truth."""

    model_config = ConfigDict(extra="forbid")

    id: str  # blake2 of (season, week, author, kind, salt)
    season: int
    week: int
    author_kind: str  # player | team | media
    author_id: str  # player/team id ("" for media)
    author: str  # display handle at post time
    text: str
    likes: int
    kind: str  # hype | result | viral | drama | milestone | transfer


class GamePlan(BaseModel):
    """One manager's pre-match game plan for a specific fixture: optional
    per-match dial overrides (None = keep the standing book), an optional
    focus target on the opponent's roster, and an optional one-match
    lineup. Consumed when the fixture sims; stale plans (fixture already
    played, roster moved on) are re-validated at apply time, never
    trusted. The prep edge itself is DERIVED at sim time from scout
    knowledge — it is not stored, so it can't go stale."""

    model_config = ConfigDict(extra="forbid")

    fixture_id: str
    aggression: float | None = None
    pace: float | None = None
    util_discipline: float | None = None
    eco_greed: float | None = None
    map_control: float | None = None
    site_focus: str | None = None
    focus_target: str | None = None  # opponent pid to hunt
    starter_ids: list[str] = Field(default_factory=list)  # this match only


class PatchChange(BaseModel):
    """One live balance modifier: a delta to a numeric knob on one agent
    ability (cost / charges / ult_points). The ACTIVE set is cumulative
    across patches; runtime_gamedata applies it when building each week's
    GameData, so the bare-engine gates (which load the registry directly)
    never see one."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str
    ability_id: str
    field: str  # cost | charges | ult_points
    delta: int


class PatchNote(BaseModel):
    """One shipped balance patch, for the news/UI. `lines` are the
    human-readable change list ("Jett: Cloudburst 200 -> 250 credits")."""

    model_config = ConfigDict(extra="forbid")

    season: int
    week: int
    version: str  # e.g. "3.07"
    lines: list[str] = Field(default_factory=list)


class StaffMember(BaseModel):
    """Backroom staff. Quality (1-99) scales the slot's effect:
    coach → training growth, analyst → scouting speed + stat depth,
    physio → stamina recovery. Human orgs only; AI orgs' staff stay
    abstract (their baked-in multipliers assume a league-average bench).

    v3 members carry a full identity (age, region, specialty, career) so
    they get a profile page like players do; v2 saves load with the
    defaults below and read as journeymen with no paper trail."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    role: str  # coach | analyst | physio
    quality: float
    salary: int  # per week
    age: int = 38
    region: str = ""
    # Coach: training category they drill best (mechanical | tactical |
    # mental | team). Analyst/physio: flavor for now.
    specialty: str = ""
    traits: list[str] = Field(default_factory=list)
    # Career lines, newest last (e.g. "S2: assistant, Berlin Wolves").
    history: list[str] = Field(default_factory=list)
    # Trophies collected while employed (appended by the campaign layer).
    titles: list[str] = Field(default_factory=list)
    seasons_experience: int = 0
    # The org they last worked for IN THIS SAVE ("" = none) — hiring an
    # ex-rival staffer carries part of their old book (knowledge leak).
    last_org: str = ""
    # Non-empty for coaching-tree members: the player id they used to be.
    former_player_id: str = ""


class SponsorObjective(BaseModel):
    """Achievement-linked bonus (Motorsport-Manager-style): the brand
    pays extra when the org delivers a result. `met` is None while the
    season can still decide it."""

    model_config = ConfigDict(extra="forbid")

    kind: str  # make_playoffs | win_split | make_masters | win_champions | beat_top4 | top_half
    bonus: int
    met: bool | None = None


class SponsorDeal(BaseModel):
    """A named sponsorship: weekly cash, optional per-win bonus, finite
    term, optional achievement objectives."""

    model_config = ConfigDict(extra="forbid")

    name: str
    kind: str  # upfront | steady | performance
    signing_bonus: int = 0
    weekly: int = 0
    per_win: int = 0
    weeks_left: int = 0
    objectives: list[SponsorObjective] = Field(default_factory=list)


class SponsorPackage(BaseModel):
    """One payment structure for an offer — the user picks one at
    signing (cash now vs steady vs results-loaded)."""

    model_config = ConfigDict(extra="forbid")

    signing_bonus: int = 0
    weekly: int = 0
    per_win: int = 0


class SponsorOffer(BaseModel):
    """A brand courting one slot. Carries all three payment structures
    and the objectives that will ride on the deal; sits in the market
    until `expires_week`."""

    model_config = ConfigDict(extra="forbid")

    brand: str
    slot: str
    weeks: int
    expires_week: int
    upfront: SponsorPackage
    steady: SponsorPackage
    performance: SponsorPackage
    objectives: list[SponsorObjective] = Field(default_factory=list)


class RetiredRecord(BaseModel):
    """A career that ended — enough to remember them by."""

    model_config = ConfigDict(extra="forbid")

    season: int  # season after which they retired
    handle: str
    real_name: str = ""
    age: int
    team_name: str = ""  # last club ("" = free agent)
    peak_note: str = ""  # e.g. "career 71 CA"


class TransferOffer(BaseModel):
    """A bid for one of the seller's contracted players (`player_id`, owned by
    `from_team`) from `to_team`. Sits on the table for a bounded number of weeks,
    then quietly withdraws.

    A plain cash bid leaves the package fields at their defaults (`fee` cash to
    the seller, nothing coming back). A package bid additionally sends
    `offer_player_ids` (players moving from the buyer to the seller) and may
    route cash either way via `cash_to_seller` / `cash_to_buyer`; when a package
    is present `fee` mirrors `cash_to_seller` for backward-compatible display."""

    model_config = ConfigDict(extra="forbid")

    player_id: str
    from_team: str
    to_team: str
    fee: int
    expires_week: int
    # Package extras (default empty/zero == a plain cash bid).
    offer_player_ids: list[str] = Field(default_factory=list)
    cash_to_seller: int = 0
    cash_to_buyer: int = 0


class AwardRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    season: int
    award: str
    player_id: str
    handle: str
    team_name: str
    value: str  # display string, e.g. "1.24 rating over 18 maps"


class HofRecord(BaseModel):
    """One Hall of Fame career (manager/hof.py). Stored — not derived —
    because retired players are deleted from `players`; this list is the
    save's permanent memory of them."""

    model_config = ConfigDict(extra="forbid")

    season: int  # season of induction (= retirement season)
    player_id: str
    handle: str
    real_name: str = ""
    team_name: str = ""  # last club
    score: float
    blurb: str  # why they're in, one line


class ManagerContract(BaseModel):
    """A legacy-mode manager's deal with their org: a term, a per-season
    board goal (SponsorObjective kind vocabulary), and the board's
    patience (0-100). Patience moves at the offseason review (goal
    met/missed) and drifts a little with in-season streaks; it hitting
    the floor is a dismissal (manager/career.py)."""

    model_config = ConfigDict(extra="forbid")

    start_season: int
    seasons: int  # contract length
    # make_playoffs | win_split | make_masters | win_champions | top_half
    goal: str
    patience: float = 75.0


class ManagerSeat(BaseModel):
    """One human manager's career identity. The id is minted at creation
    ("mgr_{founding team id}") and FOLLOWS THE PERSON — in legacy mode a
    dismissal re-seats them at a new org but the id (and so their whole
    chronicle) persists. Sandbox seats have no contract and never move."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    team_id: str  # current org ("" = between jobs, offers pending)
    contract: ManagerContract | None = None
    archetype: str = ""  # the career-offer archetype they accepted
    # The org a dismissal just removed them from — how a browser session
    # still keyed to the old team finds its seat while unemployed.
    last_team_id: str = ""


class CareerOffer(BaseModel):
    """One org courting a manager — at new game (legacy mode start) or on
    the job market after a dismissal. Deterministic from (seed, season,
    seat), never stored long: accepting or the next offseason clears it."""

    model_config = ConfigDict(extra="forbid")

    team_id: str
    archetype: str  # dynasty | rebuilder | academy | sleeping_giant
    seasons: int
    goal: str
    patience: float
    blurb: str


class ChronicleEntry(BaseModel):
    """One entry in the campaign's append-only career history (see
    manager/chronicle.py — the writers and readers both live there).
    `week` 0 marks an entry backfilled by migration from a pre-chronicle
    save (its real week is unknown). Never pruned (owner call): the
    chronicle IS the save's long-term memory."""

    model_config = ConfigDict(extra="forbid")

    id: str  # blake2 of (season, week, kind, subject) — dedup key
    season: int
    week: int
    # champions_title | masters_title | regional_title | challengers_title |
    # award | retirement | signing | release | renewal | transfer | poach |
    # debut | milestone | dismissal | appointment | hall_of_fame | rivalry |
    # meta_shift  (see chronicle.KIND_IMPORTANCE)
    kind: str
    importance: float  # 0-100; readers slice by it, writers never prune
    team_id: str = ""  # primary org involved ("" = none/world)
    player_id: str = ""  # primary player involved
    manager_id: str = ""  # human seat responsible ("" = AI/world event)
    text: str  # one human-readable line, ASCII
    data: dict[str, str] = Field(default_factory=dict)  # small typed payload


class InboxItem(BaseModel):
    """One weekly inbox/notification entry. Generated at the end of a tick
    from real subsystem outcomes (see manager/inbox.py); the model lives
    here so it saves/loads with the rest of GameState.

    `id` is a deterministic blake2 hash of (season, week, category,
    subject) — stable across runs, never a salted Python hash(). `tab`
    names the UI tab a click should jump to (or None for a pure notice)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    season: int
    week: int
    # news | talk | transfer | sponsor | scouting | development | match | board
    category: str
    title: str  # short, <= 70 chars
    body: str  # plain text, may be multi-line
    unread: bool = True
    tab: str | None = None


class GameState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = SCHEMA_VERSION
    seed: int
    season: int = 1
    week: int = 1
    phase: str = "regular"  # regular | playoffs | offseason
    # The "primary" human manager (host / single player). Kept for back-compat
    # and as the default acting manager; `human_team_ids` is the authoritative
    # set of all human-controlled teams (>=1). Solo play == one human here.
    user_team_id: str
    human_team_ids: list[str] = Field(default_factory=list)

    # World shape: which regional leagues exist and how big each is. Written
    # once by new_campaign (from the roster pack's world block, or these
    # defaults) and read by every phase of the season state machine. The
    # defaults match the classic 3x8 fictional world, so pre-pack saves load
    # unchanged without a migration.
    league_regions: list[Region] = Field(
        default_factory=lambda: [Region.AMERICAS, Region.EMEA, Region.PACIFIC]
    )
    teams_per_region: int = 8
    tier2_per_region: int = 6
    # Id of the roster pack this campaign was created from (None = generated
    # fictional world). Informational — the pack is baked in at creation.
    roster_pack: str | None = None

    # Which human's private state (inbox, scouting, sponsors, staff, ...) the
    # per-team delegating properties below resolve to. Set per web request from
    # the caller's session; None -> the primary user_team_id. NOT persisted.
    _acting_team_id: str | None = PrivateAttr(default=None)

    teams: dict[str, Team] = Field(default_factory=dict)
    players: dict[str, Player] = Field(default_factory=dict)
    free_agent_ids: list[str] = Field(default_factory=list)

    fixtures: list[Fixture] = Field(default_factory=list)
    standings: dict[str, TeamRecord] = Field(default_factory=dict)
    training_focus: dict[str, str] = Field(default_factory=dict)

    news: list[str] = Field(default_factory=list)
    # Per-manager PRIVATE news: subsystem events that belong to one manager
    # (scout reports completing, sponsor-objective outcomes, a player on YOUR
    # roster retiring). push_private_news keeps the line in the shared `news`
    # feed too (so the CLI panel + broadcast ticker are unchanged), but also
    # records it here keyed by owner, so in a shared world each manager's inbox
    # only surfaces their own private events, never a rival's.
    private_news_by: dict[str, list[str]] = Field(default_factory=dict)
    # Weekly inbox feed (oldest first), per human manager. Populated at the end
    # of each tick. Reached via the `inbox` property (acting manager's feed).
    inboxes: dict[str, list[InboxItem]] = Field(default_factory=dict)
    champions: list[ChampionRecord] = Field(default_factory=list)
    retired: list[RetiredRecord] = Field(default_factory=list)
    fa_counter: int = 0  # monotonic id counter for generated free agents

    # Season analytics (reset at rollover, after awards are handed out).
    player_stats: dict[str, PlayerSeasonStats] = Field(default_factory=dict)
    team_stats: dict[str, TeamSeasonStats] = Field(default_factory=dict)
    awards: list[AwardRecord] = Field(default_factory=list)
    # Season splits (also reset at rollover): per-map and per-agent lines
    # for players, per-map records for teams.
    player_map_stats: dict[str, dict[str, PlayerSeasonStats]] = Field(
        default_factory=dict
    )
    player_agent_stats: dict[str, dict[str, PlayerSeasonStats]] = Field(
        default_factory=dict
    )
    team_map_stats: dict[str, dict[str, TeamMapStats]] = Field(default_factory=dict)
    # Time-series (SURVIVE season rollover, capped): performance points for
    # anyone who played that week; development points for human rosters.
    stat_history: dict[str, list[StatSnap]] = Field(default_factory=dict)
    dev_history: dict[str, list[DevSnap]] = Field(default_factory=dict)
    # Social layer: the shared feed (capped) — world-visible by design.
    social_feed: list[SocialPost] = Field(default_factory=list)

    # Scouting, per human manager: which rival each one's scout watches, and
    # how much of each team's true attributes that manager knows (0..1; own
    # team is always 1.0). Reached via `scout_target` / `scout_progress`.
    scout_targets: dict[str, str | None] = Field(default_factory=dict)
    scout_progress_by: dict[str, dict[str, float]] = Field(default_factory=dict)

    # Talk module: one 1:1 per week, per manager. Holds "s{season}w{week}".
    talked_weeks: dict[str, str] = Field(default_factory=dict)

    # Incoming transfer bids for user players (AI↔AI moves resolve
    # instantly and only leave news lines).
    transfer_offers: list[TransferOffer] = Field(default_factory=list)

    # Per-map dressed lineups. Key = "{team_id}|{fixture_id}|{map_id}" -> the
    # five player ids that dress for that map. Absent -> the team's default
    # lineup / auto top-five (see campaign.dressed_for). Cleared per season at
    # offseason and pruned as fixtures are played.
    map_lineups: dict[str, list[str]] = Field(default_factory=dict)

    # Pairwise player relationships ("pidA|pidB" sorted → 0-100). Sparse;
    # pruned toward the most-informative entries. Survives transfers.
    relationships: dict[str, float] = Field(default_factory=dict)

    # Masters seeding (set when the international bracket is drawn;
    # cleared at offseason). Seeds 1-3 = regional champs by record.
    masters_seeds: list[str] = Field(default_factory=list)
    # Champions (the season-capping second international): 8 teams —
    # the six Masters sides plus the two best remaining league records.
    champions_seeds: list[str] = Field(default_factory=list)

    # Legacy pre-M4 single sponsor deal/offer, per human manager (AI org
    # finances stay background). Reached via `sponsor` / `sponsor_offer`.
    sponsor_by: dict[str, SponsorDeal | None] = Field(default_factory=dict)
    sponsor_offer_by: dict[str, SponsorDeal | None] = Field(default_factory=dict)

    # Backroom staff: hired members by role, per human manager (reached via
    # `staff`), hiring from ONE shared world-level free-agent pool — in a
    # shared world managers compete for the same coaches.
    staff_by: dict[str, dict[str, StaffMember]] = Field(default_factory=dict)
    staff_pool: list[StaffMember] = Field(default_factory=list)

    # -- multi-manager plumbing ----------------------------------------------
    #
    # The campaign holds one shared world; each human manages one team. Their
    # PRIVATE state (inbox, scouting, sponsors, staff, facilities) lives in the
    # per-team `*_by` maps above. The single-name properties below resolve to
    # the ACTING manager's slice so the whole engine — which was written for one
    # human and says `gs.inbox`, `gs.facilities`, `gs.staff`, ... — keeps working
    # unchanged. Web requests set `_acting_team_id` from the caller's session
    # (under the game lock); the offline CLI and tests leave it None and get the
    # primary `user_team_id`.

    @model_validator(mode="after")
    def _default_human_team_ids(self) -> "GameState":
        if not self.human_team_ids:
            self.human_team_ids = [self.user_team_id]
        return self

    @property
    def acting_team_id(self) -> str:
        return self._acting_team_id or self.user_team_id

    def set_acting(self, team_id: str | None) -> None:
        """Bind the acting manager for subsequent property access. Call under
        the game lock in the web layer; `None` restores the primary user."""
        self._acting_team_id = team_id

    def is_human(self, team_id: str) -> bool:
        """True if a human manages this team (so the AI must not touch it)."""
        return team_id in self.human_team_ids

    # -- per-manager delegating properties -----------------------------------
    # Mutable containers return the stored object (via setdefault) so in-place
    # mutation by the engine persists; scalars read/write the acting slice.

    @property
    def inbox(self) -> list[InboxItem]:
        return self.inboxes.setdefault(self.acting_team_id, [])

    @inbox.setter
    def inbox(self, value: list[InboxItem]) -> None:
        self.inboxes[self.acting_team_id] = value

    @property
    def private_news(self) -> list[str]:
        """The acting manager's private news lines (see private_news_by)."""
        return self.private_news_by.setdefault(self.acting_team_id, [])

    @property
    def scout_target(self) -> str | None:
        return self.scout_targets.get(self.acting_team_id)

    @scout_target.setter
    def scout_target(self, value: str | None) -> None:
        self.scout_targets[self.acting_team_id] = value

    @property
    def scout_progress(self) -> dict[str, float]:
        return self.scout_progress_by.setdefault(self.acting_team_id, {})

    @scout_progress.setter
    def scout_progress(self, value: dict[str, float]) -> None:
        self.scout_progress_by[self.acting_team_id] = value

    @property
    def talked_week(self) -> str:
        return self.talked_weeks.get(self.acting_team_id, "")

    @talked_week.setter
    def talked_week(self, value: str) -> None:
        self.talked_weeks[self.acting_team_id] = value

    @property
    def sponsor(self) -> "SponsorDeal | None":
        return self.sponsor_by.get(self.acting_team_id)

    @sponsor.setter
    def sponsor(self, value: "SponsorDeal | None") -> None:
        self.sponsor_by[self.acting_team_id] = value

    @property
    def sponsor_offer(self) -> "SponsorDeal | None":
        return self.sponsor_offer_by.get(self.acting_team_id)

    @sponsor_offer.setter
    def sponsor_offer(self, value: "SponsorDeal | None") -> None:
        self.sponsor_offer_by[self.acting_team_id] = value

    @property
    def sponsor_slots(self) -> dict[str, "SponsorDeal"]:
        return self.sponsor_slots_by.setdefault(self.acting_team_id, {})

    @sponsor_slots.setter
    def sponsor_slots(self, value: dict[str, "SponsorDeal"]) -> None:
        self.sponsor_slots_by[self.acting_team_id] = value

    @property
    def sponsor_slot_offers(self) -> dict[str, "SponsorDeal"]:
        return self.sponsor_slot_offers_by.setdefault(self.acting_team_id, {})

    @sponsor_slot_offers.setter
    def sponsor_slot_offers(self, value: dict[str, "SponsorDeal"]) -> None:
        self.sponsor_slot_offers_by[self.acting_team_id] = value

    @property
    def sponsor_market(self) -> dict[str, list["SponsorOffer"]]:
        return self.sponsor_market_by.setdefault(self.acting_team_id, {})

    @sponsor_market.setter
    def sponsor_market(self, value: dict[str, list["SponsorOffer"]]) -> None:
        self.sponsor_market_by[self.acting_team_id] = value

    @property
    def sponsor_relations(self) -> dict[str, float]:
        return self.sponsor_relations_by.setdefault(self.acting_team_id, {})

    @sponsor_relations.setter
    def sponsor_relations(self, value: dict[str, float]) -> None:
        self.sponsor_relations_by[self.acting_team_id] = value

    @property
    def facilities(self) -> dict[str, int]:
        return self.facilities_by.setdefault(self.acting_team_id, {})

    @facilities.setter
    def facilities(self, value: dict[str, int]) -> None:
        self.facilities_by[self.acting_team_id] = value

    @property
    def staff(self) -> dict[str, "StaffMember"]:
        return self.staff_by.setdefault(self.acting_team_id, {})

    @staff.setter
    def staff(self, value: dict[str, "StaffMember"]) -> None:
        self.staff_by[self.acting_team_id] = value

    @property
    def game_plan(self) -> "GamePlan | None":
        """The acting manager's pre-match plan (None = play the book)."""
        return self.game_plans_by.get(self.acting_team_id)

    @game_plan.setter
    def game_plan(self, value: "GamePlan | None") -> None:
        if value is None:
            self.game_plans_by.pop(self.acting_team_id, None)
        else:
            self.game_plans_by[self.acting_team_id] = value

    def sentiment(self, team_id: str) -> float:
        """Community sentiment for a team (50 = neutral; missing = 50)."""
        return self.team_sentiment.get(team_id, 50.0)

    # -- helpers -------------------------------------------------------------

    def roster(self, team_id: str) -> list[Player]:
        return [self.players[pid] for pid in self.teams[team_id].player_ids]

    def fixtures_for_week(self, week: int | None = None) -> list[Fixture]:
        w = self.week if week is None else week
        return [f for f in self.fixtures if f.week == w]

    def team_fixture(self, team_id: str, week: int | None = None) -> Fixture | None:
        for f in self.fixtures_for_week(week):
            if team_id in (f.team_a, f.team_b):
                return f
        return None

    def _h2h_series(self, a: str, b: str) -> int:
        """Head-to-head series margin between two teams this season: a's
        wins over b minus b's over a, among their played REGULAR-season
        meetings. Only regular fixtures feed the standings (playoff results
        never touch TeamRecord), so the tiebreaker must ignore playoff
        rematches — otherwise a bracket game could reorder the league table
        that seeded that very bracket."""
        margin = 0
        for f in self.fixtures:
            if (
                f.stage == "regular"
                and f.played
                and f.winner_id is not None
                and {f.team_a, f.team_b} == {a, b}
            ):
                margin += 1 if f.winner_id == a else -1
        return margin

    def standings_order(
        self, region: str | None = None, tier: int = 1
    ) -> list[str]:
        """Table order, optionally restricted to one region's league.
        Tables are per-tier; pass tier=0 for everything.

        Tiebreakers, in order: wins, round differential, then — within a
        group still tied on both — a head-to-head MINI-TABLE (each team's net
        H2H margin against only the other tied teams), then rounds won, then
        team id. The mini-table keeps the order transitive even when three+
        teams tie in a rock-paper-scissors cycle (A>B>C>A); applying pairwise
        H2H inside a global comparator would resolve such a cycle by
        insertion order instead."""
        tids = [
            t
            for t in self.standings
            if (region is None or str(self.teams[t].region) == region)
            and (tier == 0 or self.teams[t].tier == tier)
        ]
        # Primary sort: wins then differential (id keeps it stable).
        tids.sort(
            key=lambda t: (-self.standings[t].wins, -self.standings[t].diff, t)
        )
        ordered: list[str] = []
        i = 0
        while i < len(tids):
            j = i
            w, d = self.standings[tids[i]].wins, self.standings[tids[i]].diff
            while (
                j < len(tids)
                and self.standings[tids[j]].wins == w
                and self.standings[tids[j]].diff == d
            ):
                j += 1
            group = tids[i:j]
            if len(group) > 1:
                # Rank the tied group by net H2H margin among ITSELF — a
                # scalar per team, so the order is transitive.
                def mini_key(t: str) -> tuple:
                    margin = sum(
                        self._h2h_series(t, o) for o in group if o != t
                    )
                    r = self.standings[t]
                    return (-margin, -r.rounds_won, t)

                group.sort(key=mini_key)
            ordered.extend(group)
            i = j
        return ordered

    def regions(self) -> list[str]:
        """Regions that actually have league teams, sorted."""
        return sorted({str(t.region) for t in self.teams.values()})

    def push_news(self, msg: str) -> None:
        self.news.append(f"[S{self.season} W{self.week}] {msg}")
        del self.news[:-60]

    def push_private_news(self, msg: str, owner: str | None = None) -> None:
        """A news line that belongs to ONE manager. It still lands in the
        shared `news` feed (the CLI panel and broadcast ticker keep showing it),
        but is ALSO recorded against `owner` (defaults to the acting manager) so
        only that manager's inbox surfaces it in a shared world. Stamped with
        the same [Sx Wy] label as push_news so the inbox's week filter works."""
        self.push_news(msg)
        bucket = self.private_news_by.setdefault(owner or self.acting_team_id, [])
        bucket.append(f"[S{self.season} W{self.week}] {msg}")
        del bucket[:-60]

    # -- persistence ------------------------------------------------------------

    def save(self, path: Path | str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.model_dump_json(indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path | str) -> "GameState":
        raw = Path(path).read_text(encoding="utf-8")
        data = json.loads(raw)
        version = int(data.get("schema_version", 1))
        if version > SCHEMA_VERSION:
            raise ValueError(
                f"save is schema v{version}, but this build only understands "
                f"up to v{SCHEMA_VERSION} — update the game to load it."
            )
        # Walk any registered migrations forward to the current version. New
        # fields with defaults need no migration; this is for structural
        # changes (renames/moves) that a plain load couldn't absorb.
        while version < SCHEMA_VERSION:
            data = _MIGRATIONS[version](data)
            version += 1
        data["schema_version"] = SCHEMA_VERSION
        return cls.model_validate(data)

    # -- finance depth (M4) ---------------------------------------------------
    # Three concurrent sponsor slots ("title", "jersey", "peripheral"), keyed
    # by slot name; at most one active deal and one pending offer per slot.
    # The legacy `sponsor`/`sponsor_offer` fields above are pre-M4 saves'
    # single deal — no longer written to by new offers, but still honored so
    # an in-flight deal keeps paying out (see manager/sponsors.py).
    # All per human manager (keyed by team id), reached via the matching
    # `sponsor_slots` / `sponsor_slot_offers` / `sponsor_market` /
    # `sponsor_relations` / `facilities` delegating properties.
    #
    # Three concurrent sponsor slots ("title", "jersey", "peripheral") per
    # manager; at most one active deal + one pending offer per slot.
    sponsor_slots_by: dict[str, dict[str, SponsorDeal]] = Field(default_factory=dict)
    sponsor_slot_offers_by: dict[str, dict[str, SponsorDeal]] = Field(
        default_factory=dict
    )
    # The sponsor MARKET (Motorsport-Manager-style): competing offers per slot,
    # each carrying three payment structures + objectives.
    sponsor_market_by: dict[str, dict[str, list[SponsorOffer]]] = Field(
        default_factory=dict
    )
    # Brand relationship memory (0-100, 50 = neutral): met objectives and
    # completed deals raise it, failures and snubs lower it; it scales the
    # money that brand offers next time.
    sponsor_relations_by: dict[str, dict[str, float]] = Field(default_factory=dict)
    # Upgradeable org facilities, level 0-3 (missing key == level 0):
    # "training_center", "analytics_suite", "marketing_office".
    facilities_by: dict[str, dict[str, int]] = Field(default_factory=dict)

    # -- coaching + meta depth (v4) -------------------------------------------
    # Pre-match game plans, per human manager (reached via `game_plan`).
    # At most one live plan per manager — for their next fixture.
    game_plans_by: dict[str, GamePlan] = Field(default_factory=dict)
    # Community sentiment per team (0-100, 50 = neutral; missing = 50).
    # Derived weekly from the social layer's real outcomes and fed back
    # into confidence/morale and sponsor pressure. World-shared.
    team_sentiment: dict[str, float] = Field(default_factory=dict)
    # Live balance patches: the cumulative active modifier set (applied by
    # runtime_gamedata when building each week's GameData — default empty,
    # so the bare-engine gates never see them) and the shipped notes.
    agent_patches: list[PatchChange] = Field(default_factory=list)
    patch_history: list[PatchNote] = Field(default_factory=list)

    # -- the Chronicle (v5) ----------------------------------------------------
    # Append-only career history (manager/chronicle.py). Titles, awards,
    # retirements, market moves, debuts, milestones — recorded at the
    # moment they happen; career profiles, reputation, memories, the Hall
    # of Fame and narrative callbacks are pure readers. NEVER pruned.
    chronicle: list[ChronicleEntry] = Field(default_factory=list)
    # Milestone bookkeeping: last celebrated 5-point overall band per
    # player (human rosters; see chronicle.weekly_milestones).
    dev_marks: dict[str, int] = Field(default_factory=dict)
    # Debut bookkeeping: "" = generated this save, debut pending;
    # "s{n}w{k}" = debut recorded. Absent = predates the system.
    debut_marks: dict[str, str] = Field(default_factory=dict)
    # Season-start current-ability per player, snapshotted the moment a
    # season's rosters settle. The Most Improved award reads it against
    # end-of-season CA. Additive/defaulted (see load(): new fields need no
    # migration); empty on old saves -> the award simply skips until the
    # next offseason repopulates it.
    season_start_ca: dict[str, float] = Field(default_factory=dict)
    # Lifetime box-score totals per living player, rolled up at each
    # offseason before player_stats resets. Pruned to current players
    # (retirees pass into the Hall of Fame instead). Additive/defaulted.
    career_stats: dict[str, CareerStats] = Field(default_factory=dict)
    # Mentorships: protege player id -> mentor player id. A manager pairs a
    # young player with a veteran teammate for a bounded development boost.
    # Empty by default (hands-off sims never set one, so the balance gates
    # are byte-identical); additive/defaulted, pruned at the offseason.
    mentorships: dict[str, str] = Field(default_factory=dict)

    # -- Legacy Mode (v5) ------------------------------------------------------
    # "sandbox" = the classic game (pick any org, manage forever).
    # "legacy" = the career game: offers, contracts, boards that fire you.
    # Both support solo and shared (LAN) play; old saves load as sandbox.
    game_mode: str = "sandbox"
    # Every human seat gets a ManagerSeat (both modes) so careers/reputation
    # work everywhere; only legacy seats carry contracts. Keyed by seat id.
    managers: dict[str, ManagerSeat] = Field(default_factory=dict)
    # Pending job-market offers per DISMISSED manager seat. Non-empty =
    # that manager must accept a job before the world can advance.
    career_offers_by: dict[str, list[CareerOffer]] = Field(default_factory=dict)

    # Org rivalries ("tidA|tidB" sorted -> intensity 0-100; manager/
    # rivalries.py). Heat from playoff meetings/poaches; cools offseason.
    rivalries: dict[str, float] = Field(default_factory=dict)
    # The Hall of Fame — inducted at retirement, kept forever.
    hall_of_fame: list[HofRecord] = Field(default_factory=list)
    # Organizational knowledge per org: "playbook:<map>", "antistrat:<tid>",
    # "methodology" -> 0-100 (manager/knowledge.py). Accrues from play,
    # decays at offseason/patches, leaks with staff moves.
    org_knowledge: dict[str, dict[str, float]] = Field(default_factory=dict)

    def manager_for(self, team_id: str) -> "ManagerSeat | None":
        """The seat currently managing a team (None = AI-run)."""
        for mid in sorted(self.managers):
            if self.managers[mid].team_id == team_id:
                return self.managers[mid]
        return None

    def seat_for_session(self, team_id: str) -> "ManagerSeat | None":
        """The seat a UI session keyed to `team_id` belongs to: the
        employed seat at that org, else the (unique in practice) fired
        seat whose last org it was — a dismissed manager's browser stays
        bound to the old team until they accept a new job."""
        seat = self.manager_for(team_id)
        if seat is not None:
            return seat
        for mid in sorted(self.managers):
            s = self.managers[mid]
            if not s.team_id and s.last_team_id == team_id:
                return s
        return None
