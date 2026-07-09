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

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from esports_sim.schemas import Player, Team

SCHEMA_VERSION = 1

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
    rating_sum: float = 0.0

    @property
    def rating(self) -> float:
        return self.rating_sum / max(self.maps, 1)

    @property
    def kd(self) -> float:
        return self.kills / max(self.deaths, 1)

    @property
    def hs_pct(self) -> float:
        return 100.0 * self.headshots / max(self.kills, 1)


class TeamSeasonStats(BaseModel):
    model_config = ConfigDict(extra="forbid")

    maps: int = 0
    atk_rounds: int = 0
    atk_won: int = 0
    def_rounds: int = 0
    def_won: int = 0
    pistols: int = 0
    pistols_won: int = 0


class StaffMember(BaseModel):
    """Backroom staff. Quality (1-99) scales the slot's effect:
    coach → training growth, analyst → scouting speed, physio → stamina
    recovery. User team only; AI orgs' staff stay abstract."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    role: str  # coach | analyst | physio
    quality: float
    salary: int  # per week


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
    """An AI org's bid for one of the user's contracted players. Sits on
    the table for a bounded number of weeks, then quietly withdraws."""

    model_config = ConfigDict(extra="forbid")

    player_id: str
    from_team: str
    to_team: str
    fee: int
    expires_week: int


class AwardRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    season: int
    award: str
    player_id: str
    handle: str
    team_name: str
    value: str  # display string, e.g. "1.24 rating over 18 maps"


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
    user_team_id: str

    teams: dict[str, Team] = Field(default_factory=dict)
    players: dict[str, Player] = Field(default_factory=dict)
    free_agent_ids: list[str] = Field(default_factory=list)

    fixtures: list[Fixture] = Field(default_factory=list)
    standings: dict[str, TeamRecord] = Field(default_factory=dict)
    training_focus: dict[str, str] = Field(default_factory=dict)

    news: list[str] = Field(default_factory=list)
    # Weekly inbox feed (oldest first). Populated at the end of each tick;
    # pre-inbox saves load with an empty list (default). See manager/inbox.py.
    inbox: list[InboxItem] = Field(default_factory=list)
    champions: list[ChampionRecord] = Field(default_factory=list)
    retired: list[RetiredRecord] = Field(default_factory=list)
    fa_counter: int = 0  # monotonic id counter for generated free agents

    # Season analytics (reset at rollover, after awards are handed out).
    player_stats: dict[str, PlayerSeasonStats] = Field(default_factory=dict)
    team_stats: dict[str, TeamSeasonStats] = Field(default_factory=dict)
    awards: list[AwardRecord] = Field(default_factory=list)

    # Scouting: which rival the user's scout watches, and how much of each
    # team's true attributes are known (0..1; own team is always 1.0).
    scout_target: str | None = None
    scout_progress: dict[str, float] = Field(default_factory=dict)

    # Talk module: one 1:1 per week. Holds "s{season}w{week}" once used.
    talked_week: str = ""

    # Incoming transfer bids for user players (AI↔AI moves resolve
    # instantly and only leave news lines).
    transfer_offers: list[TransferOffer] = Field(default_factory=list)

    # Pairwise player relationships ("pidA|pidB" sorted → 0-100). Sparse;
    # pruned toward the most-informative entries. Survives transfers.
    relationships: dict[str, float] = Field(default_factory=dict)

    # Masters seeding (set when the international bracket is drawn;
    # cleared at offseason). Seeds 1-3 = regional champs by record.
    masters_seeds: list[str] = Field(default_factory=list)
    # Champions (the season-capping second international): 8 teams —
    # the six Masters sides plus the two best remaining league records.
    champions_seeds: list[str] = Field(default_factory=list)

    # Sponsorship (user team only; AI org finances stay background).
    sponsor: SponsorDeal | None = None
    sponsor_offer: SponsorDeal | None = None

    # Backroom staff: hired members by role + the current candidate market
    # (refreshed each offseason).
    staff: dict[str, StaffMember] = Field(default_factory=dict)
    staff_candidates: dict[str, list[StaffMember]] = Field(default_factory=dict)

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

    def standings_order(
        self, region: str | None = None, tier: int = 1
    ) -> list[str]:
        """Table order, optionally restricted to one region's league.
        Tables are per-tier; pass tier=0 for everything."""

        def key(tid: str) -> tuple:
            r = self.standings[tid]
            return (-r.wins, -(r.diff), -r.rounds_won, tid)

        tids = [
            t
            for t in self.standings
            if (region is None or str(self.teams[t].region) == region)
            and (tier == 0 or self.teams[t].tier == tier)
        ]
        return sorted(tids, key=key)

    def regions(self) -> list[str]:
        """Regions that actually have league teams, sorted."""
        return sorted({str(t.region) for t in self.teams.values()})

    def push_news(self, msg: str) -> None:
        self.news.append(f"[S{self.season} W{self.week}] {msg}")
        del self.news[:-60]

    # -- persistence ------------------------------------------------------------

    def save(self, path: Path | str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.model_dump_json(indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path | str) -> "GameState":
        raw = Path(path).read_text(encoding="utf-8")
        return cls.model_validate_json(raw)

    # -- finance depth (M4) ---------------------------------------------------
    # Three concurrent sponsor slots ("title", "jersey", "peripheral"), keyed
    # by slot name; at most one active deal and one pending offer per slot.
    # The legacy `sponsor`/`sponsor_offer` fields above are pre-M4 saves'
    # single deal — no longer written to by new offers, but still honored so
    # an in-flight deal keeps paying out (see manager/sponsors.py).
    sponsor_slots: dict[str, SponsorDeal] = Field(default_factory=dict)
    sponsor_slot_offers: dict[str, SponsorDeal] = Field(default_factory=dict)
    # The sponsor MARKET (Motorsport-Manager-style): competing offers per
    # slot, each carrying three payment structures + objectives. Replaces
    # sponsor_slot_offers for new offers (old field still expires cleanly).
    sponsor_market: dict[str, list[SponsorOffer]] = Field(default_factory=dict)
    # Brand relationship memory (0-100, 50 = neutral): met objectives and
    # completed deals raise it, failures and snubs lower it; it scales the
    # money that brand offers next time.
    sponsor_relations: dict[str, float] = Field(default_factory=dict)
    # Upgradeable org facilities, level 0-3 (missing key == level 0):
    # "training_center", "analytics_suite", "marketing_office". User only.
    facilities: dict[str, int] = Field(default_factory=dict)
