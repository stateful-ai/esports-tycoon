"""Unit tests for the synthetic-player harness's pure layers.

The harness's job is to tell an agent the truth about a screen. These tests
pin the parts of that contract that do not need a browser: the digest an agent
reads, the findings ledger it writes, and the persona briefs it plays under.
The browser half lives in ``test_playtest_browser.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from esports_sim.playtest.dom import (
    OPEN_OVERLAYS_SCRIPT,
    SCREEN_SCRIPT,
    VISIBLE_JS,
    render_console,
    render_digest,
)
from esports_sim.playtest.findings import (
    AREAS,
    SEVERITIES,
    Finding,
    aggregate,
    append_finding,
    load_all,
    load_findings,
    render_report,
)
from esports_sim.playtest.personas import PERSONAS, persona


def _snapshot(**overrides):
    base = {
        "url": "/",
        "title": "esports-sim",
        "bodyText": "",
        "context": "Season 1 · Week 3 · Regular — Alpine Echo",
        "balance": "108,600 cr",
        "inGame": True,
        "overlays": [],
        "tabs": [
            {"tab": "dashboard", "label": "DASHBOARD", "active": True},
            {"tab": "club", "label": "CLUB", "active": False},
        ],
        "subtabs": [],
        "screenTitle": "DASHBOARD",
        "cards": [],
        "tables": [],
        "controls": [],
        "links": [],
        "viewTextLength": 1200,
    }
    base.update(overrides)
    return base


# ── digest ───────────────────────────────────────────────────────────────


def test_digest_leads_with_where_you_are():
    text = render_digest(_snapshot())
    assert text.splitlines()[0] == "SCREEN: DASHBOARD"
    assert "CONTEXT: Season 1 · Week 3" in text
    assert "BALANCE: 108,600 cr" in text


def test_digest_marks_the_active_tab():
    text = render_digest(_snapshot())
    assert "[DASHBOARD]" in text
    assert "[CLUB]" not in text


def test_digest_warns_that_an_overlay_blocks_the_page():
    # An agent that misses this clicks into a modal and reports a phantom bug.
    text = render_digest(_snapshot(overlays=[{"id": "profile", "title": "Slyshot"}]))
    assert "OVERLAY OPEN" in text
    assert "profile" in text
    assert "Slyshot" in text


def test_digest_lists_controls_with_the_handles_needed_to_click_them():
    text = render_digest(
        _snapshot(
            controls=[
                {"kind": "button", "label": "Advance Week", "id": "advance-btn",
                 "disabled": False, "type": "", "value": ""},
                {"kind": "button", "label": "Sign", "id": "", "disabled": True,
                 "type": "", "value": ""},
            ]
        )
    )
    assert "Advance Week" in text
    assert "#advance-btn" in text
    assert "[disabled]" in text


def test_digest_reports_table_totals_not_just_the_rows_it_prints():
    rows = [[f"Player {i}", str(i)] for i in range(30)]
    text = render_digest(_snapshot(tables=[{"headers": ["PLAYER", "OVR"], "rows": rows, "total": 30}]))
    assert "TABLE 1 (30 rows)" in text
    # Truncation must announce itself, or an agent reports "only 12 players".
    assert "more rows" in text


def test_digest_falls_back_to_raw_text_when_no_structure_is_recognised():
    # Bespoke overlays do not use the card/table conventions. Reporting them as
    # empty would be the harness lying about a screen that is full.
    text = render_digest(_snapshot(cards=[], tables=[], bodyText="Slyshot · Controller · IGL · age 18"))
    assert "SCREEN TEXT:" in text
    assert "Slyshot" in text


def test_digest_prefers_structure_over_raw_text():
    text = render_digest(
        _snapshot(cards=[{"heading": "SQUAD", "body": "five players"}], bodyText="raw dump")
    )
    assert "CARDS (1)" in text
    assert "SCREEN TEXT:" not in text


def test_digest_includes_the_screenshot_path_when_given_one():
    assert "runs/x/001.png" in render_digest(_snapshot(), screenshot="runs/x/001.png")


def test_digest_rejects_a_non_mapping():
    with pytest.raises(TypeError):
        render_digest(["not", "a", "snapshot"])  # type: ignore[arg-type]


def test_screen_script_is_a_single_javascript_expression():
    # It is passed straight to page.evaluate, so it must be one arrow function.
    assert SCREEN_SCRIPT.strip().startswith("() => {")
    assert SCREEN_SCRIPT.strip().endswith("}")


def test_every_injected_script_uses_the_one_visibility_rule():
    """The harness must not hold two opinions about what is on screen.

    profile.css keeps the closed profile overlay at `display: flex;
    opacity: 0; pointer-events: none` so it can fade out. A check that looks
    only at `display` therefore calls that closed modal "open" — which makes
    the harness refuse to advance the week, and makes every later click search
    inside an invisible overlay. Both bugs happened; this pins the fix.
    """
    from esports_sim.playtest import session as session_module

    scripts = [SCREEN_SCRIPT, OPEN_OVERLAYS_SCRIPT]
    source = Path(session_module.__file__).read_text(encoding="utf-8")

    for script in scripts:
        assert VISIBLE_JS.strip() in script

    # No JS in the session module may hand-roll its own visibility predicate.
    assert "const vis = (n) =>" not in source, (
        "session.py defines a second visibility rule; inject VISIBLE_JS instead"
    )


def test_the_visibility_rule_covers_every_way_a_node_can_be_invisible():
    for guard in ("visibility", "display", "opacity", "pointerEvents", "getBoundingClientRect"):
        assert guard in VISIBLE_JS, f"the visibility rule ignores {guard}"


def test_render_console_is_empty_when_nothing_broke():
    assert render_console([]) == ""
    assert render_console(None) == ""


def test_render_console_reports_what_broke():
    text = render_console([{"kind": "pageerror", "text": "TypeError: x is undefined", "step": 4}])
    assert "pageerror" in text
    assert "TypeError" in text


# ── findings ─────────────────────────────────────────────────────────────


def test_finding_rejects_an_unknown_severity():
    with pytest.raises(ValueError, match="unknown severity"):
        Finding(severity="catastrophic", area="club", title="t", detail="d")


def test_finding_rejects_an_unknown_area():
    with pytest.raises(ValueError, match="unknown area"):
        Finding(severity="bug", area="somewhere", title="t", detail="d")


@pytest.mark.parametrize("field", ["title", "detail"])
def test_finding_rejects_empty_prose(field):
    kwargs = {"severity": "bug", "area": "club", "title": "t", "detail": "d", field: "   "}
    with pytest.raises(ValueError):
        Finding(**kwargs)


def test_severities_are_ordered_worst_first():
    # The order IS the triage policy: a blocker must never sort below a nit.
    assert SEVERITIES[0] == "blocker"
    assert SEVERITIES.index("confusing") < SEVERITIES.index("cosmetic")
    assert SEVERITIES[-1] == "praise"


def test_every_top_level_tab_has_a_findings_area():
    from esports_sim.playtest.session import TABS

    # A tab with no area forces its findings into "other", where they vanish.
    for tab in TABS:
        name = "match" if tab == "tactics" else tab
        assert name in AREAS, f"tab {tab!r} has no findings area"


def test_findings_round_trip_through_the_ledger(tmp_path):
    path = tmp_path / "findings.jsonl"
    original = Finding(
        severity="confusing", area="market", title="Bid button does nothing visible",
        detail="Clicking Bid produced no confirmation.", persona="first-timer",
        repro="Market > Players > Bid", week=3, tags=("market", "feedback"),
    )
    append_finding(path, original)
    loaded = load_findings(path)
    assert loaded == [original]


def test_ledger_is_append_only(tmp_path):
    path = tmp_path / "findings.jsonl"
    for index in range(3):
        append_finding(path, Finding(severity="bug", area="club", title=f"t{index}", detail="d"))
    assert len(load_findings(path)) == 3


def test_loading_a_missing_ledger_is_not_an_error(tmp_path):
    assert load_findings(tmp_path / "nope.jsonl") == []


def test_a_corrupt_line_names_its_line_number(tmp_path):
    path = tmp_path / "findings.jsonl"
    append_finding(path, Finding(severity="bug", area="club", title="ok", detail="d"))
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"severity": "nonsense", "area": "club", "title": "x",
                                 "detail": "y"}) + "\n")
    with pytest.raises(ValueError, match=r":2:"):
        load_findings(path)


def test_load_all_merges_every_persona_run(tmp_path):
    for name in ("first-timer", "optimiser"):
        append_finding(
            tmp_path / name / "findings.jsonl",
            Finding(severity="bug", area="club", title="same wall", detail="d", persona=name),
        )
    assert len(load_all(tmp_path)) == 2


def test_aggregate_sorts_blockers_above_everything():
    findings = [
        Finding(severity="cosmetic", area="club", title="nit", detail="d"),
        Finding(severity="blocker", area="market", title="stuck", detail="d"),
        Finding(severity="confusing", area="inbox", title="unclear", detail="d"),
    ]
    assert [g["severity"] for g in aggregate(findings)] == ["blocker", "confusing", "cosmetic"]


def test_aggregate_groups_the_same_issue_and_keeps_who_hit_it():
    # Corroboration is the strongest signal in the file; it must survive.
    findings = [
        Finding(severity="confusing", area="club", title="Form has no scale",
                detail="Is 58 good?", persona="first-timer"),
        Finding(severity="confusing", area="club", title="form has no scale",
                detail="No units anywhere.", persona="skimmer"),
    ]
    groups = aggregate(findings)
    assert len(groups) == 1
    assert groups[0]["count"] == 2
    assert groups[0]["personas"] == ["first-timer", "skimmer"]
    assert len(groups[0]["details"]) == 2


def test_aggregate_ranks_corroborated_issues_above_lonely_ones():
    findings = [
        Finding(severity="bug", area="club", title="alone", detail="d", persona="a"),
        Finding(severity="bug", area="market", title="agreed", detail="d", persona="a"),
        Finding(severity="bug", area="market", title="agreed", detail="d2", persona="b"),
    ]
    assert [g["title"] for g in aggregate(findings)] == ["agreed", "alone"]


def test_aggregate_of_nothing_is_empty():
    assert aggregate([]) == []


def test_report_says_so_when_there_is_nothing_to_report():
    assert "No findings recorded." in render_report([])


def test_report_leads_with_the_worst_and_names_the_personas():
    findings = [
        Finding(severity="cosmetic", area="club", title="nit", detail="d", persona="skimmer"),
        Finding(severity="blocker", area="market", title="cannot sign", detail="d",
                persona="optimiser", screenshot="runs/x/007.png"),
    ]
    report = render_report(findings)
    assert report.index("BLOCKER") < report.index("COSMETIC")
    assert "cannot sign" in report
    assert "optimiser" in report
    assert "runs/x/007.png" in report


# ── personas ─────────────────────────────────────────────────────────────


def test_persona_ids_are_unique():
    ids = [p.id for p in PERSONAS]
    assert len(ids) == len(set(ids))


def test_personas_disagree_about_what_matters():
    # Identical watch-lists would make five agents into one averaged reviewer.
    watch_lists = [set(p.watch_for) for p in PERSONAS]
    for index, first in enumerate(watch_lists):
        for second in watch_lists[index + 1:]:
            assert not first & second, "two personas share a watch-for item"


@pytest.mark.parametrize("subject", PERSONAS, ids=lambda p: p.id)
def test_every_persona_brief_is_playable(subject):
    brief = subject.brief()
    assert subject.name in brief
    assert subject.goal in brief
    assert subject.behaviour in brief
    for item in subject.watch_for:
        assert item in brief
    assert str(subject.weeks) in brief
    assert subject.weeks >= 1


def test_unknown_persona_names_the_valid_ids():
    with pytest.raises(KeyError, match="first-timer"):
        persona("nobody")
