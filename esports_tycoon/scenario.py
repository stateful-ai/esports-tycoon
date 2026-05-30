"""Author-facing helpers for hand-rolling a new save from scratch.

The canonical canned save (``saves/week6.yaml``) is the system of record, but it
is also large, dense, and entirely about one specific team — not a great
starting point for a hand-authored scenario. :func:`template` emits a minimal
*valid* save: every required field from the typed schema
(:mod:`esports_tycoon.schema`) is present, with placeholder values and inline
comments naming what each field is for. An author can pipe it to a file, edit
it, then run ``python -m esports_tycoon validate-save <path>`` to confirm the
shape held.

The template is byte-stable and self-contained: no f-strings, no datetimes —
just a frozen literal so the bytes ``scenario template`` writes today match the
bytes it writes tomorrow. The shape mirrors the field-declaration order in
:mod:`esports_tycoon.schema` (the same order the canonical serializer emits) so
an author reading the typed schema and an author reading the template see the
same skeleton.

The template ships exactly one player, one rival org, and one canned map
result — the minimum to satisfy the typed schema plus
:func:`esports_tycoon.canned.loader.check_referential_integrity` — and **no**
``memory_log`` entries / cites / clash pairs, because those are the parts of the
save that are hardest to author by hand (every cite ID has to resolve under the
no-hallucinated-history grounding contract). Authors add them once the skeleton
loads.

The test suite pins three contracts:

* the template emitted *is* a valid save the loader accepts;
* the bytes are stable across calls (no nondeterminism, no env leakage);
* the placeholder shape names every required top-level section.
"""

from __future__ import annotations

#: The exact bytes ``scenario template`` emits. A frozen literal (not built up
#: from ``yaml.safe_dump`` on a dict) so the comments survive — PyYAML drops
#: comments on round-trip — and so the output is byte-stable by construction.
#:
#: Every field present is one the typed schema requires; collections that are
#: optional (memory_log, clash_pairs, relationships, chirper_feed) are omitted
#: rather than spelled empty, matching the canonical save's
#: ``exclude_defaults`` convention. Authors fill in the placeholders, then
#: ``python -m esports_tycoon validate-save <path>`` confirms it loads.
TEMPLATE: str = """\
# Minimal valid esports-tycoon save. Edit the placeholders below, then run:
#   python -m esports_tycoon validate-save <this-file>
# Field-by-field reference: saves/SCHEMA.md.

# The save-format version this build speaks. Do not edit; the loader will
# refuse a future version and migrate an older one forward (loader._MIGRATIONS).
schema_version: 0

# RNG seed for the match resolver. Any non-negative int; the same save + same
# seed produces a bit-reproducible match.
seed: 0

save:
  id: my_save                       # stable opaque id for this save
  title: My Scenario                # human-facing title
  game: Vector Strike               # the (fictional) game; keep as-is for M0
  tone: dry-mockumentary            # narrative tone the content pack honours
  flavor: valorant-flavored         # flavor tag; free-form
  fiction_note: No real esports IP, players, orgs, or games. All names invented.
  season:
    league: My League               # league name
    division: My Division           # split / division name
    total_weeks: 8                  # season length in weeks (>=1)
    current_week: 1                 # week this save represents (>=1)
    playoff_cutoff: 6               # last playoff-qualifying place (>=1)
  team:
    id: myteam                      # the managed team's opaque id
    name: My Team
    tag: MYT
    handle: '@myteam'
    blurb: One-line org description.
    standing:
      wins: 0
      losses: 0
      place: 1                      # current table position (>=1)
      of: 8                         # number of teams in the table (>=1)
      note: One-line standing note.

# Roster. At least one player. Roles are: IGL, DUELIST, CONTROLLER, SENTINEL,
# INITIATOR (a full canonical lineup is one of each, but the schema does not
# require five). Memory logs and relationships are optional and omitted here —
# add them once the skeleton loads. Every memory id, if added, must be of the
# form mem:<this-player-id>:<event_slug> and globally unique.
players:
- id: player_one                    # opaque player id; referenced by relationships, cites, etc.
  name: Player One
  handle: '@player_one'
  role: IGL                         # one of: IGL, DUELIST, CONTROLLER, SENTINEL, INITIATOR
  age: 25                           # non-negative integer
  signature_operative: Atlas        # the operative this player mains
  bio: One- or two-sentence bio.
  persona_voice: One-line voice contract — how this character speaks.
  traits:
  - placeholder-trait               # free-form trait tags

# Rival orgs in the league. At least one is needed because last_week.opponent
# below must resolve to a rival_org id. The star's id lives in the same id
# space as players (cites / clash_pairs can reference either).
rivals:
- id: rival_one                     # opaque rival org id; referenced by last_week.opponent
  name: Rival One
  tag: RV1
  handle: '@rival_one'
  archetype: One-line archetype label.
  star:
    id: rival_star_one              # opaque rival-star id; same id space as players
    name: Rival Star One
    role: DUELIST
    handle: '@rival_star_one'
  bio: One- or two-sentence rival bio.
  pressure_on_overcast: One-line description of the pressure this rival exerts.

# Last week's result. The opponent must be a rival_org id defined above.
# chirper_feed is optional and omitted here; add posts once you have memory_log
# entries to cite (a post's `cites` must resolve to a memory id that exists).
last_week:
  week: 0                           # week number this result is from (>=0)
  opponent: rival_one               # must match one of rivals[].id above
  format: Bo3                       # free-form series format label
  result: loss                      # free-form result label (win / loss / draw)
  scoreline:
    overcast: 0                     # maps won by your team (>=0)
    opponent: 2                     # maps won by the opponent (>=0)
    maps:
    - map: Helix                    # map name
      overcast: 0
      opponent: 13
      result: loss
  headline: One-line wrap-up headline.
"""


def template() -> str:
    """Return the minimal valid save YAML template as a string.

    The result is byte-stable across calls and across processes — it is the
    frozen :data:`TEMPLATE` literal, returned verbatim. Wrapping the constant
    in a function (rather than re-exporting the literal directly) gives the
    CLI and any future caller a single seam to route through if the template
    ever needs to take parameters.
    """
    return TEMPLATE
