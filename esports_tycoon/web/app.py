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
    /week7       the exported hook becomes a deterministic next-focus choice
    /week7/result
                 the locked focus becomes a deterministic pressure payoff
    /week8       the pressure payoff becomes a deterministic prep tradeoff
    /week8/scrim the prep response becomes a deterministic scrim setup
    /week8/match the scrim setup becomes a deterministic match-plan preview
    /week8/match/result
                 the match plan becomes a deterministic match result + Week-9 hook
    /week9       the Week-8 result becomes a deterministic Week-9 fallout setup
    /week9/prep  the Week-9 setup response becomes a deterministic prep lane
    /week9/scrim the Week-9 prep lane becomes a deterministic scrim read
    /week9/match the Week-9 scrim read becomes a deterministic match plan
    /week9/match/result the Week-9 match plan becomes a deterministic result
    /week10/fallout the Week-9 result becomes a deterministic Week-10 fallout choice
    /week10/prep the Week-10 fallout response becomes an analyst-desk prep block
    /week10/scrim the Week-10 prep block becomes a deterministic scrim protocol
    /week10/match the Week-10 scrim protocol becomes a deterministic match plan
    /week10/match/result the Week-10 match plan becomes a deterministic result
    /week10/post-match-review the Week-10 result becomes a durable review lesson
    /week11/setup the Week-10 review carry-forward becomes a Week-11 opening posture
    /feed        the week-6 Chirper feed — serves the saved feed.snapshot.html
                 verbatim once the week is finalized, so it cannot drift from it

Flask is imported here (lazily, via :func:`create_app`) and nowhere else, keeping
the engine and its tests free of the web dependency.
"""

from __future__ import annotations

import mimetypes
import os
from pathlib import Path
from typing import Optional

from esports_tycoon.canned import loader
from esports_tycoon.content.config import ContentConfig
from esports_tycoon.runner.engine import run_slice, slice_id
from esports_tycoon.runner.events import slice_events
from esports_tycoon.runner.model import (
    ANALYST_READS,
    OPEN_TEXT_MAX,
    PRACTICE_CHOICES,
    TRAINING_DRILLS,
    SliceConfig,
    SliceDecisions,
    normalize_open_text,
    training_decision_for_drill,
)
from esports_tycoon.runner.recap import (
    FEED_FILENAME,
    RECAP_FILENAME,
    WEEK7_SETUP_FILENAME,
    render_feed_html,
    render_week7_setup_json,
)
from esports_tycoon.runner.week7 import (
    WEEK7_FOCUS_FILENAME,
    WEEK7_PRESSURE_FILENAME,
    focus_payload_from_json,
    render_week7_focus_json,
    render_week7_pressure_json,
    resolve_week7_focus,
    resolve_week7_pressure,
    setup_payload_from_json,
    setup_payload_from_week7_setup,
    week7_focus_options,
)
from esports_tycoon.runner.week8 import (
    WEEK8_MATCH_PLAN_FILENAME,
    WEEK8_MATCH_RESULT_FILENAME,
    WEEK8_PREP_FILENAME,
    WEEK8_SCRIM_FILENAME,
    pressure_payload_from_json,
    render_week8_match_plan_json,
    render_week8_match_result_json,
    render_week8_prep_json,
    render_week8_scrim_json,
    resolve_week8_match_plan,
    resolve_week8_match_result,
    resolve_week8_prep,
    resolve_week8_scrim,
    week8_match_plan_from_json,
    week8_match_preview,
    week8_match_result_from_json,
    week8_prep_from_json,
    week8_prep_plan,
    week8_scrim_from_json,
    week8_scrim_plan,
)
from esports_tycoon.runner.week9 import (
    WEEK9_MATCH_PLAN_FILENAME,
    WEEK9_MATCH_RESULT_FILENAME,
    WEEK9_PREP_FILENAME,
    WEEK9_SCRIM_FILENAME,
    WEEK9_SETUP_FILENAME,
    render_week9_match_plan_json,
    render_week9_match_result_json,
    render_week9_prep_json,
    render_week9_scrim_json,
    render_week9_setup_json,
    resolve_week9_match_plan,
    resolve_week9_match_result,
    resolve_week9_prep,
    resolve_week9_scrim,
    resolve_week9_setup,
    week9_match_plan_from_json,
    week9_match_plan_preview,
    week9_match_result_from_json,
    week9_prep_from_json,
    week9_prep_plan,
    week9_scrim_from_json,
    week9_scrim_plan,
    week9_setup_from_json,
    week9_setup_plan,
)
from esports_tycoon.runner.week10 import (
    WEEK10_FALLOUT_FILENAME,
    WEEK10_MATCH_PLAN_FILENAME,
    WEEK10_MATCH_RESULT_FILENAME,
    WEEK10_POST_MATCH_REVIEW_FILENAME,
    WEEK10_PREP_FILENAME,
    WEEK10_SCRIM_FILENAME,
    render_week10_fallout_json,
    render_week10_match_plan_json,
    render_week10_match_result_json,
    render_week10_post_match_review_json,
    render_week10_prep_json,
    render_week10_scrim_json,
    resolve_week10_fallout,
    resolve_week10_match_plan,
    resolve_week10_match_result,
    resolve_week10_post_match_review,
    resolve_week10_prep,
    resolve_week10_scrim,
    week10_fallout_from_json,
    week10_fallout_plan,
    week10_match_plan_from_json,
    week10_match_plan_preview,
    week10_match_result_from_json,
    week10_post_match_review_from_json,
    week10_post_match_review_plan,
    week10_prep_from_json,
    week10_prep_plan,
    week10_scrim_from_json,
    week10_scrim_plan,
)
from esports_tycoon.runner.week11 import (
    WEEK11_SETUP_FILENAME,
    render_week11_setup_json,
    resolve_week11_setup,
    week11_setup_from_json,
    week11_setup_plan,
)
from esports_tycoon.schema import WorldState

__all__ = ["create_app"]

_PRACTICE_VALUES = frozenset(value for value, _, _ in PRACTICE_CHOICES)
mimetypes.add_type("image/webp", ".webp")


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

    def fallout_repair_unlocked() -> bool:
        return any(
            not clash.cross_team and {clash.a, clash.b} == {"vex", "pixie"}
            for clash in world.clash_pairs
        )

    def available_training_drills():
        if fallout_repair_unlocked():
            return TRAINING_DRILLS
        return tuple(drill for drill in TRAINING_DRILLS if drill.value != "pixie_flash_repair")

    def available_training_values() -> frozenset[str]:
        return frozenset(drill.value for drill in available_training_drills())

    def current_decisions() -> Optional[SliceDecisions]:
        """Build :class:`SliceDecisions` from the session, or ``None`` if the MC
        (the required first step) has not been made yet."""
        focus = session.get("practice_focus")
        if focus not in _PRACTICE_VALUES:
            return None
        training_drill = session.get("training_drill", "none")
        if training_drill not in available_training_values():
            training_drill = "none"
        training_points, decision_effects = training_decision_for_drill(training_drill)
        return SliceDecisions(
            practice_focus=focus,
            team_talk=session.get("team_talk", ""),
            fallout_post=session.get("fallout_post", ""),
            training_points=training_points,
            decision_effects=decision_effects,
        )

    def require_decisions():
        decisions = current_decisions()
        if decisions is None:
            flash("Pick what the team drills in practice first.")
            return None
        return decisions

    def training_effect_label(effect) -> str:
        sign = "+" if effect.delta >= 0 else ""
        return f"{display_name(effect.player)} {sign}{effect.delta} {effect.skill} ({effect.training_points} TP)"

    def training_spent(decisions: SliceDecisions) -> int:
        return sum(effect.training_points for effect in decisions.decision_effects)

    def relationship_fallout_label(fallout) -> str:
        a = display_name(fallout.a)
        b = display_name(fallout.b)
        if fallout.kind == "flashpoint":
            verdict = "flared"
        elif fallout.kind == "split":
            verdict = "split the room"
        elif fallout.kind == "repair":
            verdict = "cooled down"
        else:
            verdict = "simmered"
        return f"{a} ↔ {b} ({fallout.axis}) {verdict}: {fallout.summary}"

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
            "training_effect_label": training_effect_label,
            "training_spent": training_spent,
            "relationship_fallout_label": relationship_fallout_label,
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
            training_drill = (request.form.get("training_drill") or "none").strip()
            if training_drill not in available_training_values():
                flash("Choose one focused training drill.")
                return redirect(url_for("practice"))
            session["practice_focus"] = focus
            session["training_drill"] = training_drill
            return redirect(url_for("prematch"))
        return render_template(
            "practice.html",
            choices=PRACTICE_CHOICES,
            training_drills=available_training_drills(),
            analyst_reads=ANALYST_READS if fallout_repair_unlocked() else (),
            selected=session.get("practice_focus"),
            selected_training=session.get("training_drill", "none"),
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
                training_points=decisions.training_points,
                decision_effects=decisions.decision_effects,
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
            week7_setup_path=str(run_dir / WEEK7_SETUP_FILENAME),
            cited=cited,
        )

    @app.route("/week7", methods=["GET", "POST"])
    def week7():
        decisions = require_decisions()
        if decisions is None:
            return redirect(url_for("practice"))
        result = run_slice(world, config, decisions, content_config=content_config)
        if result.week7_setup is None:
            flash("Week 7 focus unlocks after a repair-vs-reps focused rep.")
            return redirect(url_for("practice"))

        setup = setup_payload_from_week7_setup(result.week7_setup)
        options = week7_focus_options(setup)
        lock = None
        focus_path = ""
        if request.method == "POST":
            selected = (request.form.get("week7_focus") or "").strip()
            try:
                lock = resolve_week7_focus(setup, selected)
            except ValueError:
                flash("Choose a Week 7 focus.")
            else:
                run_dir = output_root / result.slice_id
                run_dir.mkdir(parents=True, exist_ok=True)
                setup_target = run_dir / WEEK7_SETUP_FILENAME
                if not setup_target.exists():
                    setup_export = render_week7_setup_json(slice_events(result, world))
                    if setup_export:
                        setup_target.write_text(setup_export, encoding="utf-8", newline="\n")
                target = run_dir / WEEK7_FOCUS_FILENAME
                target.write_text(render_week7_focus_json(lock), encoding="utf-8", newline="\n")
                focus_path = str(target)
        return render_template(
            "week7.html",
            result=result,
            setup=setup,
            options=options,
            lock=lock,
            focus_path=focus_path,
        )

    @app.route("/week7/result", methods=["GET", "POST"])
    def week7_result():
        decisions = require_decisions()
        if decisions is None:
            return redirect(url_for("practice"))
        result = run_slice(world, config, decisions, content_config=content_config)
        if result.week7_setup is None:
            flash("Week 7 pressure unlocks after a repair-vs-reps focused rep.")
            return redirect(url_for("practice"))

        run_dir = output_root / result.slice_id
        setup_path = run_dir / WEEK7_SETUP_FILENAME
        focus_path = run_dir / WEEK7_FOCUS_FILENAME
        pressure_path = run_dir / WEEK7_PRESSURE_FILENAME
        missing = [
            name
            for name, path in (
                (WEEK7_SETUP_FILENAME, setup_path),
                (WEEK7_FOCUS_FILENAME, focus_path),
            )
            if not path.is_file()
        ]
        pressure = None
        written_path = ""
        if not missing:
            try:
                setup = setup_payload_from_json(setup_path.read_text(encoding="utf-8"))
                focus = focus_payload_from_json(focus_path.read_text(encoding="utf-8"))
                resolved = resolve_week7_pressure(setup, focus)
            except ValueError as exc:
                flash(str(exc))
            else:
                if request.method == "POST":
                    run_dir.mkdir(parents=True, exist_ok=True)
                    pressure_path.write_text(
                        render_week7_pressure_json(resolved),
                        encoding="utf-8",
                        newline="\n",
                    )
                    written_path = str(pressure_path)
                    pressure = resolved
                elif pressure_path.is_file():
                    written_path = str(pressure_path)
                    pressure = resolved

        return render_template(
            "week7_result.html",
            result=result,
            missing=missing,
            pressure=pressure,
            pressure_path=written_path,
        )

    @app.route("/week8", methods=["GET", "POST"])
    def week8():
        decisions = require_decisions()
        if decisions is None:
            return redirect(url_for("practice"))
        result = run_slice(world, config, decisions, content_config=content_config)
        if result.week7_setup is None:
            flash("Week 8 prep unlocks after a Week 7 pressure result.")
            return redirect(url_for("practice"))

        run_dir = output_root / result.slice_id
        setup_path = run_dir / WEEK7_SETUP_FILENAME
        focus_path = run_dir / WEEK7_FOCUS_FILENAME
        pressure_path = run_dir / WEEK7_PRESSURE_FILENAME
        prep_path = run_dir / WEEK8_PREP_FILENAME
        missing = [
            name
            for name, path in (
                (WEEK7_SETUP_FILENAME, setup_path),
                (WEEK7_FOCUS_FILENAME, focus_path),
                (WEEK7_PRESSURE_FILENAME, pressure_path),
            )
            if not path.is_file()
        ]
        plan = None
        lock = None
        prep_written_path = ""
        if not missing:
            try:
                setup = setup_payload_from_json(setup_path.read_text(encoding="utf-8"))
                focus = focus_payload_from_json(focus_path.read_text(encoding="utf-8"))
                pressure = pressure_payload_from_json(pressure_path.read_text(encoding="utf-8"))
                plan = week8_prep_plan(setup, focus, pressure)
            except ValueError as exc:
                flash(str(exc))
            else:
                if request.method == "POST":
                    selected = (request.form.get("week8_prep") or "").strip()
                    try:
                        lock = resolve_week8_prep(plan, selected)
                    except ValueError:
                        flash("Choose a Week 8 prep response.")
                    else:
                        prep_path.write_text(
                            render_week8_prep_json(lock),
                            encoding="utf-8",
                            newline="\n",
                        )
                        prep_written_path = str(prep_path)
                elif prep_path.is_file():
                    try:
                        lock = week8_prep_from_json(prep_path.read_text(encoding="utf-8"))
                    except ValueError as exc:
                        flash(str(exc))
                    else:
                        prep_written_path = str(prep_path)

        return render_template(
            "week8.html",
            result=result,
            missing=missing,
            plan=plan,
            lock=lock,
            prep_path=prep_written_path,
        )

    @app.route("/week8/scrim", methods=["GET", "POST"])
    def week8_scrim():
        decisions = require_decisions()
        if decisions is None:
            return redirect(url_for("practice"))
        result = run_slice(world, config, decisions, content_config=content_config)
        if result.week7_setup is None:
            flash("Week 8 scrim setup unlocks after Week 8 prep.")
            return redirect(url_for("practice"))

        run_dir = output_root / result.slice_id
        setup_path = run_dir / WEEK7_SETUP_FILENAME
        focus_path = run_dir / WEEK7_FOCUS_FILENAME
        pressure_path = run_dir / WEEK7_PRESSURE_FILENAME
        prep_path = run_dir / WEEK8_PREP_FILENAME
        scrim_path = run_dir / WEEK8_SCRIM_FILENAME
        missing = [
            name
            for name, path in (
                (WEEK7_SETUP_FILENAME, setup_path),
                (WEEK7_FOCUS_FILENAME, focus_path),
                (WEEK7_PRESSURE_FILENAME, pressure_path),
                (WEEK8_PREP_FILENAME, prep_path),
            )
            if not path.is_file()
        ]
        plan = None
        lock = None
        scrim_written_path = ""
        if not missing:
            try:
                setup = setup_payload_from_json(setup_path.read_text(encoding="utf-8"))
                focus = focus_payload_from_json(focus_path.read_text(encoding="utf-8"))
                pressure = pressure_payload_from_json(pressure_path.read_text(encoding="utf-8"))
                prep = week8_prep_from_json(prep_path.read_text(encoding="utf-8"))
                plan = week8_scrim_plan(setup, focus, pressure, prep)
            except ValueError as exc:
                flash(str(exc))
            else:
                if request.method == "POST":
                    selected = (request.form.get("week8_scrim") or "").strip()
                    try:
                        lock = resolve_week8_scrim(plan, selected)
                    except ValueError:
                        flash("Choose a Week 8 scrim call.")
                    else:
                        scrim_path.write_text(
                            render_week8_scrim_json(lock),
                            encoding="utf-8",
                            newline="\n",
                        )
                        scrim_written_path = str(scrim_path)
                elif scrim_path.is_file():
                    try:
                        lock = week8_scrim_from_json(scrim_path.read_text(encoding="utf-8"))
                    except ValueError as exc:
                        flash(str(exc))
                    else:
                        scrim_written_path = str(scrim_path)

        return render_template(
            "week8_scrim.html",
            result=result,
            missing=missing,
            plan=plan,
            lock=lock,
            scrim_path=scrim_written_path,
        )

    @app.route("/week8/match", methods=["GET", "POST"])
    def week8_match():
        decisions = require_decisions()
        if decisions is None:
            return redirect(url_for("practice"))
        result = run_slice(world, config, decisions, content_config=content_config)
        if result.week7_setup is None:
            flash("Week 8 match preview unlocks after the Week 8 scrim.")
            return redirect(url_for("practice"))

        run_dir = output_root / result.slice_id
        setup_path = run_dir / WEEK7_SETUP_FILENAME
        focus_path = run_dir / WEEK7_FOCUS_FILENAME
        pressure_path = run_dir / WEEK7_PRESSURE_FILENAME
        prep_path = run_dir / WEEK8_PREP_FILENAME
        scrim_path = run_dir / WEEK8_SCRIM_FILENAME
        match_plan_path = run_dir / WEEK8_MATCH_PLAN_FILENAME
        missing = [
            name
            for name, path in (
                (WEEK7_SETUP_FILENAME, setup_path),
                (WEEK7_FOCUS_FILENAME, focus_path),
                (WEEK7_PRESSURE_FILENAME, pressure_path),
                (WEEK8_PREP_FILENAME, prep_path),
                (WEEK8_SCRIM_FILENAME, scrim_path),
            )
            if not path.is_file()
        ]
        preview = None
        lock = None
        match_plan_written_path = ""
        if not missing:
            try:
                setup = setup_payload_from_json(setup_path.read_text(encoding="utf-8"))
                focus = focus_payload_from_json(focus_path.read_text(encoding="utf-8"))
                pressure = pressure_payload_from_json(pressure_path.read_text(encoding="utf-8"))
                prep = week8_prep_from_json(prep_path.read_text(encoding="utf-8"))
                scrim = week8_scrim_from_json(scrim_path.read_text(encoding="utf-8"))
                preview = week8_match_preview(setup, focus, pressure, prep, scrim)
            except ValueError as exc:
                flash(str(exc))
            else:
                if request.method == "POST":
                    selected = (request.form.get("week8_match_plan") or "").strip()
                    try:
                        lock = resolve_week8_match_plan(preview, selected)
                    except ValueError:
                        flash("Choose a Week 8 match plan.")
                    else:
                        match_plan_path.write_text(
                            render_week8_match_plan_json(lock),
                            encoding="utf-8",
                            newline="\n",
                        )
                        match_plan_written_path = str(match_plan_path)
                elif match_plan_path.is_file():
                    try:
                        lock = week8_match_plan_from_json(match_plan_path.read_text(encoding="utf-8"))
                    except ValueError as exc:
                        flash(str(exc))
                    else:
                        match_plan_written_path = str(match_plan_path)

        return render_template(
            "week8_match.html",
            result=result,
            missing=missing,
            preview=preview,
            lock=lock,
            match_plan_path=match_plan_written_path,
        )

    @app.route("/week8/match/result", methods=["GET", "POST"])
    def week8_match_result():
        decisions = require_decisions()
        if decisions is None:
            return redirect(url_for("practice"))
        result = run_slice(world, config, decisions, content_config=content_config)
        if result.week7_setup is None:
            flash("Week 8 match result unlocks after the Week 8 match plan.")
            return redirect(url_for("practice"))

        run_dir = output_root / result.slice_id
        match_plan_path = run_dir / WEEK8_MATCH_PLAN_FILENAME
        match_result_path = run_dir / WEEK8_MATCH_RESULT_FILENAME
        missing = [
            name
            for name, path in (
                (WEEK8_MATCH_PLAN_FILENAME, match_plan_path),
            )
            if not path.is_file()
        ]
        plan = None
        match_result = None
        match_result_written_path = ""
        if not missing:
            try:
                plan = week8_match_plan_from_json(match_plan_path.read_text(encoding="utf-8"))
            except ValueError as exc:
                flash(str(exc))
            else:
                if request.method == "POST":
                    match_result = resolve_week8_match_result(plan)
                    match_result_path.write_text(
                        render_week8_match_result_json(match_result),
                        encoding="utf-8",
                        newline="\n",
                    )
                    match_result_written_path = str(match_result_path)
                elif match_result_path.is_file():
                    try:
                        match_result = week8_match_result_from_json(
                            match_result_path.read_text(encoding="utf-8")
                        )
                    except ValueError as exc:
                        flash(str(exc))
                    else:
                        match_result_written_path = str(match_result_path)

        return render_template(
            "week8_match_result.html",
            result=result,
            missing=missing,
            plan=plan,
            match_result=match_result,
            match_result_path=match_result_written_path,
        )

    @app.route("/week9", methods=["GET", "POST"])
    def week9():
        decisions = require_decisions()
        if decisions is None:
            return redirect(url_for("practice"))
        result = run_slice(world, config, decisions, content_config=content_config)
        if result.week7_setup is None:
            flash("Week 9 setup unlocks after the Week 8 match result.")
            return redirect(url_for("practice"))

        run_dir = output_root / result.slice_id
        match_result_path = run_dir / WEEK8_MATCH_RESULT_FILENAME
        week9_setup_path = run_dir / WEEK9_SETUP_FILENAME
        missing = [
            name
            for name, path in (
                (WEEK8_MATCH_RESULT_FILENAME, match_result_path),
            )
            if not path.is_file()
        ]
        plan = None
        lock = None
        week9_setup_written_path = ""
        if not missing:
            try:
                match_result = week8_match_result_from_json(
                    match_result_path.read_text(encoding="utf-8")
                )
                plan = week9_setup_plan(match_result)
            except ValueError as exc:
                flash(str(exc))
            else:
                if request.method == "POST":
                    selected = (request.form.get("week9_response") or "").strip()
                    try:
                        lock = resolve_week9_setup(plan, selected)
                    except ValueError:
                        flash("Choose a Week 9 response.")
                    else:
                        week9_setup_path.write_text(
                            render_week9_setup_json(lock),
                            encoding="utf-8",
                            newline="\n",
                        )
                        week9_setup_written_path = str(week9_setup_path)
                elif week9_setup_path.is_file():
                    try:
                        lock = week9_setup_from_json(week9_setup_path.read_text(encoding="utf-8"))
                    except ValueError as exc:
                        flash(str(exc))
                    else:
                        week9_setup_written_path = str(week9_setup_path)

        return render_template(
            "week9.html",
            result=result,
            missing=missing,
            plan=plan,
            lock=lock,
            week9_setup_path=week9_setup_written_path,
        )

    @app.route("/week9/prep", methods=["GET", "POST"])
    def week9_prep():
        decisions = require_decisions()
        if decisions is None:
            return redirect(url_for("practice"))
        result = run_slice(world, config, decisions, content_config=content_config)
        if result.week7_setup is None:
            flash("Week 9 prep unlocks after the Week 9 setup response.")
            return redirect(url_for("practice"))

        run_dir = output_root / result.slice_id
        week9_setup_path = run_dir / WEEK9_SETUP_FILENAME
        week9_prep_path = run_dir / WEEK9_PREP_FILENAME
        missing = [
            name
            for name, path in (
                (WEEK9_SETUP_FILENAME, week9_setup_path),
            )
            if not path.is_file()
        ]
        plan = None
        lock = None
        week9_prep_written_path = ""
        if not missing:
            try:
                setup = week9_setup_from_json(week9_setup_path.read_text(encoding="utf-8"))
                plan = week9_prep_plan(setup)
            except ValueError as exc:
                flash(str(exc))
            else:
                if request.method == "POST":
                    selected = (request.form.get("week9_prep") or "").strip()
                    try:
                        lock = resolve_week9_prep(plan, selected)
                    except ValueError:
                        flash("Choose a Week 9 prep lane.")
                    else:
                        week9_prep_path.write_text(
                            render_week9_prep_json(lock),
                            encoding="utf-8",
                            newline="\n",
                        )
                        week9_prep_written_path = str(week9_prep_path)
                elif week9_prep_path.is_file():
                    try:
                        lock = week9_prep_from_json(week9_prep_path.read_text(encoding="utf-8"))
                    except ValueError as exc:
                        flash(str(exc))
                    else:
                        week9_prep_written_path = str(week9_prep_path)

        return render_template(
            "week9_prep.html",
            result=result,
            missing=missing,
            plan=plan,
            lock=lock,
            week9_prep_path=week9_prep_written_path,
        )

    @app.route("/week9/scrim", methods=["GET", "POST"])
    def week9_scrim():
        decisions = require_decisions()
        if decisions is None:
            return redirect(url_for("practice"))
        result = run_slice(world, config, decisions, content_config=content_config)
        if result.week7_setup is None:
            flash("Week 9 scrim unlocks after the Week 9 prep lane.")
            return redirect(url_for("practice"))

        run_dir = output_root / result.slice_id
        week9_setup_path = run_dir / WEEK9_SETUP_FILENAME
        week9_prep_path = run_dir / WEEK9_PREP_FILENAME
        week9_scrim_path = run_dir / WEEK9_SCRIM_FILENAME
        missing = [
            name
            for name, path in (
                (WEEK9_SETUP_FILENAME, week9_setup_path),
                (WEEK9_PREP_FILENAME, week9_prep_path),
            )
            if not path.is_file()
        ]
        plan = None
        lock = None
        week9_scrim_written_path = ""
        if not missing:
            try:
                setup = week9_setup_from_json(week9_setup_path.read_text(encoding="utf-8"))
                prep = week9_prep_from_json(week9_prep_path.read_text(encoding="utf-8"))
                plan = week9_scrim_plan(setup, prep)
            except ValueError as exc:
                flash(str(exc))
            else:
                if request.method == "POST":
                    selected = (request.form.get("week9_scrim") or "").strip()
                    try:
                        lock = resolve_week9_scrim(plan, selected)
                    except ValueError:
                        flash("Choose a Week 9 scrim read.")
                    else:
                        week9_scrim_path.write_text(
                            render_week9_scrim_json(lock),
                            encoding="utf-8",
                            newline="\n",
                        )
                        week9_scrim_written_path = str(week9_scrim_path)
                elif week9_scrim_path.is_file():
                    try:
                        lock = week9_scrim_from_json(week9_scrim_path.read_text(encoding="utf-8"))
                    except ValueError as exc:
                        flash(str(exc))
                    else:
                        week9_scrim_written_path = str(week9_scrim_path)

        return render_template(
            "week9_scrim.html",
            result=result,
            missing=missing,
            plan=plan,
            lock=lock,
            week9_scrim_path=week9_scrim_written_path,
        )

    @app.route("/week9/match", methods=["GET", "POST"])
    def week9_match():
        decisions = require_decisions()
        if decisions is None:
            return redirect(url_for("practice"))
        result = run_slice(world, config, decisions, content_config=content_config)
        if result.week7_setup is None:
            flash("Week 9 match plan unlocks after the Week 9 scrim read.")
            return redirect(url_for("practice"))

        run_dir = output_root / result.slice_id
        week9_setup_path = run_dir / WEEK9_SETUP_FILENAME
        week9_prep_path = run_dir / WEEK9_PREP_FILENAME
        week9_scrim_path = run_dir / WEEK9_SCRIM_FILENAME
        week9_match_plan_path = run_dir / WEEK9_MATCH_PLAN_FILENAME
        missing = [
            name
            for name, path in (
                (WEEK9_SETUP_FILENAME, week9_setup_path),
                (WEEK9_PREP_FILENAME, week9_prep_path),
                (WEEK9_SCRIM_FILENAME, week9_scrim_path),
            )
            if not path.is_file()
        ]
        preview = None
        lock = None
        week9_match_plan_written_path = ""
        if not missing:
            try:
                setup = week9_setup_from_json(week9_setup_path.read_text(encoding="utf-8"))
                prep = week9_prep_from_json(week9_prep_path.read_text(encoding="utf-8"))
                scrim = week9_scrim_from_json(week9_scrim_path.read_text(encoding="utf-8"))
                preview = week9_match_plan_preview(setup, prep, scrim)
            except ValueError as exc:
                flash(str(exc))
            else:
                if request.method == "POST":
                    selected = (request.form.get("week9_match_plan") or "").strip()
                    try:
                        lock = resolve_week9_match_plan(preview, selected)
                    except ValueError:
                        flash("Choose a Week 9 match plan.")
                    else:
                        week9_match_plan_path.write_text(
                            render_week9_match_plan_json(lock),
                            encoding="utf-8",
                            newline="\n",
                        )
                        week9_match_plan_written_path = str(week9_match_plan_path)
                elif week9_match_plan_path.is_file():
                    try:
                        lock = week9_match_plan_from_json(week9_match_plan_path.read_text(encoding="utf-8"))
                    except ValueError as exc:
                        flash(str(exc))
                    else:
                        week9_match_plan_written_path = str(week9_match_plan_path)

        return render_template(
            "week9_match.html",
            result=result,
            missing=missing,
            preview=preview,
            lock=lock,
            week9_match_plan_path=week9_match_plan_written_path,
        )

    @app.route("/week9/match/result", methods=["GET", "POST"])
    def week9_match_result():
        decisions = require_decisions()
        if decisions is None:
            return redirect(url_for("practice"))
        result = run_slice(world, config, decisions, content_config=content_config)
        if result.week7_setup is None:
            flash("Week 9 match result unlocks after the Week 9 match plan.")
            return redirect(url_for("practice"))

        run_dir = output_root / result.slice_id
        week9_setup_path = run_dir / WEEK9_SETUP_FILENAME
        week9_prep_path = run_dir / WEEK9_PREP_FILENAME
        week9_scrim_path = run_dir / WEEK9_SCRIM_FILENAME
        week9_match_plan_path = run_dir / WEEK9_MATCH_PLAN_FILENAME
        week9_match_result_path = run_dir / WEEK9_MATCH_RESULT_FILENAME
        missing = [
            name
            for name, path in (
                (WEEK9_SETUP_FILENAME, week9_setup_path),
                (WEEK9_PREP_FILENAME, week9_prep_path),
                (WEEK9_SCRIM_FILENAME, week9_scrim_path),
                (WEEK9_MATCH_PLAN_FILENAME, week9_match_plan_path),
            )
            if not path.is_file()
        ]
        plan = None
        match_result = None
        week9_match_result_written_path = ""
        if not missing:
            try:
                setup = week9_setup_from_json(week9_setup_path.read_text(encoding="utf-8"))
                prep = week9_prep_from_json(week9_prep_path.read_text(encoding="utf-8"))
                scrim = week9_scrim_from_json(week9_scrim_path.read_text(encoding="utf-8"))
                plan = week9_match_plan_from_json(week9_match_plan_path.read_text(encoding="utf-8"))
            except ValueError as exc:
                flash(str(exc))
            else:
                if request.method == "POST":
                    match_result = resolve_week9_match_result(setup, prep, scrim, plan)
                    week9_match_result_path.write_text(
                        render_week9_match_result_json(match_result),
                        encoding="utf-8",
                        newline="\n",
                    )
                    week9_match_result_written_path = str(week9_match_result_path)
                elif week9_match_result_path.is_file():
                    try:
                        match_result = week9_match_result_from_json(
                            week9_match_result_path.read_text(encoding="utf-8")
                        )
                    except ValueError as exc:
                        flash(str(exc))
                    else:
                        week9_match_result_written_path = str(week9_match_result_path)

        return render_template(
            "week9_match_result.html",
            result=result,
            missing=missing,
            plan=plan,
            match_result=match_result,
            week9_match_result_path=week9_match_result_written_path,
        )

    @app.route("/week10/fallout", methods=["GET", "POST"])
    def week10_fallout():
        decisions = require_decisions()
        if decisions is None:
            return redirect(url_for("practice"))
        result = run_slice(world, config, decisions, content_config=content_config)
        if result.week7_setup is None:
            flash("Week 10 fallout unlocks after the Week 9 match result.")
            return redirect(url_for("practice"))

        run_dir = output_root / result.slice_id
        week9_match_result_path = run_dir / WEEK9_MATCH_RESULT_FILENAME
        week10_fallout_path = run_dir / WEEK10_FALLOUT_FILENAME
        missing = [
            name
            for name, path in (
                (WEEK9_MATCH_RESULT_FILENAME, week9_match_result_path),
            )
            if not path.is_file()
        ]
        plan = None
        lock = None
        week10_fallout_written_path = ""
        if not missing:
            try:
                match_result = week9_match_result_from_json(
                    week9_match_result_path.read_text(encoding="utf-8")
                )
                plan = week10_fallout_plan(match_result)
            except ValueError as exc:
                flash(str(exc))
            else:
                if request.method == "POST":
                    selected = (request.form.get("week10_fallout") or "").strip()
                    try:
                        lock = resolve_week10_fallout(match_result, plan, selected)
                    except ValueError:
                        flash("Choose a Week 10 fallout response.")
                    else:
                        week10_fallout_path.write_text(
                            render_week10_fallout_json(lock),
                            encoding="utf-8",
                            newline="\n",
                        )
                        week10_fallout_written_path = str(week10_fallout_path)
                elif week10_fallout_path.is_file():
                    try:
                        lock = week10_fallout_from_json(week10_fallout_path.read_text(encoding="utf-8"))
                    except ValueError as exc:
                        flash(str(exc))
                    else:
                        week10_fallout_written_path = str(week10_fallout_path)

        return render_template(
            "week10_fallout.html",
            result=result,
            missing=missing,
            plan=plan,
            lock=lock,
            week10_fallout_path=week10_fallout_written_path,
        )

    @app.route("/week10/prep", methods=["GET", "POST"])
    def week10_prep():
        decisions = require_decisions()
        if decisions is None:
            return redirect(url_for("practice"))
        result = run_slice(world, config, decisions, content_config=content_config)
        if result.week7_setup is None:
            flash("Week 10 prep unlocks after the Week 10 fallout response.")
            return redirect(url_for("practice"))

        run_dir = output_root / result.slice_id
        week10_fallout_path = run_dir / WEEK10_FALLOUT_FILENAME
        week10_prep_path = run_dir / WEEK10_PREP_FILENAME
        missing = [
            name
            for name, path in (
                (WEEK10_FALLOUT_FILENAME, week10_fallout_path),
            )
            if not path.is_file()
        ]
        plan = None
        lock = None
        week10_prep_written_path = ""
        if not missing:
            try:
                fallout = week10_fallout_from_json(week10_fallout_path.read_text(encoding="utf-8"))
                plan = week10_prep_plan(fallout)
            except ValueError as exc:
                flash(str(exc))
            else:
                if request.method == "POST":
                    selected = (request.form.get("week10_prep") or "").strip()
                    try:
                        lock = resolve_week10_prep(fallout, plan, selected)
                    except ValueError:
                        flash("Choose a Week 10 prep allocation.")
                    else:
                        week10_prep_path.write_text(
                            render_week10_prep_json(lock),
                            encoding="utf-8",
                            newline="\n",
                        )
                        week10_prep_written_path = str(week10_prep_path)
                elif week10_prep_path.is_file():
                    try:
                        lock = week10_prep_from_json(week10_prep_path.read_text(encoding="utf-8"))
                    except ValueError as exc:
                        flash(str(exc))
                    else:
                        week10_prep_written_path = str(week10_prep_path)

        return render_template(
            "week10_prep.html",
            result=result,
            missing=missing,
            plan=plan,
            lock=lock,
            week10_prep_path=week10_prep_written_path,
        )

    @app.route("/week10/scrim", methods=["GET", "POST"])
    def week10_scrim():
        decisions = require_decisions()
        if decisions is None:
            return redirect(url_for("practice"))
        result = run_slice(world, config, decisions, content_config=content_config)
        if result.week7_setup is None:
            flash("Week 10 scrim unlocks after the Week 10 prep block.")
            return redirect(url_for("practice"))

        run_dir = output_root / result.slice_id
        week10_prep_path = run_dir / WEEK10_PREP_FILENAME
        week10_scrim_path = run_dir / WEEK10_SCRIM_FILENAME
        missing = [
            name
            for name, path in (
                (WEEK10_PREP_FILENAME, week10_prep_path),
            )
            if not path.is_file()
        ]
        plan = None
        lock = None
        week10_scrim_written_path = ""
        if not missing:
            try:
                prep = week10_prep_from_json(week10_prep_path.read_text(encoding="utf-8"))
                plan = week10_scrim_plan(prep)
            except ValueError as exc:
                flash(str(exc))
            else:
                if request.method == "POST":
                    selected = (request.form.get("week10_scrim") or "").strip()
                    try:
                        lock = resolve_week10_scrim(prep, plan, selected)
                    except ValueError:
                        flash("Choose a Week 10 scrim protocol.")
                    else:
                        week10_scrim_path.write_text(
                            render_week10_scrim_json(lock),
                            encoding="utf-8",
                            newline="\n",
                        )
                        week10_scrim_written_path = str(week10_scrim_path)
                elif week10_scrim_path.is_file():
                    try:
                        lock = week10_scrim_from_json(week10_scrim_path.read_text(encoding="utf-8"))
                    except ValueError as exc:
                        flash(str(exc))
                    else:
                        week10_scrim_written_path = str(week10_scrim_path)

        return render_template(
            "week10_scrim.html",
            result=result,
            missing=missing,
            plan=plan,
            lock=lock,
            week10_scrim_path=week10_scrim_written_path,
        )

    @app.route("/week10/match", methods=["GET", "POST"])
    def week10_match():
        decisions = require_decisions()
        if decisions is None:
            return redirect(url_for("practice"))
        result = run_slice(world, config, decisions, content_config=content_config)
        if result.week7_setup is None:
            flash("Week 10 match plan unlocks after the Week 10 scrim.")
            return redirect(url_for("practice"))

        run_dir = output_root / result.slice_id
        week10_scrim_path = run_dir / WEEK10_SCRIM_FILENAME
        week10_match_plan_path = run_dir / WEEK10_MATCH_PLAN_FILENAME
        missing = [
            name
            for name, path in (
                (WEEK10_SCRIM_FILENAME, week10_scrim_path),
            )
            if not path.is_file()
        ]
        preview = None
        lock = None
        week10_match_plan_written_path = ""
        if not missing:
            try:
                scrim = week10_scrim_from_json(week10_scrim_path.read_text(encoding="utf-8"))
                preview = week10_match_plan_preview(scrim)
            except ValueError as exc:
                flash(str(exc))
            else:
                if request.method == "POST":
                    selected = (request.form.get("week10_match_plan") or "").strip()
                    try:
                        lock = resolve_week10_match_plan(preview, selected)
                    except ValueError:
                        flash("Choose a Week 10 match plan.")
                    else:
                        week10_match_plan_path.write_text(
                            render_week10_match_plan_json(lock),
                            encoding="utf-8",
                            newline="\n",
                        )
                        week10_match_plan_written_path = str(week10_match_plan_path)
                elif week10_match_plan_path.is_file():
                    try:
                        lock = week10_match_plan_from_json(week10_match_plan_path.read_text(encoding="utf-8"))
                    except ValueError as exc:
                        flash(str(exc))
                    else:
                        week10_match_plan_written_path = str(week10_match_plan_path)

        return render_template(
            "week10_match.html",
            result=result,
            missing=missing,
            preview=preview,
            lock=lock,
            week10_match_plan_path=week10_match_plan_written_path,
        )

    @app.route("/week10/match/result", methods=["GET", "POST"])
    def week10_match_result():
        decisions = require_decisions()
        if decisions is None:
            return redirect(url_for("practice"))
        result = run_slice(world, config, decisions, content_config=content_config)
        if result.week7_setup is None:
            flash("Week 10 match result unlocks after the Week 10 match plan.")
            return redirect(url_for("practice"))

        run_dir = output_root / result.slice_id
        week10_match_plan_path = run_dir / WEEK10_MATCH_PLAN_FILENAME
        week10_match_result_path = run_dir / WEEK10_MATCH_RESULT_FILENAME
        missing = [
            name
            for name, path in (
                (WEEK10_MATCH_PLAN_FILENAME, week10_match_plan_path),
            )
            if not path.is_file()
        ]
        plan = None
        match_result = None
        week10_match_result_written_path = ""
        if not missing:
            try:
                plan = week10_match_plan_from_json(week10_match_plan_path.read_text(encoding="utf-8"))
            except ValueError as exc:
                flash(str(exc))
            else:
                if request.method == "POST":
                    match_result = resolve_week10_match_result(plan)
                    week10_match_result_path.write_text(
                        render_week10_match_result_json(match_result),
                        encoding="utf-8",
                        newline="\n",
                    )
                    week10_match_result_written_path = str(week10_match_result_path)
                elif week10_match_result_path.is_file():
                    try:
                        match_result = week10_match_result_from_json(
                            week10_match_result_path.read_text(encoding="utf-8")
                        )
                    except ValueError as exc:
                        flash(str(exc))
                    else:
                        week10_match_result_written_path = str(week10_match_result_path)

        return render_template(
            "week10_match_result.html",
            result=result,
            missing=missing,
            plan=plan,
            match_result=match_result,
            week10_match_result_path=week10_match_result_written_path,
        )

    @app.route("/week10/post-match-review", methods=["GET", "POST"])
    def week10_post_match_review():
        decisions = require_decisions()
        if decisions is None:
            return redirect(url_for("practice"))
        result = run_slice(world, config, decisions, content_config=content_config)
        if result.week7_setup is None:
            flash("Week 10 post-match review unlocks after the Week 10 result.")
            return redirect(url_for("practice"))

        run_dir = output_root / result.slice_id
        week10_match_result_path = run_dir / WEEK10_MATCH_RESULT_FILENAME
        week10_review_path = run_dir / WEEK10_POST_MATCH_REVIEW_FILENAME
        missing = [
            name
            for name, path in (
                (WEEK10_MATCH_RESULT_FILENAME, week10_match_result_path),
            )
            if not path.is_file()
        ]
        review_plan = None
        review_lock = None
        week10_review_written_path = ""
        if not missing:
            try:
                match_result = week10_match_result_from_json(
                    week10_match_result_path.read_text(encoding="utf-8")
                )
                review_plan = week10_post_match_review_plan(match_result)
            except ValueError as exc:
                flash(str(exc))
            else:
                if request.method == "POST":
                    selected = (request.form.get("week10_post_match_review") or "").strip()
                    try:
                        review_lock = resolve_week10_post_match_review(review_plan, selected)
                    except ValueError:
                        flash("Choose a Week 10 post-match review.")
                    else:
                        week10_review_path.write_text(
                            render_week10_post_match_review_json(review_lock),
                            encoding="utf-8",
                            newline="\n",
                        )
                        week10_review_written_path = str(week10_review_path)
                elif week10_review_path.is_file():
                    try:
                        review_lock = week10_post_match_review_from_json(
                            week10_review_path.read_text(encoding="utf-8")
                        )
                    except ValueError as exc:
                        flash(str(exc))
                    else:
                        week10_review_written_path = str(week10_review_path)

        return render_template(
            "week10_post_match_review.html",
            result=result,
            missing=missing,
            review_plan=review_plan,
            review_lock=review_lock,
            week10_review_path=week10_review_written_path,
        )

    @app.route("/week11/setup", methods=["GET", "POST"])
    def week11_setup():
        decisions = require_decisions()
        if decisions is None:
            return redirect(url_for("practice"))
        result = run_slice(world, config, decisions, content_config=content_config)
        if result.week7_setup is None:
            flash("Week 11 setup unlocks after the Week 10 post-match review.")
            return redirect(url_for("practice"))

        run_dir = output_root / result.slice_id
        week10_review_path = run_dir / WEEK10_POST_MATCH_REVIEW_FILENAME
        week11_setup_path = run_dir / WEEK11_SETUP_FILENAME
        missing = [
            name
            for name, path in (
                (WEEK10_POST_MATCH_REVIEW_FILENAME, week10_review_path),
            )
            if not path.is_file()
        ]
        setup_plan = None
        setup_lock = None
        week11_setup_written_path = ""
        if not missing:
            try:
                review = week10_post_match_review_from_json(week10_review_path.read_text(encoding="utf-8"))
                setup_plan = week11_setup_plan(review)
            except ValueError as exc:
                flash(str(exc))
            else:
                if request.method == "POST":
                    selected = (request.form.get("week11_setup") or "").strip()
                    try:
                        setup_lock = resolve_week11_setup(setup_plan, selected)
                    except ValueError:
                        flash("Choose a Week 11 setup posture.")
                    else:
                        week11_setup_path.write_text(
                            render_week11_setup_json(setup_lock),
                            encoding="utf-8",
                            newline="\n",
                        )
                        week11_setup_written_path = str(week11_setup_path)
                elif week11_setup_path.is_file():
                    try:
                        setup_lock = week11_setup_from_json(week11_setup_path.read_text(encoding="utf-8"))
                    except ValueError as exc:
                        flash(str(exc))
                    else:
                        week11_setup_written_path = str(week11_setup_path)

        return render_template(
            "week11_setup.html",
            result=result,
            missing=missing,
            setup_plan=setup_plan,
            setup_lock=setup_lock,
            week11_setup_path=week11_setup_written_path,
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
        # live feed from the in-memory event stream, byte-identical to the snapshot
        # in templated mode.
        result = run_slice(world, config, decisions, content_config=content_config)
        return render_feed_html(slice_events(result, world), world)

    @app.get("/healthz")
    def healthz():
        return {"status": "ok", "backend": content_config.backend}

    return app
