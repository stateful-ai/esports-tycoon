"""Canonical save root for esports-tycoon.

``saves/`` is the single documented home for the M0 canned save —
``saves/week6.yaml`` is the Week-6-of-8 save the slice runs on, and
``saves/SCHEMA.md`` is its field reference. The save is a **generated
artifact** of the canonical serializer (``esports_tycoon.canned.canonical``):
its source-of-truth content is the typed :class:`~esports_tycoon.schema.WorldState`
the loader materializes from it, its on-disk bytes are whatever the canonical
serializer emits for that world, and the supported way to (re)write the bytes
is ``make regen-golden`` (``scripts/regen_golden.py``). The fixture is never
hand-edited; see ``saves/SCHEMA.md`` § *Regeneration & blessing*.

This module is empty by design: it exists so the directory ships as package
data inside the wheel and the loader can resolve the save through
:func:`importlib.resources.files` no matter whether the project is run from a
source checkout or an installed wheel.

The save's on-disk shape is documented in :file:`SCHEMA.md`; the typed loader
that consumes it lives in :mod:`esports_tycoon.canned.loader`.
"""
