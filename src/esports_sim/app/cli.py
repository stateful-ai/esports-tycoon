"""Terminal front-end. `python -m esports_sim` to play.

Thin by design: every rule lives in the manager/sim layers; this file only
renders state and forwards menu choices.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table

from esports_sim.manager import advance_week, career, new_campaign, telemetry
from esports_sim.manager.market import (
    ROSTER_MIN,
    asking_salary,
    can_sign,
    player_quality,
    release_player,
    renew_contract,
    roster_ready,
    sign_player,
)
from esports_sim.manager.schedule import regular_season_weeks
from esports_sim.manager.state import GameState
from esports_sim.manager.training import FOCUS_OPTIONS
from esports_sim.registry import load_all
from esports_sim.registry.loader import GameData
from esports_sim.registry.rosters import list_roster_packs, load_roster_pack
from esports_sim.schemas import Player

console = Console()
SAVE_DIR = Path("saves")
DEFAULT_SAVE = SAVE_DIR / "campaign.json"


def ask(prompt: str = "> ") -> str:
    try:
        # Strip BOM/CR too — piped stdin on Windows can smuggle both in.
        return input(prompt).strip().strip("﻿\r").strip()
    except (EOFError, KeyboardInterrupt):
        return "q"


def fmt_cr(n: int) -> str:
    return f"{n:,} cr"


def team_name(gs: GameState, tid: str) -> str:
    return gs.teams[tid].name if tid in gs.teams else tid


def handle_of(gs: GameState, pid: str) -> str:
    p = gs.players.get(pid)
    return p.handle if p is not None else pid


# ---------------------------------------------------------------------------
# Screens


def title_screen(gd: GameData) -> GameState | None:
    console.print(
        Panel.fit(
            "[bold magenta]VALORANT ESPORTS MANAGER[/]\n"
            "[dim]run an org · build a roster · win Champions[/]",
            border_style="magenta",
        )
    )
    has_save = DEFAULT_SAVE.exists()
    console.print("  1) New game")
    if has_save:
        console.print("  2) Continue")
    console.print("  q) Quit")
    while True:
        c = ask()
        if c == "1":
            return new_game_screen(gd)
        if c == "2" and has_save:
            gs = GameState.load(DEFAULT_SAVE)
            console.print(
                f"[green]Loaded[/] — season {gs.season}, week {gs.week}, "
                f"{team_name(gs, gs.user_team_id)}"
            )
            return gs
        if c == "q":
            return None


def new_game_screen(gd: GameData) -> GameState:
    raw = ask("Campaign seed (blank = 2026): ")
    seed = int(raw) if raw.isdigit() else 2026
    # World choice: the generated fictional league, or an installed
    # roster pack (real teams imported under data/rosters/).
    pack = None
    packs = list_roster_packs()
    if packs:
        console.print("World: 0) Fictional (generated)")
        for i, m in enumerate(packs, 1):
            console.print(f"       {i}) {m.name} - {m.description[:60]}")
        c = ask("World number (blank = 0): ")
        if c.isdigit() and 1 <= int(c) <= len(packs):
            pack = load_roster_pack(packs[int(c) - 1].id)
    # Game mode: sandbox (classic) or a legacy career.
    console.print("Mode: 1) Sandbox - pick any org, manage forever")
    console.print("      2) Legacy - start from job offers; boards can fire you")
    mode = "legacy" if ask("Mode (blank = 1): ") == "2" else "sandbox"
    # Build a preview campaign to show the actual league the seed produces.
    preview_team = (
        sorted(t.id for t in pack.teams.values() if t.tier == 1)[0]
        if pack is not None
        else "team_nexus"
    )
    gs = new_campaign(gd, seed, user_team_id=preview_team, pack=pack)
    if mode == "legacy":
        offers = career.new_game_offers(gs, 0)
        console.print("Your offers:")
        for i, o in enumerate(offers, 1):
            t = gs.teams[o.team_id]
            goal = career.GOAL_LABELS.get(o.goal, o.goal)
            console.print(
                f"  {i}) {t.name} [{o.archetype.replace('_', ' ')}] - "
                f"{o.seasons}-season deal, board wants: {goal}"
            )
            console.print(f"     {o.blurb}")
        while True:
            c = ask("Offer number: ")
            if c.isdigit() and 1 <= int(c) <= len(offers):
                offer = offers[int(c) - 1]
                break
        gs = new_campaign(
            gd, seed, user_team_id=offer.team_id, pack=pack,
            mode="legacy", career_offer=offer,
        )
        console.print(
            f"[green]You take over at {team_name(gs, gs.user_team_id)}.[/] "
            f"(seed {seed})"
        )
        save(gs)
        return gs
    table = Table(title="Pick your team", border_style="dim")
    table.add_column("#")
    table.add_column("Team")
    table.add_column("Avg quality", justify="right")
    table.add_column("Balance", justify="right")
    table.add_column("Reputation", justify="right")
    ordered = sorted(
        (t for t in gs.teams if gs.teams[t].tier == 1),
        key=lambda t: -sum(player_quality(p) for p in gs.roster(t)),
    )
    for i, tid in enumerate(ordered, 1):
        t = gs.teams[tid]
        avg_q = sum(player_quality(p) for p in gs.roster(tid)) / max(
            len(t.player_ids), 1
        )
        table.add_row(
            str(i), t.name, f"{avg_q:.1f}", f"{t.balance:,}", f"{t.reputation:.0f}"
        )
    console.print(table)
    while True:
        c = ask("Team number: ")
        if c.isdigit() and 1 <= int(c) <= len(ordered):
            picked = ordered[int(c) - 1]
            break
    # Rebuild with the picked team so the human seat (human_team_ids, staff
    # market, scouting state) is initialised for the right org — determinism
    # makes this the same world, just seen from the picked chair.
    gs = new_campaign(gd, seed, user_team_id=picked, pack=pack)
    console.print(
        f"[green]You are now managing {team_name(gs, gs.user_team_id)}.[/] "
        f"(seed {seed})"
    )
    save(gs)
    return gs


def save(gs: GameState) -> None:
    gs.save(DEFAULT_SAVE)


def hub_header(gs: GameState) -> None:
    t = gs.teams[gs.user_team_id]
    fixture = gs.team_fixture(gs.user_team_id)
    if gs.phase == "offseason":
        next_match = "offseason — advance to start the new season"
    elif fixture is None:
        next_match = "no match this week"
    else:
        opp = fixture.team_b if fixture.team_a == gs.user_team_id else fixture.team_a
        next_match = (
            f"vs {team_name(gs, opp)} "
            f"({'BO3 ' + fixture.stage if fixture.best_of == 3 else fixture.maps[0]})"
        )
    console.print(
        Panel(
            f"[bold]{t.name}[/]   season {gs.season} · week {gs.week} · {gs.phase}\n"
            f"balance [yellow]{fmt_cr(t.balance)}[/] · world rank #{t.world_rank} · "
            f"chemistry {t.chemistry:.0f}\n"
            f"this week: [cyan]{next_match}[/]",
            border_style="blue",
        )
    )


def roster_screen(gs: GameState) -> None:
    tid = gs.user_team_id
    while True:
        roster = gs.roster(tid)
        table = Table(title=f"{team_name(gs, tid)} roster", border_style="dim")
        for col in ("#", "Handle", "Age", "Role", "Style"):
            table.add_column(col)
        for col in ("Qual", "Form", "Stam", "Morale", "Contract", "Salary"):
            table.add_column(col, justify="right")
        for i, p in enumerate(roster, 1):
            stam_style = "red" if p.stamina < 40 else ""
            con_style = "red" if p.contract_weeks_left <= 6 else ""
            table.add_row(
                str(i), p.handle, str(p.age), p.role, p.playstyle,
                f"{player_quality(p):.1f}", f"{p.form:.0f}",
                f"[{stam_style}]{p.stamina:.0f}[/]" if stam_style else f"{p.stamina:.0f}",
                f"{p.morale:.0f}",
                f"[{con_style}]{p.contract_weeks_left}w[/]"
                if con_style
                else f"{p.contract_weeks_left}w",
                f"{p.salary:,}",
            )
        console.print(table)
        console.print("  [dim]<n> player detail · r<n> renew · x<n> release · b back[/]")
        c = ask()
        if c in ("b", "q", ""):
            return
        if c.startswith("r") and c[1:].isdigit() and 1 <= int(c[1:]) <= len(roster):
            p = roster[int(c[1:]) - 1]
            est = max(asking_salary(p), int(p.salary * 1.1 / 100) * 100)
            confirm = ask(f"Renew {p.handle} at ~{est:,}/wk for 48w? (y/n) ")
            if confirm == "y":
                ok, msg = renew_contract(gs, tid, p.id)
                if ok:
                    telemetry.record_action(
                        gs, "renew", {"player_id": p.id}, source="cli"
                    )
                console.print(f"[{'green' if ok else 'red'}]{msg}[/]")
        elif c.startswith("x") and c[1:].isdigit() and 1 <= int(c[1:]) <= len(roster):
            p = roster[int(c[1:]) - 1]
            confirm = ask(
                f"Release {p.handle}? Severance {p.salary * 6:,} cr. (y/n) "
            )
            if confirm == "y":
                ok, msg = release_player(gs, tid, p.id)
                if ok:
                    telemetry.record_action(
                        gs, "release", {"player_id": p.id}, source="cli"
                    )
                console.print(f"[{'green' if ok else 'red'}]{msg}[/]")
        elif c.isdigit() and 1 <= int(c) <= len(roster):
            player_detail(gs, roster[int(c) - 1])


def player_detail(gs: GameState, p: Player) -> None:
    table = Table(title=f"{p.handle} — {p.real_name}", border_style="dim")
    table.add_column("Attribute")
    table.add_column("Value", justify="right")
    for attr_id, val in sorted(p.attributes.items()):
        bar = "#" * int(val / 10)  # ASCII: legacy Windows consoles are cp1252
        table.add_row(attr_id, f"{val:5.1f} [cyan]{bar}[/]")
    console.print(table)
    agents = ", ".join(f"{m.agent_id} ({m.mastery:.0f})" for m in p.agent_pool)
    maps = ", ".join(f"{m.map_id} ({m.mastery:.0f})" for m in p.map_pool)
    console.print(
        f"  age {p.age} · {p.role}/{p.playstyle} · agents: {agents}\n"
        f"  maps: {maps}\n"
        f"  tags: {', '.join(p.personality_tags) or '—'}   "
        f"salary {p.salary:,}/wk · {p.contract_weeks_left}w left"
    )
    ask("[enter to go back] ")


def training_screen(gs: GameState) -> None:
    current = gs.training_focus.get(gs.user_team_id, "tactical")
    console.print(f"Current focus: [cyan]{current}[/]")
    for i, opt in enumerate(FOCUS_OPTIONS, 1):
        console.print(f"  {i}) {opt}")
    c = ask("Focus (or b): ")
    if c.isdigit() and 1 <= int(c) <= len(FOCUS_OPTIONS):
        gs.training_focus[gs.user_team_id] = FOCUS_OPTIONS[int(c) - 1]
        telemetry.record_action(
            gs, "set_training",
            {"focus": FOCUS_OPTIONS[int(c) - 1]},
            source="cli",
        )
        console.print(f"[green]Focus set to {FOCUS_OPTIONS[int(c) - 1]}.[/]")


def market_screen(gs: GameState) -> None:
    tid = gs.user_team_id
    while True:
        fas = sorted(
            (gs.players[pid] for pid in gs.free_agent_ids),
            key=lambda p: -player_quality(p),
        )
        table = Table(title="Free agents", border_style="dim")
        for col in ("#", "Handle", "Age", "Role", "Style"):
            table.add_column(col)
        for col in ("Qual", "Ask/wk",):
            table.add_column(col, justify="right")
        for i, p in enumerate(fas[:15], 1):
            table.add_row(
                str(i), p.handle, str(p.age), p.role, p.playstyle,
                f"{player_quality(p):.1f}", f"{asking_salary(p):,}",
            )
        console.print(table)
        t = gs.teams[tid]
        console.print(
            f"  roster {len(t.player_ids)}/5 · balance {fmt_cr(t.balance)}\n"
            "  [dim]s<n> sign · <n> detail · b back[/]"
        )
        c = ask()
        if c in ("b", "q", ""):
            return
        if c.startswith("s") and c[1:].isdigit() and 1 <= int(c[1:]) <= len(fas[:15]):
            p = fas[int(c[1:]) - 1]
            ok, why = can_sign(gs, tid, p.id)
            if not ok:
                console.print(f"[red]{why}[/]")
                continue
            confirm = ask(f"Sign {p.handle} at {asking_salary(p):,}/wk for 40w? (y/n) ")
            if confirm == "y":
                ok, msg = sign_player(gs, tid, p.id)
                if ok:
                    telemetry.record_action(
                        gs, "sign", {"player_id": p.id}, source="cli"
                    )
                console.print(f"[{'green' if ok else 'red'}]{msg}[/]")
        elif c.isdigit() and 1 <= int(c) <= len(fas[:15]):
            player_detail(gs, fas[int(c) - 1])


def league_screen(gs: GameState) -> None:
    table = Table(
        title=f"Season {gs.season} standings", border_style="dim"
    )
    for col in ("#", "Team"):
        table.add_column(col)
    for col in ("W", "L", "RD"):
        table.add_column(col, justify="right")
    for i, tid in enumerate(gs.standings_order(), 1):
        r = gs.standings[tid]
        style = "bold cyan" if tid == gs.user_team_id else ""
        name = f"[{style}]{team_name(gs, tid)}[/]" if style else team_name(gs, tid)
        table.add_row(str(i), name, str(r.wins), str(r.losses), f"{r.diff:+d}")
    console.print(table)

    console.print(f"[bold]Week {gs.week} fixtures[/]")
    for f in gs.fixtures_for_week():
        tag = f" [magenta]{f.stage}[/]" if f.stage != "regular" else ""
        console.print(
            f"  {team_name(gs, f.team_a)} vs {team_name(gs, f.team_b)}"
            f" ({'BO3' if f.best_of == 3 else f.maps[0]}){tag}"
        )
    played_last = [f for f in gs.fixtures if f.played and f.week == gs.week - 1]
    if played_last:
        console.print(f"[bold]Last week[/]")
        for f in played_last:
            a, b = f.map_score
            score = (
                f"{a}-{b}"
                if f.best_of == 3
                else f"{f.results[0].score_a}-{f.results[0].score_b}"
            )
            console.print(
                f"  {team_name(gs, f.team_a)} {score} {team_name(gs, f.team_b)}"
            )
    ask("[enter to go back] ")


def finances_screen(gs: GameState) -> None:
    from esports_sim.manager.economy import weekly_sponsor_income

    t = gs.teams[gs.user_team_id]
    payroll = sum(p.salary for p in gs.roster(gs.user_team_id))
    income = weekly_sponsor_income(t)
    console.print(
        Panel(
            f"balance [yellow]{fmt_cr(t.balance)}[/]\n"
            f"weekly sponsor income  [green]+{income:,}[/]\n"
            f"weekly payroll         [red]-{payroll:,}[/]\n"
            f"net                    {'+' if income >= payroll else ''}{income - payroll:,}",
            title="Finances",
            border_style="yellow",
        )
    )
    for p in gs.roster(gs.user_team_id):
        console.print(f"  {p.handle:14s} {p.salary:>8,}/wk · {p.contract_weeks_left}w left")
    ask("[enter to go back] ")


def news_screen(gs: GameState) -> None:
    console.print(Panel("\n".join(gs.news[-15:]) or "quiet week", title="News"))
    ask("[enter to go back] ")


def render_week_results(gs: GameState, report) -> None:
    console.print(Rule(f"Week {report.week} results"))
    for f in report.fixtures:
        mine = gs.user_team_id in (f.team_a, f.team_b)
        a, b = f.map_score
        score = (
            f"{a}-{b}"
            if f.best_of == 3
            else (f"{f.results[0].score_a}-{f.results[0].score_b}" if f.results else "w/o")
        )
        line = (
            f"{team_name(gs, f.team_a)} [bold]{score}[/] {team_name(gs, f.team_b)}"
        )
        if f.stage != "regular":
            line = f"[magenta]{f.stage.upper()}[/] " + line
        console.print(("[cyan]> [/]" if mine else "  ") + line)
        if mine and f.id in report.match_stats:
            render_match_detail(gs, f, report.match_stats[f.id])
    for note in report.notes:
        console.print(f"[yellow]{note}[/]")
    if report.user_expenses or report.user_income:
        net = report.user_income - report.user_expenses
        console.print(
            f"[dim]weekly finances: +{report.user_income:,} sponsor, "
            f"-{report.user_expenses:,} payroll (net {net:+,})[/]"
        )


def render_match_detail(gs: GameState, fixture, stats_list) -> None:
    for map_result, stats in zip(fixture.results, stats_list):
        console.print(
            f"    [bold]{map_result.map_id}[/]: "
            f"{team_name(gs, fixture.team_a)} {map_result.score_a}-"
            f"{map_result.score_b} {team_name(gs, fixture.team_b)}"
        )
        # Round timeline, compressed to a strip of colored pips (ASCII only
        # so legacy Windows consoles don't choke).
        pips = []
        for r in stats.rounds:
            mine = r.winner_id == gs.user_team_id
            symbol = {"elim": "x", "spike_detonation": "*", "spike_defused": "d", "time": "t"}
            pips.append(
                f"[{'green' if mine else 'red'}]{symbol.get(r.reason, '.')}[/]"
            )
        console.print("    " + "".join(pips))
        table = Table(border_style="dim", pad_edge=False)
        table.add_column("Player")
        for col in ("K", "D", "FK", "HS", "Rating"):
            table.add_column(col, justify="right")
        ordered = sorted(stats.lines.values(), key=lambda l: -l.rating)
        for line in ordered:
            style = (
                "cyan"
                if gs.players.get(line.player_id)
                and line.player_id in gs.teams[gs.user_team_id].player_ids
                else ""
            )
            name = handle_of(gs, line.player_id)
            table.add_row(
                f"[{style}]{name}[/]" if style else name,
                str(line.kills), str(line.deaths), str(line.first_kills),
                str(line.headshots), f"{line.rating:.2f}",
            )
        console.print(table)
    console.print(
        "    [dim]legend: x elim  * spike detonated  d defused  t time[/]"
    )


def job_market_screen(gs: GameState) -> None:
    """A dismissed legacy manager picks their next club — the world does
    not advance until they do (same rule the web advance gate enforces)."""
    for mid in career.blocked_seats(gs):
        offers = gs.career_offers_by[mid]
        console.print(
            "[red]The board has relieved you of your duties.[/] "
            "Offers on the table:"
        )
        for i, o in enumerate(offers, 1):
            goal = career.GOAL_LABELS.get(o.goal, o.goal)
            console.print(
                f"  {i}) {team_name(gs, o.team_id)} "
                f"[{o.archetype.replace('_', ' ')}] - {o.seasons}-season "
                f"deal, board wants: {goal}"
            )
        while True:
            c = ask("Offer number: ")
            if c.isdigit() and 1 <= int(c) <= len(offers):
                ok, msg = career.accept_offer(gs, mid, offers[int(c) - 1].team_id)
                if ok:
                    telemetry.record_action(
                        gs, "accept_job",
                        {"seat": mid},
                        team_id=offers[int(c) - 1].team_id,
                        source="cli",
                    )
                    console.print(f"[green]{msg}[/]")
                    break
        save(gs)


def advance_screen(gs: GameState, gd: GameData) -> None:
    # A dismissed legacy manager must take a job before the world moves.
    if career.blocked_seats(gs):
        job_market_screen(gs)
    # A legal roster is required to tick a match week (the offseason tick plays
    # no matches, so it's exempt). Same rule the web ready-up enforces.
    if gs.phase != "offseason":
        ok, why = roster_ready(gs, gs.user_team_id)
        if not ok:
            console.print(f"[red]{why}.[/]")
            return
    telemetry.record_action(gs, "advance", source="cli")
    report = advance_week(gs, gd)
    render_week_results(gs, report)
    save(gs)
    console.print("[dim]autosaved[/]")
    if career.blocked_seats(gs):
        job_market_screen(gs)


def hub(gs: GameState, gd: GameData) -> None:
    while True:
        console.print()
        hub_header(gs)
        console.print(
            "  1) roster   2) training   3) market   4) league   "
            "5) finances   6) news\n  [bold]p) play week[/]   s) save   q) quit"
        )
        c = ask()
        if c == "1":
            roster_screen(gs)
        elif c == "2":
            training_screen(gs)
        elif c == "3":
            market_screen(gs)
        elif c == "4":
            league_screen(gs)
        elif c == "5":
            finances_screen(gs)
        elif c == "6":
            news_screen(gs)
        elif c == "p":
            advance_screen(gs, gd)
        elif c == "s":
            save(gs)
            console.print("[green]saved[/]")
        elif c == "q":
            save(gs)
            console.print("[green]saved — see you next split[/]")
            return


# ---------------------------------------------------------------------------
# Headless auto mode (used for demos and end-to-end verification)


def auto_play(
    gd: GameData, weeks: int, seed: int, team: str, roster: str | None = None
) -> None:
    pack = load_roster_pack(roster) if roster else None
    gs = new_campaign(gd, seed, user_team_id=team, pack=pack)
    # A hands-off manager who at least renews contracts, keeps a legal roster,
    # and rests the team.
    for _ in range(weeks):
        for p in gs.roster(gs.user_team_id):
            if 0 < p.contract_weeks_left <= 4:
                renew_contract(gs, gs.user_team_id, p.id)
        # Never tick a match week short-handed: fill empty seats with the best
        # affordable free agent (mirrors the roster-min invariant).
        while len(gs.teams[team].player_ids) < ROSTER_MIN and gs.free_agent_ids:
            best = max(
                (gs.players[pid] for pid in gs.free_agent_ids),
                key=lambda p: (player_quality(p), p.id),
            )
            ok, _ = sign_player(gs, team, best.id)
            if not ok:
                break
        avg_stamina = sum(p.stamina for p in gs.roster(gs.user_team_id)) / max(
            len(gs.teams[gs.user_team_id].player_ids), 1
        )
        gs.training_focus[gs.user_team_id] = "rest" if avg_stamina < 60 else "tactical"
        report = advance_week(gs, gd)
        mine = next(
            (f for f in report.fixtures if gs.user_team_id in (f.team_a, f.team_b)),
            None,
        )
        if mine is not None:
            a, b = mine.map_score
            score = (
                f"{a}-{b}"
                if mine.best_of == 3
                else (
                    f"{mine.results[0].score_a}-{mine.results[0].score_b}"
                    if mine.results
                    else "w/o"
                )
            )
            won = mine.winner_id == gs.user_team_id
            console.print(
                f"S{report.season} W{report.week:2d} "
                f"[{'green' if won else 'red'}]{'W' if won else 'L'}[/] "
                f"{team_name(gs, mine.team_a)} {score} {team_name(gs, mine.team_b)}"
            )
        for note in report.notes:
            console.print(f"  [yellow]{note}[/]")
    t = gs.teams[gs.user_team_id]
    console.print(
        f"\nfinal: rank #{t.world_rank}, balance {fmt_cr(t.balance)}, "
        f"season {gs.season} week {gs.week}"
    )
    save(gs)
    return gs


def main() -> None:
    parser = argparse.ArgumentParser(prog="esports_sim")
    parser.add_argument("--auto", type=int, default=0, help="headless: play N weeks")
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--team", type=str, default="team_nexus")
    parser.add_argument(
        "--roster",
        type=str,
        default=None,
        help="roster pack id under data/rosters/ (e.g. vct-2026); "
        "default = generated fictional world",
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="with --auto: print a deterministic season-report JSON after the run "
        "(headless analytics export for LLM-playtest / analysis)",
    )
    parser.add_argument(
        "--playtest",
        type=int,
        default=0,
        help="headless: run N full seasons and print a deterministic multi-season "
        "playtest summary JSON (title/award timelines, dynasties, career arcs)",
    )
    parser.add_argument("--web", action="store_true", help="launch the browser UI")
    # Honour $PORT (dev-server harnesses assign one) when --port isn't given.
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8420)))
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="bind address; 0.0.0.0 (default) lets LAN players connect, "
        "127.0.0.1 keeps it to this PC only",
    )
    args = parser.parse_args()

    if args.web:
        from esports_sim.web.server import run  # deferred: needs [web] extras

        run(port=args.port, open_browser=not args.no_browser, host=args.host)
        return

    gd = load_all()
    if args.playtest > 0:
        import json

        from esports_sim.manager import analytics

        pack = load_roster_pack(args.roster) if args.roster else None
        gs = new_campaign(gd, args.seed, user_team_id=args.team, pack=pack)
        # Hands-off: keep the user roster legal, let the world play out N seasons.
        while gs.season <= args.playtest:
            while len(gs.teams[args.team].player_ids) < ROSTER_MIN and gs.free_agent_ids:
                best = max(
                    (gs.players[pid] for pid in gs.free_agent_ids),
                    key=lambda p: (player_quality(p), p.id),
                )
                ok, _ = sign_player(gs, args.team, best.id)
                if not ok:
                    break
            advance_week(gs, gd)
        print(json.dumps(analytics.playtest_summary(gs), indent=2, ensure_ascii=True))
        return

    if args.auto > 0:
        gs = auto_play(gd, args.auto, args.seed, args.team, roster=args.roster)
        if args.report:
            import json

            from esports_sim.manager import analytics

            print(json.dumps(analytics.season_report(gs), indent=2, ensure_ascii=True))
        return

    gs = title_screen(gd)
    if gs is not None:
        hub(gs, gd)


if __name__ == "__main__":
    sys.exit(main())
