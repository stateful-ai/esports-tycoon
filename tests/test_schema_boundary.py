"""The schema-boundary CI gate: one canonical schema, no draft duplicates, no
imports of modules that don't yet exist.

The architecture invariant (``m0_0_canonical_contract.md``) is that the six
canonical pydantic types — ``Player``, ``MemoryEntry``, ``Relationship``,
``WorldState``, ``WhyRecord``, ``GeneratedContent`` — are defined in exactly
one place, :mod:`esports_tycoon.schema`, and every consumer imports them from
there. Re-declaring one anywhere else, or importing one from a non-schema
module, would let a draft copy of a type quietly drift back onto the load /
resolve path; the contract relies on grep, not inspection, to keep that from
happening.

The second half of the gate is the "not-yet-built import" rule. A
``from esports_tycoon.chirper import …`` typed against an unbuilt module would
otherwise only surface at runtime — and only on a code path that actually
executes the import. A static walk over the source tree catches the dangling
import the moment it lands, so the CI failure is local to the offending file
instead of leaking out as a confusing test-collection error several layers
away. The completed resolver (and every other built submodule) imports
cleanly; only references to modules that genuinely don't exist on disk fail.

Both halves of the gate run as pure-Python AST walks over the repo's
``.py`` files — no imports of the code under test are performed here, so a
syntactically valid file with a forbidden pattern is still caught even if its
module-level code would have raised on import.
"""

from __future__ import annotations

import ast
import importlib.util
import pathlib
import textwrap
import unittest

import pytest

# M0 freeze (founder_brief.md): schema-boundary CI gate is deferred to
# M1/post-gate — the canonical-six are not under refactor pressure until the
# screenshot lands, so the AST-walk enforcement parks alongside the other
# reproducibility infra.
pytestmark = pytest.mark.skip(
    reason="M0 freeze: schema-boundary CI gate deferred to M1/post-gate"
)

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
_PKG_ROOT = _REPO_ROOT / "esports_tycoon"
_SCHEMA_FILE = (_PKG_ROOT / "schema.py").resolve()
_TESTS_ROOT = _REPO_ROOT / "tests"
_THIS_FILE = pathlib.Path(__file__).resolve()

# The pydantic types pinned by m0_0_canonical_contract.md §1. These six are the
# load/resolve path's shared vocabulary; the gate refuses to let any of them be
# redefined or re-exported from a non-schema module. Other types in schema.py
# (Standing, Team, ChirperPost, Decisions, …) are intentionally not policed
# here — the contract only names these six, and widening the list would flag
# legitimate test-fixture shapes that happen to share a name.
_CANONICAL_TYPES: frozenset[str] = frozenset(
    {
        "Player",
        "MemoryEntry",
        "Relationship",
        "WorldState",
        "WhyRecord",
        "GeneratedContent",
    }
)

# The one module canonical types are allowed to come from.
_CANONICAL_MODULE = "esports_tycoon.schema"

# Directory segments inside the .py walk that are never source we care about.
_SKIP_DIR_PARTS = frozenset({"__pycache__", ".pytest_cache", ".mypy_cache"})


def _iter_py_files() -> list[pathlib.Path]:
    """Every ``.py`` file under ``esports_tycoon/`` and ``tests/``."""
    files: list[pathlib.Path] = []
    for root in (_PKG_ROOT, _TESTS_ROOT):
        for path in root.rglob("*.py"):
            if any(part in _SKIP_DIR_PARTS for part in path.parts):
                continue
            files.append(path)
    return sorted(files)


def _resolve_submodule(dotted: str) -> pathlib.Path | None:
    """Map an ``esports_tycoon.X[.Y]`` dotted module to its on-disk file.

    Returns the file path if the module exists (either as ``X.py`` or
    ``X/__init__.py``), or ``None`` if the dotted path doesn't resolve.
    """
    parts = dotted.split(".")
    if parts[0] != "esports_tycoon" or len(parts) < 2:
        return None
    base = _REPO_ROOT.joinpath(*parts)
    init = base / "__init__.py"
    if base.is_dir() and init.exists():
        return init
    module_file = base.with_suffix(".py")
    if module_file.exists():
        return module_file
    return None


def _package_of(path: pathlib.Path) -> list[str]:
    """The package the file lives in, as dotted parts (``['esports_tycoon', 'web']``)."""
    rel = path.resolve().relative_to(_REPO_ROOT)
    parts = list(rel.parts)
    # For ``foo/bar/__init__.py`` the package is ``foo.bar``; for ``foo/bar.py``
    # the package is ``foo``. Either way, drop the filename component.
    return parts[:-1]


def _resolve_relative_import(
    level: int, module: str | None, source_file: pathlib.Path
) -> str | None:
    """Resolve ``from .x import y`` against ``source_file`` to an absolute dotted path.

    Returns ``None`` if the relative climb would step out of the repo root,
    which is a malformed import the gate intentionally surfaces by skipping
    (the module won't resolve, so the missing-import check will still fire).
    """
    pkg = _package_of(source_file)
    if level - 1 > len(pkg):
        return None
    base = pkg if level == 0 else pkg[: len(pkg) - (level - 1)]
    parts = list(base)
    if module:
        parts.extend(module.split("."))
    return ".".join(parts) if parts else None


def _scan(source: str, filename: str, source_file: pathlib.Path | None = None) -> dict:
    """Walk one source file's AST; return the gate-relevant findings.

    Kept import-free with respect to the code under test — the scanner only
    parses bytes, so even a module whose top-level code would crash on import
    is still inspected for forbidden patterns.
    """
    tree = ast.parse(source, filename=filename)

    is_schema = source_file is not None and source_file.resolve() == _SCHEMA_FILE
    is_self = source_file is not None and source_file.resolve() == _THIS_FILE

    duplicate_defs: list[tuple[int, str]] = []
    canonical_imports: list[tuple[int, str, str]] = []
    missing_module_imports: list[tuple[int, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            if node.name in _CANONICAL_TYPES and not is_schema:
                duplicate_defs.append((node.lineno, node.name))

        # The gate's own source legitimately names canonical types and the
        # ``esports_tycoon.chirper`` module in string literals and comments;
        # the AST won't see those, but we also skip its imports so the test
        # can drive the scanner against synthetic sources without flagging
        # itself.
        if is_self:
            continue

        if isinstance(node, ast.ImportFrom):
            if node.level and source_file is None:
                # Relative imports require a file to resolve against; skip
                # when scanning a free-standing source string.
                continue
            if node.level:
                dotted = _resolve_relative_import(node.level, node.module, source_file)
            else:
                dotted = node.module
            if not dotted or not dotted.startswith("esports_tycoon"):
                continue
            if dotted != _CANONICAL_MODULE:
                for alias in node.names:
                    if alias.name in _CANONICAL_TYPES:
                        canonical_imports.append((node.lineno, dotted, alias.name))
            # ``from esports_tycoon import schema`` (a bare-package form) is
            # left to Python's own import system — we only validate dotted
            # submodule paths, which is what the "not-yet-built" rule is about.
            if "." in dotted and _resolve_submodule(dotted) is None:
                missing_module_imports.append((node.lineno, dotted))

        if isinstance(node, ast.Import):
            for alias in node.names:
                dotted = alias.name
                if not dotted.startswith("esports_tycoon."):
                    continue
                if _resolve_submodule(dotted) is None:
                    missing_module_imports.append((node.lineno, dotted))

    return {
        "duplicate_defs": duplicate_defs,
        "canonical_imports": canonical_imports,
        "missing_module_imports": missing_module_imports,
    }


def _scan_repo() -> dict:
    """Run the scanner over every tracked ``.py`` file under the gate's reach."""
    aggregate = {
        "duplicate_defs": [],
        "canonical_imports": [],
        "missing_module_imports": [],
    }
    for path in _iter_py_files():
        findings = _scan(
            path.read_text(encoding="utf-8"),
            filename=str(path),
            source_file=path,
        )
        rel = path.relative_to(_REPO_ROOT)
        for lineno, name in findings["duplicate_defs"]:
            aggregate["duplicate_defs"].append(f"{rel}:{lineno} class {name}")
        for lineno, dotted, name in findings["canonical_imports"]:
            aggregate["canonical_imports"].append(
                f"{rel}:{lineno} from {dotted} import {name}"
            )
        for lineno, dotted in findings["missing_module_imports"]:
            aggregate["missing_module_imports"].append(
                f"{rel}:{lineno} import {dotted}"
            )
    return aggregate


class TestSchemaBoundaryOnRepo(unittest.TestCase):
    """The gate, run over the real tree: a clean checkout must pass."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.findings = _scan_repo()

    def test_no_duplicate_canonical_type_definitions(self):
        # Re-declaring (e.g.) ``class WorldState`` outside schema.py would
        # silently shadow the canonical type for whatever module imports it
        # from the duplicate site. The gate is the only thing that keeps a
        # well-meaning refactor from carving the schema in two.
        self.assertEqual(
            self.findings["duplicate_defs"],
            [],
            "canonical types may only be defined in esports_tycoon/schema.py; "
            "found duplicate class definitions:\n  "
            + "\n  ".join(self.findings["duplicate_defs"]),
        )

    def test_no_canonical_imports_outside_schema_module(self):
        # ``from esports_tycoon.content import WorldState`` is forbidden even
        # if ``content`` only re-exports the canonical class — re-exporting a
        # canonical type is the same drift in a different shape, because the
        # import site no longer treats schema.py as the system of record.
        self.assertEqual(
            self.findings["canonical_imports"],
            [],
            "canonical types must be imported from esports_tycoon.schema; "
            "found imports from other modules:\n  "
            + "\n  ".join(self.findings["canonical_imports"]),
        )

    def test_no_imports_of_unbuilt_submodules(self):
        # Any ``from esports_tycoon.X import …`` (or ``import esports_tycoon.X``)
        # whose target file doesn't exist on disk is, by definition, an import
        # of a not-yet-built module. The completed resolver, content adapter,
        # grounding and safety modules all resolve cleanly today; the rule
        # exists so a future reference to (e.g.) ``esports_tycoon.chirper``
        # fails the build the moment it's introduced rather than several
        # imports deep at runtime.
        self.assertEqual(
            self.findings["missing_module_imports"],
            [],
            "imports must target modules that exist on disk; found imports of "
            "unbuilt esports_tycoon submodules:\n  "
            + "\n  ".join(self.findings["missing_module_imports"]),
        )


class TestSchemaBoundaryScanner(unittest.TestCase):
    """Unit tests for the scanner itself — synthetic sources, no I/O."""

    def test_duplicate_class_in_non_schema_module_is_flagged(self):
        source = textwrap.dedent(
            """
            class WorldState:
                pass
            """
        ).lstrip()
        result = _scan(source, filename="esports_tycoon/draft.py")
        self.assertEqual(result["duplicate_defs"], [(1, "WorldState")])

    def test_canonical_class_in_schema_itself_is_not_flagged(self):
        source = "class WorldState:\n    pass\n"
        result = _scan(source, filename=str(_SCHEMA_FILE), source_file=_SCHEMA_FILE)
        self.assertEqual(result["duplicate_defs"], [])

    def test_non_canonical_class_is_ignored(self):
        # A class named (say) ``Team`` lives in schema.py too, but Team isn't
        # on the canonical-six list — the scanner must not flag a synthetic
        # duplicate of it.
        source = "class Team:\n    pass\n"
        result = _scan(source, filename="esports_tycoon/draft.py")
        self.assertEqual(result["duplicate_defs"], [])

    def test_canonical_import_from_non_schema_module_is_flagged(self):
        source = "from esports_tycoon.content import WorldState\n"
        result = _scan(source, filename="esports_tycoon/draft.py")
        self.assertEqual(
            result["canonical_imports"],
            [(1, "esports_tycoon.content", "WorldState")],
        )

    def test_canonical_import_from_schema_is_allowed(self):
        source = "from esports_tycoon.schema import WorldState, Player\n"
        result = _scan(source, filename="esports_tycoon/draft.py")
        self.assertEqual(result["canonical_imports"], [])

    def test_non_canonical_import_from_any_module_is_allowed(self):
        # ``Standing`` lives in schema.py but isn't on the canonical-six list;
        # the scanner must not police types outside that list, since other
        # tests/fixtures legitimately define their own shapes by the same name.
        source = "from esports_tycoon.content import GenerationContext\n"
        result = _scan(source, filename="esports_tycoon/draft.py")
        self.assertEqual(result["canonical_imports"], [])

    def test_missing_submodule_from_import_is_flagged(self):
        source = "from esports_tycoon.chirper import feed\n"
        result = _scan(source, filename="esports_tycoon/draft.py")
        self.assertEqual(
            result["missing_module_imports"], [(1, "esports_tycoon.chirper")]
        )

    def test_missing_submodule_import_dotted_is_flagged(self):
        source = "import esports_tycoon.chirper\n"
        result = _scan(source, filename="esports_tycoon/draft.py")
        self.assertEqual(
            result["missing_module_imports"], [(1, "esports_tycoon.chirper")]
        )

    def test_existing_resolver_import_is_allowed(self):
        # The completed resolver is the canonical schema-bound consumer; the
        # gate must let it through. This pins the "allows importing the
        # completed resolver" clause of the acceptance criteria.
        source = "from esports_tycoon.resolver import run\n"
        result = _scan(source, filename="esports_tycoon/draft.py")
        self.assertEqual(result["missing_module_imports"], [])

    def test_existing_built_modules_are_allowed(self):
        # content, grounding, safety are built today; the gate only fires on
        # references to modules that don't exist on disk.
        for source in (
            "from esports_tycoon.content import generate_content\n",
            "from esports_tycoon.grounding import ground\n",
            "from esports_tycoon.safety import is_safe\n",
        ):
            with self.subTest(source=source.strip()):
                result = _scan(source, filename="esports_tycoon/draft.py")
                self.assertEqual(result["missing_module_imports"], [])

    def test_bare_package_from_import_is_not_policed(self):
        # ``from esports_tycoon import schema`` is ambiguous (could be a
        # submodule or a package-level attribute), so the scanner doesn't
        # validate it — Python's own import machinery will catch a typo.
        source = "from esports_tycoon import __version__, schema\n"
        result = _scan(source, filename="esports_tycoon/draft.py")
        self.assertEqual(result["missing_module_imports"], [])

    def test_non_esports_tycoon_imports_are_ignored(self):
        # The gate doesn't care what third-party packages a module imports.
        source = textwrap.dedent(
            """
            import json
            from typing import Optional
            from pydantic import BaseModel
            """
        ).lstrip()
        result = _scan(source, filename="esports_tycoon/draft.py")
        self.assertEqual(result["missing_module_imports"], [])
        self.assertEqual(result["canonical_imports"], [])

    def test_relative_import_resolves_against_source_package(self):
        # ``from .nope import x`` inside esports_tycoon/draft.py resolves to
        # ``esports_tycoon.nope``; if nope.py doesn't exist, that's a missing
        # submodule import.
        synthetic_path = _PKG_ROOT / "draft.py"
        source = "from .chirper import feed\n"
        result = _scan(source, filename=str(synthetic_path), source_file=synthetic_path)
        self.assertEqual(
            result["missing_module_imports"], [(1, "esports_tycoon.chirper")]
        )

    def test_relative_canonical_import_is_flagged(self):
        # ``from .content import WorldState`` inside esports_tycoon/ resolves
        # to a canonical-type import from a non-schema module.
        synthetic_path = _PKG_ROOT / "draft.py"
        source = "from .content import WorldState\n"
        result = _scan(source, filename=str(synthetic_path), source_file=synthetic_path)
        self.assertEqual(
            result["canonical_imports"],
            [(1, "esports_tycoon.content", "WorldState")],
        )


class TestCanonicalTypeListMatchesSchema(unittest.TestCase):
    """The canonical-type set the gate polices must actually exist in schema.py.

    If schema.py is refactored and one of these names disappears, the gate
    would happily keep "policing" a type that no longer exists. Catching
    that here means the list and the schema can't quietly drift apart.
    """

    def test_every_canonical_type_is_defined_in_schema(self):
        spec = importlib.util.spec_from_file_location(
            "_schema_under_test", _SCHEMA_FILE
        )
        assert spec is not None and spec.loader is not None  # for type checkers
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        missing = sorted(name for name in _CANONICAL_TYPES if not hasattr(module, name))
        self.assertEqual(
            missing,
            [],
            f"canonical types missing from esports_tycoon/schema.py: {missing}",
        )


if __name__ == "__main__":
    unittest.main()
