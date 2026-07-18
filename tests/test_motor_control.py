from __future__ import annotations

from esports_sim.policy.base import MotorControl, MotorMovement, MovementPace
from esports_sim.registry import load_all
from esports_sim.sim.engine import _MatchSim, simulate_match_result


def _moving_sim():
    sim = _MatchSim(
        load_all(), "team_nexus", "team_vanguard", "haven", seed=101
    )
    ps = sim.p[sorted(sim.p)[0]]
    ps.callout = sim.map.attacker_spawn
    ps.x = 0.0
    ps.y = 0.0
    ps.path = [(10.0, 0.0)]
    ps.move_dest = ps.callout
    ps.move_eta = 5
    return sim, ps


def _control(legal, movement, pace, turn=0.0):
    return next(
        control
        for control in legal
        if control.movement == movement
        and control.pace == pace
        and control.turn_degrees == turn
    )


def test_motor_pace_and_hold_resolve_distinctly() -> None:
    run_sim, run_ps = _moving_sim()
    walk_sim, walk_ps = _moving_sim()
    hold_sim, hold_ps = _moving_sim()

    run_legal = run_sim._motor_legal_controls(run_ps)
    walk_legal = walk_sim._motor_legal_controls(walk_ps)
    hold_legal = hold_sim._motor_legal_controls(hold_ps)
    run_sim._apply_motor_control(
        run_ps,
        _control(run_legal, MotorMovement.ADVANCE, MovementPace.RUN),
        run_legal,
        1,
        (),
    )
    walk_sim._apply_motor_control(
        walk_ps,
        _control(walk_legal, MotorMovement.ADVANCE, MovementPace.WALK),
        walk_legal,
        1,
        (),
    )
    hold_sim._apply_motor_control(
        hold_ps,
        _control(hold_legal, MotorMovement.HOLD, MovementPace.RUN),
        hold_legal,
        1,
        (),
    )

    assert run_ps.x > walk_ps.x > hold_ps.x == 0.0
    assert walk_ps.movement_pace == MovementPace.WALK
    assert hold_ps.move_eta == 6


def test_fast_control_tiebreak_matches_serialized_contract() -> None:
    """The allocation-cheap tie key preserves the old JSON field ordering."""
    sim, ps = _moving_sim()
    policy = next(iter(sim.player_policies.values()))
    for has_route in (False, True):
        ps.move_eta = 5 if has_route else -1
        legal = sim._motor_legal_controls(ps)
        movement = MotorMovement.ADVANCE if has_route else MotorMovement.HOLD
        candidates = [
            control
            for control in legal
            if control.movement == movement and control.pace == MovementPace.RUN
        ]
        desired_turns = (
            (-90.0, -45.0, -22.5, 0.0, 22.5, 45.0, 90.0)
            if has_route
            else (0.0,)
        )
        for desired_turn in desired_turns:
            expected = min(
                candidates,
                key=lambda control: (
                    abs(desired_turn - control.turn_degrees),
                    abs(control.turn_degrees),
                    control.model_dump_json(),
                ),
            )
            actual = policy.control_fast_state(
                has_route, 0.0, desired_turn if has_route else None, legal, None
            )
            assert actual is expected


def test_engine_rejects_unoffered_turn_and_exposes_pose_v2() -> None:
    sim, ps = _moving_sim()
    legal = sim._motor_legal_controls(ps)
    invalid = MotorControl(
        movement=MotorMovement.ADVANCE,
        pace=MovementPace.RUN,
        turn_degrees=90.0,
    )
    sim._apply_motor_control(ps, invalid, legal, 1, ())

    # Invalid controls fall back to the compatibility RUN command; policies
    # can only choose increments the engine offered.
    assert ps.x > 0.0
    assert ps.heading_degrees == 0.0
    event = sim.log[-1]
    assert event.type == "round.control"
    assert event.turn_degrees == 0.0

    ps.path = []
    ps.move_dest = None
    ps.move_eta = -1
    stationary = sim._motor_legal_controls(ps)
    sim._apply_motor_control(
        ps,
        _control(stationary, MotorMovement.HOLD, MovementPace.RUN, 45.0),
        stationary,
        2,
        (),
    )
    observation = sim._observe(
        ps.pid,
        round_num=1,
        tick=2,
        spike_planted=False,
        is_attacking=True,
        order="hold",
    )
    assert observation.schema_version == 2
    assert observation.self_state.x == ps.x
    assert observation.self_state.y == ps.y
    assert observation.self_state.heading_degrees == 45.0
    assert observation.navigation_heading_degrees is None


def test_running_is_heard_coarsely_while_walking_is_silent() -> None:
    sim = _MatchSim(
        load_all(), "team_nexus", "team_vanguard", "haven", seed=103
    )
    observer = next(ps for ps in sim.p.values() if ps.team_id == "team_nexus")
    enemy = next(ps for ps in sim.p.values() if ps.team_id == "team_vanguard")
    observer.callout = sim.map.attacker_spawn
    enemy.callout = sim.map.defender_spawn
    observer.x = observer.y = 10.0
    enemy.x, enemy.y = 20.0, 10.0
    sim._sightline = lambda *_args: (False, None)

    enemy.motor_movement = MotorMovement.ADVANCE
    enemy.movement_pace = MovementPace.RUN
    heard = sim._enemy_readouts(observer.pid, tick=5)
    assert len(heard) == 1
    assert heard[0].source == "heard"
    assert heard[0].last_seen_callout == enemy.callout
    assert heard[0].last_seen_x is None
    assert heard[0].last_seen_y is None

    sim._enemy_memory[observer.pid].clear()
    enemy.movement_pace = MovementPace.WALK
    assert sim._enemy_readouts(observer.pid, tick=6) == []


def test_analytics_can_skip_control_replay_without_changing_outcomes() -> None:
    gd = load_all()
    full = simulate_match_result(
        gd, "team_nexus", "team_vanguard", "haven", seed=107
    )
    compact = simulate_match_result(
        gd,
        "team_nexus",
        "team_vanguard",
        "haven",
        seed=107,
        capture_control_events=False,
    )
    assert (full.score_a, full.score_b, full.winner_id) == (
        compact.score_a,
        compact.score_b,
        compact.winner_id,
    )
    essential = {"round.start", "round.end", "match.end"}
    assert [
        event.model_dump_json() for event in full.events if event.type in essential
    ] == [
        event.model_dump_json() for event in compact.events if event.type in essential
    ]
    assert any(event.type == "round.control" for event in full.events)
    assert not any(event.type == "round.control" for event in compact.events)
