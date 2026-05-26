"""The auto-recap artifact: ``recap.md`` + ``feed.snapshot.html`` over the run-log.

Every slice run, always on (never opt-in, per ``scope-m0.md``), writes three files
to ``runs/<slice_id>/`` for the founder to screenshot and share:

* **``events.jsonl``** — the append-only, ordered, typed run-log (see
  :mod:`esports_tycoon.runner.events`). This is the *source*, not a sidecar.
* **``recap.md``** — a markdown write-up of the whole week (the fixture, the
  decisions, the match and its key moments, the morale fallout, the Chirper feed,
  and — the thesis made visible — *what the room remembered*), **derived from the
  run-log**: :func:`render_recap_md` projects the events, it does not re-author the
  week from the :class:`SliceResult`.
* **``feed.snapshot.html``** — a standalone, self-contained Chirper page (inline
  CSS, no external assets) showing the week's feed exactly as the in-app feed view
  renders it. Like the recap, it is **a projection of the run-log**:
  :func:`render_feed_html` reads the feed off the event stream, not off the
  :class:`SliceResult`, so both artifacts are views over the same source.

Keeping the recap a view over the run-log is the architecture principle here: the
log is the system of record for what a run did, and the artifacts are derived
projections of it (company memory ``mem_20260525T191715Z_469386``). The renderers
are **pure and dependency-free** (stdlib only — no Jinja2, no Flask) and
**deterministic**: built from the event stream / :class:`SliceResult` with no clock
or entropy, escaped with :func:`html.escape`, and written with explicit ``\\n``
newlines and UTF-8, so the same seed + same decisions yields byte-identical files
on re-run.
"""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Sequence, TypeVar, Union

from esports_tycoon.runner.events import (
    EVENTS_FILENAME,
    FeedPosted,
    GroundingSummary,
    HalftimeAck,
    KeyMomentLogged,
    MatchResolved,
    MoraleDelta,
    PracticeChosen,
    RoomRemembered,
    SliceEvent,
    SliceStarted,
    StandoutsLogged,
    TeamTalk,
    read_events,
    slice_events,
    write_events,
)
from esports_tycoon.runner.model import PRACTICE_CHOICES, SliceResult
from esports_tycoon.schema import MEMORY_ID_RE, WorldState

__all__ = [
    "RECAP_FILENAME",
    "FEED_FILENAME",
    "EVENTS_FILENAME",
    "REMEMBERED_SLOT_LABEL",
    "render_recap_md",
    "render_feed_html",
    "write_artifacts",
]

RECAP_FILENAME = "recap.md"
FEED_FILENAME = "feed.snapshot.html"

#: The label of the fixed scannable slot at the top of ``recap.md`` that
#: surfaces the bound precedent (the narration's recalled cite). Rendered as a
#: blockquote one-liner just below the slice header so the founder can scan it
#: at the first glance of the screenshot; suppressed entirely when no precedent
#: bound, so a "no recall" run is read as absence rather than as an empty slot.
REMEMBERED_SLOT_LABEL = "Remembered"

_PRACTICE_LABELS = {value: label for value, label, _ in PRACTICE_CHOICES}
_PRACTICE_BLURBS = {value: blurb for value, _, blurb in PRACTICE_CHOICES}

#: How each content backend is described in the recap header. Only ``templated``
#: is byte-deterministic and zero-API; a ``vllm`` recap must say so plainly rather
#: than inherit the templated "zero-API" claim.
_MODE_LABELS = {
    "templated": "templated mode (zero-API)",
    "vllm": "vllm mode (local Qwen 7B/8B)",
}


# --------------------------------------------------------------------------- #
# Shared lookups.
# --------------------------------------------------------------------------- #
def _rival_name(world: WorldState, opponent_id: str) -> str:
    for rival in world.rivals:
        if rival.id == opponent_id:
            return rival.name
    return opponent_id


def _rival_archetype(world: WorldState, opponent_id: str) -> str:
    for rival in world.rivals:
        if rival.id == opponent_id:
            return rival.archetype
    return ""


def _display_name(world: WorldState, player_id: str) -> str:
    for player in world.players:
        if player.id == player_id:
            name = player.name
            if '"' in name:
                return name.split('"')[1]
            return name.split()[0] if name.split() else name
    return player_id


def _name_list(world: WorldState, ids: list[str]) -> str:
    names = [_display_name(world, pid) for pid in ids]
    if not names:
        return "—"
    if len(names) == 1:
        return names[0]
    return f"{', '.join(names[:-1])} and {names[-1]}"


def _cite_owner_id(cite: str) -> str:
    """The owner segment parsed out of a ``mem:<owner>:<event_slug>`` cite.

    The format is enforced at :class:`~esports_tycoon.schema.MemoryEntry`
    construction time, so any cite that has reached an event log has already
    been validated — a regex miss here would mean a hand-built event slipped
    past the validator, which we surface loudly rather than swallow.
    """
    match = MEMORY_ID_RE.match(cite)
    if match is None:
        raise ValueError(f"malformed cite id reached the recap: {cite!r}")
    return match.group(1)


# --------------------------------------------------------------------------- #
# recap.md — derived from the run-log
# --------------------------------------------------------------------------- #
_E = TypeVar("_E", bound=SliceEvent)


def _one(events: Sequence[SliceEvent], kind: type[_E]) -> _E:
    """The single event of ``kind`` in the log, or a clear error if it is absent.

    The recap's singleton beats (the run header, the resolved match, the grounding
    tally, …) are emitted exactly once per run; a missing one means a malformed or
    truncated log, which should fail loudly rather than render a half-recap.
    """
    for event in events:
        if isinstance(event, kind):
            return event
    raise ValueError(f"run-log is missing a required {kind.__name__} event")


def _all(events: Sequence[SliceEvent], kind: type[_E]) -> list[_E]:
    """Every event of ``kind`` in the log, in logged order."""
    return [event for event in events if isinstance(event, kind)]


def render_recap_md(events: Sequence[SliceEvent], world: WorldState) -> str:
    """Render the deterministic markdown recap from a slice's run-log.

    The recap is a **projection of the event stream** (``events.jsonl``), not a
    second authoring of the week: every fact rendered here is read out of an event,
    with ``world`` used only to resolve the IDs those events reference — player IDs
    to display names, opponent and cite IDs to their names and summaries.
    """
    started = _one(events, SliceStarted)
    practice = _one(events, PracticeChosen)
    team_talk_event = _one(events, TeamTalk)
    match = _one(events, MatchResolved)
    halftime = _one(events, HalftimeAck)
    standouts = _one(events, StandoutsLogged)
    remembered = _one(events, RoomRemembered)
    grounding = _one(events, GroundingSummary)

    save = world.save
    standing = save.team.standing
    opponent = _rival_name(world, started.opponent)
    archetype = _rival_archetype(world, started.opponent)
    ovc, opp = match.scoreline
    h_ovc, h_opp = match.halftime_scoreline
    verdict = "win" if ovc > opp else "loss"

    lines: list[str] = []
    lines.append(f"# {save.team.name} — Week {save.season.current_week}: {verdict}")
    lines.append("")
    lines.append(
        f"_{save.title}. {save.season.league}, {save.season.division}._  "
    )
    mode = _MODE_LABELS.get(started.content_backend, f"{started.content_backend} mode")
    lines.append(
        f"_Slice `{started.slice_id}` · seed `{started.seed}` · {mode}._"
    )
    lines.append("")

    # The fixed scannable slot for the bound precedent — a one-line blockquote
    # below the slice header so the "the room remembered me" beat reads first
    # in the screenshot. Suppressed when no precedent bound; on the templated
    # path under the canonical week-6 fixture this always fires.
    bound_cite = match.cites[0] if match.cites else None
    if bound_cite is not None:
        entry = world.resolve_cite(bound_cite)
        if entry is not None:
            who = _display_name(world, _cite_owner_id(bound_cite))
            lines.append(
                f"> **{REMEMBERED_SLOT_LABEL}:** {who}, week {entry.week} — "
                f"{entry.summary} (`{bound_cite}`)"
            )
            lines.append("")

    lines.append("## The fixture")
    lines.append("")
    cutoff = save.season.playoff_cutoff
    lines.append(
        f"Must-win. {save.team.name} ({standing.wins}–{standing.losses}, "
        f"{standing.place} of {standing.of}; top {cutoff} make playoffs) "
        f"host **{opponent}** ({archetype}) on {started.map}."
    )
    lines.append("")

    lines.append("## The week")
    lines.append("")
    focus = practice.focus
    lines.append(
        f"- **Practice (your call):** {_PRACTICE_LABELS.get(focus, focus)} — {_PRACTICE_BLURBS.get(focus, '')}"
    )
    team_talk = team_talk_event.text or "—"
    lines.append(f"- **Team talk:** “{team_talk}”")
    lines.append("")

    lines.append("## The match")
    lines.append("")
    lines.append(match.narration)
    lines.append("")
    lines.append(
        f"**Final:** {save.team.name} {ovc}–{opp} {opponent} "
        f"(_{verdict}_). Half: {h_ovc}–{h_opp}."
    )
    lines.append("")
    half_author = halftime.author or "the bench"
    lines.append(f"Half-time, {half_author}: “{halftime.text}”")
    lines.append("")

    lines.append("### Key moments")
    lines.append("")
    lines.append("| Round | Beat | Who | Detail |")
    lines.append("| --- | --- | --- | --- |")
    for moment in _all(events, KeyMomentLogged):
        who = _name_list(world, moment.actors)
        lines.append(f"| {moment.round} | {moment.kind} | {who} | {moment.descriptor} |")
    lines.append("")

    lines.append("### Standouts")
    lines.append("")
    lines.append(f"- **MVP:** {_display_name(world, standouts.mvp)}")
    lines.append(f"- **Carried:** {_name_list(world, standouts.who_carried)}")
    lines.append(f"- **Came apart:** {_name_list(world, standouts.who_tilted)}")
    lines.append("")

    lines.append("### Morale")
    lines.append("")
    lines.append("| Player | Change |")
    lines.append("| --- | --- |")
    # Morale events are logged in roster order, so the table stays stable.
    for morale in _all(events, MoraleDelta):
        lines.append(f"| {_display_name(world, morale.player)} | {morale.delta:+d} |")
    lines.append("")

    lines.append("## The fallout — Chirper")
    lines.append("")
    for post in _all(events, FeedPosted):
        cite_note = f"  _(cites: {', '.join(post.cites)})_" if post.cites else ""
        lines.append(f"- **{post.author_name}** ({post.author_handle}): “{post.text}”{cite_note}")
    lines.append("")

    lines.append("## What the room remembered")
    lines.append("")
    lines.append(
        "Every line above is grounded in a real memory from the canned log — "
        "no invented history."
    )
    lines.append("")
    if remembered.cites:
        for cite in remembered.cites:
            entry = world.resolve_cite(cite)
            summary = entry.summary if entry is not None else "(unresolved)"
            lines.append(f"- `{cite}` — {summary}")
    else:
        lines.append("- (no precedent was cited this week)")
    lines.append("")
    rate = grounding.grounded_ok / grounding.grounded_total if grounding.grounded_total else 1.0
    pct = round(rate * 100)
    lines.append(
        f"_Grounding: {grounding.grounded_ok}/{grounding.grounded_total} grounded lines "
        f"resolved ({pct}%)._"
    )
    lines.append("")

    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# feed.snapshot.html
# --------------------------------------------------------------------------- #
_FEED_CSS = """\
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body {
  margin: 0; padding: 2rem 1rem;
  font: 16px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  background: #15181c; color: #e7e9ea;
}
.feed { max-width: 600px; margin: 0 auto; }
.feed > header { padding: 0 0 1rem; border-bottom: 1px solid #2f3336; margin-bottom: 0.5rem; }
.feed > header h1 { font-size: 1.25rem; margin: 0 0 0.25rem; }
.feed > header p { margin: 0; color: #71767b; font-size: 0.9rem; }
.post { display: flex; gap: 0.75rem; padding: 1rem 0; border-bottom: 1px solid #2f3336; }
.avatar {
  flex: 0 0 44px; width: 44px; height: 44px; border-radius: 50%;
  background: #3a3f44; color: #e7e9ea; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
}
.post .body { min-width: 0; }
.post .meta { color: #71767b; font-size: 0.9rem; }
.post .meta .name { color: #e7e9ea; font-weight: 700; }
.post .text { margin: 0.15rem 0 0; white-space: pre-wrap; word-wrap: break-word; }
.post .cites { margin: 0.4rem 0 0; color: #71767b; font-size: 0.78rem; }
.feed > footer { padding-top: 1rem; color: #71767b; font-size: 0.8rem; }
"""


def _avatar_initial(name: str) -> str:
    cleaned = name.lstrip("@")
    return escape(cleaned[0].upper()) if cleaned else "?"


def render_feed_html(events: Sequence[SliceEvent], world: WorldState) -> str:
    """Render the standalone, self-contained Chirper snapshot from a slice's run-log.

    Like :func:`render_recap_md`, this is a **projection of the event stream**: the
    posts, the scoreline, and the grounding tally are read out of events, with
    ``world`` only resolving the opponent ID and the cite IDs each post references.
    """
    started = _one(events, SliceStarted)
    match = _one(events, MatchResolved)
    grounding = _one(events, GroundingSummary)

    save = world.save
    opponent = _rival_name(world, started.opponent)
    ovc, opp = match.scoreline
    verdict = "win" if ovc > opp else "loss"
    title = f"Chirper — {save.team.name} Week {save.season.current_week}"

    parts: list[str] = []
    parts.append("<!DOCTYPE html>")
    parts.append('<html lang="en">')
    parts.append("<head>")
    parts.append('<meta charset="utf-8">')
    parts.append('<meta name="viewport" content="width=device-width, initial-scale=1">')
    parts.append(f"<title>{escape(title)}</title>")
    parts.append(f"<style>\n{_FEED_CSS}</style>")
    parts.append("</head>")
    parts.append("<body>")
    parts.append('<main class="feed">')
    parts.append("<header>")
    parts.append(f"<h1>Chirper · {escape(save.team.name)} Week {save.season.current_week}</h1>")
    parts.append(
        f"<p>{escape(save.team.name)} {ovc}–{opp} {escape(opponent)} "
        f"on {escape(started.map)} ({escape(verdict)})</p>"
    )
    parts.append("</header>")

    for post in _all(events, FeedPosted):
        parts.append('<article class="post">')
        parts.append(f'<div class="avatar">{_avatar_initial(post.author_name)}</div>')
        parts.append('<div class="body">')
        parts.append(
            f'<div class="meta"><span class="name">{escape(post.author_name)}</span> '
            f"{escape(post.author_handle)}</div>"
        )
        parts.append(f'<p class="text">{escape(post.text)}</p>')
        if post.cites:
            resolved = "; ".join(
                escape(entry.summary)
                for entry in (world.resolve_cite(c) for c in post.cites)
                if entry is not None
            )
            if resolved:
                parts.append(f'<p class="cites">↳ remembering: {resolved}</p>')
        parts.append("</div>")
        parts.append("</article>")

    parts.append(
        f"<footer>Grounded in the canned memory log · "
        f"{grounding.grounded_ok}/{grounding.grounded_total} lines resolved · "
        f"slice {escape(started.slice_id)} · seed {started.seed}</footer>"
    )
    parts.append("</main>")
    parts.append("</body>")
    parts.append("</html>")
    return "\n".join(parts) + "\n"


# --------------------------------------------------------------------------- #
# Writing the artifacts.
# --------------------------------------------------------------------------- #
def write_artifacts(
    result: SliceResult, world: WorldState, output_root: Union[str, Path]
) -> tuple[Path, Path, Path]:
    """Write ``events.jsonl`` + ``recap.md`` + ``feed.snapshot.html`` to
    ``<output_root>/<slice_id>/``.

    The run-log is written first; **both** the recap and the feed snapshot are then
    derived from that persisted log (read back and projected), so each artifact is
    provably a view over ``events.jsonl`` and never drifts from it. Returns the
    three written paths, in ``(recap, feed, events)`` order. Files are written with
    UTF-8 and explicit ``\\n`` newlines so they are byte-identical across platforms
    and re-runs.
    """
    run_dir = Path(output_root) / result.slice_id
    run_dir.mkdir(parents=True, exist_ok=True)

    events_path = write_events(slice_events(result, world), run_dir / EVENTS_FILENAME)
    events = read_events(events_path)

    recap_path = run_dir / RECAP_FILENAME
    feed_path = run_dir / FEED_FILENAME
    recap_path.write_text(render_recap_md(events, world), encoding="utf-8", newline="\n")
    feed_path.write_text(render_feed_html(events, world), encoding="utf-8", newline="\n")
    return recap_path, feed_path, events_path
