"""Canonical save root for esports-tycoon.

``saves/`` is the single documented home for hand-authored canned saves —
``saves/week6.yaml`` is the M0 Week-6-of-8 save the slice runs on, and
``saves/SCHEMA.md`` is its field reference. This module is empty by design: it
exists so the directory ships as package data inside the wheel and the loader
can resolve the save through :func:`importlib.resources.files` no matter
whether the project is run from a source checkout or an installed wheel.

The save's on-disk shape is documented in :file:`SCHEMA.md`; the typed loader
that consumes it lives in :mod:`esports_tycoon.canned.loader`.
"""
