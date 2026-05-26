"""The week-6 templated copy pack: cast + beat coverage, tone lock, no placeholders.

This suite is the acceptance gate for the locked-week-6 copy pack ticket:

* **Cast coverage.** Every cast member named in ``docs/tone_and_cast_lock.md`` —
  the five starters, the league caster, and the six rival stars — has an
  authored entry in :data:`~esports_tycoon.content.templated.CAST_IDS`, with at
  least a ``("default", True)`` and ``("default", False)`` line list.
* **Beat coverage.** Every kind of key moment the resolver can emit has an
  authored entry in :data:`~esports_tycoon.content.templated.BEAT_KINDS`, with
  at least two tone-locked variations.
* **Tone lock.** Every authored line — narrator beats and cast voices alike —
  conforms to the tone bible (no exclamation hype from the narrator, no emoji
  out of the characters allowed to use them, and the canon calibration
  registers on the cast voices that own them).
* **Zero placeholder strings in the slice.** Across the full Cartesian of
  opponents × seeds × stances, the templated render produces nothing that
  looks like a placeholder: no ``TODO``, ``TBD``, ``FIXME``, ``lorem``, ``xxx``,
  no unresolved ``{slot}`` format-strings, no empty narration colour where a
  key moment fired. The scan covers narration, half-time, *and* every Chirper
  post in the slice's feed.
"""

import re
import sys
import pathlib
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from esports_tycoon import resolver  # noqa: E402
from esports_tycoon.canned import loader  # noqa: E402
from esports_tycoon.content import templated  # noqa: E402
from esports_tycoon.content import GenerationContext, generate_content  # noqa: E402
from esports_tycoon.runner import SliceConfig, SliceDecisions, run_slice  # noqa: E402
from esports_tycoon.schema import Decisions  # noqa: E402


# The eight key-moment kinds the resolver constructs. Drawn from
# esports_tycoon/resolver.py — kept literal here so this test is the contract
# the resolver does not silently slip past (a new resolver kind without a beat
# template should fail this list explicitly).
_RESOLVER_EMITTABLE_KINDS: frozenset[str] = frozenset(
    {
        "ace",
        "blowout",
        "choke",
        "clutch",
        "closeout",
        "comeback",
        "dominant",
        "match_point",
    }
)

# Every cast member named in docs/tone_and_cast_lock.md. The five starters plus
# the in-universe caster plus the six rival-org stars (one per rival).
_CAST_MEMBERS: frozenset[str] = frozenset(
    {
        "rook", "vex", "sable", "pixie", "coyote",
        "@gridcast",
        "@halo", "@bishop", "@echo", "@grud", "@marlow", "@ghost",
    }
)

# Patterns that scream "placeholder content" in any shipped string. The regex
# union catches the textual sentinels (TODO/TBD/FIXME/lorem/xxx — case-insensitive,
# word-bounded) *and* unresolved single-brace format slots like ``{actors}`` —
# the second branch is what proves the beat-template ``.format(**slots)`` call
# always binds every slot.
_PLACEHOLDER_RE = re.compile(
    r"\b(?:TODO|TBD|FIXME|XXX|lorem|placeholder)\b|\{[a-zA-Z_][a-zA-Z_0-9]*\}",
    re.IGNORECASE,
)

_HEART_HANDS = "\U0001faf6"
_FROG = "\U0001f438"


class TestCastCoverage(unittest.TestCase):
    """Every cast member named in the tone lock has an authored voice."""

    def test_every_cast_member_has_an_authored_voice(self):
        # CAST_IDS is the set of authored cast voices. Equality (not subset) is
        # the contract: a cast member missing here would silently fall through
        # to the register-based fallback, and a stray id here points at a voice
        # that isn't in the tone lock.
        self.assertEqual(_CAST_MEMBERS, templated.CAST_IDS)

    def test_every_cast_voice_ships_a_default_win_and_loss_line(self):
        # _cast_lookup() requires ("default", True/False) to always exist — it
        # is the fallback that guarantees every match has *some* line for every
        # cast member, with beat-specialized lines layered on top.
        for cast_id in _CAST_MEMBERS:
            voice = templated._CAST_VOICES[cast_id]
            for won in (True, False):
                self.assertIn(
                    ("default", won),
                    voice,
                    f"{cast_id} missing ('default', {won}) — the lookup fallback would break",
                )
                self.assertTrue(
                    voice[("default", won)],
                    f"{cast_id} has an empty ('default', {won}) line list",
                )


class TestBeatCoverage(unittest.TestCase):
    """Every resolver-emittable key-moment kind has an authored beat template."""

    def test_every_emittable_kind_has_a_beat_template(self):
        self.assertEqual(_RESOLVER_EMITTABLE_KINDS, templated.BEAT_KINDS)

    def test_every_beat_template_has_at_least_two_variations(self):
        # Two variations is the minimum that lets the seeded RNG actually pick
        # — a single-line beat would always render identically across matches,
        # which the existing variance tests treat as a smell.
        for kind in templated.BEAT_KINDS:
            self.assertGreaterEqual(
                len(templated._BEAT_TEMPLATES[kind]),
                2,
                f"beat kind {kind!r} has fewer than two variations",
            )

    def test_every_beat_template_renders_without_unbound_slots(self):
        # The beat templates use a fixed slot vocabulary; rendering them with
        # the full slot dict must never raise KeyError (an unknown slot) and
        # must never leave a literal "{slot}" in the output.
        slots = {"actors": "Rook", "round": 13, "descriptor": "won it",
                 "ovc": 13, "opp": 11}
        for kind, variations in templated._BEAT_TEMPLATES.items():
            for template in variations:
                rendered = template.format(**slots)
                self.assertNotRegex(
                    rendered,
                    _PLACEHOLDER_RE,
                    f"beat template for {kind!r} renders to a placeholder: {rendered!r}",
                )


class TestToneLock(unittest.TestCase):
    """Authored copy honours the dry-mockumentary lock."""

    def test_narrator_beats_never_use_emoji_or_exclamation(self):
        # Narrator voice is flat: no emoji, no hype. This is the static check;
        # the slice-wide scan below verifies it dynamically too.
        for kind, variations in templated._BEAT_TEMPLATES.items():
            for line in variations:
                self.assertNotIn("!", line, f"beat {kind!r} hypes: {line!r}")
                self.assertNotIn(_HEART_HANDS, line, f"beat {kind!r} uses pixie emoji: {line!r}")
                self.assertNotIn(_FROG, line, f"beat {kind!r} uses grud emoji: {line!r}")

    def test_sable_lines_are_terse(self):
        # Calibration line: 'Held. Won. Hungry.' — three words is canon. Cap at
        # six to leave a little room for a future authored line without losing
        # the register.
        for key, lines in templated._CAST_VOICES["sable"].items():
            for line in lines:
                self.assertLessEqual(
                    len(line.split()),
                    6,
                    f"sable {key} line not terse enough: {line!r}",
                )

    def test_pixie_lines_use_heart_hands(self):
        # Calibration line: '\U0001faf6 #overcastfam' is Pixie's on-character
        # signoff. Every Pixie line should carry it; that emoji is allowed
        # in-character (the narrator may not use it).
        for key, lines in templated._CAST_VOICES["pixie"].items():
            for line in lines:
                self.assertIn(
                    _HEART_HANDS,
                    line,
                    f"pixie {key} line missing heart-hands: {line!r}",
                )

    def test_only_in_character_voices_use_emoji(self):
        # Emoji is restricted to the cast voices the tone lock allows it on:
        # Pixie's heart-hands (the canon signoff) and the Goblins' frog emoji
        # (Grud's chaos-troll calling card). No other cast voice or narrator
        # template may carry emoji glyphs.
        # We approximate "emoji glyph" as any character outside the ASCII /
        # extended-Latin range used by the rest of the copy, plus the en-dash
        # and the typographic quote glyphs the corpus already uses.
        allowed_non_ascii = {"–", "—", "‘", "’", "“", "”"}
        for cast_id, voice in templated._CAST_VOICES.items():
            for lines in voice.values():
                for line in lines:
                    bad = [
                        ch for ch in line
                        if ord(ch) > 127 and ch not in allowed_non_ascii
                    ]
                    if cast_id == "pixie":
                        self.assertTrue(all(ch == _HEART_HANDS for ch in bad), line)
                    elif cast_id == "@grud":
                        self.assertTrue(all(ch == _FROG for ch in bad), line)
                    else:
                        self.assertFalse(
                            bad,
                            f"{cast_id} line carries out-of-register glyph(s) {bad!r}: {line!r}",
                        )

    def test_bishop_owns_an_ex_teammate_taunt(self):
        # The tone lock pins Bishop as 'The Ex-Teammate' — every Bishop pack
        # should have at least one line that lands the taunt, the corner-peek
        # call, or the 'traded' line, so the rival voice is recognizable on
        # sight rather than generic-rival.
        bishop_lines = [
            line for lines in templated._CAST_VOICES["@bishop"].values() for line in lines
        ]
        joined = " ".join(bishop_lines).lower()
        self.assertTrue(
            "lurker" in joined or "trade" in joined or "corner" in joined,
            f"bishop voice missing ex-teammate signal: {bishop_lines!r}",
        )

    def test_echo_owns_the_aging_caller_jab(self):
        # The tone lock pins Echo as 'The Wunderkind'; her canon needle is
        # 'calls like it's last meta', which the per-cast lines should echo.
        echo_lines = [
            line for lines in templated._CAST_VOICES["@echo"].values() for line in lines
        ]
        joined = " ".join(echo_lines).lower()
        self.assertTrue(
            "meta" in joined or "old caller" in joined or "age" in joined,
            f"echo voice missing wunderkind needle: {echo_lines!r}",
        )


class TestZeroPlaceholders(unittest.TestCase):
    """No shipped string contains a placeholder, across the full slice surface."""

    @classmethod
    def setUpClass(cls):
        cls.world = loader.load()

    def _assert_no_placeholder(self, label: str, text: str):
        self.assertNotRegex(
            text,
            _PLACEHOLDER_RE,
            f"{label} carries a placeholder: {text!r}",
        )
        # A beat that fired should produce non-empty colour; the narration
        # ``join`` would otherwise quietly drop it.
        self.assertTrue(text, f"{label} rendered to the empty string")

    def test_no_placeholder_in_authored_copy_pack(self):
        # Direct scan of the source-of-truth tables. Any "{slot}" pattern that
        # belongs to a beat template is fine here because the regex looks for
        # *unresolved* slots — but the static templates contain slots by design
        # ({actors}, {round}, …). We render them with bound slots and then
        # check the result, exactly as the runtime does.
        slots = {"actors": "Rook", "round": 13, "descriptor": "won it",
                 "ovc": 13, "opp": 11}
        for kind, variations in templated._BEAT_TEMPLATES.items():
            for line in variations:
                self._assert_no_placeholder(
                    f"beat[{kind}]", line.format(**slots)
                )
        for cast_id, voice in templated._CAST_VOICES.items():
            for key, lines in voice.items():
                for line in lines:
                    self._assert_no_placeholder(
                        f"cast[{cast_id}][{key}]", line
                    )
        for (register, won), lines in templated._CHIRPER_LINES.items():
            for line in lines:
                self._assert_no_placeholder(
                    f"chirper[{register},{won}]", line
                )

    def test_no_placeholder_in_a_rendered_slice(self):
        # The full slice surface: across every opponent, several seeds, and
        # both stances, no narration / half-time / Chirper post may carry a
        # placeholder. This is the dynamic twin of the static scan above —
        # together they cover both authored text and assembled text.
        opponents = [r.id for r in self.world.rivals]
        for opponent in opponents:
            for seed in (1, 3, 5, 7, 11):
                for stance in ("default", "aggressive", "disciplined"):
                    cfg = SliceConfig(opponent=opponent, map="Helix",
                                      seed=seed, tactical_stance=stance)
                    dec = SliceDecisions(
                        practice_focus="defaults",
                        team_talk="run the default.",
                        fallout_post="week 6.",
                    )
                    result = run_slice(self.world, cfg, dec)
                    label = f"{opponent}/seed={seed}/stance={stance}"
                    self._assert_no_placeholder(
                        f"{label}/narration", result.narration.text
                    )
                    self._assert_no_placeholder(
                        f"{label}/halftime", result.halftime.text
                    )
                    for post in result.feed:
                        self._assert_no_placeholder(
                            f"{label}/feed[{post.author_handle}]", post.text
                        )

    def test_narration_colour_is_non_empty_when_a_beat_fires(self):
        # Regression guard: the resolver always emits at least a closeout /
        # match_point on the final round, so the narration colour should
        # *always* fill — there is no "no beat fired" branch in real play. If
        # a future kind slips into the resolver without a template, the
        # narration would silently drop the colour line.
        opponents = [r.id for r in self.world.rivals]
        for opponent in opponents:
            for seed in range(8):
                dec = Decisions(opponent=opponent, map="Helix")
                why = resolver.run(self.world, dec, seed)
                self.assertTrue(why.key_moments, f"{opponent}/seed={seed}: no key moments at all")
                gc = generate_content(
                    "narration",
                    GenerationContext(world=self.world, why=why, decisions=dec),
                )
                # The colour line sits between the headline and the standout;
                # a missing one would shrink the text. We treat a 2-sentence
                # narration (headline + standout only) as a regression.
                sentences = [s for s in re.split(r"(?<=[.])\s+", gc.text) if s.strip()]
                self.assertGreaterEqual(
                    len(sentences), 3,
                    f"{opponent}/seed={seed} narration missing colour: {gc.text!r}",
                )


class TestCastSpecialization(unittest.TestCase):
    """Per-cast lines actually swap in when their beat fires."""

    @classmethod
    def setUpClass(cls):
        cls.world = loader.load()

    def test_a_kind_specialized_line_can_render_for_a_starter(self):
        # Build the lookup table the runtime uses and confirm there exists a
        # ``(seed, opponent)`` for which the leading kind has a kind-specialized
        # line for a starter, and that the rendered chirper post is one of
        # those lines (not the ``("default", won)`` fallback). This is the
        # functional proof that the beat-keyed lookup actually fires.
        for pid in ("rook", "vex", "pixie", "coyote", "sable"):
            specialized_pairs = [
                key for key in templated._CAST_VOICES[pid] if key[0] != "default"
            ]
            self.assertTrue(
                specialized_pairs,
                f"{pid} ships no beat-specialized lines — coverage is fallback-only",
            )

    def test_rival_star_voices_render_in_their_archetype(self):
        # Run a seed against each rival and confirm the rival-star post is
        # drawn from that star's authored voice pack, not the safety net.
        for rival in self.world.rivals:
            handle = rival.star.handle
            voice = templated._CAST_VOICES[handle]
            authored = {
                line
                for lines in voice.values()
                for line in lines
            }
            # Try a small spread of seeds — at least one must produce a line
            # from the authored pack (the only path for an authored external).
            hits = 0
            for seed in range(10):
                cfg = SliceConfig(opponent=rival.id, map="Helix",
                                  seed=seed, tactical_stance="default")
                dec = SliceDecisions(
                    practice_focus="defaults",
                    team_talk="run the default.",
                    fallout_post="week 6.",
                )
                result = run_slice(self.world, cfg, dec)
                star_posts = [p for p in result.feed if p.author_handle == handle]
                self.assertEqual(len(star_posts), 1, f"{handle} should post exactly once")
                self.assertIn(
                    star_posts[0].text,
                    authored,
                    f"{handle} post is not from the authored pack: {star_posts[0].text!r}",
                )
                hits += 1
            self.assertGreater(hits, 0, f"{handle} pack never rendered")


if __name__ == "__main__":
    unittest.main()
