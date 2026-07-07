"""Season schedule construction: double round-robin + a 4-team playoff."""

from __future__ import annotations

from esports_sim.manager.state import Fixture


def round_robin_rounds(team_ids: list[str]) -> list[list[tuple[str, str]]]:
    """Circle-method round robin. len(teams) must be even. Returns one list
    of (home, away) pairs per round."""
    ids = list(team_ids)
    n = len(ids)
    assert n % 2 == 0, "round robin needs an even team count"
    rounds: list[list[tuple[str, str]]] = []
    for r in range(n - 1):
        pairs: list[tuple[str, str]] = []
        for i in range(n // 2):
            a, b = ids[i], ids[n - 1 - i]
            # Alternate nominal home/away so first-attack side varies.
            pairs.append((a, b) if r % 2 == 0 else (b, a))
        rounds.append(pairs)
        ids = [ids[0]] + [ids[-1]] + ids[1:-1]
    return rounds


def build_regular_season(
    team_ids: list[str], map_ids: list[str], season: int
) -> list[Fixture]:
    """Double round-robin, one match per team per week, BO1 on a rotating
    map. 8 teams -> 14 weeks."""
    ordered = sorted(team_ids)
    maps = sorted(map_ids)
    single = round_robin_rounds(ordered)
    rounds = single + [[(b, a) for (a, b) in rnd] for rnd in single]
    fixtures: list[Fixture] = []
    for week_idx, rnd in enumerate(rounds, start=1):
        for match_idx, (a, b) in enumerate(rnd):
            map_id = maps[(week_idx + match_idx) % len(maps)]
            fixtures.append(
                Fixture(
                    id=f"s{season}w{week_idx}m{match_idx}",
                    week=week_idx,
                    stage="regular",
                    best_of=1,
                    team_a=a,
                    team_b=b,
                    maps=[map_id],
                )
            )
    return fixtures


def regular_season_weeks(n_teams: int) -> int:
    return 2 * (n_teams - 1)


def build_semifinals(
    standings_order: list[str], map_ids: list[str], season: int, week: int
) -> list[Fixture]:
    """1v4 and 2v3, BO3 across the map pool."""
    maps = sorted(map_ids)
    top = standings_order[:4]
    pairs = [(top[0], top[3]), (top[1], top[2])]
    return [
        Fixture(
            id=f"s{season}semi{i}",
            week=week,
            stage="semi",
            best_of=3,
            team_a=a,
            team_b=b,
            maps=maps[:3],
        )
        for i, (a, b) in enumerate(pairs)
    ]


def build_final(
    winners: list[str], map_ids: list[str], season: int, week: int
) -> Fixture:
    maps = sorted(map_ids)
    return Fixture(
        id=f"s{season}final",
        week=week,
        stage="final",
        best_of=3,
        team_a=winners[0],
        team_b=winners[1],
        maps=maps[:3],
    )
