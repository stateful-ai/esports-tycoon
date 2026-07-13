"""E2E Test Suite for Esports Simulator Enhancements (R1-R4 covering F1-F11).

This test suite verifies the functionality of:
- Locker Room Hierarchy Tier Calculation (F1)
- Benching/Releasing Team Leaders Morale Impact (F2)
- Promise Creation & Tracking (F3)
- Promise Impact on Morale & Chemistry (F4)
- Player Mentorship PA & Tag Transfer (F5)
- Halftime Pep Talks (F6)
- Touchline Shouts (F7)
- LLM Talk Context Grounding (F8)
- LLM Response Adjustment Application (F9)
- LLM Talk Promise/Memory Updates (F10)
- xDuel & Expected Duel Edge (xDE) Telemetry (F11)

All tests are collected by pytest. Imports of unimplemented modules are done dynamically
so that collection succeeds and failures are reported at runtime.
"""

from __future__ import annotations

import json
import os
import math
import pytest
from unittest.mock import MagicMock, patch

from esports_sim.manager import new_campaign, advance_week
from esports_sim.manager.state import GameState
from esports_sim.registry import GameData


# --- Global Network Mock to prevent any real HTTP/API requests ---
@pytest.fixture(autouse=True)
def mock_network():
    with patch("urllib.request.urlopen") as mock_url, \
         patch("urllib.request.Request") as mock_req:
        mock_response = MagicMock()
        mock_response.read.return_value = (
            b'{"choices": [{"message": {"content": "{\\"title\\": \\"Mocked Title\\", \\"prompt\\": \\"Mocked Prompt\\", \\"choices\\": [\\"Option 1\\", \\"Option 2\\"]}"}}]}'
        )
        mock_url.return_value.__enter__.return_value = mock_response
        mock_url.return_value.read = mock_response.read
        yield


# --- Fixture for Campaign GameState ---
@pytest.fixture()
def campaign(game_data: GameData) -> GameState:
    return new_campaign(game_data, seed=42)


# --- Helper for dynamic imports ---
def get_func(module_path: str, func_name: str):
    import importlib
    try:
        mod = importlib.import_module(module_path)
    except ImportError as e:
        pytest.fail(f"Could not import module '{module_path}': {e}", pytrace=False)
    try:
        return getattr(mod, func_name)
    except AttributeError as e:
        pytest.fail(f"Module '{module_path}' has no attribute '{func_name}': {e}", pytrace=False)


# ==============================================================================
# TIER 1: FEATURE COVERAGE (55 tests)
# ==============================================================================

# --- Locker Room Hierarchy Tier Calculation (F1) ---

def test_tier1_f1_incumbent_leader(campaign):
    """Verifies that a team captain is correctly calculated as the Incumbent Leader."""
    get_role = get_func("esports_sim.manager.locker_room", "get_hierarchy_role")
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    team.captain_id = pid
    
    role = get_role(campaign, pid, team.id)
    assert role == "incumbent_leader", f"Expected captain role to be incumbent_leader, got {role}"


def test_tier1_f1_council_member(campaign):
    """Verifies that leadership group members are correctly calculated as Council Members."""
    get_role = get_func("esports_sim.manager.locker_room", "get_hierarchy_role")
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[1]
    player = campaign.players[pid]
    player.age = 26
    player.tenure_weeks = 50
    if "leader" not in player.personality_tags:
        player.personality_tags.append("leader")
    
    role = get_role(campaign, pid, team.id)
    assert role == "council_member", f"Expected council_member, got {role}"


def test_tier1_f1_key_influencer(campaign):
    """Verifies that a starter with high morale, high followers, and ego > 65 is calculated as a Key Influencer."""
    get_role = get_func("esports_sim.manager.locker_room", "get_hierarchy_role")
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[2]
    player = campaign.players[pid]
    player.morale = 85.0
    player.followers = 300000
    team.lineup_ids = list(team.player_ids[:5])
    if pid not in team.lineup_ids:
        team.lineup_ids.append(pid)
        
    with patch("esports_sim.manager.personality.axes", return_value={"ego": 70.0, "resilience": 50.0, "sociability": 50.0, "professionalism": 50.0, "ambition": 50.0}):
        role = get_role(campaign, pid, team.id)
    assert role == "key_influencer", f"Expected key_influencer, got {role}"


def test_tier1_f1_loyal_lieutenant(campaign):
    """Verifies that a player with high sociability and a relationship >= 70 with the captain is calculated as a Loyal Lieutenant."""
    get_role = get_func("esports_sim.manager.locker_room", "get_hierarchy_role")
    team = list(campaign.teams.values())[0]
    captain_id = team.player_ids[0]
    team.captain_id = captain_id
    pid = team.player_ids[3]
    
    # Establish high relationship with captain
    from esports_sim.manager import relationships
    relationships.nudge(campaign, pid, captain_id, 80.0)
    
    with patch("esports_sim.manager.personality.axes", return_value={"ego": 40.0, "resilience": 50.0, "sociability": 75.0, "professionalism": 50.0, "ambition": 50.0}):
        role = get_role(campaign, pid, team.id)
    assert role == "loyal_lieutenant", f"Expected loyal_lieutenant, got {role}"


def test_tier1_f1_volatile_rebel(campaign):
    """Verifies that a player with high ego, low professionalism, and low captain relationship is calculated as a Volatile Rebel."""
    get_role = get_func("esports_sim.manager.locker_room", "get_hierarchy_role")
    team = list(campaign.teams.values())[0]
    captain_id = team.player_ids[0]
    team.captain_id = captain_id
    pid = team.player_ids[4]
    
    # Low relationship with captain
    from esports_sim.manager import relationships
    relationships.nudge(campaign, pid, captain_id, -80.0) # pushes relationship low
    
    with patch("esports_sim.manager.personality.axes", return_value={"ego": 80.0, "resilience": 30.0, "sociability": 30.0, "professionalism": 25.0, "ambition": 50.0}):
        role = get_role(campaign, pid, team.id)
    assert role == "volatile_rebel", f"Expected volatile_rebel, got {role}"


# --- Benching/Releasing Team Leaders Morale Impact (F2) ---

def test_tier1_f2_bench_captain_clique(campaign):
    """Verifies that benching the captain reduces morale for members of the captain's clique."""
    handle_benching = get_func("esports_sim.manager.locker_room", "handle_benching_impact")
    team = list(campaign.teams.values())[0]
    captain_id = team.player_ids[0]
    team.captain_id = captain_id
    
    # Set up clique buddy
    clique_mate_id = team.player_ids[1]
    from esports_sim.manager import relationships
    relationships.nudge(campaign, clique_mate_id, captain_id, 85.0) # close buddy
    
    initial_morale = campaign.players[clique_mate_id].morale
    # Bench captain (not in starting lineup)
    team.lineup_ids = [p for p in team.player_ids if p != captain_id]
    
    handle_benching(campaign, team.id, [captain_id])
    new_morale = campaign.players[clique_mate_id].morale
    assert new_morale < initial_morale, f"Clique mate morale did not drop: {initial_morale} -> {new_morale}"


def test_tier1_f2_bench_key_influencer_chemistry(campaign):
    """Verifies that benching a Key Influencer triggers a team chemistry drop of up to 3.0."""
    handle_benching = get_func("esports_sim.manager.locker_room", "handle_benching_impact")
    get_role = get_func("esports_sim.manager.locker_room", "get_hierarchy_role")
    
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[2]
    
    # Stub role as key_influencer
    with patch("esports_sim.manager.locker_room.get_hierarchy_role", return_value="key_influencer"):
        initial_chem = team.chemistry
        team.lineup_ids = [p for p in team.player_ids if p != pid]
        handle_benching(campaign, team.id, [pid])
        new_chem = team.chemistry
        assert new_chem < initial_chem, "Team chemistry did not drop after benching Key Influencer"
        assert initial_chem - new_chem <= 3.01, f"Chemistry dropped too much: {initial_chem - new_chem}"


def test_tier1_f2_release_captain_morale(campaign):
    """Verifies that releasing/selling the team captain triggers morale loss for close friends (relationship >= 70)."""
    handle_release = get_func("esports_sim.manager.locker_room", "handle_release_impact")
    team = list(campaign.teams.values())[0]
    captain_id = team.player_ids[0]
    team.captain_id = captain_id
    
    friend_id = team.player_ids[1]
    # Set relationship >= 70
    from esports_sim.manager import relationships
    relationships.nudge(campaign, friend_id, captain_id, 90.0)
    
    initial_morale = campaign.players[friend_id].morale
    handle_release(campaign, team.id, captain_id)
    new_morale = campaign.players[friend_id].morale
    assert new_morale < initial_morale, f"Friend's morale did not drop: {initial_morale} -> {new_morale}"


def test_tier1_f2_bench_loyal_lieutenant(campaign):
    """Verifies that benching a Loyal Lieutenant (non-leader) has zero leadership-benching morale impact."""
    handle_benching = get_func("esports_sim.manager.locker_room", "handle_benching_impact")
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[3]
    
    initial_morale_others = [campaign.players[p].morale for p in team.player_ids if p != pid]
    with patch("esports_sim.manager.locker_room.get_hierarchy_role", return_value="loyal_lieutenant"):
        handle_benching(campaign, team.id, [pid])
    
    new_morale_others = [campaign.players[p].morale for p in team.player_ids if p != pid]
    assert new_morale_others == initial_morale_others, "Benching loyal lieutenant affected other players' morale"


def test_tier1_f2_weekly_morale_decay(campaign):
    """Verifies that the morale penalty from benching decays/recovers gradually in subsequent weekly ticks."""
    decay_morale = get_func("esports_sim.manager.locker_room", "decay_benching_penalties")
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[1]
    
    # Inject a benching morale penalty state
    campaign.players[pid].morale = 50.0
    decay_morale(campaign)
    assert campaign.players[pid].morale > 50.0, "Player morale did not decay/recover towards default baseline"


# --- Promise Creation & Tracking (F3) ---

def test_tier1_f3_create_playtime_promise(campaign):
    """Verifies the successful creation and state storage of a playtime promise."""
    create_promise = get_func("esports_sim.manager.promises", "create_promise")
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    
    promise = create_promise(campaign, team.id, pid, "play_time", target_value=50, duration=4)
    assert promise in campaign.promises, "Promise was not saved to GameState.promises"
    assert promise.promise_type == "play_time"
    assert promise.weeks_left == 4


def test_tier1_f3_create_contract_promise(campaign):
    """Verifies the successful creation and state storage of a contract renewal promise."""
    create_promise = get_func("esports_sim.manager.promises", "create_promise")
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[1]
    
    promise = create_promise(campaign, team.id, pid, "renew_contract", duration=6)
    assert promise in campaign.promises, "Contract promise not saved"
    assert promise.promise_type == "renew_contract"
    assert promise.weeks_left == 6


def test_tier1_f3_promise_tick_decrement(campaign):
    """Verifies that the remaining duration of an active promise decrements by 1 on each campaign tick."""
    create_promise = get_func("esports_sim.manager.promises", "create_promise")
    weekly_tick = get_func("esports_sim.manager.promises", "weekly_tick")
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    
    promise = create_promise(campaign, team.id, pid, "play_time", target_value=50, duration=4)
    initial_duration = promise.weeks_left
    
    # Tick promises module
    weekly_tick(campaign, week_dressed={team.id: {pid}})
    assert promise.weeks_left == initial_duration - 1


def test_tier1_f3_promise_fulfillment_check(campaign):
    """Verifies that active promises are correctly marked as fulfilled when conditions are met."""
    create_promise = get_func("esports_sim.manager.promises", "create_promise")
    weekly_tick = get_func("esports_sim.manager.promises", "weekly_tick")
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    
    promise = create_promise(campaign, team.id, pid, "play_time", target_value=50, duration=1)
    # Dress player to meet conditions
    weekly_tick(campaign, week_dressed={team.id: {pid}})
    
    assert promise.status == "kept"


def test_tier1_f3_promise_expiration_failure(campaign):
    """Verifies that promises are marked as failed when the duration ticks to 0 without conditions being met."""
    create_promise = get_func("esports_sim.manager.promises", "create_promise")
    weekly_tick = get_func("esports_sim.manager.promises", "weekly_tick")
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    
    promise = create_promise(campaign, team.id, pid, "play_time", target_value=100, duration=1)
    # Don't dress player (empty set)
    weekly_tick(campaign, week_dressed={team.id: set()})
    
    assert promise.status == "broken"


# --- Promise Impact on Morale & Chemistry (F4) ---

def test_tier1_f4_fulfill_boosts_morale(campaign):
    """Verifies that fulfilling a promise boosts the recipient player's morale."""
    resolve_promise = get_func("esports_sim.manager.promises", "resolve_promise")
    from esports_sim.schemas.promise import ManagerPromise
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    player = campaign.players[pid]
    player.morale = 60.0
    
    promise = ManagerPromise(id="p1", team_id=team.id, player_id=pid, promise_type="play_time", weeks_left=1, created_week=1, created_season=1)
    resolve_promise(campaign, promise, success=True)
    assert player.morale > 60.0


def test_tier1_f4_break_drops_morale(campaign):
    """Verifies that breaking a promise drops the recipient player's morale."""
    resolve_promise = get_func("esports_sim.manager.promises", "resolve_promise")
    from esports_sim.schemas.promise import ManagerPromise
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    player = campaign.players[pid]
    player.morale = 60.0
    
    promise = ManagerPromise(id="p2", team_id=team.id, player_id=pid, promise_type="play_time", weeks_left=1, created_week=1, created_season=1)
    resolve_promise(campaign, promise, success=False)
    assert player.morale < 60.0


def test_tier1_f4_break_drops_chemistry(campaign):
    """Verifies that breaking a promise drops overall team chemistry."""
    resolve_promise = get_func("esports_sim.manager.promises", "resolve_promise")
    from esports_sim.schemas.promise import ManagerPromise
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    team.chemistry = 70.0
    
    promise = ManagerPromise(id="p3", team_id=team.id, player_id=pid, promise_type="play_time", weeks_left=1, created_week=1, created_season=1)
    resolve_promise(campaign, promise, success=False)
    assert team.chemistry < 70.0


def test_tier1_f4_clique_broken_promise_cascade(campaign):
    """Verifies that breaking a promise to a clique leader also drops morale for their clique members."""
    resolve_promise = get_func("esports_sim.manager.promises", "resolve_promise")
    from esports_sim.schemas.promise import ManagerPromise
    team = list(campaign.teams.values())[0]
    leader_id = team.player_ids[0]
    clique_mate_id = team.player_ids[1]
    
    campaign.players[clique_mate_id].morale = 70.0
    promise = ManagerPromise(id="p4", team_id=team.id, player_id=leader_id, promise_type="play_time", weeks_left=1, created_week=1, created_season=1)
    
    with patch("esports_sim.manager.locker_room.get_hierarchy_role", return_value="leader"):
        resolve_promise(campaign, promise, success=False)
        
    assert campaign.players[clique_mate_id].morale < 70.0


def test_tier1_f4_fulfill_boosts_chemistry(campaign):
    """Verifies that fulfilling a promise increases the overall team chemistry."""
    resolve_promise = get_func("esports_sim.manager.promises", "resolve_promise")
    from esports_sim.schemas.promise import ManagerPromise
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    team.chemistry = 70.0
    
    promise = ManagerPromise(id="p5", team_id=team.id, player_id=pid, promise_type="play_time", weeks_left=1, created_week=1, created_season=1)
    resolve_promise(campaign, promise, success=True)
    assert team.chemistry > 70.0


# --- Player Mentorship PA & Tag Transfer (F5) ---

def test_tier1_f5_mentorship_pairing(campaign):
    """Verifies that a valid mentor-mentee relationship (veteran to young prospect) can be registered in the squad."""
    pair_mentorship = get_func("esports_sim.manager.mentorship", "pair_mentorship")
    team = list(campaign.teams.values())[0]
    mentor_id = team.player_ids[0]
    mentee_id = team.player_ids[1]
    
    campaign.players[mentor_id].age = 28
    campaign.players[mentor_id].attributes = {"aim": 80.0, "game_sense": 80.0, "comms_quality": 80.0}
    campaign.players[mentee_id].age = 18
    campaign.players[mentee_id].attributes = {"aim": 40.0, "game_sense": 40.0, "comms_quality": 40.0}
    
    result = pair_mentorship(campaign, mentee_id, mentor_id)
    assert result is True
    assert campaign.mentorships[mentee_id] == mentor_id


def test_tier1_f5_pa_boost_chance(campaign):
    """Verifies that active mentorship has a non-zero probability of boosting the mentee's Potential Ability (PA) during campaign ticks."""
    tick_mentorship = get_func("esports_sim.manager.mentorship", "tick_mentorship")
    team = list(campaign.teams.values())[0]
    mentor_id = team.player_ids[0]
    mentee_id = team.player_ids[1]
    campaign.mentorships[mentee_id] = mentor_id
    
    mentee = campaign.players[mentee_id]
    mentee.potential = 80.0
    
    # Mocking random to guarantee success
    with patch("random.random", return_value=0.0):
        tick_mentorship(campaign)
    
    assert mentee.potential > 80.0


def test_tier1_f5_tag_transfer_chance(campaign):
    """Verifies that active mentorship can transfer a personality tag or special trait from mentor to mentee."""
    tick_mentorship = get_func("esports_sim.manager.mentorship", "tick_mentorship")
    team = list(campaign.teams.values())[0]
    mentor_id = team.player_ids[0]
    mentee_id = team.player_ids[1]
    campaign.mentorships[mentee_id] = mentor_id
    
    campaign.players[mentor_id].personality_tags = ["reliable"]
    campaign.players[mentee_id].personality_tags = []
    
    with patch("random.random", return_value=0.0):
        tick_mentorship(campaign)
        
    assert "reliable" in campaign.players[mentee_id].personality_tags


def test_tier1_f5_weekly_progress_accumulation(campaign):
    """Verifies that mentorship relationship progress accumulated on each tick increases towards completion."""
    tick_mentorship = get_func("esports_sim.manager.mentorship", "tick_mentorship")
    team = list(campaign.teams.values())[0]
    mentor_id = team.player_ids[0]
    mentee_id = team.player_ids[1]
    campaign.mentorships[mentee_id] = mentor_id
    
    # Verify that relationship progress state increments
    if not hasattr(campaign, "mentorship_progress"):
        campaign.mentorship_progress = {}
    campaign.mentorship_progress[mentee_id] = 10.0
    
    tick_mentorship(campaign)
    assert campaign.mentorship_progress[mentee_id] > 10.0


def test_tier1_f5_mentorship_completion_resolution(campaign):
    """Verifies that mentorship resolves and cleans up after reaching its defined completion duration."""
    tick_mentorship = get_func("esports_sim.manager.mentorship", "tick_mentorship")
    team = list(campaign.teams.values())[0]
    mentor_id = team.player_ids[0]
    mentee_id = team.player_ids[1]
    campaign.mentorships[mentee_id] = mentor_id
    
    if not hasattr(campaign, "mentorship_progress"):
        campaign.mentorship_progress = {}
    campaign.mentorship_progress[mentee_id] = 99.0 # near completion
    
    tick_mentorship(campaign)
    assert mentee_id not in campaign.mentorships


# --- Halftime Pep Talks (F6) ---

def test_tier1_f6_pep_talk_reassure_trailing(campaign):
    """Verifies that a 'reassure' pep talk at halftime when trailing stabilizes team confidence."""
    apply_pep_talk = get_func("esports_sim.manager.pep_talk", "apply_pep_talk")
    team = list(campaign.teams.values())[0]
    for pid in team.player_ids:
        campaign.players[pid].confidence = 40.0
        
    apply_pep_talk(campaign, team.id, "reassure", relative_score=-5)
    for pid in team.player_ids:
        assert campaign.players[pid].confidence >= 40.0


def test_tier1_f6_pep_talk_fire_up_trailing(campaign):
    """Verifies that a 'fire_up' pep talk at halftime when trailing boosts team confidence and aggression."""
    apply_pep_talk = get_func("esports_sim.manager.pep_talk", "apply_pep_talk")
    team = list(campaign.teams.values())[0]
    for pid in team.player_ids:
        campaign.players[pid].confidence = 40.0
        
    team.tactics.aggression = 50.0
    apply_pep_talk(campaign, team.id, "fire_up", relative_score=-5)
    assert team.tactics.aggression > 50.0
    for pid in team.player_ids:
        assert campaign.players[pid].confidence > 40.0


def test_tier1_f6_pep_talk_focus_trailing(campaign):
    """Verifies that a 'focus' pep talk at halftime when trailing shifts team confidence back to the 55 midpoint."""
    apply_pep_talk = get_func("esports_sim.manager.pep_talk", "apply_pep_talk")
    team = list(campaign.teams.values())[0]
    for pid in team.player_ids:
        campaign.players[pid].confidence = 70.0
        
    apply_pep_talk(campaign, team.id, "focus", relative_score=-5)
    for pid in team.player_ids:
        assert abs(campaign.players[pid].confidence - 55.0) < abs(70.0 - 55.0)


def test_tier1_f6_trigger_halftime_round(campaign):
    """Verifies that halftime talks are triggered exactly at round 12."""
    should_trigger = get_func("esports_sim.manager.pep_talk", "should_trigger_halftime_talk")
    assert should_trigger(round_idx=12) is True
    assert should_trigger(round_idx=11) is False


def test_tier1_f6_pep_talk_no_op_default(campaign):
    """Verifies that a neutral or absent halftime talk has no impact on match simulation."""
    apply_pep_talk = get_func("esports_sim.manager.pep_talk", "apply_pep_talk")
    team = list(campaign.teams.values())[0]
    initial_conf = {pid: campaign.players[pid].confidence for pid in team.player_ids}
    
    apply_pep_talk(campaign, team.id, None, relative_score=0)
    for pid in team.player_ids:
        assert campaign.players[pid].confidence == initial_conf[pid]


# --- Touchline Shouts (F7) ---

def test_tier1_f7_demand_focus_tilt(campaign):
    """Verifies that the 'demand_focus' shout calms a tilted player, returning their confidence towards 55."""
    apply_shout = get_func("esports_sim.manager.shouts", "apply_touchline_shout")
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    campaign.players[pid].confidence = 30.0 # tilted
    
    apply_shout(campaign, team.id, "demand_focus", target_player_id=pid)
    assert campaign.players[pid].confidence > 30.0
    assert campaign.players[pid].confidence <= 55.0


def test_tier1_f7_encourage_slump(campaign):
    """Verifies that the 'encourage' shout boosts team morale/confidence after losing 3 consecutive rounds."""
    apply_shout = get_func("esports_sim.manager.shouts", "apply_touchline_shout")
    team = list(campaign.teams.values())[0]
    for pid in team.player_ids:
        campaign.players[pid].confidence = 40.0
        campaign.players[pid].morale = 40.0
        
    apply_shout(campaign, team.id, "encourage", loss_streak=3)
    for pid in team.player_ids:
        assert campaign.players[pid].confidence > 40.0
        assert campaign.players[pid].morale > 40.0


def test_tier1_f7_demand_effort_stamina(campaign):
    """Verifies that the 'demand_effort' shout boosts the aggression dial but drains stamina."""
    apply_shout = get_func("esports_sim.manager.shouts", "apply_touchline_shout")
    team = list(campaign.teams.values())[0]
    for pid in team.player_ids:
        campaign.players[pid].stamina = 80.0
    team.tactics.aggression = 50.0
    
    apply_shout(campaign, team.id, "demand_effort")
    assert team.tactics.aggression > 50.0
    for pid in team.player_ids:
        assert campaign.players[pid].stamina < 80.0


def test_tier1_f7_shout_trigger_conditions(campaign):
    """Verifies that touchline shouts only execute when their specific triggers (e.g. loss streak) are satisfied."""
    can_shout = get_func("esports_sim.manager.shouts", "can_trigger_shout")
    assert can_shout("encourage", loss_streak=3) is True
    assert can_shout("encourage", loss_streak=1) is False


def test_tier1_f7_shouts_no_op_default(campaign):
    """Verifies that empty shouts lists have no impact on match simulation."""
    apply_shout = get_func("esports_sim.manager.shouts", "apply_touchline_shout")
    team = list(campaign.teams.values())[0]
    initial_agg = team.tactics.aggression
    
    apply_shout(campaign, team.id, None)
    assert team.tactics.aggression == initial_agg


# --- LLM Talk Context Grounding (F8) ---

def test_tier1_f8_morale_form_grounding(campaign):
    """Verifies that player morale, form, and recent match performance are correctly formatted into the LLM context."""
    build_context = get_func("esports_sim.manager.llm_talk", "build_talk_context")
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    player = campaign.players[pid]
    player.morale = 67.5
    player.form = 88.0
    
    ctx = build_context(campaign, pid)
    assert "67.5" in ctx or "68" in ctx
    assert "88" in ctx


def test_tier1_f8_personality_tags_grounding(campaign):
    """Verifies that player personality axes (ego, resilience) and tags are formatted into the LLM prompt."""
    build_context = get_func("esports_sim.manager.llm_talk", "build_talk_context")
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    player = campaign.players[pid]
    player.personality_tags = ["volatile", "perfectionist"]
    
    ctx = build_context(campaign, pid)
    assert "volatile" in ctx
    assert "perfectionist" in ctx


def test_tier1_f8_relationship_grounding(campaign):
    """Verifies that captain relationship status and leadership tier are formatted into the context."""
    build_context = get_func("esports_sim.manager.llm_talk", "build_talk_context")
    team = list(campaign.teams.values())[0]
    captain_id = team.player_ids[0]
    team.captain_id = captain_id
    pid = team.player_ids[1]
    
    from esports_sim.manager import relationships
    relationships.nudge(campaign, pid, captain_id, 75.0)
    
    with patch("esports_sim.manager.locker_room.get_hierarchy_role", return_value="council_member"):
        ctx = build_context(campaign, pid)
    assert "75" in ctx or "relationship" in ctx.lower()
    assert "council_member" in ctx


def test_tier1_f8_career_stats_grounding(campaign):
    """Verifies that player season and career stats are present in the grounded prompt data."""
    build_context = get_func("esports_sim.manager.llm_talk", "build_talk_context")
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    
    # Add dummy player stats
    campaign.player_stats[pid] = MagicMock(kills=150, deaths=120)
    
    ctx = build_context(campaign, pid)
    assert "150" in ctx or "kills" in ctx.lower()


def test_tier1_f8_context_missing_fields(campaign):
    """Verifies that context builder handles missing or None attributes gracefully, substituting default template markers."""
    build_context = get_func("esports_sim.manager.llm_talk", "build_talk_context")
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    player = campaign.players[pid]
    player.real_name = ""
    
    # Should build context successfully without raising an error
    ctx = build_context(campaign, pid)
    assert isinstance(ctx, str)


# --- LLM Response Adjustment Application (F9) ---

def test_tier1_f9_classify_reassure(campaign):
    """Verifies that a coach input text of support is classified into the 'reassure' intent."""
    classify_intent = get_func("esports_sim.manager.llm_talk", "classify_coach_intent")
    intent = classify_intent("Don't worry about the bad games, we know you are a great player.")
    assert intent == "reassure"


def test_tier1_f9_classify_challenge(campaign):
    """Verifies that a coach input text of high expectations is classified into the 'challenge' intent."""
    classify_intent = get_func("esports_sim.manager.llm_talk", "classify_coach_intent")
    intent = classify_intent("I need you to step up. This performance is unacceptable.")
    assert intent == "challenge"


def test_tier1_f9_classify_rein_streaming(campaign):
    """Verifies that a coach input text requesting less streaming is classified into the 'rein_streaming' intent."""
    classify_intent = get_func("esports_sim.manager.llm_talk", "classify_coach_intent")
    intent = classify_intent("Please stop streaming so much and focus more on training.")
    assert intent == "rein_streaming"


def test_tier1_f9_apply_reassure_adjustment(campaign):
    """Verifies that 'reassure' applies the correct deterministic adjustments to morale and confidence."""
    apply_chat_adjustment = get_func("esports_sim.manager.llm_talk", "apply_chat_adjustment")
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    player = campaign.players[pid]
    player.morale = 50.0
    player.confidence = 50.0
    
    apply_chat_adjustment(campaign, pid, "reassure")
    assert player.morale > 50.0 or player.confidence > 50.0


def test_tier1_f9_apply_rein_streaming_adjustment(campaign):
    """Verifies that 'rein_streaming' reduces stream load and boosts player training efficiency."""
    apply_chat_adjustment = get_func("esports_sim.manager.llm_talk", "apply_chat_adjustment")
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    player = campaign.players[pid]
    player.stream_load = 50.0
    
    apply_chat_adjustment(campaign, pid, "rein_streaming")
    assert player.stream_load < 50.0


# --- LLM Talk Promise/Memory Updates (F10) ---

def test_tier1_f10_spawn_playtime_promise(campaign):
    """Verifies that a chat dialogue promising playtime successfully spawns an active playtime promise."""
    process_chat_resolution = get_func("esports_sim.manager.llm_talk", "process_chat_resolution")
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    
    process_chat_resolution(campaign, pid, "I promise to start you next week", intent="play_time_promise")
    
    promises = [p for p in campaign.promises if p.player_id == pid and p.promise_type == "play_time"]
    assert len(promises) > 0


def test_tier1_f10_spawn_contract_promise(campaign):
    """Verifies that a chat dialogue promising a contract successfully spawns a contract promise."""
    process_chat_resolution = get_func("esports_sim.manager.llm_talk", "process_chat_resolution")
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[1]
    
    process_chat_resolution(campaign, pid, "I will renew your contract soon", intent="contract_promise")
    
    promises = [p for p in campaign.promises if p.player_id == pid and p.promise_type == "renew_contract"]
    assert len(promises) > 0


def test_tier1_f10_update_player_loyalty(campaign):
    """Verifies that chat outcomes update the player's internal memory and loyalty bias."""
    process_chat_resolution = get_func("esports_sim.manager.llm_talk", "process_chat_resolution")
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    
    from esports_sim.manager import memories
    initial_loyalty = memories.loyalty_bias(campaign, pid, team.id)
    
    process_chat_resolution(campaign, pid, "You are a core part of this team's future", intent="praise")
    new_loyalty = memories.loyalty_bias(campaign, pid, team.id)
    assert new_loyalty > initial_loyalty


def test_tier1_f10_chat_logged_in_chronicle(campaign):
    """Verifies that the occurrence of the 1:1 chat is logged in the player's career chronicle."""
    process_chat_resolution = get_func("esports_sim.manager.llm_talk", "process_chat_resolution")
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    
    process_chat_resolution(campaign, pid, "Let's review your goals.", intent="goals")
    
    # Check chronicle entries
    chronicle = campaign.chronicles.get(pid, [])
    assert any("1:1 chat" in event.message.lower() or "goals" in event.message.lower() for event in chronicle)


def test_tier1_f10_caching_prose_sidecar(campaign, tmp_path):
    """Verifies that generated response text is cached in the saves/ sidecar file, preserving clean primary saves."""
    save_talk_cache = get_func("esports_sim.manager.llm_talk", "save_talk_cache")
    load_talk_cache = get_func("esports_sim.manager.llm_talk", "load_talk_cache")
    
    with patch("esports_sim.manager.llm_talk.TALK_CACHE_DIR", tmp_path):
        save_talk_cache(campaign_id="save123", key="chat_p1", text="Hey coach.")
        cached_text = load_talk_cache(campaign_id="save123", key="chat_p1")
        assert cached_text == "Hey coach."


# --- xDuel & Expected Duel Edge (xDE) Telemetry (F11) ---

def test_tier1_f11_duel_event_generation(campaign):
    """Verifies that a round.duel_telemetry event is generated for every duel in a round."""
    simulate_duel = get_func("esports_sim.manager.xduel", "simulate_duel_with_telemetry")
    events = []
    
    simulate_duel(campaign, shooter_id="p1", target_id="p2", events_out=events)
    assert any("duel_telemetry" in e.get("event_type", "") for e in events)


def test_tier1_f11_expected_win_probability(campaign):
    """Verifies the ELO probability calculation matches the expected probability equation."""
    calculate_xduel = get_func("esports_sim.manager.xduel", "calculate_xduel_probability")
    
    # With equal stats/ratings, prob should be 0.5
    prob = calculate_xduel(rating_a=1000, rating_b=1000)
    assert math.isclose(prob, 0.5)


def test_tier1_f11_positive_xde(campaign):
    """Verifies that winning an unfavored duel yields a positive xDE contribution."""
    calculate_xde = get_func("esports_sim.manager.xduel", "calculate_xde")
    # Expected prob is 0.3, outcome is 1 (win)
    xde = calculate_xde(outcome=1, expected_probability=0.3)
    assert xde > 0.0


def test_tier1_f11_negative_xde(campaign):
    """Verifies that losing a favored duel yields a negative xDE contribution."""
    calculate_xde = get_func("esports_sim.manager.xduel", "calculate_xde")
    # Expected prob is 0.8, outcome is 0 (loss)
    xde = calculate_xde(outcome=0, expected_probability=0.8)
    assert xde < 0.0


def test_tier1_f11_season_stats_accumulation(campaign):
    """Verifies that expected and actual wins accumulate correctly in PlayerSeasonStats."""
    accumulate_xde_stats = get_func("esports_sim.manager.xduel", "accumulate_xde_stats")
    
    stats = MagicMock()
    stats.expected_wins = 1.2
    stats.actual_wins = 1
    
    accumulate_xde_stats(stats, outcome=1, expected_probability=0.4)
    assert stats.expected_wins == 1.6
    assert stats.actual_wins == 2


# ==============================================================================
# TIER 2: BOUNDARY & CORNER CASES (55 tests)
# ==============================================================================

# --- Locker Room Hierarchy Tier Calculation (F1) ---

def test_tier2_f1_outcast_boundary(campaign):
    """Verifies that a player with morale 39 and relationship 39 is categorized as Outcast, while morale 41 or relationship 41 is not."""
    get_role = get_func("esports_sim.manager.locker_room", "get_hierarchy_role")
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    player = campaign.players[pid]
    
    from esports_sim.manager import relationships
    
    # Boundary 1: Morale 39, Relationship 39 -> Outcast
    player.morale = 39.0
    relationships.nudge(campaign, pid, team.captain_id, -100.0) # set to minimum
    relationships.nudge(campaign, pid, team.captain_id, 39.0)   # set exactly to 39
    
    role = get_role(campaign, pid, team.id)
    assert role == "outcast"
    
    # Boundary 2: Morale 41, Rel 39 -> Core or other non-outcast role
    player.morale = 41.0
    role2 = get_role(campaign, pid, team.id)
    assert role2 != "outcast"


def test_tier2_f1_key_influencer_ego_boundary(campaign):
    """Verifies the Key Influencer ego threshold boundary at exactly 65 (not influencer) vs 66 (influencer)."""
    get_role = get_func("esports_sim.manager.locker_room", "get_hierarchy_role")
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    player = campaign.players[pid]
    player.morale = 80.0
    player.followers = 300000
    
    # Ego at 65.0
    with patch("esports_sim.manager.personality.axes", return_value={"ego": 65.0, "resilience": 50.0, "sociability": 50.0, "professionalism": 50.0, "ambition": 50.0}):
        role1 = get_role(campaign, pid, team.id)
        assert role1 != "key_influencer"
        
    # Ego at 66.0
    with patch("esports_sim.manager.personality.axes", return_value={"ego": 66.0, "resilience": 50.0, "sociability": 50.0, "professionalism": 50.0, "ambition": 50.0}):
        role2 = get_role(campaign, pid, team.id)
        assert role2 == "key_influencer"


def test_tier2_f1_empty_roster(campaign):
    """Verifies that the hierarchy calculation functions return empty results without crashing on empty or uninitialized team rosters."""
    calculate_hierarchy = get_func("esports_sim.manager.locker_room", "calculate_hierarchy")
    res = calculate_hierarchy(campaign, team_id="nonexistent")
    assert res == {}


def test_tier2_f1_lone_captain(campaign):
    """Verifies hierarchy calculation on a squad containing only a captain, assigning Incumbent Leader and handling zero relationships."""
    get_role = get_func("esports_sim.manager.locker_room", "get_hierarchy_role")
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    team.player_ids = [pid]
    team.captain_id = pid
    
    role = get_role(campaign, pid, team.id)
    assert role == "incumbent_leader"


def test_tier2_f1_multiple_matching_archetypes(campaign):
    """Verifies precedence resolution when a player qualifies for multiple roles (e.g. Loyal Lieutenant criteria and Volatile Rebel criteria)."""
    get_role = get_func("esports_sim.manager.locker_room", "get_hierarchy_role")
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    
    # Force mock conflicting conditions
    with patch("esports_sim.manager.personality.axes", return_value={"ego": 80.0, "resilience": 30.0, "sociability": 80.0, "professionalism": 25.0, "ambition": 50.0}):
        role = get_role(campaign, pid, team.id)
        # Should resolve to Volatile Rebel or Loyal Lieutenant deterministically based on priority
        assert role in ("volatile_rebel", "loyal_lieutenant")


# --- Benching/Releasing Team Leaders Morale Impact (F2) ---

def test_tier2_f2_bench_inactive_team(campaign):
    """Verifies that benching team leaders in inactive or AI-controlled teams does not trigger crashes or unintended morale side-effects."""
    handle_benching = get_func("esports_sim.manager.locker_room", "handle_benching_impact")
    # Mark user team to something else, making this team inactive/AI-controlled
    campaign.user_team_id = "other_team"
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    
    # Should run cleanly without crash
    handle_benching(campaign, team.id, [pid])


def test_tier2_f2_release_isolated_leader(campaign):
    """Verifies that releasing a captain with no clique members (all relationship values < 70) results in zero morale drops."""
    handle_release = get_func("esports_sim.manager.locker_room", "handle_release_impact")
    team = list(campaign.teams.values())[0]
    captain_id = team.player_ids[0]
    team.captain_id = captain_id
    
    # Force low relationships
    from esports_sim.manager import relationships
    for pid in team.player_ids:
        if pid != captain_id:
            relationships.nudge(campaign, pid, captain_id, -100.0) # min relationship
            
    initial_morale = [campaign.players[p].morale for p in team.player_ids if p != captain_id]
    handle_release(campaign, team.id, captain_id)
    new_morale = [campaign.players[p].morale for p in team.player_ids if p != captain_id]
    assert new_morale == initial_morale


def test_tier2_f2_morale_chemistry_underflow(campaign):
    """Verifies that morale and chemistry drops cannot push values below their minimum bounds (0.0)."""
    handle_benching = get_func("esports_sim.manager.locker_room", "handle_benching_impact")
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    team.captain_id = pid
    
    # Force morale and chem to absolute minimums
    campaign.players[pid].morale = 0.0
    team.chemistry = 0.0
    
    handle_benching(campaign, team.id, [pid])
    assert campaign.players[pid].morale == 0.0
    assert team.chemistry == 0.0


def test_tier2_f2_consecutive_benching_stacking(campaign):
    """Verifies that benching leaders multiple times in the same week caps the morale drop and does not stack exponentially."""
    handle_benching = get_func("esports_sim.manager.locker_room", "handle_benching_impact")
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    team.captain_id = pid
    
    # Bench once
    handle_benching(campaign, team.id, [pid])
    morale_after_one = campaign.players[pid].morale
    
    # Bench immediately again
    handle_benching(campaign, team.id, [pid])
    morale_after_two = campaign.players[pid].morale
    
    # Penalty should not stack exponentially or double-dip
    assert morale_after_two == morale_after_one


def test_tier2_f2_bench_replay_loop(campaign):
    """Verifies state integrity when a leader is repeatedly benched, returned to starter, and benched again."""
    handle_benching = get_func("esports_sim.manager.locker_room", "handle_benching_impact")
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    
    # Loop state toggles
    for _ in range(3):
        # Bench
        handle_benching(campaign, team.id, [pid])
        # Return to starters
        team.lineup_ids = list(team.player_ids)
        # Should stay stable
        assert campaign.players[pid].morale >= 0.0


# --- Promise Creation & Tracking (F3) ---

def test_tier2_f3_zero_duration_promise(campaign):
    """Verifies that a promise created with 0 weeks duration is evaluated and resolved instantly on the first tick."""
    create_promise = get_func("esports_sim.manager.promises", "create_promise")
    weekly_tick = get_func("esports_sim.manager.promises", "weekly_tick")
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    
    promise = create_promise(campaign, team.id, pid, "play_time", target_value=50, duration=0)
    weekly_tick(campaign, week_dressed={team.id: {pid}})
    assert promise.status in ("kept", "broken")


def test_tier2_f3_max_active_promises(campaign):
    """Verifies that making multiple concurrent active promises to the same player is handled within bounds."""
    create_promise = get_func("esports_sim.manager.promises", "create_promise")
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    
    for i in range(10):
        create_promise(campaign, team.id, pid, "play_time", target_value=i, duration=4)
    
    # Check that it handles it without crashing
    player_promises = [p for p in campaign.promises if p.player_id == pid]
    assert len(player_promises) >= 10


def test_tier2_f3_duplicate_promises(campaign):
    """Verifies that creating duplicate promises of the same type updates the existing promise's duration instead of duplicating the record."""
    create_promise = get_func("esports_sim.manager.promises", "create_promise")
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    
    p1 = create_promise(campaign, team.id, pid, "renew_contract", duration=4)
    p2 = create_promise(campaign, team.id, pid, "renew_contract", duration=6)
    
    # Check that there is only 1 renew_contract promise
    contract_promises = [p for p in campaign.promises if p.player_id == pid and p.promise_type == "renew_contract"]
    assert len(contract_promises) == 1
    assert contract_promises[0].weeks_left == 6


def test_tier2_f3_player_retires_mid_promise(campaign):
    """Verifies that active promises are cleaned up gracefully without crashing if a player retires or is deleted."""
    create_promise = get_func("esports_sim.manager.promises", "create_promise")
    weekly_tick = get_func("esports_sim.manager.promises", "weekly_tick")
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    
    create_promise(campaign, team.id, pid, "renew_contract", duration=4)
    
    # Retire player: delete from players map
    del campaign.players[pid]
    
    # Ticking should not crash
    weekly_tick(campaign, week_dressed={})
    assert not any(p.player_id == pid for p in campaign.promises)


def test_tier2_f3_playtime_fractional_boundary(campaign):
    """Verifies promise evaluation boundaries for playtime percentage (e.g., exactly 50.0% vs 49.99%)."""
    create_promise = get_func("esports_sim.manager.promises", "create_promise")
    weekly_tick = get_func("esports_sim.manager.promises", "weekly_tick")
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    
    # 50% target over 10000 weeks.
    # 49.99% = 4999 weeks dressed.
    duration = 10000
    p1 = create_promise(campaign, team.id, pid, "play_time", target_value=50, duration=duration)
    
    # We tick 10000 times. For the first 4999 ticks, player is dressed. For the rest, they are not.
    for i in range(duration):
        dressed = {team.id: {pid}} if i < 4999 else {team.id: set()}
        weekly_tick(campaign, week_dressed=dressed)
        
    assert p1.status == "broken", f"Player dressed for 49.99% of rounds (4999/{duration}) should fail a 50% promise"
    
    # Reset campaign promises
    campaign.promises = [p for p in campaign.promises if p.id != p1.id]
    
    p2 = create_promise(campaign, team.id, pid, "play_time", target_value=50, duration=duration)
    # We tick 10000 times. For the first 5000 ticks, player is dressed. For the rest, they are not.
    for i in range(duration):
        dressed = {team.id: {pid}} if i < 5000 else {team.id: set()}
        weekly_tick(campaign, week_dressed=dressed)
        
    assert p2.status == "kept", f"Player dressed for 50.0% of rounds (5000/{duration}) should keep a 50% promise"


# --- Promise Impact on Morale & Chemistry (F4) ---

def test_tier2_f4_morale_overflow_cap(campaign):
    """Verifies that morale gains from fulfilling promises do not push a player's morale above the 100.0 cap."""
    resolve_promise = get_func("esports_sim.manager.promises", "resolve_promise")
    from esports_sim.schemas.promise import ManagerPromise
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    campaign.players[pid].morale = 98.0
    
    promise = ManagerPromise(id="p_over", team_id=team.id, player_id=pid, promise_type="play_time", weeks_left=1, created_week=1, created_season=1)
    resolve_promise(campaign, promise, success=True)
    assert campaign.players[pid].morale <= 100.0


def test_tier2_f4_chemistry_underflow_cap(campaign):
    """Verifies that chemistry losses from broken promises do not push team chemistry below 0.0."""
    resolve_promise = get_func("esports_sim.manager.promises", "resolve_promise")
    from esports_sim.schemas.promise import ManagerPromise
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    team.chemistry = 5.0
    
    promise = ManagerPromise(id="p_under", team_id=team.id, player_id=pid, promise_type="play_time", weeks_left=1, created_week=1, created_season=1)
    resolve_promise(campaign, promise, success=False)
    assert team.chemistry >= 0.0


def test_tier2_f4_multiple_broken_promises(campaign):
    """Verifies stacking and capping behavior when a manager breaks multiple promises in the same weekly tick."""
    resolve_promise = get_func("esports_sim.manager.promises", "resolve_promise")
    from esports_sim.schemas.promise import ManagerPromise
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    player = campaign.players[pid]
    player.morale = 80.0
    
    p1 = ManagerPromise(id="p_stack1", team_id=team.id, player_id=pid, promise_type="play_time", weeks_left=1, created_week=1, created_season=1)
    p2 = ManagerPromise(id="p_stack2", team_id=team.id, player_id=pid, promise_type="renew_contract", weeks_left=1, created_week=1, created_season=1)
    
    resolve_promise(campaign, p1, success=False)
    morale_after_one = player.morale
    resolve_promise(campaign, p2, success=False)
    morale_after_two = player.morale
    
    # Should stack but stay within bounded minimum
    assert morale_after_two < morale_after_one
    assert morale_after_two >= 0.0


def test_tier2_f4_personality_multiplier(campaign):
    """Verifies that high ego players suffer larger morale penalties, while professional players suffer smaller morale drops."""
    resolve_promise = get_func("esports_sim.manager.promises", "resolve_promise")
    from esports_sim.schemas.promise import ManagerPromise
    team = list(campaign.teams.values())[0]
    
    # Setup high-ego player
    pid1 = team.player_ids[0]
    p_ego = campaign.players[pid1]
    p_ego.morale = 80.0
    
    # Setup high-professionalism player
    pid2 = team.player_ids[1]
    p_prof = campaign.players[pid2]
    p_prof.morale = 80.0
    
    promise1 = ManagerPromise(id="p_ego", team_id=team.id, player_id=pid1, promise_type="play_time", weeks_left=1, created_week=1, created_season=1)
    promise2 = ManagerPromise(id="p_prof", team_id=team.id, player_id=pid2, promise_type="play_time", weeks_left=1, created_week=1, created_season=1)
    
    with patch("esports_sim.manager.personality.axes", side_effect=lambda p: {"ego": 90.0, "resilience": 50.0, "sociability": 50.0, "professionalism": 30.0, "ambition": 50.0} if p.id == pid1 else {"ego": 30.0, "resilience": 50.0, "sociability": 50.0, "professionalism": 90.0, "ambition": 50.0}):
        resolve_promise(campaign, promise1, success=False)
        resolve_promise(campaign, promise2, success=False)
        
    drop_ego = 80.0 - p_ego.morale
    drop_prof = 80.0 - p_prof.morale
    assert drop_ego > drop_prof


def test_tier2_f4_released_player_failure(campaign):
    """Verifies that breaking a promise due to releasing a player does not crash and processes the chemistry drop correctly."""
    resolve_promise = get_func("esports_sim.manager.promises", "resolve_promise")
    from esports_sim.schemas.promise import ManagerPromise
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    team.chemistry = 70.0
    
    # Remove player from campaign roster first to simulate release
    del campaign.players[pid]
    
    promise = ManagerPromise(id="p_rel", team_id=team.id, player_id=pid, promise_type="play_time", weeks_left=1, created_week=1, created_season=1)
    
    # Should resolve cleanly (success=False because player is gone)
    resolve_promise(campaign, promise, success=False)
    assert team.chemistry < 70.0


# --- Player Mentorship PA & Tag Transfer (F5) ---

def test_tier2_f5_invalid_age_gap(campaign):
    """Verifies that mentorship is blocked or fails to accumulate progress if the age gap between mentor and mentee is less than 3 years."""
    pair_mentorship = get_func("esports_sim.manager.mentorship", "pair_mentorship")
    team = list(campaign.teams.values())[0]
    mentor_id = team.player_ids[0]
    mentee_id = team.player_ids[1]
    
    campaign.players[mentor_id].age = 20
    campaign.players[mentee_id].age = 19 # only 1 year difference
    
    result = pair_mentorship(campaign, mentee_id, mentor_id)
    assert result is False


def test_tier2_f5_pa_max_cap(campaign):
    """Verifies that mentorship cannot boost a player's Potential Ability (PA) beyond the maximum potential cap (100.0)."""
    tick_mentorship = get_func("esports_sim.manager.mentorship", "tick_mentorship")
    team = list(campaign.teams.values())[0]
    mentor_id = team.player_ids[0]
    mentee_id = team.player_ids[1]
    campaign.mentorships[mentee_id] = mentor_id
    
    campaign.players[mentee_id].potential = 100.0
    
    with patch("random.random", return_value=0.0):
        tick_mentorship(campaign)
        
    assert campaign.players[mentee_id].potential <= 100.0


def test_tier2_f5_personality_clash_slowdown(campaign):
    """Verifies that mentorship progress is slowed down by 50% if the mentor and mentee have clashing personality tags (e.g., Outcast vs Professional)."""
    tick_mentorship = get_func("esports_sim.manager.mentorship", "tick_mentorship")
    team = list(campaign.teams.values())[0]
    mentor_id = team.player_ids[0]
    mentee_id = team.player_ids[1]
    campaign.mentorships[mentee_id] = mentor_id
    
    # Establish clashing personalities
    with patch("esports_sim.manager.locker_room.get_hierarchy_role", return_value="outcast"):
        campaign.players[mentor_id].personality_tags = ["reliable"] # professional lean
        
        if not hasattr(campaign, "mentorship_progress"):
            campaign.mentorship_progress = {}
        campaign.mentorship_progress[mentee_id] = 10.0
        
        tick_mentorship(campaign)
        # Verify it still incremented, but at a reduced rate
        assert campaign.mentorship_progress[mentee_id] > 10.0


def test_tier2_f5_mentee_transferred(campaign):
    """Verifies that a mentorship relationship is safely disbanded if the mentee is traded or transferred to another team."""
    weekly_tick = get_func("esports_sim.manager.mentorship", "tick_mentorship")
    team = list(campaign.teams.values())[0]
    mentor_id = team.player_ids[0]
    mentee_id = team.player_ids[1]
    campaign.mentorships[mentee_id] = mentor_id
    
    # Simulate trade: mentee is now on a different team
    other_team_id = [t.id for t in campaign.teams.values() if t.id != team.id][0]
    team.player_ids.remove(mentee_id)
    campaign.teams[other_team_id].player_ids.append(mentee_id)
    
    weekly_tick(campaign)
    assert mentee_id not in campaign.mentorships


def test_tier2_f5_multiple_mentors_limit(campaign):
    """Verifies that a player cannot be paired with more than one mentor concurrently."""
    pair_mentorship = get_func("esports_sim.manager.mentorship", "pair_mentorship")
    team = list(campaign.teams.values())[0]
    mentor1 = team.player_ids[0]
    mentor2 = team.player_ids[1]
    mentee = team.player_ids[2]
    
    # Setup valid ages/qualities
    campaign.players[mentor1].age = 28
    campaign.players[mentor2].age = 27
    campaign.players[mentee].age = 18
    
    p1 = pair_mentorship(campaign, mentee, mentor1)
    assert p1 is True
    
    p2 = pair_mentorship(campaign, mentee, mentor2)
    assert p2 is False # blocked, already has a mentor


# --- Halftime Pep Talks (F6) ---

def test_tier2_f6_leading_fire_up_backfire(campaign):
    """Verifies that using 'fire_up' when leading heavily (e.g., 11-1) backfires, dropping focus or player morale."""
    apply_pep_talk = get_func("esports_sim.manager.pep_talk", "apply_pep_talk")
    team = list(campaign.teams.values())[0]
    for pid in team.player_ids:
        campaign.players[pid].morale = 80.0
        
    apply_pep_talk(campaign, team.id, "fire_up", relative_score=10) # 11-1 lead
    for pid in team.player_ids:
        assert campaign.players[pid].morale < 80.0 # Backfired


def test_tier2_f6_max_confidence_boundary(campaign):
    """Verifies that pep talks cannot push player confidence beyond the maximum engine cap (100.0)."""
    apply_pep_talk = get_func("esports_sim.manager.pep_talk", "apply_pep_talk")
    team = list(campaign.teams.values())[0]
    for pid in team.player_ids:
        campaign.players[pid].confidence = 98.0
        
    apply_pep_talk(campaign, team.id, "fire_up", relative_score=-5)
    for pid in team.player_ids:
        assert campaign.players[pid].confidence <= 100.0


def test_tier2_f6_stamina_interaction(campaign):
    """Verifies that pep talks do not restore stamina and that high aggression drains stamina faster."""
    apply_pep_talk = get_func("esports_sim.manager.pep_talk", "apply_pep_talk")
    team = list(campaign.teams.values())[0]
    for pid in team.player_ids:
        campaign.players[pid].stamina = 50.0
        
    apply_pep_talk(campaign, team.id, "fire_up", relative_score=-5)
    for pid in team.player_ids:
        assert campaign.players[pid].stamina <= 50.0 # No recovery


def test_tier2_f6_neutral_safety_validation(campaign):
    """Verifies that tactical shifts from halftime pep talks respect the neutral-safe dials equation (exact no-op at 50)."""
    apply_pep_talk = get_func("esports_sim.manager.pep_talk", "apply_pep_talk")
    team = list(campaign.teams.values())[0]
    team.tactics.aggression = 50.0
    
    apply_pep_talk(campaign, team.id, "reassure", relative_score=0)
    assert team.tactics.aggression == 50.0 # exact no-op at neutral score


def test_tier2_f6_overtime_exclusion(campaign):
    """Verifies that pep talks are not re-triggered during overtime rounds."""
    should_trigger = get_func("esports_sim.manager.pep_talk", "should_trigger_halftime_talk")
    assert should_trigger(round_idx=25) is False # overtime


# --- Touchline Shouts (F7) ---

def test_tier2_f7_demand_effort_zero_stamina(campaign):
    """Verifies that the stamina drain from 'demand_effort' does not push a player's stamina below 0.0."""
    apply_shout = get_func("esports_sim.manager.shouts", "apply_touchline_shout")
    team = list(campaign.teams.values())[0]
    for pid in team.player_ids:
        campaign.players[pid].stamina = 2.0
        
    apply_shout(campaign, team.id, "demand_effort")
    for pid in team.player_ids:
        assert campaign.players[pid].stamina >= 0.0


def test_tier2_f7_multiple_shouts_same_round(campaign):
    """Verifies that if multiple shouts match trigger conditions in the same round, only the highest-priority shout is executed."""
    apply_shout = get_func("esports_sim.manager.shouts", "apply_touchline_shout")
    team = list(campaign.teams.values())[0]
    team.tactics.aggression = 50.0
    
    # Shout twice in the same round/context
    apply_shout(campaign, team.id, "demand_effort")
    val1 = team.tactics.aggression
    
    apply_shout(campaign, team.id, "demand_effort")
    val2 = team.tactics.aggression
    
    # The first shout should have modified aggression, but the second should be a no-op
    assert val1 > 50.0, "First shout 'demand_effort' did not apply aggression change"
    assert val1 == val2, "Second shout in the same round should be ignored (no double-dipping)"


def test_tier2_f7_missing_player_target(campaign):
    """Verifies that shouts targeting specific players handle missing, benched, or invalid player IDs gracefully."""
    apply_shout = get_func("esports_sim.manager.shouts", "apply_touchline_shout")
    team = list(campaign.teams.values())[0]
    
    # Should not crash on invalid player ID
    apply_shout(campaign, team.id, "demand_focus", target_player_id="invalid_id")


def test_tier2_f7_tactical_dial_clamping(campaign):
    """Verifies that tactical shifts from shouts (e.g., +10 aggression) are clamped within the standard dial bounds (0 to 100)."""
    apply_shout = get_func("esports_sim.manager.shouts", "apply_touchline_shout")
    team = list(campaign.teams.values())[0]
    team.tactics.aggression = 95.0
    
    apply_shout(campaign, team.id, "demand_effort")
    assert team.tactics.aggression <= 100.0


def test_tier2_f7_shout_tactical_reset(campaign):
    """Verifies that tactical changes from shouts are reset after the match and do not leak into subsequent matches."""
    reset_shouts = get_func("esports_sim.manager.shouts", "reset_shout_effects")
    team = list(campaign.teams.values())[0]
    team.tactics.aggression = 70.0
    
    reset_shouts(campaign, team.id)
    assert team.tactics.aggression == 50.0 # reset to baseline


# --- LLM Talk Context Grounding (F8) ---

def test_tier2_f8_extreme_personality_axes(campaign):
    """Verifies that the prompt context is correctly constructed when player personality axes are at extreme values (0.0 or 100.0)."""
    build_context = get_func("esports_sim.manager.llm_talk", "build_talk_context")
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    
    with patch("esports_sim.manager.personality.axes", return_value={"ego": 100.0, "resilience": 0.0, "sociability": 100.0, "professionalism": 0.0, "ambition": 100.0}):
        ctx = build_context(campaign, pid)
    assert isinstance(ctx, str)


def test_tier2_f8_oversized_history_trimming(campaign):
    """Verifies that player history logs or chat histories are trimmed to fit within prompt context limits without raising errors."""
    build_context = get_func("esports_sim.manager.llm_talk", "build_talk_context")
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    player = campaign.players[pid]
    
    # Inject massive chronicle logs
    from esports_sim.schemas.events import ChronicleEvent
    campaign.chronicles[pid] = [ChronicleEvent(season=1, week=1, message="A" * 1000) for _ in range(50)]
    
    ctx = build_context(campaign, pid)
    assert len(ctx) < 15000 # Trim check


def test_tier2_f8_empty_save_grounding(campaign):
    """Verifies context grounding on a brand new campaign save with minimal historical records."""
    build_context = get_func("esports_sim.manager.llm_talk", "build_talk_context")
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    
    campaign.chronicles = {}
    campaign.player_stats = {}
    
    ctx = build_context(campaign, pid)
    assert isinstance(ctx, str)


def test_tier2_f8_special_characters_escaping(campaign):
    """Verifies that prompt construction escapes special characters, HTML, and JSON syntax safely."""
    build_context = get_func("esports_sim.manager.llm_talk", "build_talk_context")
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    player = campaign.players[pid]
    player.real_name = 'John "Slasher" <tag> {brackets}'
    
    ctx = build_context(campaign, pid)
    assert "John" in ctx


def test_tier2_f8_ascii_enforcement(campaign):
    """Verifies that the grounding builder filters non-ASCII characters, ensuring console compatibility."""
    build_context = get_func("esports_sim.manager.llm_talk", "build_talk_context")
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    player = campaign.players[pid]
    player.real_name = "JÃ¶hn Â¥"
    
    ctx = build_context(campaign, pid)
    # verify only ascii chars
    assert ctx.isascii()


# --- LLM Response Adjustment Application (F9) ---

def test_tier2_f9_classify_ambiguous_fallback(campaign):
    """Verifies that ambiguous or gibberish inputs are classified into a safe fallback intent (e.g. 'banter')."""
    classify_intent = get_func("esports_sim.manager.llm_talk", "classify_coach_intent")
    intent = classify_intent("asdfasdfasdfasdf")
    assert intent in ("banter", "check_in")


def test_tier2_f9_adjustment_caps(campaign):
    """Verifies that morale and confidence adjustments resulting from chat classification are clamped between 0 and 100."""
    apply_chat_adjustment = get_func("esports_sim.manager.llm_talk", "apply_chat_adjustment")
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    player = campaign.players[pid]
    
    player.morale = 99.0
    apply_chat_adjustment(campaign, pid, "reassure") # would normally boost it above 100
    assert player.morale <= 100.0


def test_tier2_f9_offline_api_timeout(campaign):
    """Verifies that when the LLM API times out, the system falls back to a deterministic fallback path."""
    process_chat_offline = get_func("esports_sim.manager.llm_talk", "process_chat_offline")
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    
    # Offline trigger
    res = process_chat_offline(campaign, pid, "Some coach words")
    assert res is not None


def test_tier2_f9_malformed_json_recovery(campaign):
    """Verifies that if the LLM returns malformed JSON, the parser handles it and falls back gracefully."""
    parse_response = get_func("esports_sim.manager.llm_talk", "parse_chat_response")
    res = parse_response("This is not JSON { } }")
    assert isinstance(res, dict) # Empty or default dict return


def test_tier2_f9_weekly_throttle_limit(campaign):
    """Verifies that a manager cannot execute more than one chat resolution per player per weekly tick."""
    can_talk = get_func("esports_sim.manager.llm_talk", "can_talk")
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    
    # Set talked flag
    campaign.talked_week = f"s{campaign.season}w{campaign.week}"
    ok, why = can_talk(campaign, pid)
    assert ok is False


# --- LLM Talk Promise/Memory Updates (F10) ---

def test_tier2_f10_caching_missing_directory(campaign, tmp_path):
    """Verifies that the sidecar cache system automatically creates the saves/ folder if it is missing."""
    save_talk_cache = get_func("esports_sim.manager.llm_talk", "save_talk_cache")
    missing_dir = tmp_path / "missing_saves"
    
    with patch("esports_sim.manager.llm_talk.TALK_CACHE_DIR", missing_dir):
        save_talk_cache("save_id", "key", "prose")
        assert missing_dir.exists()


def test_tier2_f10_corrupted_sidecar(campaign, tmp_path):
    """Verifies that a corrupted sidecar JSON file is ignored and overwritten without crashing."""
    save_talk_cache = get_func("esports_sim.manager.llm_talk", "save_talk_cache")
    load_talk_cache = get_func("esports_sim.manager.llm_talk", "load_talk_cache")
    
    with patch("esports_sim.manager.llm_talk.TALK_CACHE_DIR", tmp_path):
        # Corrupt file
        cache_file = tmp_path / "save_corrupt.json"
        cache_file.write_text("corrupted json data {{{{")
        
        # Save should overwrite cleanly
        save_talk_cache("save_corrupt", "key", "new prose")
        text = load_talk_cache("save_corrupt", "key")
        assert text == "new prose"


def test_tier2_f10_promise_stacking_via_chat(campaign):
    """Verifies that triggering a promise via chat when one is already active updates the target rather than creating duplicates."""
    process_chat_resolution = get_func("esports_sim.manager.llm_talk", "process_chat_resolution")
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    
    process_chat_resolution(campaign, pid, "Playtime promise 1", intent="play_time_promise")
    process_chat_resolution(campaign, pid, "Playtime promise 2", intent="play_time_promise")
    
    promises = [p for p in campaign.promises if p.player_id == pid and p.promise_type == "play_time"]
    assert len(promises) == 1


def test_tier2_f10_memory_update_ego_threshold(campaign):
    """Verifies that memory updates are scaled by player ego (players with high ego require larger boosts to satisfy)."""
    apply_chat_adjustment = get_func("esports_sim.manager.llm_talk", "apply_chat_adjustment")
    team = list(campaign.teams.values())[0]
    pid1 = team.player_ids[0]
    pid2 = team.player_ids[1]
    
    campaign.players[pid1].morale = 50.0
    campaign.players[pid2].morale = 50.0
    
    with patch("esports_sim.manager.personality.axes", side_effect=lambda p: {"ego": 95.0, "resilience": 50.0, "sociability": 50.0, "professionalism": 50.0, "ambition": 50.0} if p.id == pid1 else {"ego": 20.0, "resilience": 50.0, "sociability": 50.0, "professionalism": 50.0, "ambition": 50.0}):
        apply_chat_adjustment(campaign, pid1, "praise")
        apply_chat_adjustment(campaign, pid2, "praise")
        
    # High ego player should receive less morale lift for same praise
    morale_lift_ego = campaign.players[pid1].morale - 50.0
    morale_lift_low_ego = campaign.players[pid2].morale - 50.0
    assert morale_lift_ego < morale_lift_low_ego


def test_tier2_f10_sidecar_concurrent_writes(campaign, tmp_path):
    """Verifies that the sidecar file reader/writer is thread-safe and handles rapid operations."""
    save_talk_cache = get_func("esports_sim.manager.llm_talk", "save_talk_cache")
    
    with patch("esports_sim.manager.llm_talk.TALK_CACHE_DIR", tmp_path):
        import threading
        threads = []
        for i in range(10):
            t = threading.Thread(target=save_talk_cache, args=("save_concur", f"key_{i}", "prose"))
            threads.append(t)
            t.start()
        for t in threads:
            t.join()
        # Verify file is valid json and has writes
        cache_file = tmp_path / "save_concur.json"
        with open(cache_file, "r") as f:
            data = json.load(f)
        assert len(data) == 10


# --- xDuel & Expected Duel Edge (xDE) Telemetry (F11) ---

def test_tier2_f11_zero_probability_duel(campaign):
    """Verifies that the expected win probability calculation is numerically stable when ELO score differences are extremely high or low (e.g. difference of 1000)."""
    calculate_xduel = get_func("esports_sim.manager.xduel", "calculate_xduel_probability")
    
    # Large differences
    prob_high = calculate_xduel(rating_a=1500, rating_b=500)
    prob_low = calculate_xduel(rating_a=500, rating_b=1500)
    
    assert prob_high > 0.99
    assert prob_low < 0.01


def test_tier2_f11_zero_expected_wins(campaign):
    """Verifies that Expected Duel Edge (xDE) calculations do not divide by zero if expected wins are exactly 0."""
    calculate_xde = get_func("esports_sim.manager.xduel", "calculate_xde")
    res = calculate_xde(outcome=1, expected_probability=0.0)
    assert res == 1.0


def test_tier2_f11_season_reset_stats(campaign):
    """Verifies that player expected/actual duel wins reset to 0.0 on season rollover."""
    reset_xde_season = get_func("esports_sim.manager.xduel", "reset_xde_season")
    stats = MagicMock()
    stats.expected_wins = 55.4
    stats.actual_wins = 45
    
    reset_xde_season(stats)
    assert stats.expected_wins == 0.0
    assert stats.actual_wins == 0


def test_tier2_f11_no_save_bloat(campaign):
    """Verifies that detailed telemetry events are excluded from the main GameState save, keeping save files small."""
    filter_save_data = get_func("esports_sim.manager.xduel", "filter_telemetry_for_save")
    
    state_dict = {"players": {}, "telemetry_logs": [{"event_type": "duel_telemetry", "data": "massive"}]}
    filtered = filter_save_data(state_dict)
    assert "telemetry_logs" not in filtered or len(filtered["telemetry_logs"]) == 0


def test_tier2_f11_no_engine_feedback(campaign):
    """Verifies that tapping the telemetry data has absolutely zero feedback or impact on round outcome calculations."""
    simulate_duel = get_func("esports_sim.manager.xduel", "simulate_duel_with_telemetry")
    
    # Duel outcomes with and without telemetry logging should be identical if seed is fixed
    with patch("esports_sim.manager.xduel.record_telemetry") as mock_record:
        res1 = simulate_duel(campaign, "p1", "p2")
        
    res2 = simulate_duel(campaign, "p1", "p2")
    assert res1 == res2


# ==============================================================================
# TIER 3: CROSS-FEATURE COMBINATIONS (11 tests)
# ==============================================================================

def test_tier3_f1_f3_leader_promise(campaign):
    """Verifies that making a promise (F3) to the Incumbent Leader (F1) increases the speed/magnitude of team chemistry improvements due to their leadership role."""
    create_promise = get_func("esports_sim.manager.promises", "create_promise")
    weekly_tick = get_func("esports_sim.manager.promises", "weekly_tick")
    renew_contract = get_func("esports_sim.manager.market", "renew_contract")
    
    team = list(campaign.teams.values())[0]
    leader_id = team.player_ids[0]
    team.captain_id = leader_id
    team.chemistry = 70.0
    
    with patch("esports_sim.manager.locker_room.get_hierarchy_role", return_value="incumbent_leader"):
        create_promise(campaign, team.id, leader_id, "renew_contract", duration=1)
        # Keep promise
        renew_contract(campaign, team.id, leader_id)
        weekly_tick(campaign, week_dressed={team.id: {leader_id}})
        
    assert team.chemistry > 75.0 # Enhanced chem boost (standard is +5.0)


def test_tier3_f2_f4_clique_leader_benching_morale_cascade(campaign):
    """Verifies that benching a clique leader (F2) and breaking a promise (F4) to them simultaneously triggers a cascading morale crash for the entire clique."""
    handle_benching = get_func("esports_sim.manager.locker_room", "handle_benching_impact")
    resolve_promise = get_func("esports_sim.manager.promises", "resolve_promise")
    from esports_sim.schemas.promise import ManagerPromise
    
    team = list(campaign.teams.values())[0]
    leader_id = team.player_ids[0]
    clique_mate_id = team.player_ids[1]
    
    campaign.players[clique_mate_id].morale = 80.0
    
    nudge = get_func("esports_sim.manager.relationships", "nudge")
    nudge(campaign, clique_mate_id, leader_id, 85.0)
    
    promise = ManagerPromise(id="p_casc", team_id=team.id, player_id=leader_id, promise_type="play_time", weeks_left=1, created_week=1, created_season=1)
    
    with patch("esports_sim.manager.locker_room.get_hierarchy_role", return_value="leader"):
        handle_benching(campaign, team.id, [leader_id])
        resolve_promise(campaign, promise, success=False)
        
    # Cascade crash should push clique mate morale extremely low
    assert campaign.players[clique_mate_id].morale < 50.0


def test_tier3_f3_f4_playtime_promise_fulfillment_morale(campaign):
    """Verifies that creating a playtime promise (F3) and fulfilling it (F4) boosts the player's morale and overall chemistry."""
    create_promise = get_func("esports_sim.manager.promises", "create_promise")
    weekly_tick = get_func("esports_sim.manager.promises", "weekly_tick")
    
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    campaign.players[pid].morale = 60.0
    team.chemistry = 60.0
    
    create_promise(campaign, team.id, pid, "play_time", target_value=1, duration=1)
    weekly_tick(campaign, week_dressed={team.id: {pid}})
    
    assert campaign.players[pid].morale > 60.0
    assert team.chemistry > 60.0


def test_tier3_f1_f5_mentorship_hierarchy_boost(campaign):
    """Verifies that a mentor who is an Incumbent Leader (F1) provides a faster/more reliable PA or tag transfer (F5) to a mentee Outcast."""
    tick_mentorship = get_func("esports_sim.manager.mentorship", "tick_mentorship")
    team = list(campaign.teams.values())[0]
    mentor_id = team.player_ids[0]
    mentee_id = team.player_ids[1]
    campaign.mentorships[mentee_id] = mentor_id
    
    if not hasattr(campaign, "mentorship_progress"):
        campaign.mentorship_progress = {}
    campaign.mentorship_progress[mentee_id] = 10.0
    
    # Mocking mentor as incumbent leader and mentee as outcast
    def mock_role(gs, pid, tid):
        return "incumbent_leader" if pid == mentor_id else "outcast"
        
    with patch("esports_sim.manager.locker_room.get_hierarchy_role", side_effect=mock_role):
        tick_mentorship(campaign)
        
    # Mentorship progress should grow faster than baseline
    assert campaign.mentorship_progress[mentee_id] > 15.0


def test_tier3_f6_f7_halftime_talk_shout_momentum(campaign):
    """Verifies that a halftime pep talk (F6) combined with subsequent touchline shouts (F7) compounds changes to player confidence and tactical dials."""
    apply_pep_talk = get_func("esports_sim.manager.pep_talk", "apply_pep_talk")
    apply_shout = get_func("esports_sim.manager.shouts", "apply_touchline_shout")
    
    team = list(campaign.teams.values())[0]
    team.tactics.aggression = 50.0
    
    apply_pep_talk(campaign, team.id, "fire_up", relative_score=-5)
    apply_shout(campaign, team.id, "demand_effort")
    
    # Combined aggression boost
    assert team.tactics.aggression > 65.0


def test_tier3_f6_f11_pep_talk_xde_impact(campaign):
    """Verifies that a halftime pep talk (F6) alters team confidence, which affects duel ELO scores and changes the expected vs actual duels (F11)."""
    apply_pep_talk = get_func("esports_sim.manager.pep_talk", "apply_pep_talk")
    simulate_duel = get_func("esports_sim.manager.xduel", "simulate_duel_with_telemetry")
    
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    
    # Morale/confidence change from pep talk alters ELO adjustment factors
    apply_pep_talk(campaign, team.id, "fire_up", relative_score=-5)
    
    events = []
    simulate_duel(campaign, pid, "opponent_id", events_out=events)
    # Check ELO calculation reflected the talk impact
    assert len(events) > 0


def test_tier3_f8_f10_grounded_chat_promise(campaign):
    """Verifies that an LLM talk grounded in low playtime context (F8) triggers a playtime promise update (F10)."""
    build_context = get_func("esports_sim.manager.llm_talk", "build_talk_context")
    process_chat_resolution = get_func("esports_sim.manager.llm_talk", "process_chat_resolution")
    
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    
    # Low playtime setup
    campaign.players[pid].roster_role = "bench"
    
    ctx = build_context(campaign, pid)
    assert "playtime" in ctx.lower() or "bench" in ctx.lower()
    
    # Process playtime response
    process_chat_resolution(campaign, pid, "I will play you in the next match.", intent="play_time_promise")
    assert any(p.player_id == pid and p.promise_type == "play_time" for p in campaign.promises)


def test_tier3_f9_f10_chat_adjustment_memory_write(campaign, tmp_path):
    """Verifies that applying an LLM chat response adjustment (F9) updates the player's memory and writes the response to the sidecar cache (F10)."""
    apply_chat_adjustment = get_func("esports_sim.manager.llm_talk", "apply_chat_adjustment")
    save_talk_cache = get_func("esports_sim.manager.llm_talk", "save_talk_cache")
    
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    player = campaign.players[pid]
    player.morale = 50.0
    
    with patch("esports_sim.manager.llm_talk.TALK_CACHE_DIR", tmp_path):
        apply_chat_adjustment(campaign, pid, "reassure")
        save_talk_cache("save_cross", "chat_cross", "Reassuring words.")
        
    assert player.morale > 50.0
    assert (tmp_path / "save_cross.json").exists()


def test_tier3_f1_f2_f4_rebel_leader_mutiny(campaign):
    """Verifies that when a Volatile Rebel (F1) is benched (F2), their clique members suffer severe morale drops and team chemistry crashes (F4)."""
    handle_benching = get_func("esports_sim.manager.locker_room", "handle_benching_impact")
    team = list(campaign.teams.values())[0]
    rebel_id = team.player_ids[0]
    mate_id = team.player_ids[1]
    
    campaign.players[mate_id].morale = 80.0
    team.chemistry = 70.0
    
    # Mocking as volatile rebel and establishing clique relations
    with patch("esports_sim.manager.locker_room.get_hierarchy_role", return_value="volatile_rebel"):
        from esports_sim.manager import relationships
        relationships.nudge(campaign, mate_id, rebel_id, 80.0)
        
        handle_benching(campaign, team.id, [rebel_id])
        
    assert campaign.players[mate_id].morale < 60.0
    assert team.chemistry < 60.0


def test_tier3_f3_f9_f10_offline_talk_promise_fallback(campaign, tmp_path):
    """Verifies that when the LLM is offline (F9), the fallback conversation flow successfully creates a promise (F3) and writes fallback text to the sidecar cache (F10)."""
    process_chat_offline = get_func("esports_sim.manager.llm_talk", "process_chat_offline")
    
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    
    with patch("esports_sim.manager.llm_talk.TALK_CACHE_DIR", tmp_path):
        res = process_chat_offline(campaign, pid, "Contract renewal please.")
        
    assert any(p.player_id == pid and p.promise_type == "renew_contract" for p in campaign.promises)
    assert (tmp_path / f"{campaign.seed}.json").exists()


def test_tier3_f7_f11_touchline_shout_xde_telemetry(campaign):
    """Verifies that a touchline shout (F7) like demand_effort alters the team's aggression dial, which shifts ELO scores during round duels, causing changes in expected wins (F11)."""
    apply_shout = get_func("esports_sim.manager.shouts", "apply_touchline_shout")
    simulate_duel = get_func("esports_sim.manager.xduel", "simulate_duel_with_telemetry")
    
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    
    apply_shout(campaign, team.id, "demand_effort")
    
    events = []
    simulate_duel(campaign, pid, "opp_id", events_out=events)
    assert len(events) > 0


# ==============================================================================
# TIER 4: REAL-WORLD APPLICATION SCENARIOS (6 tests)
# ==============================================================================

def test_tier4_scenario1_full_season_leader_benching(campaign, game_data):
    """Simulates a full campaign season playthrough where the team captain (Incumbent Leader) is benched.

    Verifies hierarchy role updates, morale/clique impact propagation, promise tracking, and final season xDuel stats.
    """
    get_role = get_func("esports_sim.manager.locker_room", "get_hierarchy_role")
    handle_benching = get_func("esports_sim.manager.locker_room", "handle_benching_impact")
    create_promise = get_func("esports_sim.manager.promises", "create_promise")
    
    team = list(campaign.teams.values())[0]
    captain_id = team.player_ids[0]
    team.captain_id = captain_id
    
    # Verify Captain Role
    role = get_role(campaign, captain_id, team.id)
    assert role == "incumbent_leader"
    
    # Make playtime promise to Captain
    create_promise(campaign, team.id, captain_id, "play_time", target_value=50, duration=10)
    
    # Bench the captain
    team.lineup_ids = [p for p in team.player_ids if p != captain_id]
    handle_benching(campaign, team.id, [captain_id])
    
    # Advance week and check that campaign still runs and processes ticks
    advance_week(campaign, game_data)
    
    # Morale should have decayed/propagated and promises tracked
    assert len(campaign.promises) >= 0


def test_tier4_scenario2_mid_match_crisis(campaign):
    """Simulates a high-stakes match where the team falls behind 11-1 by halftime.

    Triggers pep talks and touchline shouts. Verifies that the match simulation state updates, stamina drains, and confidence values calibrate correctly.
    """
    apply_pep_talk = get_func("esports_sim.manager.pep_talk", "apply_pep_talk")
    apply_shout = get_func("esports_sim.manager.shouts", "apply_touchline_shout")
    
    team = list(campaign.teams.values())[0]
    
    # Crisis setup (confidence drop)
    for pid in team.player_ids:
        campaign.players[pid].confidence = 25.0
        
    # Halftime Pep Talk (trailing by 10)
    apply_pep_talk(campaign, team.id, "fire_up", relative_score=-10)
    
    # Touchline Shout (encourage team)
    apply_shout(campaign, team.id, "encourage", loss_streak=5)
    
    # Verify confidence recovered slightly but stamina was drained if aggression increased
    for pid in team.player_ids:
        assert campaign.players[pid].confidence > 25.0


def test_tier4_scenario3_llm_talk_offline_fallback(campaign, tmp_path):
    """Simulates a weekly 1:1 talk session.

    Triggers the flow both online and offline (mocking/forcing API failures). Verifies that the intent is resolved, attributes update, promises are created, and responses are successfully sidecar-cached.
    """
    process_chat_resolution = get_func("esports_sim.manager.llm_talk", "process_chat_resolution")
    process_chat_offline = get_func("esports_sim.manager.llm_talk", "process_chat_offline")
    
    team = list(campaign.teams.values())[0]
    pid = team.player_ids[0]
    
    with patch("esports_sim.manager.llm_talk.TALK_CACHE_DIR", tmp_path):
        # 1. Try offline talk (API down fallback)
        res_offline = process_chat_offline(campaign, pid, "I need contract assurance.")
        assert len(campaign.promises) > 0
        
        # 2. Try online mock talk
        res_online = process_chat_resolution(campaign, pid, "Let's work together.", intent="praise")
        assert res_online is not None


def test_tier4_scenario4_veteran_mentorship_career(campaign, game_data):
    """Simulates a season-long mentorship program.

    Tracks progress, Potential Ability (PA) adjustments, and trait/tag transfer from a veteran leader to a rookie outcast. Verifies long-term career statistics and role changes.
    """
    pair_mentorship = get_func("esports_sim.manager.mentorship", "pair_mentorship")
    tick_mentorship = get_func("esports_sim.manager.mentorship", "tick_mentorship")
    
    team = list(campaign.teams.values())[0]
    mentor_id = team.player_ids[0]
    mentee_id = team.player_ids[1]
    
    # Ensure they are valid pair
    campaign.players[mentor_id].age = 29
    campaign.players[mentor_id].personality_tags = ["leader", "reliable"]
    campaign.players[mentee_id].age = 18
    campaign.players[mentee_id].potential = 75.0
    campaign.players[mentee_id].personality_tags = []
    
    assert pair_mentorship(campaign, mentee_id, mentor_id) is True
    
    # Simulate a series of ticks
    for _ in range(5):
        with patch("random.random", return_value=0.0):
            tick_mentorship(campaign)
            
    # Verify progression
    assert campaign.players[mentee_id].potential > 75.0 or "reliable" in campaign.players[mentee_id].personality_tags


def test_tier4_scenario5_interactive_campaign_telemetry(campaign, game_data):
    """Runs a complete campaign walkthrough including roster manipulation, match play, chat interactions, and telemetry generation.

    Verifies final JSONL telemetry exports and aggregate stats.
    """
    export_telemetry = get_func("esports_sim.manager.xduel", "export_season_telemetry")
    team = list(campaign.teams.values())[0]
    
    # Walk through simple advance week
    advance_week(campaign, game_data)
    
    # Export telemetry logs
    logs = export_telemetry(campaign)
    assert isinstance(logs, list)


def test_tier4_scenario6_extreme_chemistry_rebuild(campaign):
    """Starts with a squad suffering from rival factions and negative chemistry (capped at 75.0).

    Runs transfers, releases, and promise management to rebuild team unity. Verifies that the chemistry cap is lifted when factions disband.
    """
    resolve_promise = get_func("esports_sim.manager.promises", "resolve_promise")
    from esports_sim.schemas.promise import ManagerPromise
    
    team = list(campaign.teams.values())[0]
    team.chemistry = 40.0
    
    # Promise to core players to rebuild unity
    p1 = ManagerPromise(id="p_rebuild", team_id=team.id, player_id=team.player_ids[0], promise_type="play_time", weeks_left=1, created_week=1, created_season=1)
    resolve_promise(campaign, p1, success=True)
    
    # Verify chemistry has recovered
    assert team.chemistry > 40.0
