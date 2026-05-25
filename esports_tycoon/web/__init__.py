"""The local web app: manager view + Chirper feed in one Flask process.

This is the UI surface the founder locked for M0 (``scope-m0.md``): a single local
web app served on ``127.0.0.1``, not a TUI. It is a thin shell over the headless
:mod:`esports_tycoon.runner` engine — it collects the week's decisions (one MC plus
two 120-char open-text moments), walks the player through practice → match →
fallout, and on completion writes the ``runs/<slice_id>/`` recap artifact.

Flask is an opt-in dependency (``pip install -e .[web]``); it is imported lazily
inside :func:`create_app`, so importing this package — or running the engine and
its tests — never requires Flask to be installed.

    from esports_tycoon.web import create_app
    create_app().run(host="127.0.0.1", port=8000)
"""

from esports_tycoon.web.app import create_app

__all__ = ["create_app"]
