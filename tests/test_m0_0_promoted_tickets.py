"""The three M0.0 enablers promoted from DoD line items to active tickets.

[`docs/m0_0_promoted_tickets.md`](../docs/m0_0_promoted_tickets.md) is the
durable record of that promotion. This module is its regression net: it pins
the *artifact* (the doc names three tickets with acceptance criteria), the
*cross-reference* (`docs/founder_brief.md`'s W1/W3/W4 lines cite each ticket
by id), and the *implementation seams* each ticket points to (the four
toolchain-pin files, ``scripts/regen_golden.py``, and the shared
:class:`~esports_tycoon.canned.loader.SaveError` contract).

A single module so the three halves move together: promoting a ticket without
wiring it into the W-lines, or letting an implementation seam regress out from
under a ticket's acceptance bar, leaves the doc claiming a contract the
codebase no longer keeps. The pin trips before the contradiction lands.
"""

from __future__ import annotations

import pathlib
import re
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from esports_tycoon.canned import loader  # noqa: E402

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
_TICKETS_DOC = _REPO_ROOT / "docs" / "m0_0_promoted_tickets.md"
_FOUNDER_BRIEF = _REPO_ROOT / "docs" / "founder_brief.md"
_INDEX_DOC = _REPO_ROOT / "docs" / "INDEX.md"

# The three tickets and the W-lines each one unblocks. Encoded once here so the
# rest of the module stays declarative; a change to either the id grammar or
# the W-mapping lands as a deliberate edit to this table.
_TICKETS: tuple[tuple[str, str, frozenset[str]], ...] = (
    ("M0.0-T1", "Pin the serialization toolchain", frozenset({"W1", "W3", "W4"})),
    ("M0.0-T2", "Deterministic golden-bless script", frozenset({"W1", "W4"})),
    ("M0.0-T3", "Shared typed `SaveError` contract", frozenset({"W3", "W4"})),
)


class TestPromotedTicketsDoc(unittest.TestCase):
    """``docs/m0_0_promoted_tickets.md`` names each ticket with acceptance criteria."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.text = _TICKETS_DOC.read_text(encoding="utf-8")

    def test_doc_exists(self) -> None:
        # The whole promotion is anchored on this file existing — a deletion
        # or rename would leave the W-line citations dangling.
        self.assertTrue(
            _TICKETS_DOC.exists(),
            "docs/m0_0_promoted_tickets.md is the durable promotion record",
        )

    def test_each_ticket_has_a_named_section(self) -> None:
        # The three tickets must each have a ``## M0.0-Tn — <title>`` heading.
        # The exact title pins which ticket got which id, so a future edit
        # that renamed (say) T1 to a different surface trips here.
        for ticket_id, title, _ in _TICKETS:
            with self.subTest(ticket=ticket_id):
                heading = f"## {ticket_id} — {title}"
                self.assertIn(
                    heading,
                    self.text,
                    f"ticket {ticket_id} must have a section ``{heading}``",
                )

    def test_each_ticket_carries_an_acceptance_criteria_block(self) -> None:
        # An "active ticket with acceptance criteria" is the literal acceptance
        # of this promotion task — every ticket section must carry an
        # ``**Acceptance criteria.**`` block with at least one numbered bar.
        # Slice the text into per-ticket sections so a missing block on one
        # ticket cannot be papered over by another's.
        sections = self._split_by_ticket_section()
        for ticket_id, _, _ in _TICKETS:
            with self.subTest(ticket=ticket_id):
                section = sections[ticket_id]
                self.assertIn(
                    "**Acceptance criteria.**",
                    section,
                    f"{ticket_id} must carry a ``**Acceptance criteria.**`` block",
                )
                # At least one numbered bar after the header. A ticket whose
                # acceptance reduces to prose isn't reviewable.
                acceptance_start = section.index("**Acceptance criteria.**")
                tail = section[acceptance_start:]
                self.assertRegex(
                    tail,
                    r"\n\s*1\.\s+\S",
                    f"{ticket_id}'s acceptance criteria must include a numbered list",
                )

    def test_each_ticket_names_the_w_lines_it_unblocks(self) -> None:
        # The cross-reference acceptance ("they are referenced by the W1/W3/W4
        # DoD lines they unblock") is symmetrical: each ticket's section must
        # name every W-line it unblocks under an ``**Unblocks.**`` heading, so
        # a reader landing on a ticket can trace it forward to the W-lines.
        sections = self._split_by_ticket_section()
        for ticket_id, _, w_lines in _TICKETS:
            with self.subTest(ticket=ticket_id):
                section = sections[ticket_id]
                self.assertIn(
                    "**Unblocks.**",
                    section,
                    f"{ticket_id} must carry a ``**Unblocks.**`` heading",
                )
                for w_line in sorted(w_lines):
                    self.assertRegex(
                        section,
                        rf"\*\*{w_line}\*\*(?=\s|$)",
                        f"{ticket_id}'s Unblocks block must name **{w_line}**",
                    )

    def _split_by_ticket_section(self) -> dict[str, str]:
        # Slice on the ``## M0.0-Tn`` headings; each section runs up to (but
        # not including) the next ``## `` heading. A ticket section that
        # disappeared from the doc would produce a ``KeyError`` here, which
        # the per-ticket subtests above turn into a clearer failure.
        marker = re.compile(r"^## (M0\.0-T\d+) —", re.MULTILINE)
        positions = [
            (match.group(1), match.start()) for match in marker.finditer(self.text)
        ]
        positions.append(("__END__", len(self.text)))
        sections: dict[str, str] = {}
        for (ticket_id, start), (_, next_start) in zip(positions, positions[1:]):
            sections[ticket_id] = self.text[start:next_start]
        return sections


class TestFounderBriefCitesTicketsOnWLines(unittest.TestCase):
    """``docs/founder_brief.md``'s W1/W3/W4 critical-path line cites each ticket."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.text = _FOUNDER_BRIEF.read_text(encoding="utf-8")

    def test_critical_path_line_exists(self) -> None:
        # The W0→W4 sequencing line is the spine the citations attach to; a
        # rewrite that dropped it would leave the M0.0 tickets unanchored
        # from the W-lines they're meant to unblock.
        self.assertRegex(
            self.text,
            r"Critical path:.*W0.*W1.*W2.*W3.*W4",
            "founder_brief.md must keep the W0→W4 critical-path line",
        )

    def test_each_ticket_id_appears_on_the_critical_path_line(self) -> None:
        # The acceptance is that each ticket is "referenced by the W1/W3/W4 DoD
        # lines they unblock"; the simplest in-doc enforcement is that every
        # ticket id shows up on the critical-path line itself, alongside the
        # W-line(s) it unblocks. Restrict the search to that one line so a
        # passing reference (say, in a later footnote) cannot spoof the bar.
        critical_path_line = next(
            line for line in self.text.splitlines() if "Critical path:" in line
        )
        for ticket_id, _, _ in _TICKETS:
            with self.subTest(ticket=ticket_id):
                self.assertIn(
                    ticket_id,
                    critical_path_line,
                    f"founder_brief.md's critical-path line must cite {ticket_id} "
                    f"by id — the W-line it unblocks should name the ticket",
                )

    def test_critical_path_line_pairs_each_ticket_with_its_w_lines(self) -> None:
        # Sharper than mere presence: the ticket id must appear close to each
        # W-line it unblocks (within the same parenthetical aside on the
        # critical-path line). A future edit that named the ticket only under
        # an unrelated W-line — orphaning the cross-reference — fails here.
        critical_path_line = next(
            line for line in self.text.splitlines() if "Critical path:" in line
        )
        # Carve the line into per-W segments: each segment owns the text from
        # ``W<n>`` up to the next ``W<n+1>`` or the end of the line.
        segments = self._segment_by_w_line(critical_path_line)
        for ticket_id, _, w_lines in _TICKETS:
            for w_line in sorted(w_lines):
                with self.subTest(ticket=ticket_id, w=w_line):
                    self.assertIn(
                        ticket_id,
                        segments[w_line],
                        f"{w_line}'s segment of the critical-path line must "
                        f"name {ticket_id}, the ticket it unblocks",
                    )

    def test_critical_path_line_links_to_the_promoted_tickets_doc(self) -> None:
        # The W-line citation has to lead a reader to the doc that holds the
        # acceptance criteria. A bare ``M0.0-T1`` text without a link would
        # require the reader to guess the doc path; the link removes the guess.
        critical_path_line = next(
            line for line in self.text.splitlines() if "Critical path:" in line
        )
        self.assertIn("m0_0_promoted_tickets.md", critical_path_line)

    def _segment_by_w_line(self, line: str) -> dict[str, str]:
        markers: list[tuple[str, int]] = []
        for w_line in ("W0", "W1", "W2", "W3", "W4"):
            # Anchor to the first occurrence so a later mention of the same
            # W-line (in a parenthetical citation) doesn't relocate the
            # segment boundary.
            position = line.find(w_line)
            self.assertNotEqual(
                position,
                -1,
                f"critical-path line missing the {w_line} marker",
            )
            markers.append((w_line, position))
        markers.sort(key=lambda item: item[1])
        markers.append(("__END__", len(line)))
        segments: dict[str, str] = {}
        for (name, start), (_, end) in zip(markers, markers[1:]):
            segments[name] = line[start:end]
        return segments


class TestImplementationSeamsArePresent(unittest.TestCase):
    """The seams each ticket points to are present in-tree.

    A ticket is "active" only as long as the surface it names exists. These
    bars are deliberately shallow — they pin presence, not the per-bar
    contract that the existing tests
    (``test_toolchain_pin.py`` / ``test_regen_golden.py`` /
    ``test_referential_integrity.py``) carry on top — so this module trips on
    the *promotion* coming undone (a file deleted, a class renamed) rather
    than on the broader M1-scope contracts those tests pin.
    """

    # --- T1: serialization toolchain pin ----------------------------------- #
    def test_t1_pyproject_pins_single_python_minor(self) -> None:
        text = (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertRegex(
            text,
            r'requires-python\s*=\s*">=\s*3\.\d+\s*,\s*<\s*3\.\d+\s*"',
            "pyproject.toml must pin a single Python minor with a lower AND "
            "upper bound (M0.0-T1 acceptance criterion 1)",
        )

    def test_t1_constraints_file_pins_byte_identity_libs(self) -> None:
        # The five byte-identity-affecting libraries M0.0-T1 names. Pinned
        # with ``==``; a slipped pin re-shapes the canonical bytes on a clean
        # checkout.
        text = (_REPO_ROOT / "constraints.txt").read_text(encoding="utf-8")
        for name in ("PyYAML", "pydantic", "pydantic_core",
                     "typing_extensions", "annotated-types"):
            with self.subTest(library=name):
                self.assertRegex(
                    text,
                    rf"(?m)^{re.escape(name)}==[A-Za-z0-9_.\-+]+\s*$",
                    f"constraints.txt must pin {name} with == "
                    "(M0.0-T1 acceptance criterion 2)",
                )

    def test_t1_makefile_install_passes_constraints_to_pip(self) -> None:
        text = (_REPO_ROOT / "Makefile").read_text(encoding="utf-8")
        self.assertRegex(
            text,
            r"pip install\b[^\n]*-c\s+[\"']?(?:\$\(CONSTRAINTS\)|constraints\.txt)",
            "Makefile install target must pass -c constraints.txt to pip "
            "(M0.0-T1 acceptance criterion 3)",
        )

    def test_t1_ci_workflow_uses_make_install(self) -> None:
        ci = _REPO_ROOT / ".github" / "workflows" / "ci.yml"
        self.assertTrue(ci.exists(), "CI workflow must exist")
        self.assertRegex(
            ci.read_text(encoding="utf-8"),
            r"\bmake install\b",
            "CI workflow must invoke make install so the constraints pass "
            "runs in CI too (M0.0-T1 acceptance criterion 3)",
        )

    # --- T2: deterministic golden-bless script ----------------------------- #
    def test_t2_regen_golden_script_exists_and_is_callable(self) -> None:
        from scripts import regen_golden

        self.assertTrue(
            hasattr(regen_golden, "regenerate"),
            "scripts/regen_golden.py must expose regenerate(...) "
            "(M0.0-T2 acceptance criterion 1)",
        )
        self.assertTrue(
            hasattr(regen_golden, "main"),
            "scripts/regen_golden.py must expose main(...) for CLI use "
            "(M0.0-T2 acceptance criterion 4)",
        )

    def test_t2_check_flag_is_documented(self) -> None:
        # The ``--check`` mode is the CI-friendly form named in the ticket;
        # asserting it in the parser keeps the doc's promise that CI / pre-
        # commit can call this script with a non-mutating mode.
        from scripts import regen_golden

        # Capture argparse's help text rather than running the parser — a
        # missing flag fails here with a readable message.
        import io
        import contextlib

        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            try:
                regen_golden.main(["--help"])
            except SystemExit:
                pass  # argparse exits after printing help
        self.assertIn(
            "--check",
            buffer.getvalue(),
            "scripts/regen_golden.py must expose a --check flag "
            "(M0.0-T2 acceptance criterion 4)",
        )

    # --- T3: shared typed SaveError contract ------------------------------- #
    def test_t3_save_error_base_is_a_value_error(self) -> None:
        self.assertTrue(
            issubclass(loader.SaveError, ValueError),
            "SaveError must be a ValueError subclass for back-compat "
            "(M0.0-T3 acceptance criterion 1)",
        )

    def test_t3_save_error_carries_field_path_and_source(self) -> None:
        exc = loader.SaveError("boom", field_path="players[0].id", source="<x>")
        self.assertEqual(exc.field_path, "players[0].id")
        self.assertEqual(exc.source, "<x>")

    def test_t3_four_named_siblings_inherit_from_save_error(self) -> None:
        # The four failure categories the load path is responsible for, each
        # a SaveError subclass and each disjoint from its siblings.
        siblings = (
            loader.SaveYamlError,
            loader.SchemaVersionError,
            loader.SaveSchemaError,
            loader.SaveReferentialIntegrityError,
        )
        for subclass in siblings:
            with self.subTest(subclass=subclass.__name__):
                self.assertTrue(
                    issubclass(subclass, loader.SaveError),
                    f"{subclass.__name__} must inherit from SaveError "
                    "(M0.0-T3 acceptance criterion 2)",
                )
        # Disjoint siblings: no two share an ancestry below ``SaveError``.
        for i, left in enumerate(siblings):
            for right in siblings[i + 1 :]:
                with self.subTest(pair=(left.__name__, right.__name__)):
                    self.assertFalse(
                        issubclass(left, right) or issubclass(right, left),
                        f"{left.__name__} and {right.__name__} must be "
                        "disjoint siblings (M0.0-T3 acceptance criterion 2)",
                    )

    def test_t3_schema_version_error_defaults_field_path(self) -> None:
        # The version-gate's typed error has a known field path — the author
        # knows where to look without reading the message.
        exc = loader.SchemaVersionError("nope", source="<x>")
        self.assertEqual(
            exc.field_path,
            "schema_version",
            "SchemaVersionError.field_path must default to 'schema_version' "
            "(M0.0-T3 acceptance criterion 4)",
        )


class TestIndexLinksTheDoc(unittest.TestCase):
    """``docs/INDEX.md`` lists the promoted-tickets doc.

    The doc index is the discoverability surface for `docs/` — a doc that
    landed without an index entry is half-landed; a reader who finds the
    repo via the index would never see it.
    """

    def test_index_links_to_promoted_tickets_doc(self) -> None:
        text = _INDEX_DOC.read_text(encoding="utf-8")
        self.assertIn(
            "m0_0_promoted_tickets.md",
            text,
            "docs/INDEX.md must link the new promoted-tickets doc",
        )


if __name__ == "__main__":
    unittest.main()
