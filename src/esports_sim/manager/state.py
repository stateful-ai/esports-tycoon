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

SCHEMA_VERSION = 2

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


_MIGRATIONS: dict[int, "callable"] = {1: _migrate_v1_to_v2}

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
    clutches: int = 0
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
    # The "primary" human manager (host / single player). Kept for back-compat
    # and as the default acting manager; `human_team_ids` is the authoritative
    # set of all human-controlled teams (>=1). Solo play == one human here.
    user_team_id: str
    human_team_ids: list[str] = Field(default_factory=list)

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

    # Backroom staff per human manager: hired members by role + the current
    # candidate market (refreshed each offseason). Reached via `staff` /
    # `staff_candidates`.
    staff_by: dict[str, dict[str, StaffMember]] = Field(default_factory=dict)
    staff_candidates_by: dict[str, dict[str, list[StaffMember]]] = Field(
        default_factory=dict
    )

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
    def staff_candidates(self) -> dict[str, list["StaffMember"]]:
        return self.staff_candidates_by.setdefault(self.acting_team_id, {})

    @staff_candidates.setter
    def staff_candidates(self, value: dict[str, list["StaffMember"]]) -> None:
        self.staff_candidates_by[self.acting_team_id] = value

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
