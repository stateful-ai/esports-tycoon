"""The toolchain pin contract: pydantic + PyYAML + Python minor are pinned, and
the lock that pins them is the one CI installs from.

The byte-identity contract on the canonical save
(``saves/SCHEMA.md`` → **Byte-identity normalization**) only holds if every
checkout dumps through the same pydantic, the same PyYAML, on the same Python
minor that blessed the committed golden
(``tests/golden/week6_canonical.yaml``). Pinning ranges in ``pyproject.toml``
is necessary but not sufficient — pip's resolver can still drift if a
transitive (``pydantic_core``, ``typing_extensions``, ``annotated-types``)
slips a minor and changes serialization behaviour, and ``requires-python``
needs an upper bound to actually pin the interpreter minor rather than just
floor it.

This test locks the four seams that together make the contract enforceable:

* ``pyproject.toml`` pins ``PyYAML`` and ``pydantic`` with ``==`` and
  ``requires-python`` to a single minor.
* ``constraints.txt`` exists and pins those two plus their byte-identity-
  affecting transitives (``pydantic_core``, ``typing_extensions``,
  ``annotated-types``) with ``==``.
* The pyproject pin and the constraints.txt pin agree on the version.
* ``make install`` and the CI workflow actually pass that constraints file
  through to ``pip``, so a clean clone resolves to the locked versions.

It also asserts the *running* interpreter and libraries match the pins, so a
developer who has a stale virtualenv lying around sees the failure here
instead of getting a confusing golden diff three tests later.
"""

from __future__ import annotations

import pathlib
import re
import sys
import tomllib
import unittest

import pydantic
import pytest
import yaml

# M0 freeze (founder_brief.md): pinned-toolchain enforcement is deferred to
# M1/post-gate — it backs the byte-identity contract, which itself is parked
# until the screenshot gate fires.
pytestmark = pytest.mark.skip(
    reason="M0 freeze: pinned toolchain enforcement deferred to M1/post-gate"
)

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
_PYPROJECT = _REPO_ROOT / "pyproject.toml"
_CONSTRAINTS = _REPO_ROOT / "constraints.txt"
_MAKEFILE = _REPO_ROOT / "Makefile"
_CI_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "ci.yml"

# The byte-identity-affecting libraries. ``pydantic`` and ``PyYAML`` are the two
# the canonical serializer routes through directly; ``pydantic_core``,
# ``typing_extensions``, ``annotated-types`` ride along underneath pydantic and
# have shipped behaviour changes across minors that the canonical serializer
# doesn't normalize away. All five must be locked.
_BYTE_IDENTITY_LIBS: frozenset[str] = frozenset(
    {"PyYAML", "pydantic", "pydantic_core", "typing_extensions", "annotated-types"}
)

# The two named in ``[project].dependencies`` (the others are transitives, so
# they belong only in the lock).
_PYPROJECT_PINNED_LIBS: frozenset[str] = frozenset({"PyYAML", "pydantic"})


def _normalize(name: str) -> str:
    """PEP 503-ish normalization for package names: lowercase, ``_`` → ``-``."""
    return name.lower().replace("_", "-")


def _parse_constraints(text: str) -> dict[str, str]:
    """Parse ``constraints.txt`` into ``{normalized_name: version}``.

    Tolerates blank lines and ``#``-comments (full-line and trailing); only
    accepts ``pkg==X.Y.Z`` lines, which is the entire grammar this lockfile
    uses by design. Anything else raises so a sloppy edit fails this test
    rather than silently weakening the pin.
    """
    pins: dict[str, str] = {}
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        match = re.fullmatch(r"([A-Za-z0-9_.\-]+)==([A-Za-z0-9_.\-+]+)", line)
        if not match:
            raise AssertionError(
                f"constraints.txt:{lineno}: only ``pkg==version`` pins are allowed, got {raw!r}"
            )
        pins[_normalize(match.group(1))] = match.group(2)
    return pins


class TestPyprojectPins(unittest.TestCase):
    """``pyproject.toml`` declares the pins the lockfile enforces."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.data = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))

    def test_requires_python_pins_a_single_minor(self):
        # ``>=3.12,<3.13`` (or any equivalent that lets exactly one minor in)
        # is the contract. A bare ``>=3.10`` lets pip install on any future
        # minor and would silently invalidate the byte-identity contract the
        # moment CPython ships a relevant change.
        requires = self.data["project"]["requires-python"]
        self.assertRegex(
            requires,
            r">=\s*3\.(\d+).*<\s*3\.(\d+)",
            f"requires-python must pin a single Python minor with a lower AND upper bound; got {requires!r}",
        )
        match = re.search(r">=\s*3\.(\d+).*<\s*3\.(\d+)", requires)
        assert match is not None  # for type checkers
        lower, upper = int(match.group(1)), int(match.group(2))
        self.assertEqual(
            upper - lower,
            1,
            f"requires-python must allow exactly one Python minor; got 3.{lower}..3.{upper}",
        )

    def test_pyproject_pins_byte_identity_libs_with_equality(self):
        # The two direct serialization deps must be pinned with ``==`` in
        # ``[project].dependencies`` — a range like ``pydantic>=2.0`` would
        # let pip pick up the next minor on a clean install and quietly
        # re-shape the canonical bytes.
        deps = self.data["project"]["dependencies"]
        pinned = {}
        for dep in deps:
            match = re.fullmatch(r"\s*([A-Za-z0-9_.\-]+)==([A-Za-z0-9_.\-+]+)\s*", dep)
            self.assertIsNotNone(
                match,
                f"[project].dependencies must use ``pkg==version``; got {dep!r}",
            )
            assert match is not None  # for type checkers
            pinned[_normalize(match.group(1))] = match.group(2)
        for name in _PYPROJECT_PINNED_LIBS:
            self.assertIn(
                _normalize(name),
                pinned,
                f"pyproject.toml must pin {name} in [project].dependencies",
            )


class TestConstraintsLock(unittest.TestCase):
    """``constraints.txt`` exists and pins everything ``pip`` needs to resolve."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.pins = _parse_constraints(_CONSTRAINTS.read_text(encoding="utf-8"))

    def test_constraints_file_exists(self):
        self.assertTrue(
            _CONSTRAINTS.exists(),
            "constraints.txt is the lockfile ``make install`` and CI pass to pip; without it the pin is fiction",
        )

    def test_constraints_pin_every_byte_identity_lib(self):
        # The five libraries that together govern what bytes the canonical
        # serializer emits. Missing even one (e.g. ``pydantic_core``) leaves
        # pip free to resolve a different version on a clean checkout and
        # the committed golden would drift with no source change.
        missing = sorted(
            name for name in _BYTE_IDENTITY_LIBS if _normalize(name) not in self.pins
        )
        self.assertEqual(
            missing,
            [],
            f"constraints.txt must pin every byte-identity lib; missing: {missing}",
        )

    def test_constraints_agree_with_pyproject_pins(self):
        # Pyproject says ``pydantic==2.13.4``; constraints.txt must say the
        # same. A divergence would let one of the two win silently depending
        # on which file pip resolves first, defeating the lock.
        pyproject = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
        for dep in pyproject["project"]["dependencies"]:
            match = re.fullmatch(r"\s*([A-Za-z0-9_.\-]+)==([A-Za-z0-9_.\-+]+)\s*", dep)
            assert match is not None  # validated in TestPyprojectPins
            name, version = _normalize(match.group(1)), match.group(2)
            self.assertEqual(
                self.pins.get(name),
                version,
                f"constraints.txt pin for {name} ({self.pins.get(name)!r}) disagrees with "
                f"pyproject.toml ({version!r}); they must match",
            )


class TestInstallPathConsumesLock(unittest.TestCase):
    """The Makefile and CI both actually pass ``constraints.txt`` through to pip."""

    def test_makefile_install_uses_constraints(self):
        # ``pip install -c constraints.txt -e .[dev,web]`` is what makes the
        # lockfile load-bearing. A Makefile that pinned the file in name only
        # — declaring the variable but never passing it to pip — would be a
        # silent regression here.
        text = _MAKEFILE.read_text(encoding="utf-8")
        self.assertRegex(
            text,
            r"pip install\b[^\n]*-c\s+[\"']?(?:\$\(CONSTRAINTS\)|constraints\.txt)",
            "Makefile `install` target must pass -c constraints.txt to pip",
        )

    def test_ci_workflow_invokes_make_install(self):
        # CI must go through ``make install`` so the constraints pass is the
        # same one contributors run locally. A direct ``pip install -e .``
        # in the workflow would bypass the lock.
        text = _CI_WORKFLOW.read_text(encoding="utf-8")
        self.assertRegex(
            text,
            r"\bmake install\b",
            "CI must invoke `make install` so the constraints-pinned resolve runs in CI too",
        )

    def test_ci_python_matrix_matches_pyproject_pin(self):
        # The single-minor pin in pyproject.toml is only honoured in CI if the
        # workflow actually runs that minor. A drift between the two would
        # silently widen the pin: pyproject says 3.12, CI runs 3.11, and the
        # contract is fiction.
        pyproject = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
        requires = pyproject["project"]["requires-python"]
        match = re.search(r">=\s*3\.(\d+)", requires)
        assert match is not None  # validated in TestPyprojectPins
        expected_minor = match.group(1)
        text = _CI_WORKFLOW.read_text(encoding="utf-8")
        matrix_match = re.search(
            r"python-version:\s*\[([^\]]+)\]", text
        )
        self.assertIsNotNone(
            matrix_match,
            "CI workflow must declare an inline python-version matrix list",
        )
        assert matrix_match is not None  # for type checkers
        versions = [
            v.strip().strip('"').strip("'") for v in matrix_match.group(1).split(",")
        ]
        self.assertEqual(
            versions,
            [f"3.{expected_minor}"],
            f"CI python-version matrix {versions} must match the single minor pinned in "
            f"pyproject.toml (3.{expected_minor})",
        )


class TestRunningInterpreterMatchesPins(unittest.TestCase):
    """The interpreter / libraries actually loaded match what the pins declare.

    A contributor with a stale virtualenv would otherwise see a confusing
    golden-determinism failure instead of the real root cause; failing here
    points straight at the install.
    """

    @classmethod
    def setUpClass(cls) -> None:
        cls.pyproject = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
        cls.constraints = _parse_constraints(_CONSTRAINTS.read_text(encoding="utf-8"))

    def test_python_minor_matches_pyproject_pin(self):
        match = re.search(r">=\s*3\.(\d+)", self.pyproject["project"]["requires-python"])
        assert match is not None  # validated in TestPyprojectPins
        expected = (3, int(match.group(1)))
        self.assertEqual(
            sys.version_info[:2],
            expected,
            f"running on Python {sys.version_info.major}.{sys.version_info.minor}, "
            f"pin requires {expected[0]}.{expected[1]}; the byte-identity contract assumes the pinned minor",
        )

    def test_pydantic_version_matches_lock(self):
        self.assertEqual(
            pydantic.VERSION,
            self.constraints["pydantic"],
            f"pydantic {pydantic.VERSION} is loaded, but constraints.txt pins "
            f"{self.constraints['pydantic']}; reinstall with `make install`",
        )

    def test_pyyaml_version_matches_lock(self):
        self.assertEqual(
            yaml.__version__,
            self.constraints["pyyaml"],
            f"PyYAML {yaml.__version__} is loaded, but constraints.txt pins "
            f"{self.constraints['pyyaml']}; reinstall with `make install`",
        )


if __name__ == "__main__":
    unittest.main()
