"""The shipped frontend must not depend on the open internet.

`app.js` and `profile.js` used to `import` preact and htm from esm.sh at page
load. When that host is unreachable — offline, a locked-down network, a CI
sandbox — the module graph never resolves and the UI renders as an empty
shell: the chrome and tabs paint, `#view` stays blank, and nothing says why.
The modules are vendored under `web/static/vendor/` now, and these tests keep
them that way. They are pure file reads, so they run in every CI lane.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[1] / "src/esports_sim/web/static"
VENDOR = STATIC / "vendor"

# Any absolute URL in a module specifier — the thing that needs the network at
# page load. Documentation links inside comments are not the target.
_IMPORT_URL = re.compile(
    r"""(?:^|\s)(?:import|export)\s[^;\n]*?from\s*['"](https?://[^'"]+)['"]""",
    re.MULTILINE,
)
_BARE_IMPORT = re.compile(
    r"""(?:^|\s)(?:import|export)\s[^;\n]*?from\s*['"](?!\.|/|https?://)([^'"]+)['"]""",
    re.MULTILINE,
)
_HTML_SRC = re.compile(r"""<(?:script|link)[^>]*?(?:src|href)\s*=\s*['"](https?://[^'"]+)['"]""")


def _js_files() -> list[Path]:
    return sorted(STATIC.rglob("*.js")) + sorted(STATIC.rglob("*.mjs"))


@pytest.mark.parametrize("path", _js_files(), ids=lambda p: p.name)
def test_no_module_imports_from_an_external_host(path: Path) -> None:
    hits = _IMPORT_URL.findall(path.read_text(encoding="utf-8"))
    assert not hits, (
        f"{path.name} imports {hits} over the network — the UI goes blank without "
        f"internet. Vendor it under web/static/vendor/ instead "
        f"(scripts/vendor_frontend_deps.py)."
    )


@pytest.mark.parametrize("path", sorted(STATIC.rglob("*.html")), ids=lambda p: p.name)
def test_no_page_loads_a_script_or_stylesheet_from_an_external_host(path: Path) -> None:
    hits = _HTML_SRC.findall(path.read_text(encoding="utf-8"))
    assert not hits, f"{path.name} loads {hits} from a CDN"


@pytest.mark.parametrize("path", _js_files(), ids=lambda p: p.name)
def test_no_module_uses_a_bare_specifier(path: Path) -> None:
    # Browsers cannot resolve `from "preact"` without an import map, and the
    # app ships none — so a bare specifier is a blank screen, same as a CDN.
    hits = _BARE_IMPORT.findall(path.read_text(encoding="utf-8"))
    assert not hits, f"{path.name} imports bare specifier(s) {hits} with no import map"


def test_the_vendored_modules_are_present():
    expected = {"preact.mjs", "preact-hooks.mjs", "htm.mjs"}
    missing = expected - {p.name for p in VENDOR.glob("*.mjs")}
    assert not missing, f"missing vendored module(s): {sorted(missing)}"


def test_app_and_profile_import_the_vendored_modules():
    for name in ("app.js", "profile.js"):
        source = (STATIC / name).read_text(encoding="utf-8")
        assert "./vendor/preact.mjs" in source, f"{name} does not use the vendored preact"
        assert "./vendor/htm.mjs" in source, f"{name} does not use the vendored htm"


def test_vendored_relative_imports_resolve_on_disk():
    # A vendored module importing a sibling that is not there is a 404 at page
    # load, which looks exactly like the CDN failure this all exists to prevent.
    for path in VENDOR.glob("*.mjs"):
        source = path.read_text(encoding="utf-8")
        for target in re.findall(r"""from\s*['"](\.[^'"]+)['"]""", source):
            assert (path.parent / target).resolve().exists(), (
                f"{path.name} imports {target}, which does not exist"
            )


def test_vendor_provenance_is_documented():
    readme = (VENDOR / "README.md").read_text(encoding="utf-8")
    for package in ("preact@10.19.2", "htm@3.1.1"):
        assert package in readme, f"{package} is not accounted for in vendor/README.md"
