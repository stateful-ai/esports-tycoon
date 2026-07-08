"""Rotation pacing report.

Rule of thumb (owner, 2026-07-07): an attacker rotate from one site to
another THROUGH THEIR OWN SPAWN should take ~30 s. Defender rotates run
through their side of the map and should be meaningfully faster — that
edge is the defenders' compensation for playing 5 sites blind.

Times are pure geometry: BFS room route, polyline length per hop at the
base player speed (movement=50). Run after touching map geometry.

Usage:
    .venv-win\\Scripts\\python.exe scripts\\pacing_report.py
"""

from __future__ import annotations

from collections import deque

from esports_sim.registry import load_all
from esports_sim.registry.loader import load_geometry
from esports_sim.schemas.map import CalloutZone, Site
from esports_sim.sim import constants as C

TICKS_PER_SEC = 2.0

ATK_ROTATE_TARGET = (25.0, 35.0)  # seconds, via spawn
STAGE_TARGET = (8.0, 18.0)  # spawn -> entry


def _route(m, src: str, dst: str, forbid: set[str] = frozenset()) -> list[str]:
    prev = {src: src}
    q = deque([src])
    while q:
        cur = q.popleft()
        if cur == dst:
            break
        for nxt in m.neighbors(cur):
            if nxt not in prev and nxt not in forbid:
                prev[nxt] = cur
                q.append(nxt)
    if dst not in prev:
        return []
    route = [dst]
    while route[-1] != src:
        route.append(prev[route[-1]])
    return list(reversed(route))


def _route_seconds(geo, route: list[str]) -> float:
    length = sum(geo.hop_distance(a, b) for a, b in zip(route, route[1:]))
    return length / C.PLAYER_SPEED / TICKS_PER_SEC


def _entries(m, site: str) -> list[str]:
    sites = [
        c.id
        for c in m.callouts.values()
        if str(c.site) == site and c.zone == CalloutZone.SITE
    ]
    out = set()
    for sc in sites:
        for nb in m.neighbors(sc):
            if m.callouts[nb].zone in (CalloutZone.ATTACKER_SIDE, CalloutZone.MID):
                out.add(nb)
    return sorted(out) or sites


def main() -> None:
    gd = load_all()
    any_fail = False
    for mid in sorted(gd.maps):
        m = gd.maps[mid]
        geo = load_geometry(mid)
        if geo is None:
            print(f"{mid:8s} no geometry")
            continue
        sites = [str(s) for s in m.sites if s != Site.MID]
        entry = {s: _entries(m, s)[0] for s in sites}
        spawn = m.attacker_spawn

        stages = {
            s: _route_seconds(geo, _route(m, spawn, entry[s])) for s in sites
        }
        print(f"{mid:8s} stage: " + "  ".join(f"{s.upper()}={t:4.1f}s" for s, t in stages.items()))

        for i, s1 in enumerate(sites):
            for s2 in sites[i + 1:]:
                secs = (
                    _route_seconds(geo, _route(m, entry[s1], spawn))
                    + _route_seconds(geo, _route(m, spawn, entry[s2]))
                )
                ok = ATK_ROTATE_TARGET[0] <= secs <= ATK_ROTATE_TARGET[1]
                any_fail |= not ok
                # Defender rotate: site room to site room, their side.
                d_route = _route(
                    m,
                    sorted(
                        c.id for c in m.callouts.values()
                        if str(c.site) == s1 and c.zone == CalloutZone.SITE
                    )[0],
                    sorted(
                        c.id for c in m.callouts.values()
                        if str(c.site) == s2 and c.zone == CalloutZone.SITE
                    )[0],
                    forbid={spawn},
                )
                d_secs = _route_seconds(geo, d_route) if d_route else float("nan")
                flag = "" if ok else "  <-- OUT OF BAND"
                print(
                    f"         atk {s1.upper()}->{s2.upper()} via spawn:"
                    f" {secs:5.1f}s   def rotate: {d_secs:5.1f}s{flag}"
                )
    print()
    print(f"target: attacker rotate {ATK_ROTATE_TARGET[0]:.0f}-{ATK_ROTATE_TARGET[1]:.0f}s via spawn")
    if any_fail:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
