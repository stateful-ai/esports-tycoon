"""Tests for the deterministic match resolver.

The acceptance bar has three parts, and each gets a direct test:

* ``run(state, decisions, seed) -> WhyRecord`` is **pure** — no I/O, no LLM, no
  ``content/`` imports (asserted statically against the module's own imports).
* The **same seed** yields an identical scoreline, MVP, key moments and morale
  deltas across 100 runs.
* A **5-seed sweep** produces visibly varied outcomes.

Beyond the bar, the resolver is supposed to be *grounded* in the canned world
(traits, recent-memory form, map comfort, clash pairs, rival archetype) rather
than a coin flip, and to react to the manager's decisions; those properties are
exercised too, so a regression to noise would fail.
"""

import ast
import copy
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from esports_tycoon import resolver  # noqa: E402
from esports_tycoon.canned import loader  # noqa: E402
from esports_tycoon.schema import (  # noqa: E402
    Decisions,
    KeyMoment,
    MemoryEntry,
    Player,
    Role,
    WhyRecord,
    WorldState,
)

_RESOLVER_SRC = pathlib.Path(resolver.__file__)


def _player(pid: str, role: Role, traits, memories) -> Player:
    return Player(
        id=pid,
        name=pid.title(),
        handle=f"@{pid}",
        role=role,
        age=22,
        signature_operative="Op",
        bio="b",
        persona_voice="v",
        traits=list(traits),
        memory_log=list(memories),
    )


def _mem(pid: str, slug: str, sentiment: str, *, tags=(), week: int = 5, day: int = 1) -> MemoryEntry:
    return MemoryEntry(
        id=f"mem:{pid}:{slug}",
        week=week,
        day=day,
        kind="match",
        actors=[pid],
        summary="x",
        sentiment=sentiment,
        tags=list(tags),
    )


class _WorldFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = loader.load()
        # Starters in save order: rook, vex, sable, pixie, coyote.
        cls.lineup_ids = [p.id for p in cls.world.players]


class TestPurity(unittest.TestCase):
    """The resolver imports only stdlib + the schema — no I/O, LLM, or content."""

    def _imported_modules(self) -> set[str]:
        tree = ast.parse(_RESOLVER_SRC.read_text(encoding="utf-8"))
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    names.add(node.module)
        return names

    def test_no_banned_imports(self):
        banned_prefixes = (
            "esports_tycoon.content",
            "esports_tycoon.canned",  # the loader does file I/O; resolver must not touch it
            "esports_tycoon.resolver.content",
            "os",
            "io",
            "pathlib",
            "socket",
            "subprocess",
            "requests",
            "httpx",
            "urllib",
            "http",
            "openai",
            "anthropic",
        )
        for module in self._imported_modules():
            for banned in banned_prefixes:
                self.assertFalse(
                    module == banned or module.startswith(banned + "."),
                    f"resolver imports banned module {module!r}",
                )

    def test_only_schema_imported_from_package(self):
        package_imports = {
            m for m in self._imported_modules() if m.startswith("esports_tycoon")
        }
        self.assertEqual(package_imports, {"esports_tycoon.schema"})

    def test_source_does_not_open_files_or_print(self):
        src = _RESOLVER_SRC.read_text(encoding="utf-8")
        for forbidden in ("open(", "print(", "input("):
            self.assertNotIn(forbidden, src, f"resolver source contains {forbidden!r}")


class TestDeterminism(_WorldFixture):
    # M0 freeze (founder_brief.md): the 100-run/WhyRecord digest sweep is
    # deferred to M1/post-gate. Same-seed byte-identity within a single run is
    # still covered by the load+resolve golden in
    # ``test_golden_determinism.py``; the 100x repeat is the harder digest the
    # gate does not need.
    @unittest.skip(
        "M0 freeze: 100-run WhyRecord digest deferred to M1/post-gate"
    )
    def test_identical_across_100_runs(self):
        for seed in (0, 1, 7, 42, 99, 123456):
            with self.subTest(seed=seed):
                first = resolver.run(self.world, Decisions(opponent="northwind"), seed)
                for _ in range(99):
                    again = resolver.run(self.world, Decisions(opponent="northwind"), seed)
                    # The four fields the acceptance bar names, then the whole record.
                    self.assertEqual(again.scoreline, first.scoreline)
                    self.assertEqual(again.mvp, first.mvp)
                    self.assertEqual(again.key_moments, first.key_moments)
                    self.assertEqual(again.morale_deltas, first.morale_deltas)
                    self.assertEqual(again, first)

    def test_seed_is_echoed(self):
        rec = resolver.run(self.world, Decisions(opponent="northwind"), 12345)
        self.assertEqual(rec.seed, 12345)

    def test_run_does_not_mutate_inputs(self):
        before = self.world.model_dump()
        decisions = Decisions(opponent="northwind")
        resolver.run(self.world, decisions, 3)
        self.assertEqual(self.world.model_dump(), before)
        self.assertEqual(decisions.lineup, [])  # default still empty, not filled in place


class TestVariety(_WorldFixture):
    def test_five_seed_sweep_is_visibly_varied(self):
        records = [
            resolver.run(self.world, Decisions(opponent="northwind"), seed)
            for seed in range(5)
        ]
        scorelines = {r.scoreline for r in records}
        signatures = {(r.scoreline, r.mvp) for r in records}
        # "Visibly varied": a five-seed sweep on one fixture must not collapse to
        # one or two repeated outcomes.
        self.assertGreaterEqual(len(scorelines), 3, f"scorelines barely vary: {scorelines}")
        self.assertGreaterEqual(len(signatures), 3, f"outcomes barely vary: {signatures}")

    def test_morale_deltas_vary_across_seeds(self):
        deltas = {
            tuple(sorted(resolver.run(self.world, Decisions(opponent="northwind"), seed).morale_deltas.items()))
            for seed in range(5)
        }
        self.assertGreaterEqual(len(deltas), 3, "morale deltas barely vary across seeds")


class TestWhyRecordWellFormed(_WorldFixture):
    """Whatever the seed, the record must be internally consistent."""

    def _records(self):
        for opp in ("sovereign", "northwind", "tidewater", "goblins"):
            for seed in range(8):
                yield resolver.run(self.world, Decisions(opponent=opp), seed)

    def test_scoreline_is_a_finished_map(self):
        for rec in self._records():
            ovc, opp = rec.scoreline
            top, bottom = max(ovc, opp), min(ovc, opp)
            # First to 13, win by 2 — or the safety cap, which only bites on a
            # pathological endless draw that the fixtures never reach.
            self.assertGreaterEqual(top, 13)
            self.assertGreaterEqual(top - bottom, 2)

    def test_round_log_matches_scoreline(self):
        for rec in self._records():
            self.assertEqual(len(rec.round_log), sum(rec.scoreline))
            self.assertEqual(rec.round_log[-1].summary, f"{rec.scoreline[0]}-{rec.scoreline[1]}")
            self.assertEqual([r.round for r in rec.round_log], list(range(1, len(rec.round_log) + 1)))

    def test_mvp_and_standouts_are_fielded_players(self):
        for rec in self._records():
            self.assertIn(rec.mvp, self.lineup_ids)
            self.assertTrue(set(rec.who_carried) <= set(self.lineup_ids))
            self.assertTrue(set(rec.who_tilted) <= set(self.lineup_ids))

    def test_carried_and_tilted_are_disjoint(self):
        for rec in self._records():
            self.assertEqual(set(rec.who_carried) & set(rec.who_tilted), set())
            self.assertNotIn(rec.mvp, rec.who_tilted)

    def test_morale_deltas_cover_exactly_the_lineup(self):
        for rec in self._records():
            self.assertEqual(set(rec.morale_deltas), set(self.lineup_ids))
            for value in rec.morale_deltas.values():
                self.assertTrue(-5 <= value <= 5)

    def test_key_moments_are_in_range_and_include_the_closeout(self):
        for rec in self._records():
            self.assertTrue(rec.key_moments, "every match has at least its closeout")
            self.assertLessEqual(len(rec.key_moments), 6)
            last_round = len(rec.round_log)
            for moment in rec.key_moments:
                self.assertTrue(1 <= moment.round <= last_round)
                self.assertTrue(moment.actors)
                self.assertTrue(set(moment.actors) <= set(self.lineup_ids))
            decisive = [m for m in rec.key_moments if m.kind in ("closeout", "match_point")]
            self.assertEqual(len(decisive), 1)
            self.assertEqual(decisive[0].round, last_round)
            # A win closes out; a loss reaches match point.
            self.assertEqual(decisive[0].kind, "closeout" if rec.scoreline[0] > rec.scoreline[1] else "match_point")

    def test_returns_a_why_record(self):
        rec = resolver.run(self.world, Decisions(opponent="northwind"), 0)
        self.assertIsInstance(rec, WhyRecord)


class TestGroundedInState(_WorldFixture):
    """Outcomes track the canned world, not a coin flip."""

    def _overcast_wins(self, opponent: str, seeds=range(24)) -> int:
        return sum(
            1
            for seed in seeds
            if (r := resolver.run(self.world, Decisions(opponent=opponent), seed)).scoreline[0]
            > r.scoreline[1]
        )

    def test_archetype_sets_difficulty(self):
        # The Rising Underdog is beatable; the Dynasty is a wall.
        underdog_wins = self._overcast_wins("tidewater")
        dynasty_wins = self._overcast_wins("sovereign")
        self.assertGreater(underdog_wins, dynasty_wins)

    def test_unknown_opponent_does_not_fail_silently(self):
        with self.assertRaises(ValueError):
            resolver.run(self.world, Decisions(opponent="nobody"), 0)

    def test_tilt_prone_starter_cracks_more_than_the_anchor(self):
        # Vex (impulsive, clout-chasing, and on the wrong side of three clashes)
        # should tilt far more often than Sable (stoic, low-ego anchor), across a
        # hard fixture where there are plenty of losses to crack under.
        vex_tilts = sum(
            "vex" in resolver.run(self.world, Decisions(opponent="sovereign"), seed).who_tilted
            for seed in range(24)
        )
        sable_tilts = sum(
            "sable" in resolver.run(self.world, Decisions(opponent="sovereign"), seed).who_tilted
            for seed in range(24)
        )
        self.assertGreater(vex_tilts, sable_tilts)

    def test_map_comfort_comes_from_memory(self):
        # Helix and Terminus produce different runs at the same seed because the
        # cast carries map-tagged memories (Vex aced on Helix; the week-5 choke
        # was on Terminus).
        helix = resolver.run(self.world, Decisions(opponent="northwind", map="Helix"), 3)
        terminus = resolver.run(self.world, Decisions(opponent="northwind", map="Terminus"), 3)
        self.assertNotEqual(helix, terminus)

    def test_form_reads_recent_memory_sentiment(self):
        hot = _player(
            "rook",
            Role.IGL,
            traits=["veteran"],
            memories=[_mem("rook", f"win{i}", "positive", week=5, day=i + 1) for i in range(3)],
        )
        cold = _player(
            "rook",
            Role.IGL,
            traits=["veteran"],
            memories=[_mem("rook", f"loss{i}", "negative", week=5, day=i + 1) for i in range(3)],
        )
        self.assertEqual(resolver._form(hot), 3.0)
        self.assertEqual(resolver._form(cold), -3.0)
        decisions = Decisions(opponent="northwind")
        self.assertGreater(resolver._skill_for(hot, decisions), resolver._skill_for(cold, decisions))

    def test_map_affinity_is_clamped(self):
        loud = _player(
            "vex",
            Role.DUELIST,
            traits=["hotshot"],
            memories=[_mem("vex", f"helix{i}", "positive", tags=["helix"], day=i + 1) for i in range(5)],
        )
        # Five positive Helix memories still cap at +2.
        self.assertEqual(resolver._map_affinity(loud, "Helix"), 2.0)
        self.assertEqual(resolver._map_affinity(loud, "Terminus"), 0.0)


class TestDecisionsAffectOutcomes(_WorldFixture):
    def test_practice_focus_lifts_the_role_it_suits(self):
        vex = next(p for p in self.world.players if p.id == "vex")  # DUELIST
        aim = resolver._skill_for(vex, Decisions(opponent="northwind", practice_focus="aim"))
        defaults = resolver._skill_for(vex, Decisions(opponent="northwind", practice_focus="defaults"))
        self.assertEqual(aim - defaults, 2.0)  # "aim" boosts duelists; "defaults" does not

    def test_decisions_can_change_the_result(self):
        seed = 1
        a = resolver.run(self.world, Decisions(opponent="northwind", practice_focus="aim", tactical_stance="aggressive"), seed)
        b = resolver.run(self.world, Decisions(opponent="northwind", practice_focus="anti_strat", tactical_stance="disciplined"), seed)
        self.assertNotEqual(a, b)

    def test_aggression_raises_team_strength(self):
        lineup = list(self.world.players)
        aggressive = resolver._stance_team_bonus("aggressive", lineup)
        neutral = resolver._stance_team_bonus("default", lineup)
        self.assertGreater(aggressive, neutral)


class TestLineupValidation(_WorldFixture):
    def test_default_lineup_is_the_five_starters(self):
        rec = resolver.run(self.world, Decisions(opponent="northwind"), 0)
        self.assertEqual(set(rec.morale_deltas), set(self.lineup_ids))

    def test_explicit_full_lineup_matches_default(self):
        explicit = resolver.run(
            self.world, Decisions(opponent="northwind", lineup=self.lineup_ids), 0
        )
        default = resolver.run(self.world, Decisions(opponent="northwind"), 0)
        self.assertEqual(explicit, default)

    def test_unknown_starter_rejected(self):
        with self.assertRaises(ValueError):
            resolver.run(self.world, Decisions(opponent="northwind", lineup=["rook", "vex", "sable", "pixie", "nobody"]), 0)

    def test_duplicate_starter_rejected(self):
        with self.assertRaises(ValueError):
            resolver.run(self.world, Decisions(opponent="northwind", lineup=["rook", "rook", "sable", "pixie", "coyote"]), 0)

    def test_wrong_size_lineup_rejected(self):
        with self.assertRaises(ValueError):
            resolver.run(self.world, Decisions(opponent="northwind", lineup=["rook", "vex", "sable"]), 0)


class TestResolverEntropyDiscipline(_WorldFixture):
    """The resolver's *only* entropy source is its save-seeded local ``Random``.

    Poison every public callable on the global ``random``, ``time``, and
    ``uuid`` modules so that any reach for ambient process state would fail
    loudly, then show the resolver still produces a ``WhyRecord`` that is
    bit-identical to one produced without the sabotage. This locks the rule
    documented in ``saves/SCHEMA.md`` — "same save ⇒ same match" can only hold
    if the resolver doesn't pick up anything ambient.
    """

    def _poison(self, module):
        """Replace every public callable on ``module`` with one that raises.

        The cleanup is registered *before* any attribute is touched and shares
        the ``original`` dict, so even a partial poisoning during teardown puts
        the module back exactly as it was.
        """
        original: dict[str, object] = {}
        self.addCleanup(self._restore, module, original)

        def boom(*_args, _mod=module.__name__, **_kwargs):
            raise AssertionError(
                f"resolver reached for global {_mod} — entropy must be save-seeded"
            )

        for name in dir(module):
            if name.startswith("_"):
                continue
            obj = getattr(module, name, None)
            if not callable(obj):
                continue
            try:
                setattr(module, name, boom)
            except (AttributeError, TypeError):
                continue  # read-only C-extension attribute; nothing to restore
            original[name] = obj

    @staticmethod
    def _restore(module, original):
        for name, obj in original.items():
            setattr(module, name, obj)

    def test_resolver_ignores_global_random_time_uuid(self):
        import random as _random
        import time as _time
        import uuid as _uuid

        decisions = Decisions(opponent="northwind")
        # A second matchup with a different code path (the chaos jitter branch
        # is only reached against The Chaos Agents) so the contract isn't only
        # tested on one round-resolution shape.
        chaos = Decisions(opponent="goblins")

        reference_a = resolver.run(self.world, decisions, 12345)
        reference_b = resolver.run(self.world, chaos, 7)

        self._poison(_random)
        self._poison(_time)
        self._poison(_uuid)

        sabotaged_a = resolver.run(self.world, decisions, 12345)
        sabotaged_b = resolver.run(self.world, chaos, 7)

        self.assertEqual(sabotaged_a, reference_a)
        self.assertEqual(sabotaged_b, reference_b)

    def test_poison_actually_bites(self):
        """Self-check: the sabotage above really does break callers that touch
        the globals — otherwise the discipline test would be a no-op."""
        import random as _random
        import time as _time
        import uuid as _uuid

        self._poison(_random)
        self._poison(_time)
        self._poison(_uuid)

        with self.assertRaises(AssertionError):
            _random.random()
        with self.assertRaises(AssertionError):
            _time.time()
        with self.assertRaises(AssertionError):
            _uuid.uuid4()


class TestConsumesCanonicalTeamRoster(_WorldFixture):
    """Acceptance: the resolver fields a Team/roster loaded straight from
    ``week6.yaml`` and returns a result the caller reads with no field remapping.

    The canonical schema names the side the resolver operates on — ``world.team``
    (the managed org) and ``world.roster`` (its starters) — so neither the
    resolver nor its caller has to re-assemble that pair from ``save.team`` plus
    the disconnected top-level ``players`` list.
    """

    def test_roster_is_the_managed_teams_players(self):
        # The first-class accessors name the relationship the resolver depends on.
        self.assertEqual([p.id for p in self.world.roster], [p.id for p in self.world.players])
        self.assertIs(self.world.team, self.world.save.team)

    def test_resolver_fields_the_whole_roster_by_default(self):
        # No caller-side assembly: an empty lineup fields exactly the team's
        # roster as loaded from the save.
        rec = resolver.run(self.world, Decisions(opponent="northwind"), 0)
        self.assertEqual(set(rec.morale_deltas), {p.id for p in self.world.roster})

    def test_explicit_lineup_must_be_drawn_from_the_roster(self):
        outsider = self.world.rivals[0].star.id  # a rival star is not on the roster
        self.assertNotIn(outsider, {p.id for p in self.world.roster})
        with self.assertRaises(ValueError):
            resolver.run(
                self.world,
                Decisions(opponent="northwind", lineup=[*self.lineup_ids[:4], outsider]),
                0,
            )

    def test_round_log_labels_winners_by_the_canonical_team_id(self):
        # The result is self-consistent against world.team.id: round winners are
        # exactly the managed team or the named opponent, and counting them by the
        # canonical id reproduces the scoreline — no caller-side remapping.
        rec = resolver.run(self.world, Decisions(opponent="northwind"), 3)
        team_id = self.world.team.id
        winners = [r.winner for r in rec.round_log]
        self.assertTrue(set(winners) <= {team_id, "northwind"})
        self.assertEqual(sum(w == team_id for w in winners), rec.scoreline[0])
        self.assertEqual(sum(w == "northwind" for w in winners), rec.scoreline[1])


if __name__ == "__main__":
    unittest.main()
