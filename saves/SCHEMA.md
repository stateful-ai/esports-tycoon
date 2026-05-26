# Save Schema (v0)

The on-disk shape of an `esports-tycoon` canned save (YAML). Every field below
matches one field in `esports_tycoon/schema.py`; the loader
(`esports_tycoon/canned/loader.py`) is the single entry point that validates a
file into the typed [`WorldState`][WorldState] and is the inverse of
`loader.dumps(world)`. The save is the system of record — it carries its own
`schema_version` and RNG `seed`, and the round-trip is byte-identical.

This directory (`saves/`) is the **canonical, documented save root**: the
canned Week-6-of-8 save lives at [`saves/week6.yaml`](week6.yaml), this page
documents its shape, and the founder's lock record sits beside it at
[`saves/week6.approval.yaml`](week6.approval.yaml). There is no
`canned/`-vs-`saves/` split — every loader, CLI, and validator in the codebase
resolves the save through `esports_tycoon.canned.loader.DEFAULT_SAVE_PATH`,
which points here.

If you are reading source: this document is linked from
`esports_tycoon/canned/loader.py` (the loader's module docstring points here),
and the test in `tests/test_schema_doc.py` guards that every schema field has an
entry on this page.

[WorldState]: ../esports_tycoon/schema.py

---

## Top level — `WorldState`

| Field | Type | Description |
| --- | --- | --- |
| `schema_version` | `int ≥ 0` | The save-format version this document was written against; current `0`. The loader migrates older values forward or rejects the file with a clear message — version *compatibility* is the loader's job, not the schema's. |
| `seed` | `int ≥ 0` | The save's RNG seed. Required; the match resolver draws all of its randomness from this by default, anchoring "same save ⇒ bit-reproducible match" in the save itself rather than in whatever a caller happens to pass. |
| `save` | `SaveMeta` | Top-level identity, locked tone/flavor, season context, and the managed org. |
| `players` | `list[Player]` | The five starters of the managed team, in roster order. |
| `clash_pairs` | `list[ClashPair]` | Explicit, seeded tensions between characters — combustion on paper before any LLM runs. |
| `rivals` | `list[Rival]` | The opposing orgs and the distinct narrative pressure each puts on the roster. |
| `last_week` | `LastWeek` | The week-before-the-slice result and the Chirper feed it produced. |

Two whole-save invariants are enforced at load time on top of the per-field
checks:

- **Memory IDs are globally unique** across every player's `memory_log`.
- **No dangling cites.** Every `mem:<player>:<event>` referenced from
  `clash_pairs[].seeded_by`, `rivals[].seeded_by`, or
  `last_week.chirper_feed[].cites` must resolve to a real memory entry.

A file that fails either invariant fails to load.

---

## `SaveMeta` — `save:`

| Field | Type | Description |
| --- | --- | --- |
| `id` | `str` | Short, stable identifier for this save (e.g. `week6`). |
| `title` | `str` | Human-readable title shown in inspectors and the recap header. |
| `game` | `str` | The fictional in-universe game name. Locked to `Vector Strike` for M0. |
| `tone` | `str` | The locked editorial voice. `dry-mockumentary` for M0. |
| `flavor` | `str` | The locked fiction flavor (e.g. `valorant-flavored`); pairs with `game`. |
| `fiction_note` | `str` | One-paragraph disclaimer that nothing in the save is real IP, real persons, or real orgs. |
| `season` | `Season` | League / split context for the current week. |
| `team` | `Team` | The org the founder manages. |

### `Season` — `save.season:`

| Field | Type | Description |
| --- | --- | --- |
| `league` | `str` | The in-universe league name. |
| `division` | `str` | The in-universe division and split. |
| `total_weeks` | `int ≥ 1` | Total regular-season weeks in the split. |
| `current_week` | `int ≥ 1` | The week being played in this save. |
| `playoff_cutoff` | `int ≥ 1` | The standings place that still makes playoffs (top-N advance). |

### `Team` — `save.team:`

| Field | Type | Description |
| --- | --- | --- |
| `id` | `str` | Stable, lowercase org id; referenced from match decisions, fixtures, and feed posts. |
| `name` | `str` | The team's display name. |
| `tag` | `str` | Short uppercase team tag (e.g. `OVC`). |
| `handle` | `str` | The org's Chirper handle, including the leading `@`. |
| `blurb` | `str` | One-paragraph in-universe description used in inspector views and the recap. |
| `standing` | `Standing` | Where the team currently sits in the table. |

### `Standing` — `save.team.standing:`

| Field | Type | Description |
| --- | --- | --- |
| `wins` | `int ≥ 0` | Series wins so far this split. |
| `losses` | `int ≥ 0` | Series losses so far this split. |
| `place` | `int ≥ 1` | Current standings position (1 = first place). |
| `of` | `int ≥ 1` | Total teams in the standings (place is `place` *of* `of`). |
| `note` | `str` | One-sentence editorial framing of the table position — the stakes of the upcoming week. |

---

## `Player` — entries of `players:`

| Field | Type | Description |
| --- | --- | --- |
| `id` | `str` | Stable, lowercase player id (e.g. `rook`); the owner segment of every `mem:<id>:<slug>` for this player. |
| `name` | `str` | The player's full real name as it appears on broadcast. |
| `handle` | `str` | The player's Chirper handle, including the leading `@`. |
| `role` | `Role` enum | One of `IGL`, `DUELIST`, `CONTROLLER`, `SENTINEL`, `INITIATOR`. Exactly one starter per role. |
| `age` | `int ≥ 0` | The player's age in in-universe years. |
| `signature_operative` | `str` | The in-universe agent / character they are known for piloting. |
| `bio` | `str` | A one-paragraph editorial bio establishing who they are. |
| `persona_voice` | `str` | The voice contract: how this player speaks. The templated adapter and the LLM prompt both consume this verbatim. |
| `traits` | `list[str]` | Short, lowercase trait tags (e.g. `veteran`, `hotshot`); used as steering hints, not stats. |
| `relationships` | `list[Relationship]` | Outbound relationships from this player to teammates and rivals. |
| `memory_log` | `list[MemoryEntry]` | The player's ordered precedent log — what the room remembers about them. |

A `Player` validator enforces that every entry in `memory_log` is *owned* by
this player: the `mem:<owner>:<slug>` owner segment must match `id`. A mismatch
fails the load — that is the contract that ties a memory to whose head it lives
in.

### `Relationship` — entries of `players[].relationships:`

| Field | Type | Description |
| --- | --- | --- |
| `with` | `str` | The id of the other party (a teammate id or a rival star id). |
| `kind` | `str` | The structural relation: e.g. `teammate`, `rival`, `peer`, `idol`. |
| `status` | `str` | The current emotional state: e.g. `strained`, `trusted`, `bitter`, `friction`. |
| `note` | `str` | One-sentence editorial note explaining the relationship in the founder's voice. |

### `MemoryEntry` — entries of `players[].memory_log:`

| Field | Type | Description |
| --- | --- | --- |
| `id` | `MemoryId` | Stable opaque cite id of the form `mem:<player_id>:<event_slug>` (lowercase ascii, dash-snake slug). Globally unique across the save; the owner segment must match the owning player. |
| `week` | `int ≥ 0` | The in-universe week the event happened (0 = backstory / pre-season). |
| `day` | `int 1–7` | The day inside `week`. |
| `kind` | `MemoryKind` enum | One of `match`, `scrim`, `social`, `1on1`, `press`, `rumor`. |
| `actors` | `list[str]` | Player ids involved (the owner and any others); used to filter what each player can plausibly cite. |
| `summary` | `str` | One-sentence factual recap. The renderer hands this to templates and to LLM prompts verbatim — never free-form simulation text. |
| `sentiment` | `Sentiment` enum | The entry's emotional charge: `positive`, `neutral`, or `negative`. |
| `tags` | `list[str]` | Optional short colour tags for filtering and steering the templated narrator (e.g. `bishop`, `foreshadow`, `terminus`). Open vocabulary. Omitted when empty (the save never spells `[]`). |
| `recall_tags` | `list[RecallTag]` | Opt-in to the frozen recall vocabulary: a typed subset of `{choke, clutch, tilt, rivalry}`. Both sides of the deterministic precedent recall — the resolver's `KeyMoment.tag` and this list — speak the same enum, so off-enum values fail closed at load time. Omitted when empty. |

---

## `ClashPair` — entries of `clash_pairs:`

| Field | Type | Description |
| --- | --- | --- |
| `a` | `str` | First party id (a starter id, or a rival star id when `cross_team` is true). |
| `b` | `str` | Second party id. |
| `cross_team` | `bool` | `true` if the clash crosses team lines (seeds a rival subplot); `false` for intra-room tension. |
| `axis` | `str` | Short label naming the axis of conflict (e.g. `structure vs. freelance`). |
| `summary` | `str` | One-sentence editorial summary of the clash. |
| `seeded_by` | `list[MemoryId]` | The cites that justify the clash; every id must resolve to a real `MemoryEntry`. |
| `rival_org` | `str?` | Required when `cross_team` is true: the rival org id this clash routes pressure through. Omitted for intra-team pairs. |

---

## `Rival` — entries of `rivals:`

| Field | Type | Description |
| --- | --- | --- |
| `id` | `str` | Stable lowercase org id (e.g. `northwind`); referenced from fixtures and clash pairs. |
| `name` | `str` | The org's display name. |
| `tag` | `str` | Short uppercase team tag. |
| `handle` | `str` | The org's Chirper handle, with the leading `@`. |
| `archetype` | `str` | Short label naming the narrative pressure they put on the roster (e.g. `The Dynasty`, `The Ex-Teammate`). |
| `star` | `RivalStar` | The named star carrying this rival's narrative pressure. |
| `bio` | `str` | One-paragraph editorial framing of the org. |
| `pressure_on_overcast` | `str` | One-sentence answer to "what does losing to them mean?" — the stakes of the fixture. |
| `seeded_by` | `list[MemoryId]` | Cites that justify the archetype; every id must resolve. |

### `RivalStar` — `rivals[].star:`

| Field | Type | Description |
| --- | --- | --- |
| `id` | `str` | Stable lowercase id of the star (e.g. `bishop`); appears as the `with` side of relationships and in cross-team clash pairs. |
| `name` | `str` | The star's display name. |
| `role` | `Role` enum | The star's Vector Strike role. |
| `handle` | `str` | The star's Chirper handle, with the leading `@`. |

---

## `LastWeek` — `last_week:`

| Field | Type | Description |
| --- | --- | --- |
| `week` | `int ≥ 0` | The week number being recapped (i.e. `current_week - 1`). |
| `opponent` | `str` | The rival org id played. |
| `format` | `str` | Series format (e.g. `Bo3`). |
| `result` | `str` | `win` or `loss` from the managed team's perspective. |
| `scoreline` | `Scoreline` | The series scoreline plus per-map breakdown. |
| `headline` | `str` | The one-sentence newsroom headline of the result. |
| `chirper_feed` | `list[ChirperPost]` | The Chirper feed that came out of the result. |

### `Scoreline` — `last_week.scoreline:`

| Field | Type | Description |
| --- | --- | --- |
| `overcast` | `int ≥ 0` | Maps won by the managed team. |
| `opponent` | `int ≥ 0` | Maps won by the opponent. |
| `maps` | `list[MapResult]` | Per-map breakdown of the series, in play order. |

### `MapResult` — entries of `last_week.scoreline.maps:`

| Field | Type | Description |
| --- | --- | --- |
| `map` | `str` | The in-universe map name (e.g. `Helix`). |
| `overcast` | `int ≥ 0` | Rounds won by the managed team on this map. |
| `opponent` | `int ≥ 0` | Rounds won by the opponent on this map. |
| `result` | `str` | `win` or `loss` from the managed team's perspective. |
| `note` | `str?` | Optional one-line editorial note on the map (e.g. an overtime loss from a lead). |

### `ChirperPost` — entries of `last_week.chirper_feed:`

| Field | Type | Description |
| --- | --- | --- |
| `id` | `str` | Stable post id of the form `chirp:w<week>:<nn>`; used as the target of `reply_to`. |
| `author` | `str` | The displayed handle (always present, including for external voices like casters). |
| `day` | `int 1–7` | The day in the week the post went up. |
| `text` | `str` | The post body, verbatim. |
| `cites` | `list[MemoryId]` | The memory ids the post is grounded in; every id must resolve. Omitted when empty. |
| `likes` | `int ≥ 0` | Like count at the time the save was authored. |
| `author_id` | `str?` | Player or org id of the author when in-universe; omitted for external voices (casters). |
| `reply_to` | `str?` | The `id` of the post being replied to, when this is a reply. |
| `note` | `str?` | Optional editorial note about the post (e.g. `deleted after 6 minutes`). |

---

## Conventions

- **Lowercase, dash-snake ids** for players, orgs, and event slugs. The cite-id
  regex `mem:[a-z0-9_]+:[a-z0-9_]+` is enforced; mixed-case ids fail to load.
- **Omit empty collections.** Empty `tags` / `recall_tags` / `seeded_by` /
  `cites` are omitted on the way out rather than spelled `[]`. The round-trip
  uses `exclude_defaults` to keep dumps aligned with that convention; an empty
  list re-injected into a file would silently break the byte-identical
  round-trip.
- **`extra = "forbid"`.** Any key in the YAML that is not modelled here fails
  the load loudly. The schema is therefore a *faithful, total* description of
  the save — if you want a new field, add it to `schema.py` *and* to this page
  in the same change.

## Regeneration & blessing

`saves/week6.yaml` is a **generated artifact**, never hand-edited. The
source-of-truth content is the typed [`WorldState`][WorldState] that the loader
materializes from it; the on-disk bytes are whatever the canonical serializer
(`esports_tycoon/canned/canonical.py`) emits for that world. The supported way
to (re)write those bytes is:

```sh
make regen-golden        # rewrites saves/week6.yaml in place
```

This calls [`scripts/regen_golden.py`][regen_golden], which loads the save,
validates it through the full loader (shape, cite-id, referential-integrity),
and overwrites the file with the canonical serializer's output. The operation
is a **fixed point of the canonical serializer**: running it twice in a row
writes nothing the second time, so a no-op regen leaves the file (and its
mtime) untouched. CI guards the inverse — `tests/test_regen_golden.py`
asserts the committed file is already at the fixed point, so a hand-edit that
drifts from canonical form (a re-folded scalar, an inserted comment, a
re-ordered key, a flow-style list) fails the build with a pointer back to the
script.

A change to the save's *content* — a new player, an updated bio, a corrected
memory log — flows through this script: edit the typed model or the YAML,
re-run `make regen-golden`, and commit the canonical bytes. Do not commit a
diff to `saves/week6.yaml` that the canonical serializer would not produce.

[regen_golden]: ../scripts/regen_golden.py

## Byte-identity normalization

The save's on-disk shape is one half of the contract. The *bytes* a serializer
emits for that shape are the other half — and they have to be a fixed point, so
that `dump(load(week6.yaml))` always produces the same canonical bytes on every
machine, every CPython, every PyYAML version. That guarantee is what lets a
future migration diff two saves with plain `diff`, what makes the round-trip
golden (`tests/test_golden_determinism.py`) trip on serializer drift, and what
keeps committed saves reviewable.

The canonical serializer (`esports_tycoon/canned/canonical.py`) emits exactly
the form below; the golden test pins those bytes on the week-6 save:

- **Key order is the input dict's iteration order.** No alphabetical sort. For
  a `WorldState` reaching the dumper through Pydantic, that order is the
  schema's field declaration order; for a plain `dict` it is insertion order.
  Re-ordering keys would re-write every committed save on every dump.
- **Floats use Python's shortest round-trip `repr`,** with `.0` spliced into
  the mantissa when `repr` omits the dot (so `1e-05` → `1.0e-05` and `1e+20` →
  `1.0e+20`) and the YAML 1.1 implicit-float resolver still matches without a
  `!!float` tag. The specials are canonical tokens: `.nan`, `.inf`, `-.inf`.
  `-0.0` is preserved as `-0.0`. There are no floats in week6 today, but the
  rule still has to hold the moment one appears.
- **The document ends with exactly one trailing newline** (`"…\n"`, never
  `"…"` and never `"…\n\n"`), so committed saves are POSIX-clean text files.
- **Unicode is emitted verbatim** (`allow_unicode=True`). The save carries
  em-dashes (`—`) and accented names; `\uXXXX` escapes would defeat the
  human-readable diff the canonical form promises.

Two further document-shape rules follow from the same fixed-point goal and
sit alongside the four above: **block style is forced** (no flow-style
`[...]` / `{...}`, even on short scalar lists), and **defaults are omitted**
on dump (the `exclude_defaults` rule in [Conventions](#conventions): an empty
collection in the file is omitted on the way out so it isn't re-injected as
`[]` and silently rewritten).

When any of these rules has to change, regenerate the canonical golden with
`UPDATE_GOLDEN=1 python -m pytest tests/test_golden_determinism.py`, re-bless
the fixture with `make regen-golden`, and review the resulting `diff` before
committing.

---

## Resolver entropy discipline

The save's `seed` is the **only** entropy the match resolver is allowed to
consume. `esports_tycoon.resolver.run` constructs exactly one local
`random.Random(seed)` at the top of the function and threads it explicitly
through every helper that needs a draw — nothing else. The resolver must
never read process-global random state (`random.random()`, `random.choice()`,
`random.SystemRandom()`, …), wall-clock time (`time.time`, `time.monotonic`,
…), or generate UUIDs (`uuid.uuid4`, …). The seed-in-save contract on the
top-level `seed` field leans on this: "same save ⇒ same match" can only be
true if the resolver doesn't pick up anything ambient.

The rule is guarded by
`tests/test_resolver_determinism.py::TestResolverEntropyDiscipline`. The test
poisons every public callable on the `random`, `time`, and `uuid` modules so
each one raises on access, runs the resolver, and asserts the resulting
`WhyRecord` is identical to one produced without the sabotage. Adding a new
helper that needs a draw? Take the `Random` instance as an argument — don't
import `random` (or `time`, or `uuid`) into `resolver.py`.

---

## Versioning

The save is self-describing. `schema_version` is the on-disk version the file
was written against; `CURRENT_SCHEMA_VERSION` in `esports_tycoon/schema.py` is
what this build speaks. On load:

- equal ⇒ the save is validated directly,
- lower ⇒ the loader walks `loader._MIGRATIONS` to upgrade it forward (or
  raises `SchemaVersionError` if no step is registered for that version),
- higher ⇒ `SchemaVersionError` — upgrade `esports-tycoon` to read it.

Bump `CURRENT_SCHEMA_VERSION` only when the on-disk shape changes
*incompatibly*, and register a migration step at the same time so older saves
keep loading rather than being rejected.
