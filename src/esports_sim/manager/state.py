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
    stage: str = "regular"  # regular | semi | final
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


class SponsorDeal(BaseModel):
    """A named sponsorship: weekly cash, optional per-win bonus, finite
    term. The user team holds at most one active deal plus one pending
    offer (offers expire after a week on the table)."""

    model_config = ConfigDict(extra="forbid")

    name: str
    kind: str  # upfront | steady | performance
    signing_bonus: int = 0
    weekly: int = 0
    per_win: int = 0
    weeks_left: int = 0


class AwardRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    season: int
    award: str
    player_id: str
    handle: str
    team_name: str
    value: str  # display string, e.g. "1.24 rating over 18 maps"


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
    champions: list[ChampionRecord] = Field(default_factory=list)
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

    # Sponsorship (user team only; AI org finances stay background).
    sponsor: SponsorDeal | None = None
    sponsor_offer: SponsorDeal | None = None

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

    def standings_order(self) -> list[str]:
        def key(tid: str) -> tuple:
            r = self.standings[tid]
            return (-r.wins, -(r.diff), -r.rounds_won, tid)

        return sorted(self.standings, key=key)

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
