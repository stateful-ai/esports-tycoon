"""Direct tests for the canonical YAML serializer.

The loader-level round trip (``tests/test_loader.py``) and the committed golden
(``tests/test_golden_determinism.py``) exercise the canonical serializer
end-to-end on week6. This module pins its *contract* directly: the format
guarantees the loader and the golden rely on but never poke at — float
formatting (none today in week6), block style, key-order preservation, and the
trailing-newline invariant.
"""

import math
import pathlib
import sys
import unittest

import pytest
import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from esports_tycoon.canned import canonical  # noqa: E402

# M0 freeze (founder_brief.md): byte-identity serializer + canonical YAML/float
# formatting are deferred to M1/post-gate — they harden a contract the screenshot
# gate does not depend on, and re-enforcing them now would burn cycles that
# belong on the playable slice.
pytestmark = pytest.mark.skip(
    reason="M0 freeze: byte-identity serializer + canonical YAML/float formatting deferred to M1/post-gate"
)


class TestCanonicalFloatFormatting(unittest.TestCase):
    """Floats are emitted in a deterministic, round-trippable form."""

    def _round_trip(self, value):
        text = canonical.dumps({"v": value})
        return yaml.safe_load(text)["v"]

    def test_whole_float_keeps_dot_zero(self):
        # Naked ``1`` would round-trip as an int; the canonical form must keep
        # the trailing ``.0`` so the type survives a load → dump cycle.
        self.assertEqual(canonical.dumps({"v": 1.0}), "v: 1.0\n")

    def test_simple_fraction_is_shortest_form(self):
        self.assertEqual(canonical.dumps({"v": 0.5}), "v: 0.5\n")

    def test_small_value_uses_dotted_scientific_form(self):
        # YAML 1.1's implicit float resolver requires a dot in the mantissa, so
        # ``1e-05`` (what ``repr`` would emit) gets a ``.0`` spliced in. Without
        # the dot PyYAML would have to fall back to an explicit ``!!float`` tag.
        text = canonical.dumps({"v": 1e-5})
        self.assertEqual(text, "v: 1.0e-05\n")
        self.assertNotIn("!!float", text)
        self.assertEqual(self._round_trip(1e-5), 1e-5)

    def test_large_value_round_trips_as_float(self):
        # ``repr(1e20)`` is ``'1e+20'`` — no dot. If the serializer emitted that
        # raw, YAML 1.1 would not match it implicitly as a float and PyYAML
        # would tag it. The dot-splice keeps the type clean on the way back.
        text = canonical.dumps({"v": 1e20})
        self.assertEqual(text, "v: 1.0e+20\n")
        self.assertIsInstance(self._round_trip(1e20), float)

    def test_negative_zero_round_trips(self):
        # ``-0.0`` is a distinct float bit pattern; the canonical form keeps it.
        text = canonical.dumps({"v": -0.0})
        loaded = yaml.safe_load(text)["v"]
        self.assertTrue(math.copysign(1.0, loaded) < 0)

    def test_nan_uses_canonical_token(self):
        self.assertEqual(canonical.dumps({"v": float("nan")}), "v: .nan\n")

    def test_positive_infinity_uses_canonical_token(self):
        self.assertEqual(canonical.dumps({"v": float("inf")}), "v: .inf\n")

    def test_negative_infinity_uses_canonical_token(self):
        self.assertEqual(canonical.dumps({"v": float("-inf")}), "v: -.inf\n")

    def test_repeated_dump_is_byte_identical(self):
        # Whatever the float, two dumps of the same input yield the same bytes.
        data = {"a": 1.0, "b": 0.5, "c": 1e-5, "d": -0.0, "e": float("inf")}
        self.assertEqual(canonical.dumps(data), canonical.dumps(data))


class TestCanonicalKeyOrder(unittest.TestCase):
    """Key order is what the caller hands in, not what PyYAML feels like."""

    def test_keys_are_emitted_in_input_order(self):
        # ``sort_keys=False``: the canonical form is the schema's declaration
        # order (which is how the saved dict reaches us via Pydantic), not
        # alphabetical. Re-ordering keys would re-write every save on every dump.
        data = {"zebra": 1, "alpha": 2, "mike": 3}
        text = canonical.dumps(data)
        self.assertEqual(text, "zebra: 1\nalpha: 2\nmike: 3\n")

    def test_dump_load_dump_is_a_fixed_point(self):
        # The general round-trip contract on an arbitrary nested dict: dumping
        # the parsed bytes produces byte-identical output. This is the property
        # week6's golden relies on, asserted here without the schema layer.
        data = {
            "schema_version": 0,
            "items": [
                {"id": "a", "values": [1, 2, 3]},
                {"id": "b", "values": [4, 5, 6]},
            ],
            "meta": {"note": "Em-dash — ok; accent é ok"},
        }
        first = canonical.dumps(data)
        second = canonical.dumps(yaml.safe_load(first))
        self.assertEqual(first, second)


class TestCanonicalDocumentShape(unittest.TestCase):
    """The document-level invariants every canonical dump must satisfy."""

    def test_block_style_is_forced(self):
        # No flow-style ``[...]`` / ``{...}`` even on short scalar lists.
        text = canonical.dumps({"items": [1, 2, 3]})
        self.assertNotIn("[", text)
        self.assertNotIn("{", text)

    def test_unicode_is_emitted_verbatim(self):
        # The save carries em-dashes and accented names; escaping them to
        # ``—`` would break the readable diff the canonical form promises.
        text = canonical.dumps({"v": "Spring — Split"})
        self.assertIn("—", text)
        self.assertNotIn("\\u", text)

    def test_output_ends_with_exactly_one_newline(self):
        text = canonical.dumps({"a": 1})
        self.assertTrue(text.endswith("\n"))
        self.assertFalse(text.endswith("\n\n"))

    def test_safe_dump_global_is_untouched(self):
        # The canonical dumper subclasses SafeDumper; mutating the global
        # representer table would leak the float convention to every other
        # ``yaml.safe_dump`` call in the project. This test would trip if a
        # future edit went back to ``yaml.SafeDumper.add_representer``.
        self.assertEqual(yaml.safe_dump({"v": 1e-5}), "v: 1.0e-05\n")


if __name__ == "__main__":
    unittest.main()
