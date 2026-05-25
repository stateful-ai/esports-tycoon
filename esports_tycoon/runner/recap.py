"""The auto-recap artifact: ``recap.md`` + ``feed.snapshot.html``.

Every slice run, always on (never opt-in, per ``scope-m0.md``), emits two files to
``runs/<slice_id>/`` for the founder to screenshot and share:

* **``recap.md``** — a markdown write-up of the whole week: the fixture, the
  decisions made, the match and its key moments, the morale fallout, the Chirper
  feed, and — the thesis made visible — *what the room remembered*, every cited
  memory resolved back to the canned log.
* **``feed.snapshot.html``** — a standalone, self-contained Chirper page (inline
  CSS, no external assets) showing the week's feed exactly as the in-app feed view
  renders it.

Both renderers are **pure and dependency-free** (stdlib only — no Jinja2, no
Flask), so the artifact contract lives in the core and is tested headlessly. They
are **deterministic**: built from the :class:`SliceResult` with no clock or entropy,
escaped with :func:`html.escape`, and written with explicit ``\\n`` newlines and
UTF-8, so the same seed + same decisions yields byte-identical files on re-run.
"""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Union

from esports_tycoon.runner.model import PRACTICE_CHOICES, SliceResult
from esports_tycoon.schema import WorldState

__all__ = [
    "RECAP_FILENAME",
    "FEED_FILENAME",
    "render_recap_md",
    "render_feed_html",
    "write_artifacts",
]

RECAP_FILENAME = "recap.md"
FEED_FILENAME = "feed.snapshot.html"

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


# --------------------------------------------------------------------------- #
# recap.md
# --------------------------------------------------------------------------- #
def render_recap_md(result: SliceResult, world: WorldState) -> str:
    """Render the deterministic markdown recap for one slice run."""
    save = world.save
    standing = save.team.standing
    opponent = _rival_name(world, result.config.opponent)
    archetype = _rival_archetype(world, result.config.opponent)
    ovc, opp = result.scoreline
    h_ovc, h_opp = result.halftime_scoreline
    verdict = "win" if result.won else "loss"

    lines: list[str] = []
    lines.append(f"# {save.team.name} — Week {save.season.current_week}: {verdict}")
    lines.append("")
    lines.append(
        f"_{save.title}. {save.season.league}, {save.season.division}._  "
    )
    mode = _MODE_LABELS.get(result.content_backend, f"{result.content_backend} mode")
    lines.append(
        f"_Slice `{result.slice_id}` · seed `{result.config.seed}` · {mode}._"
    )
    lines.append("")

    lines.append("## The fixture")
    lines.append("")
    cutoff = save.season.playoff_cutoff
    lines.append(
        f"Must-win. {save.team.name} ({standing.wins}–{standing.losses}, "
        f"{standing.place} of {standing.of}; top {cutoff} make playoffs) "
        f"host **{opponent}** ({archetype}) on {result.config.map}."
    )
    lines.append("")

    lines.append("## The week")
    lines.append("")
    focus = result.decisions.practice_focus
    lines.append(
        f"- **Practice (your call):** {_PRACTICE_LABELS.get(focus, focus)} — {_PRACTICE_BLURBS.get(focus, '')}"
    )
    team_talk = result.decisions.team_talk or "—"
    lines.append(f"- **Team talk:** “{team_talk}”")
    lines.append("")

    lines.append("## The match")
    lines.append("")
    lines.append(result.narration.text)
    lines.append("")
    lines.append(
        f"**Final:** {save.team.name} {ovc}–{opp} {opponent} "
        f"(_{verdict}_). Half: {h_ovc}–{h_opp}."
    )
    lines.append("")
    half_author = result.halftime.author or "the bench"
    lines.append(f"Half-time, {half_author}: “{result.halftime.text}”")
    lines.append("")

    lines.append("### Key moments")
    lines.append("")
    lines.append("| Round | Beat | Who | Detail |")
    lines.append("| --- | --- | --- | --- |")
    for moment in result.why.key_moments:
        who = _name_list(world, moment.actors)
        lines.append(f"| {moment.round} | {moment.kind} | {who} | {moment.descriptor} |")
    lines.append("")

    lines.append("### Standouts")
    lines.append("")
    lines.append(f"- **MVP:** {_display_name(world, result.why.mvp)}")
    lines.append(f"- **Carried:** {_name_list(world, result.why.who_carried)}")
    lines.append(f"- **Came apart:** {_name_list(world, result.why.who_tilted)}")
    lines.append("")

    lines.append("### Morale")
    lines.append("")
    lines.append("| Player | Change |")
    lines.append("| --- | --- |")
    # Roster order keeps the table stable across runs.
    for player in world.players:
        if player.id in result.why.morale_deltas:
            delta = result.why.morale_deltas[player.id]
            lines.append(f"| {_display_name(world, player.id)} | {delta:+d} |")
    lines.append("")

    lines.append("## The fallout — Chirper")
    lines.append("")
    for post in result.feed:
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
    if result.cited_memories:
        for cite in result.cited_memories:
            entry = world.resolve_cite(cite)
            summary = entry.summary if entry is not None else "(unresolved)"
            lines.append(f"- `{cite}` — {summary}")
    else:
        lines.append("- (no precedent was cited this week)")
    lines.append("")
    pct = round(result.grounding_rate * 100)
    lines.append(
        f"_Grounding: {result.grounded_ok}/{result.grounded_total} grounded lines "
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


def render_feed_html(result: SliceResult, world: WorldState) -> str:
    """Render the standalone, self-contained Chirper snapshot for one slice run."""
    save = world.save
    opponent = _rival_name(world, result.config.opponent)
    ovc, opp = result.scoreline
    verdict = "win" if result.won else "loss"
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
        f"on {escape(result.config.map)} ({escape(verdict)})</p>"
    )
    parts.append("</header>")

    for post in result.feed:
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
        f"{result.grounded_ok}/{result.grounded_total} lines resolved · "
        f"slice {escape(result.slice_id)} · seed {result.config.seed}</footer>"
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
) -> tuple[Path, Path]:
    """Write ``recap.md`` + ``feed.snapshot.html`` to ``<output_root>/<slice_id>/``.

    Returns the two written paths. Files are written with UTF-8 and explicit
    ``\\n`` newlines so they are byte-identical across platforms and re-runs.
    """
    run_dir = Path(output_root) / result.slice_id
    run_dir.mkdir(parents=True, exist_ok=True)

    recap_path = run_dir / RECAP_FILENAME
    feed_path = run_dir / FEED_FILENAME
    recap_path.write_text(render_recap_md(result, world), encoding="utf-8", newline="\n")
    feed_path.write_text(render_feed_html(result, world), encoding="utf-8", newline="\n")
    return recap_path, feed_path
