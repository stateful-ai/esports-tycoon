"""``saves/SCHEMA.md`` documents every save-schema field, and the loader links it.

The acceptance bar is "every schema field has a one-line description and the
loader links it". These tests guard both halves: they walk every pydantic
model that appears in a save and assert each field has a backticked entry in
``saves/SCHEMA.md``, and they assert :mod:`esports_tycoon.canned.loader` points
at the file (so the code → docs jump cannot silently rot).
"""

from __future__ import annotations

import pathlib
import re
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from esports_tycoon import schema  # noqa: E402
from esports_tycoon.canned import canonical, loader  # noqa: E402

# Every pydantic model whose fields appear in a save document, in load order.
# The resolver/content-adapter output types (``Decisions``, ``WhyRecord``,
# ``GeneratedContent``, ``KeyMoment``, ``RoundResult``) are not save-shaped, so
# they are deliberately excluded — SCHEMA.md documents the on-disk save, not
# every BaseModel in the package.
_SAVE_MODELS = [
    schema.WorldState,
    schema.SaveMeta,
    schema.Season,
    schema.Team,
    schema.Standing,
    schema.Player,
    schema.Relationship,
    schema.MemoryEntry,
    schema.ClashPair,
    schema.Rival,
    schema.RivalStar,
    schema.LastWeek,
    schema.Scoreline,
    schema.MapResult,
    schema.ChirperPost,
]


def _serialized_field_names(model: type) -> list[str]:
    """The names a field is *serialized* under (alias if it has one, else name)."""
    names: list[str] = []
    for field_name, info in model.model_fields.items():
        names.append(info.alias if info.alias else field_name)
    return names


class TestSchemaDoc(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc_path = (
            pathlib.Path(__file__).resolve().parents[1] / "saves" / "SCHEMA.md"
        )
        cls.text = cls.doc_path.read_text(encoding="utf-8")

    def test_doc_exists(self):
        self.assertTrue(self.doc_path.is_file(), f"missing {self.doc_path}")

    def test_loader_pins_doc_path(self):
        # The loader is the seam between the typed schema and SCHEMA.md; if the
        # doc moves, this is the one place to update.
        self.assertEqual(loader.SCHEMA_DOC_PATH, self.doc_path)

    def test_loader_module_docstring_references_doc(self):
        # The module docstring must surface the link too — anyone reading the
        # loader source for the first time has to learn the page exists.
        self.assertIn("SCHEMA.md", loader.__doc__ or "")

    def test_every_save_field_is_documented(self):
        # Each field name appears as a backticked token in SCHEMA.md (e.g.
        # `seed`). Backticks rather than a bare substring search avoid matching
        # prose mentions of a common word.
        backticked = set(re.findall(r"`([A-Za-z_][A-Za-z0-9_]*)`", self.text))
        missing: list[str] = []
        for model in _SAVE_MODELS:
            for field in _serialized_field_names(model):
                if field not in backticked:
                    missing.append(f"{model.__name__}.{field}")
        self.assertFalse(missing, f"undocumented save fields in SCHEMA.md: {missing}")

    def test_each_field_row_has_a_description(self):
        # SCHEMA.md is a set of Markdown tables ``| field | type | description |``.
        # A description column with fewer than ~6 non-whitespace characters is a
        # placeholder, not a real one-line description — fail loudly.
        row_re = re.compile(r"^\|\s*`([^`|]+)`\s*\|([^|]*)\|([^|]+)\|\s*$", re.MULTILINE)
        thin: list[tuple[str, str]] = []
        seen = 0
        for match in row_re.finditer(self.text):
            field, _type, desc = (match.group(1), match.group(2), match.group(3))
            seen += 1
            if len(desc.strip()) < 6:
                thin.append((field, desc.strip()))
        # Sanity: the file is a table-driven reference, so we expect many rows.
        # Sum the field counts of every save model and demand at least that many
        # documented rows. The same field name may appear in more than one
        # table row when two models share it (e.g. ``id``), and that's fine —
        # the per-field check above is the strict one; this is just a smoke that
        # the table didn't collapse.
        expected_min = sum(len(_serialized_field_names(m)) for m in _SAVE_MODELS)
        self.assertGreaterEqual(seen, expected_min)
        self.assertFalse(thin, f"SCHEMA.md rows without a real description: {thin}")


class TestByteIdentityContractDoc(unittest.TestCase):
    """``saves/SCHEMA.md`` documents the byte-identity normalization contract.

    The serializer and the round-trip golden both depend on a single written
    rule for key order, float repr, trailing newline, and unicode. These
    tests guard the documentation half of that contract: the section exists,
    each of the four named rules has a backticked anchor (so the section
    can't decay into prose that names the topic without spelling the rule),
    and the code → docs jump from
    :data:`esports_tycoon.canned.canonical.CONTRACT_DOC_ANCHOR` lands on a
    real heading.
    """

    @classmethod
    def setUpClass(cls):
        cls.doc_path = (
            pathlib.Path(__file__).resolve().parents[1] / "saves" / "SCHEMA.md"
        )
        cls.text = cls.doc_path.read_text(encoding="utf-8")

    def test_contract_section_heading_exists(self):
        # The anchor pinned in the canonical module must land on a real
        # ``## …`` heading in SCHEMA.md; the assertion is the bridge between
        # the code-side seam and the docs-side seam.
        heading = f"## {canonical.CONTRACT_DOC_ANCHOR}"
        self.assertIn(heading, self.text, f"missing SCHEMA.md heading {heading!r}")

    def test_contract_section_documents_each_named_rule(self):
        # The four rules the acceptance bar names — key order, float repr,
        # trailing newline, unicode — must each be called out in the
        # contract section by a recognisable backticked token, so the
        # section can't silently collapse to a stub.
        heading = f"## {canonical.CONTRACT_DOC_ANCHOR}"
        start = self.text.index(heading)
        # Bound the search to this section; the next ``## `` (or EOF) ends it.
        rest = self.text[start + len(heading):]
        end = rest.find("\n## ")
        section = rest if end < 0 else rest[:end]
        section_lower = section.lower()
        missing: list[str] = []
        # Each rule is paired with at least one concrete token a reader can
        # grep for, so a reword can't silently drop the rule itself.
        rule_signals = {
            "key order": ("key order", "iteration order"),
            "float repr": ("repr", ".nan"),
            "trailing newline": ("trailing newline",),
            "unicode": ("unicode", "allow_unicode"),
        }
        for rule, tokens in rule_signals.items():
            if not any(token.lower() in section_lower for token in tokens):
                missing.append(rule)
        self.assertFalse(
            missing,
            f"byte-identity contract section is missing rules: {missing}",
        )


class TestReadmeZeroApiQuickstart(unittest.TestCase):
    """The README documents the one-command, no-API-key run a fresh clone uses."""

    @classmethod
    def setUpClass(cls):
        cls.readme = (
            pathlib.Path(__file__).resolve().parents[1] / "README.md"
        ).read_text(encoding="utf-8")
        cls.lower = cls.readme.lower()

    def test_has_zero_api_quickstart_section(self):
        self.assertIn("zero-api quickstart", self.lower)

    def test_quickstart_is_no_api_no_network(self):
        # The acceptance bar is "no API key". Spell it out so a fresh-clone
        # reader can't miss it.
        self.assertIn("no api key", self.lower)
        # The templated backend is also the no-network claim; surface it.
        self.assertIn("no network", self.lower)

    def test_quickstart_documents_one_command_run(self):
        # The headline one-command path is `python -m esports_tycoon play`.
        self.assertIn("python -m esports_tycoon play", self.readme)

    def test_quickstart_covers_week_6_to_8(self):
        # The acceptance bar names "Week 6→8". The canned save is Week 6 of 8;
        # the runner can be re-run against any rival id, so the README shows the
        # 6 → 7 → 8 slate against three rivals.
        self.assertRegex(self.lower, r"6\s*(?:→|->|-+>)\s*7\s*(?:→|->|-+>)\s*8")
        # Each of the three rival ids the slate uses must appear in the README.
        for rival in ("apex_foundry", "sovereign", "last_light"):
            self.assertIn(rival, self.readme, f"rival id missing from quickstart: {rival}")

    def test_quickstart_links_schema_doc(self):
        self.assertIn("saves/SCHEMA.md", self.readme)


if __name__ == "__main__":
    unittest.main()
