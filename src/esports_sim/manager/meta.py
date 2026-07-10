"""Meta evolution: live balance patches that buff/nerf agents.

Twice a season (mid-split and over the break) the developer ships a
patch: the most-played agents catch nerfs, the ignored ones get help.
Changes are deltas to the numeric knobs the engine already consumes —
ability cost (buy-phase economics), charges (utility volume), ultimate
points (ult frequency) — held on GameState as a cumulative modifier set
and applied by `runtime_gamedata` when it builds each week's GameData.
The bare-engine gates load the registry directly, so an empty modifier
set (the default) is structurally invisible to golden/balance/pacing.

Determinism: patch timing is fixed by the calendar; content draws from a
dedicated campaign rng stream (label "patch") over sorted candidate
lists, so no other subsystem's draws ever shift.
"""

from __future__ import annotations

import numpy as np

from esports_sim.manager.state import GameState, PatchChange, PatchNote
from esports_sim.schemas import Ability, Agent

# Clamps for patched knobs — patches bend the meta, they don't break kits.
_COST_MIN, _COST_MAX = 0, 900
_CHARGES_MIN, _CHARGES_MAX = 1, 3
_ULT_MIN, _ULT_MAX = 4, 9

PATCH_HISTORY_CAP = 20


# ---------------------------------------------------------------------------
# Applying the active set


def apply_patches(
    agents: dict[str, Agent], patches: list[PatchChange]
) -> dict[str, Agent]:
    """A NEW agents dict with the cumulative modifier set applied.
    Untouched agents pass through by reference; patched ones are rebuilt
    with model_copy (Agent/Ability are frozen). Never mutates the input —
    the web server shares one registry GameData across every campaign."""
    if not patches:
        return agents
    # (agent_id, ability_id, field) -> summed delta
    deltas: dict[tuple[str, str, str], int] = {}
    for ch in patches:
        key = (ch.agent_id, ch.ability_id, ch.field)
        deltas[key] = deltas.get(key, 0) + ch.delta
    touched = {aid for (aid, _, _) in deltas}
    out: dict[str, Agent] = {}
    for aid in sorted(agents):
        agent = agents[aid]
        if aid not in touched:
            out[aid] = agent
            continue
        abilities: list[Ability] = []
        for ab in agent.abilities:
            update: dict[str, int] = {}
            cost_d = deltas.get((aid, ab.id, "cost"), 0)
            if cost_d:
                update["cost"] = int(
                    np.clip(ab.cost + cost_d, _COST_MIN, _COST_MAX)
                )
            charges_d = deltas.get((aid, ab.id, "charges"), 0)
            if charges_d:
                update["charges"] = int(
                    np.clip(ab.charges + charges_d, _CHARGES_MIN, _CHARGES_MAX)
                )
            ult_d = deltas.get((aid, ab.id, "ult_points"), 0)
            if ult_d and ab.ult_points is not None:
                update["ult_points"] = int(
                    np.clip(ab.ult_points + ult_d, _ULT_MIN, _ULT_MAX)
                )
            abilities.append(ab.model_copy(update=update) if update else ab)
        out[aid] = agent.model_copy(update={"abilities": abilities})
    return out


def _consolidate(patches: list[PatchChange]) -> list[PatchChange]:
    """Sum the cumulative set down to one entry per (agent, ability,
    field), sorted — keeps the list bounded over many seasons and the
    iteration order deterministic."""
    deltas: dict[tuple[str, str, str], int] = {}
    for ch in patches:
        key = (ch.agent_id, ch.ability_id, ch.field)
        deltas[key] = deltas.get(key, 0) + ch.delta
    return [
        PatchChange(agent_id=a, ability_id=ab, field=f, delta=d)
        for (a, ab, f), d in sorted(deltas.items())
        if d != 0
    ]


# ---------------------------------------------------------------------------
# Rolling a new patch


def _agent_usage(gs: GameState) -> dict[str, int]:
    """Maps played per agent this season (from the per-agent splits)."""
    usage: dict[str, int] = {}
    for pid in sorted(gs.player_agent_stats):
        for aid in sorted(gs.player_agent_stats[pid]):
            usage[aid] = usage.get(aid, 0) + gs.player_agent_stats[pid][aid].maps
    return usage


def meta_report(gs: GameState, agents: dict[str, Agent]) -> dict:
    """Read-only snapshot of the live meta for the UI: the most recent patch
    note, the net buff/nerf standing of every patched agent, and a usage tier
    list (most-played agents this season). `agents` is the STATIC registry
    bundle; nothing here mutates state or the registry."""
    usage = _agent_usage(gs)
    total_maps = sum(usage.values())

    # Net direction per patched agent: a negative summed delta on cost is a
    # buff (cheaper), a positive one a nerf; charges/ult flip the sign. We fold
    # everything to a simple {agent: net} where net>0 = buffed, net<0 = nerfed.
    net: dict[str, int] = {}
    for ch in gs.agent_patches:
        # cost up = nerf (-), charges/ult up = buff (+). Normalise to "power".
        signed = -ch.delta if ch.field == "cost" else ch.delta
        net[ch.agent_id] = net.get(ch.agent_id, 0) + signed
    patched = [
        {
            "agent_id": aid,
            "name": agents[aid].display_name if aid in agents else aid,
            "direction": "buff" if v > 0 else "nerf" if v < 0 else "even",
        }
        for aid, v in sorted(net.items(), key=lambda kv: (kv[1], kv[0]))
        if v != 0
    ]

    tiers = [
        {
            "agent_id": aid,
            "name": agents[aid].display_name if aid in agents else aid,
            "maps": usage[aid],
            "pick_rate": round(100.0 * usage[aid] / total_maps, 1) if total_maps else 0.0,
        }
        for aid in sorted(usage, key=lambda a: (-usage[a], a))
        if usage[aid] > 0
    ][:8]

    latest = gs.patch_history[-1] if gs.patch_history else None
    return {
        "latest_patch": (
            {
                "version": latest.version,
                "season": latest.season,
                "week": latest.week,
                "lines": list(latest.lines),
            }
            if latest is not None
            else None
        ),
        "patched_agents": patched,
        "tier_list": tiers,
    }


def _change_options(
    agent: Agent, nerf: bool
) -> list[tuple[str, str, int, str]]:
    """Legal (ability_id, field, delta, line) changes for one EFFECTIVE
    agent (active patches already applied). A nerf makes the kit dearer or
    thinner; a buff the reverse. Only options that survive the clamps are
    offered, so a patch never no-ops."""
    opts: list[tuple[str, str, int, str]] = []
    for ab in agent.abilities:
        if ab.type == "ultimate":
            if ab.ult_points is not None:
                if nerf and ab.ult_points < _ULT_MAX:
                    opts.append(
                        (ab.id, "ult_points", 1,
                         f"{ab.name} {ab.ult_points} -> {ab.ult_points + 1} points")
                    )
                elif not nerf and ab.ult_points > _ULT_MIN:
                    opts.append(
                        (ab.id, "ult_points", -1,
                         f"{ab.name} {ab.ult_points} -> {ab.ult_points - 1} points")
                    )
            continue
        if ab.cost >= 100:
            d = 50 if nerf else -50
            if _COST_MIN <= ab.cost + d <= _COST_MAX:
                opts.append(
                    (ab.id, "cost", d,
                     f"{ab.name} {ab.cost} -> {ab.cost + d} credits")
                )
        if nerf and ab.charges > _CHARGES_MIN:
            opts.append(
                (ab.id, "charges", -1,
                 f"{ab.name} {ab.charges} -> {ab.charges - 1} charges")
            )
        elif not nerf and ab.charges < _CHARGES_MAX and ab.type == "basic":
            opts.append(
                (ab.id, "charges", 1,
                 f"{ab.name} {ab.charges} -> {ab.charges + 1} charges")
            )
    return opts


def roll_patch(gs: GameState, gd, rng, version: str) -> PatchNote | None:
    """Ship one balance patch: nerf the meta's darlings, help the
    forgotten. `gd` is the STATIC registry bundle (base agents); the
    active set is applied first so options are judged against the kit as
    it currently plays. Appends to gs.agent_patches/patch_history, writes
    the news line, and returns the note (None if nothing changed)."""
    effective = apply_patches(gd.agents, gs.agent_patches)
    usage = _agent_usage(gs)
    by_usage = sorted(effective, key=lambda a: (-usage.get(a, 0), a))
    nerf_pool = [a for a in by_usage[:4] if usage.get(a, 0) > 0] or by_usage[:2]
    buff_pool = list(reversed(by_usage[-4:]))

    n_nerfs = 1 + int(rng.random() < 0.5)
    n_buffs = 1 + int(rng.random() < 0.5)
    changes: list[PatchChange] = []
    lines: list[str] = []
    picked: set[str] = set()
    for pool, nerf, count in ((nerf_pool, True, n_nerfs), (buff_pool, False, n_buffs)):
        pool = [a for a in pool if a not in picked]
        for _ in range(count):
            if not pool:
                break
            aid = pool.pop(int(rng.integers(0, len(pool))))
            picked.add(aid)
            opts = _change_options(effective[aid], nerf)
            if not opts:
                continue
            ability_id, field, delta, line = opts[int(rng.integers(0, len(opts)))]
            changes.append(
                PatchChange(
                    agent_id=aid, ability_id=ability_id, field=field, delta=delta
                )
            )
            arrow = "nerf" if nerf else "buff"
            lines.append(f"{effective[aid].display_name} ({arrow}): {line}")
    if not changes:
        return None

    gs.agent_patches = _consolidate(gs.agent_patches + changes)
    note = PatchNote(season=gs.season, week=gs.week, version=version, lines=lines)
    gs.patch_history.append(note)
    del gs.patch_history[:-PATCH_HISTORY_CAP]
    gs.push_news(
        f"Patch {version} ships — {'; '.join(lines)}."
    )
    return note
