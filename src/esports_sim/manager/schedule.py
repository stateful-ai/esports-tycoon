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


def veto_bo3(
    map_ids: list[str],
    mastery_a: dict[str, float],
    mastery_b: dict[str, float],
    tag_a: str,
    tag_b: str,
) -> tuple[list[str], list[str]]:
    """Deterministic BO3 veto: A ban, B ban, A pick, B pick, remainder is
    the decider. Teams ban where they're weakest relative to the opponent
    and pick where they're strongest. Ties break on map id.

    Returns (map order, human-readable veto log).
    """
    pool = sorted(map_ids)
    log: list[str] = []

    def score(m: str, own: dict, opp: dict) -> float:
        return own.get(m, 50.0) - 0.5 * opp.get(m, 50.0)

    def ban(own: dict, opp: dict, tag: str) -> None:
        m = min(pool, key=lambda m: (score(m, own, opp), m))
        pool.remove(m)
        log.append(f"{tag} ban {m}")

    def pick(own: dict, opp: dict, tag: str) -> str:
        m = max(pool, key=lambda m: (score(m, own, opp), m))
        pool.remove(m)
        log.append(f"{tag} pick {m}")
        return m

    # Ban down to three maps (two picks + a decider), alternating A/B so
    # the bans stay balanced for any pool size. With five maps that's one
    # ban each; with fewer, the loop simply doesn't run. (The old code
    # counted the bans twice and dumped every extra ban on team A once the
    # pool grew past five.)
    bans = max(0, len(pool) - 3)
    for i in range(bans):
        if i % 2 == 0:
            ban(mastery_a, mastery_b, tag_a)
        else:
            ban(mastery_b, mastery_a, tag_b)

    m1 = pick(mastery_a, mastery_b, tag_a)
    m2 = pick(mastery_b, mastery_a, tag_b)
    decider = pool[0]
    log.append(f"decider {decider}")
    return [m1, m2, decider], log


def build_semifinals(
    standings_order: list[str],
    season: int,
    week: int,
    veto_for,
) -> list[Fixture]:
    """1v4 and 2v3, BO3. `veto_for(a, b)` returns (maps, veto_log) — the
    campaign supplies it with live roster map masteries."""
    if len(standings_order) < 4:
        raise ValueError(
            f"a four-team semifinal needs at least four qualifiers, got "
            f"{len(standings_order)}"
        )
    top = standings_order[:4]
    pairs = [(top[0], top[3]), (top[1], top[2])]
    out = []
    for i, (a, b) in enumerate(pairs):
        maps, veto = veto_for(a, b)
        out.append(
            Fixture(
                id=f"s{season}semi{i}",
                week=week,
                stage="semi",
                best_of=3,
                team_a=a,
                team_b=b,
                maps=maps,
                veto=veto,
            )
        )
    return out


def build_final(winners: list[str], season: int, week: int, veto_for) -> Fixture:
    maps, veto = veto_for(winners[0], winners[1])
    return Fixture(
        id=f"s{season}final",
        week=week,
        stage="final",
        best_of=3,
        team_a=winners[0],
        team_b=winners[1],
        maps=maps,
        veto=veto,
    )
