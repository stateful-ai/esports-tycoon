"""Free-roam movement and visibility over the authored floor plan."""

from __future__ import annotations

import pytest

from esports_sim.policy.base import MotorMovement, MovementPace
from esports_sim.registry import load_all
from esports_sim.schemas.geometry import MapGeometry, Opening, Prop, Region
from esports_sim.schemas.map import Callout, CalloutZone, Map, MovementModel, Site
from esports_sim.sim.engine import _MatchSim
from esports_sim.sim.free_movement import FreeMovementResolver


def _callout(callout_id: str, x: float, y: float) -> Callout:
    return Callout(
        id=callout_id,
        display_name=callout_id,
        site=Site.NONE,
        zone=CalloutZone.MID,
        x=x,
        y=y,
    )


def _resolver(*, props: list[Prop] | None = None) -> FreeMovementResolver:
    map_obj = Map(
        id="free-test",
        display_name="Free Test",
        movement_model=MovementModel.FREE,
        sites=[],
        callouts={
            "left": _callout("left", 5.0, 5.0),
            "right": _callout("right", 15.0, 5.0),
        },
        adjacency={"left": ["right"], "right": ["left"]},
        attacker_spawn="left",
        defender_spawn="right",
    )
    geometry = MapGeometry(
        map_id=map_obj.id,
        regions={
            "left": Region(x=0.0, y=0.0, w=10.0, h=10.0),
            "right": Region(x=10.0, y=0.0, w=10.0, h=10.0),
        },
        openings=[Opening(between=("left", "right"), span=(4.0, 6.0))],
        props=props or [],
    )
    return FreeMovementResolver(
        map_obj,
        geometry,
        player_radius=0.25,
        collision_step=0.1,
    )


def test_free_move_crosses_only_through_authored_doorway() -> None:
    resolver = _resolver()

    through = resolver.resolve_step(9.0, 5.0, 2.0, 0.0, "left")
    assert through.callout_id == "right"
    assert through.x == pytest.approx(11.0)

    into_wall = resolver.resolve_step(9.0, 2.0, 2.0, 0.0, "left")
    assert into_wall.callout_id == "left"
    assert into_wall.x <= 10.0 + 1e-7

    shut = resolver.resolve_step(
        9.0,
        5.0,
        2.0,
        0.0,
        "left",
        frozenset((frozenset(("left", "right")),)),
    )
    assert shut.callout_id == "left"
    assert shut.x <= 10.0 + 1e-7


def test_free_move_collides_with_cover_and_slides_along_it() -> None:
    resolver = _resolver(
        props=[
            Prop(
                region="left",
                x=4.0,
                y=3.0,
                w=2.0,
                h=2.0,
                height="half",
            )
        ]
    )
    result = resolver.resolve_step(3.0, 4.0, 3.0, 1.5, "left")
    assert result.x < 6.0  # the direct diagonal endpoint
    assert result.y >= 5.25  # slid past the expanded lower prop edge


def test_visibility_uses_floor_doorway_props_and_door_state() -> None:
    resolver = _resolver(
        props=[
            Prop(
                region="right",
                x=14.0,
                y=4.5,
                w=1.0,
                h=1.0,
                height="full",
            )
        ]
    )
    assert not resolver.has_line_of_sight(
        5.0, 2.0, "left", 15.0, 2.0, "right"
    )
    assert not resolver.has_line_of_sight(
        5.0, 5.0, "left", 15.0, 5.0, "right"
    )

    clear = _resolver()
    assert clear.has_line_of_sight(5.0, 5.0, "left", 15.0, 5.0, "right")
    assert not clear.has_line_of_sight(
        5.0,
        5.0,
        "left",
        15.0,
        5.0,
        "right",
        frozenset((frozenset(("left", "right")),)),
    )


def test_ascent_exposes_and_replays_free_motor_controls() -> None:
    sim = _MatchSim(
        load_all(), "team_nexus", "team_vanguard", "ascent", seed=131
    )
    player = sim.p[sorted(sim.p)[0]]
    region = sim._geo.regions[sim.map.attacker_spawn]
    player.callout = sim.map.attacker_spawn
    player.x, player.y = region.cx, region.cy
    player.heading_degrees = 0.0
    player.move_dest = None
    player.move_eta = -1
    player.path = []

    legal = sim._motor_legal_controls(player)
    forward = next(
        control
        for control in legal
        if control.movement == MotorMovement.FORWARD
        and control.pace == MovementPace.RUN
    )
    # Routed counterexample: force the flag off rather than relying on
    # any particular live map staying routed (they are migrating one by
    # one as their traces land).
    routed_data = load_all()
    routed_map = routed_data.maps["ascent"].model_copy(
        update={"movement_model": MovementModel.ROUTED}
    )
    routed_data.maps["ascent"] = routed_map
    assert all(
        control.movement not in {
            MotorMovement.FORWARD,
            MotorMovement.BACKWARD,
            MotorMovement.STRAFE_LEFT,
            MotorMovement.STRAFE_RIGHT,
        }
        for control in _MatchSim(
            routed_data, "team_nexus", "team_vanguard", "ascent", seed=131
        )._motor_legal_controls(player)
    )

    player.planting_until = 8
    assert all(
        control.movement == MotorMovement.HOLD
        for control in sim._motor_legal_controls(player)
    )
    player.planting_until = -1

    start_x = player.x
    sim._apply_motor_control(player, forward, legal, 1, ("free", "one"))
    sim._apply_motor_control(player, forward, legal, 2, ("free", "two"))

    assert player.x > start_x
    assert player.last_motor_moved
    assert sim._round_state(player).is_moving
    controls = [event for event in sim.log if event.type == "round.control"]
    assert len(controls) == 2
    assert controls[-1].movement == "forward"
    assert controls[-1].route_active is False
    assert controls[-1].x == round(player.x, 3)


def test_ascent_physical_los_respects_the_switch_door() -> None:
    sim = _MatchSim(
        load_all(), "team_nexus", "team_vanguard", "ascent", seed=137
    )
    first = next(ps for ps in sim.p.values() if ps.team_id == "team_nexus")
    second = next(ps for ps in sim.p.values() if ps.team_id == "team_vanguard")
    room1, room2 = "a_garden", "a_site"
    portal_x, portal_y = sim._geo.portal(room1, room2)

    def inside(room: str) -> tuple[float, float]:
        region = sim._geo.regions[room]
        dx, dy = region.cx - portal_x, region.cy - portal_y
        length = (dx * dx + dy * dy) ** 0.5
        return portal_x + dx / length, portal_y + dy / length

    first.callout, second.callout = room1, room2
    first.x, first.y = inside(room1)
    second.x, second.y = inside(room2)

    assert sim._position_sightline(first, second)[0]
    sim._doors_closed.add("a_garden_door")
    assert not sim._position_sightline(first, second)[0]
