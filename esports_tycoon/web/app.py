"""The Flask slice app: one process serving the manager view + the Chirper feed.

The app is a thin presentation shell over :mod:`esports_tycoon.runner`. It holds
almost no state of its own: the only thing kept in the session is the player's
small set of decisions (the practice MC and the two open-text lines). The mid-week
pages — the resolved match and the narration — are recomputed from
``world + config + decisions`` by the deterministic engine on each request. Once the
week is finalized, ``/feed`` serves the written ``feed.snapshot.html`` byte-for-byte
rather than re-running generation, so the in-app feed can never drift from the saved
artifact (this matters under non-templated content backends, which are not
guaranteed to regenerate identical text).

The week is a short linear flow, one decision per step:

    /            manager view (briefing): standing, roster, last week's feed
    /practice    the MC — what the practice block drills
    /prematch    open-text #1 — the private pre-match team talk (<=120 chars)
    /match       the resolved match: narration, key moments, morale
    /fallout     open-text #2 — the public post-match Chirper post (<=120 chars)
                 → on submit, writes the recap artifact
    /recap       the written-up week + a pointer to the saved files
    /feed        the week-6 Chirper feed — serves the saved feed.snapshot.html
                 verbatim once the week is finalized, so it cannot drift from it

Flask is imported here (lazily, via :func:`create_app`) and nowhere else, keeping
the engine and its tests free of the web dependency.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from esports_tycoon.canned import loader
from esports_tycoon.content.config import ContentConfig
from esports_tycoon.runner.engine import run_slice, slice_id
from esports_tycoon.runner.model import (
    OPEN_TEXT_MAX,
    PRACTICE_CHOICES,
    SliceConfig,
    SliceDecisions,
    normalize_open_text,
)
from esports_tycoon.runner.recap import (
    FEED_FILENAME,
    RECAP_FILENAME,
    render_feed_html,
)
from esports_tycoon.schema import WorldState

__all__ = ["create_app"]

_PRACTICE_VALUES = frozenset(value for value, _, _ in PRACTICE_CHOICES)


def create_app(
    *,
    world: Optional[WorldState] = None,
    config: Optional[SliceConfig] = None,
    output_root: str | Path = "runs",
    content_config: Optional[ContentConfig] = None,
    secret_key: Optional[bytes | str] = None,
):
    """Build the Flask app for one local slice.

    ``world`` defaults to the packaged canned save; ``config`` to the standard
    week-6 fixture; ``content_config`` to the zero-API templated backend. Artifacts
    are written under ``output_root`` (default ``runs/``). Importing Flask here
    keeps it off the import path for everything that does not run the server.
    """
    from flask import (
        Flask,
        abort,
        flash,
        redirect,
        render_template,
        request,
        session,
        url_for,
    )

    app = Flask(__name__)
    # A local single-player app: a per-process random key signs the tiny session
    # cookie (the three decisions). Restarting mid-slice just starts a fresh week.
    app.secret_key = secret_key or os.urandom(32)

    world = world or loader.load()
    config = config or SliceConfig()
    output_root = Path(output_root)
    content_config = content_config or ContentConfig()

    rival_names = {r.id: r.name for r in world.rivals}
    rival_archetypes = {r.id: r.archetype for r in world.rivals}

    # ----------------------------------------------------------------- helpers
    def display_name(player_id: str) -> str:
        for player in world.players:
            if player.id == player_id:
                name = player.name
                return name.split('"')[1] if '"' in name else (name.split()[0] if name.split() else name)
        return player_id

    def name_list(ids) -> str:
        names = [display_name(pid) for pid in ids]
        if not names:
            return "—"
        if len(names) == 1:
            return names[0]
        return f"{', '.join(names[:-1])} and {names[-1]}"

    def opponent_name() -> str:
        return rival_names.get(config.opponent, config.opponent)

    def current_decisions() -> Optional[SliceDecisions]:
        """Build :class:`SliceDecisions` from the session, or ``None`` if the MC
        (the required first step) has not been made yet."""
        focus = session.get("practice_focus")
        if focus not in _PRACTICE_VALUES:
            return None
        return SliceDecisions(
            practice_focus=focus,
            team_talk=session.get("team_talk", ""),
            fallout_post=session.get("fallout_post", ""),
        )

    def require_decisions():
        decisions = current_decisions()
        if decisions is None:
            flash("Pick what the team drills in practice first.")
            return None
        return decisions

    # Make small helpers and shared context available to every template.
    @app.context_processor
    def _inject():
        return {
            "save": world.save,
            "team": world.save.team,
            "season": world.save.season,
            "opponent_name": opponent_name(),
            "opponent_archetype": rival_archetypes.get(config.opponent, ""),
            "fixture_map": config.map,
            "display_name": display_name,
            "name_list": name_list,
            "OPEN_TEXT_MAX": OPEN_TEXT_MAX,
        }

    # ------------------------------------------------------------------ routes
    @app.get("/")
    def briefing():
        return render_template(
            "briefing.html",
            players=world.players,
            last_week=world.last_week,
            started=current_decisions() is not None,
        )

    @app.get("/reset")
    def reset():
        session.clear()
        return redirect(url_for("practice"))

    @app.route("/practice", methods=["GET", "POST"])
    def practice():
        if request.method == "POST":
            focus = (request.form.get("practice_focus") or "").strip()
            if focus not in _PRACTICE_VALUES:
                flash("Choose one practice focus.")
                return redirect(url_for("practice"))
            session["practice_focus"] = focus
            return redirect(url_for("prematch"))
        return render_template(
            "practice.html",
            choices=PRACTICE_CHOICES,
            selected=session.get("practice_focus"),
        )

    @app.route("/prematch", methods=["GET", "POST"])
    def prematch():
        if require_decisions() is None:
            return redirect(url_for("practice"))
        if request.method == "POST":
            raw = request.form.get("team_talk", "")
            try:
                session["team_talk"] = normalize_open_text(raw, label="team talk")
            except ValueError as exc:
                flash(str(exc))
                return render_template("prematch.html", value=raw)
            return redirect(url_for("match"))
        return render_template("prematch.html", value=session.get("team_talk", ""))

    @app.get("/match")
    def match():
        decisions = require_decisions()
        if decisions is None:
            return redirect(url_for("practice"))
        result = run_slice(world, config, decisions, content_config=content_config)
        h_ovc, h_opp = result.halftime_scoreline
        return render_template(
            "match.html",
            result=result,
            half_score=f"{h_ovc}–{h_opp}",
            team_talk=decisions.team_talk,
        )

    @app.route("/fallout", methods=["GET", "POST"])
    def fallout():
        decisions = require_decisions()
        if decisions is None:
            return redirect(url_for("practice"))
        if request.method == "POST":
            raw = request.form.get("fallout_post", "")
            try:
                post = normalize_open_text(raw, label="fallout post")
            except ValueError as exc:
                flash(str(exc))
                return render_template("fallout.html", value=raw, result=run_slice(world, config, decisions, content_config=content_config))
            session["fallout_post"] = post
            # Recompute with the final decision and write the artifact, once.
            final = SliceDecisions(
                practice_focus=decisions.practice_focus,
                team_talk=decisions.team_talk,
                fallout_post=post,
            )
            from esports_tycoon.runner.recap import write_artifacts

            result = run_slice(world, config, final, content_config=content_config)
            write_artifacts(result, world, output_root)
            return redirect(url_for("recap"))
        result = run_slice(world, config, decisions, content_config=content_config)
        return render_template("fallout.html", value=session.get("fallout_post", ""), result=result)

    @app.get("/recap")
    def recap():
        decisions = require_decisions()
        if decisions is None:
            return redirect(url_for("practice"))
        result = run_slice(world, config, decisions, content_config=content_config)
        run_dir = output_root / result.slice_id
        cited = [(c, world.resolve_cite(c)) for c in result.cited_memories]
        return render_template(
            "recap.html",
            result=result,
            recap_path=str(run_dir / RECAP_FILENAME),
            feed_path=str(run_dir / FEED_FILENAME),
            cited=cited,
        )

    @app.get("/feed")
    def feed():
        decisions = require_decisions()
        if decisions is None:
            return redirect(url_for("practice"))
        # Once the week is finalized (the /fallout POST writes the artifact under
        # the content-addressed slice_id), serve that saved snapshot verbatim. The
        # slice_id is a pure hash of world + config + decisions, so we can locate
        # the file without re-running generation — and serving the bytes is the only
        # thing that *guarantees* the feed matches feed.snapshot.html for this
        # slice_id, including under non-templated backends where regenerating the
        # content could drift from what was written.
        snapshot = output_root / slice_id(world, config, decisions) / FEED_FILENAME
        if snapshot.is_file():
            return snapshot.read_bytes()
        # Not finalized yet (e.g. /feed before the post is submitted): render the
        # live feed, byte-identical to the snapshot in templated mode.
        result = run_slice(world, config, decisions, content_config=content_config)
        return render_feed_html(result, world)

    @app.get("/healthz")
    def healthz():
        return {"status": "ok", "backend": content_config.backend}

    return app
