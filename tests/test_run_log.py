"""The append-only slice run-log: ordered, typed events the recap derives from.

This is the acceptance bar for the JSONL run-log ticket:

* Running a slice **appends ordered, typed events** to ``events.jsonl`` — one JSON
  object per line, in the run's order, each a known event type.
* The recap is **derived from that log, not authored independently**: ``recap.md``
  is byte-for-byte what :func:`render_recap_md` produces from the *persisted* event
  stream, and editing the log changes the recap.
* The log stays **separate from the memory store**: events reference cast and
  precedent by ID; a memory's summary text is resolved into the recap at render
  time, never copied into the log.
* The log round-trips losslessly and is byte-identical on re-run with the same seed.
"""

import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from esports_tycoon.canned import loader  # noqa: E402
from esports_tycoon.runner import (  # noqa: E402
    EVENTS_FILENAME,
    RECAP_FILENAME,
    SliceConfig,
    SliceDecisions,
    read_events,
    render_feed_html,
    render_recap_md,
    run_slice,
    slice_events,
    write_artifacts,
    write_events,
)
from esports_tycoon.runner.events import (  # noqa: E402
    FeedPosted,
    GroundingSummary,
    KeyMomentLogged,
    MatchResolved,
    MoraleDelta,
    PracticeChosen,
    RoomRemembered,
    SliceStarted,
    StandoutsLogged,
    TeamTalk,
    serialize_event,
)


class _Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.world = loader.load()
        cls.config = SliceConfig(opponent="apex_foundry", map="Helix", seed=6)
        cls.decisions = SliceDecisions(
            practice_focus="defaults",
            team_talk="no heroes. run the default.",
            fallout_post="week 6: held the line. on to week 7.",
        )

    def result(self, **overrides):
        config = overrides.get("config", self.config)
        decisions = overrides.get("decisions", self.decisions)
        return run_slice(self.world, config, decisions)


class TestEventStreamIsOrderedAndTyped(_Fixture):
    def test_starts_with_run_identity_and_ends_with_grounding(self):
        events = slice_events(self.result(), self.world)
        self.assertIsInstance(events[0], SliceStarted)
        self.assertIsInstance(events[-1], GroundingSummary)
        self.assertIsInstance(events[-2], RoomRemembered)

    def test_section_order_matches_the_run(self):
        events = slice_events(self.result(), self.world)
        tags = [e.type for e in events]

        def first(tag):
            return tags.index(tag)

        def last(tag):
            return len(tags) - 1 - tags[::-1].index(tag)

        # The opening beats are in narrative order.
        self.assertLess(first("slice_started"), first("practice_chosen"))
        self.assertLess(first("practice_chosen"), first("team_talk"))
        self.assertLess(first("team_talk"), first("match_resolved"))
        self.assertLess(first("match_resolved"), first("halftime_ack"))
        # Key moments precede the standouts; morale follows; the feed follows that.
        self.assertLess(last("key_moment"), first("standouts"))
        self.assertLess(first("standouts"), first("morale_delta"))
        self.assertLess(last("morale_delta"), first("feed_post"))
        self.assertLess(last("feed_post"), first("memories_remembered"))

    def test_repeated_events_match_their_sources_in_count_and_order(self):
        result = self.result()
        events = slice_events(result, self.world)

        key_moments = [e for e in events if isinstance(e, KeyMomentLogged)]
        self.assertEqual(len(key_moments), len(result.why.key_moments))
        self.assertEqual([e.round for e in key_moments], [m.round for m in result.why.key_moments])

        feed = [e for e in events if isinstance(e, FeedPosted)]
        self.assertEqual(len(feed), len(result.feed))
        self.assertEqual([e.text for e in feed], [p.text for p in result.feed])

        # Morale is logged in roster order, one event per player with a delta.
        morale = [e for e in events if isinstance(e, MoraleDelta)]
        roster_order = [p.id for p in self.world.players if p.id in result.why.morale_deltas]
        self.assertEqual([e.player for e in morale], roster_order)

    def test_every_line_is_one_typed_json_object(self):
        result = self.result()
        with tempfile.TemporaryDirectory() as tmp:
            _, _, events_path = write_artifacts(result, self.world, tmp)
            lines = events_path.read_text(encoding="utf-8").splitlines()
        self.assertTrue(lines)
        known_types = {
            "slice_started", "practice_chosen", "team_talk", "match_resolved",
            "halftime_ack", "key_moment", "standouts", "morale_delta", "feed_post",
            "memories_remembered", "grounding_summary",
        }
        for line in lines:
            obj = json.loads(line)  # one JSON object per line
            self.assertIn("type", obj)
            self.assertIn(obj["type"], known_types)


class TestRecapIsDerivedFromTheLog(_Fixture):
    def test_written_recap_is_the_projection_of_the_written_log(self):
        # The on-disk recap is exactly render_recap_md over the on-disk events:
        # the artifact is a view of the log, not a second authoring of the week.
        with tempfile.TemporaryDirectory() as tmp:
            recap_path, _, events_path = write_artifacts(self.result(), self.world, tmp)
            self.assertEqual(
                recap_path.read_text(encoding="utf-8"),
                render_recap_md(read_events(events_path), self.world),
            )

    def test_written_feed_snapshot_is_the_projection_of_the_written_log(self):
        # The feed snapshot is a view of the log too: feed.snapshot.html is exactly
        # render_feed_html over the on-disk events, so neither artifact is authored
        # independently of events.jsonl.
        with tempfile.TemporaryDirectory() as tmp:
            _, feed_path, events_path = write_artifacts(self.result(), self.world, tmp)
            self.assertEqual(
                feed_path.read_text(encoding="utf-8"),
                render_feed_html(read_events(events_path), self.world),
            )

    def test_disk_roundtrip_yields_the_identical_recap(self):
        events = slice_events(self.result(), self.world)
        from_memory = render_recap_md(events, self.world)
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / EVENTS_FILENAME
            write_events(events, path)
            from_disk = render_recap_md(read_events(path), self.world)
        self.assertEqual(from_memory, from_disk)

    def test_editing_the_log_changes_the_recap(self):
        # If the recap were authored independently this would be invisible; because
        # it is derived from the log, a changed event surfaces in the recap.
        events = slice_events(self.result(), self.world)
        baseline = render_recap_md(events, self.world)
        edited = [
            TeamTalk(text="entirely different orders") if isinstance(e, TeamTalk) else e
            for e in events
        ]
        changed = render_recap_md(edited, self.world)
        self.assertNotEqual(baseline, changed)
        self.assertIn("entirely different orders", changed)
        self.assertNotIn("entirely different orders", baseline)

    def test_missing_required_event_fails_loudly(self):
        events = [e for e in slice_events(self.result(), self.world) if not isinstance(e, MatchResolved)]
        with self.assertRaises(ValueError):
            render_recap_md(events, self.world)


class TestLogStaysSeparateFromMemory(_Fixture):
    def test_events_cite_by_id_and_never_copy_summaries(self):
        result = self.result()
        self.assertTrue(result.cited_memories, "the week should cite at least one precedent")
        with tempfile.TemporaryDirectory() as tmp:
            recap_path, _, events_path = write_artifacts(result, self.world, tmp)
            log_text = events_path.read_text(encoding="utf-8")
            recap_text = recap_path.read_text(encoding="utf-8")
        for cite in result.cited_memories:
            entry = self.world.resolve_cite(cite)
            self.assertIsNotNone(entry)
            # The ID lives in the log; the summary does not — it is resolved into
            # the recap from the memory store at render time.
            self.assertIn(cite, log_text)
            self.assertNotIn(entry.summary, log_text)
            self.assertIn(entry.summary, recap_text)


class TestLogRoundTripAndDeterminism(_Fixture):
    def test_read_events_reconstructs_the_exact_typed_stream(self):
        events = slice_events(self.result(), self.world)
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / EVENTS_FILENAME
            write_events(events, path)
            restored = read_events(path)
        self.assertEqual([type(e) for e in restored], [type(e) for e in events])
        # Lossless: re-serializing the restored stream reproduces the original lines.
        self.assertEqual(
            [serialize_event(e) for e in restored],
            [serialize_event(e) for e in events],
        )

    def test_log_is_byte_identical_on_rerun_with_same_seed(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            _, _, e1 = write_artifacts(self.result(), self.world, a)
            _, _, e2 = write_artifacts(self.result(), self.world, b)
            self.assertEqual(e1.read_bytes(), e2.read_bytes())

    def test_a_different_decision_yields_a_different_log(self):
        base = slice_events(self.result(), self.world)
        other = slice_events(
            self.result(decisions=SliceDecisions(practice_focus="aim", team_talk="range day")),
            self.world,
        )
        self.assertNotEqual(
            [serialize_event(e) for e in base],
            [serialize_event(e) for e in other],
        )

    def test_read_events_rejects_a_malformed_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / EVENTS_FILENAME
            path.write_text('{"type": "no_such_event"}\n', encoding="utf-8")
            with self.assertRaises(Exception):
                read_events(path)

    def test_read_events_rejects_schema_drift_on_a_known_event(self):
        # extra="forbid" is what keeps the append-only log honest: a known event
        # type carrying an unmodelled key is schema drift, and a drifted line must
        # fail the read loudly rather than be silently truncated to its known fields.
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp) / EVENTS_FILENAME
            path.write_text(
                '{"type": "team_talk", "text": "run the default", "surprise": 1}\n',
                encoding="utf-8",
            )
            with self.assertRaises(Exception):
                read_events(path)


if __name__ == "__main__":
    unittest.main()
