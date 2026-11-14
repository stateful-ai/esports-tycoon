"""Static contracts for the in-game manager handbook and tooltip layer."""

import re
from pathlib import Path


STATIC = Path(__file__).resolve().parents[1] / "src" / "esports_sim" / "web" / "static"


def test_manager_handbook_has_first_week_screens_and_glossary() -> None:
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    js = (STATIC / "app.js").read_text(encoding="utf-8")

    assert 'id="help-body"' in html
    assert 'data-help-section="first-week"' in html
    assert 'data-help-section="screens"' in html
    assert 'data-help-section="glossary"' in html
    assert "FIRST_WEEK_STEPS" in js
    for tab in ("dashboard", "inbox", "tactics", "club", "facilities", "season", "market", "stats", "company"):
        assert f"  {tab}: {{" in js


def test_tooltips_support_shared_keys_badges_and_keyboard_focus() -> None:
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    profile = (STATIC / "profile.js").read_text(encoding="utf-8")

    assert "TOOLTIP_LIBRARY" in app
    assert "badgeIconMarkup(bd)" in app
    assert 'document.addEventListener("focusin"' in app
    assert 'document.addEventListener("focusout"' in app
    assert "window.badgeTooltip(bd)" in profile


def _glossary_entries() -> dict[str, str]:
    """Key -> handbook group for every entry in the shared glossary."""
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    start = app.index("const TOOLTIP_LIBRARY = Object.freeze({")
    block = app[start : app.index("\n});", start)]
    return dict(re.findall(r'^  (\w+): \[.*, "(\w+)"\],$', block, flags=re.MULTILINE))


def test_glossary_is_the_single_source_for_tooltips_and_key_terms() -> None:
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    entries = _glossary_entries()

    # The handbook's Key terms page renders from the tooltip library, so a
    # second hand-written term list must not reappear beside it.
    assert "HELP_GLOSSARY" not in app
    assert "Object.values(TOOLTIP_LIBRARY)" in app
    assert len(entries) >= 40

    groups_start = app.index("const GLOSSARY_GROUPS = Object.freeze([")
    groups = set(re.findall(r'\["(\w+)", "', app[groups_start : app.index("]);", groups_start)]))
    assert groups
    # An entry in an unknown group would resolve as a tooltip but silently
    # vanish from the handbook.
    assert set(entries.values()) <= groups


def test_every_static_tooltip_key_resolves_in_the_glossary() -> None:
    entries = _glossary_entries()
    used: set[str] = set()
    for name in ("app.js", "profile.js", "index.html", "inbox.js", "facilities.js", "draft.js"):
        text = (STATIC / name).read_text(encoding="utf-8")
        used |= set(re.findall(r'data-tooltip-key="([a-z_]+)"', text))
        used |= set(re.findall(r'\bterm\("([a-z_]+)"', text))
        used |= set(re.findall(r'\btip: "([a-z_]+)"', text))

    assert used, "expected shared tooltip keys in the static UI"
    assert used <= set(entries), f"tooltip keys with no glossary entry: {sorted(used - set(entries))}"


def test_stat_columns_all_explain_themselves() -> None:
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    entries = _glossary_entries()
    start = app.index("const STAT_COLS = [")
    block = app[start : app.index("];", start)]
    columns = re.findall(r'\{ k: "(\w+)", h: "[^"]+"(?:, tip: "(\w+)")?', block)

    assert len(columns) >= 20
    for key, tip in columns:
        assert (tip or key) in entries, f"stat column {key} has no glossary entry"


def test_first_week_coach_tracks_progress_outside_the_dashboard() -> None:
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    app = (STATIC / "app.js").read_text(encoding="utf-8")

    # The coach is app chrome between the nav and the view, so it spends none
    # of the Dashboard's card budget.
    assert html.index("</nav>") < html.index('id="coach"') < html.index('<main id="view">')
    assert "function renderCoach(" in app
    assert "noteCoachVisit(App.tab);" in app
    # Progress is a browser-side preference only; it never reaches the save.
    coach = app[app.index("function coachKey()") : app.index("function helpFirstWeekMarkup()")]
    assert "localStorage" in coach
    assert "api(" not in coach


def test_tooltips_wait_for_intent_and_never_outlive_their_anchor() -> None:
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    engine = app[app.index("(function initTooltipSystem()") :]

    assert "HOVER_DELAY_MS" in engine
    assert 'document.addEventListener("pointerdown"' in engine
    assert "window.hideTooltip = " in engine
    # A re-render detaches the old view; its tooltip must go with it.
    render = app[app.index("function renderApp()") : app.index("/* -- helpers")]
    assert "window.hideTooltip?.();" in render
