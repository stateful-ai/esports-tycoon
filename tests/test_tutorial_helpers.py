"""Static contracts for the in-game manager handbook and tooltip layer."""

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
