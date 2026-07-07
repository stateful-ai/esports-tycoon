---
name: esports-sim-guardrails
description: Engineering rules for the esports-sim (Valorant tycoon) project. Invoke before writing, reviewing, or generating code in this repo. Enforces determinism, typed schemas, data-driven design, the policy-per-player abstraction, and the match-engine invariants established during MVP design. Use whenever editing files under src/esports_sim/**, data/**, or tests/**, or whenever asked to "add a feature", "implement a system", or "generate code" inside this project.
---

# esports-sim guardrails

Rules that Claude-generated code in this repo must follow. These are not style preferences — each rule exists because violating it breaks a project invariant (determinism, reproducibility, schema integrity, or the RL/world-model pipeline downstream).

Read this top-to-bottom before writing code. Apply the **pre-submit checklist** at the end before claiming a task is done.

---

## The three prime directives

1. **The sim is the source of truth.** UI, LLM agents, RL harnesses, and narrative all read a deterministic event stream. Never bake logic into the UI or assume a caller will "just also" do something — if it matters, it goes in the sim and emits an event.
2. **Determinism is non-negotiable.** Same root seed + same inputs = byte-identical event log, always. Every stochastic call goes through an injected `RngTree`-derived generator. Full stop.
3. **Types at every boundary.** Every action, event, observation, and piece of state is a Pydantic v2 model with `extra="forbid"`. No dicts-of-Any at module boundaries.

If a proposed change conflicts with one of these, the change is wrong. Push back rather than compromising.

---

## Determinism rules

**Forbidden anywhere under `src/esports_sim/`:**

- `import random` — use `numpy.random.Generator` obtained from `RngTree.derive(...)`.
- `time.time()`, `time.perf_counter()`, `datetime.now()`, or any wall-clock call that influences sim state.
- `uuid.uuid4()` or anything non-deterministic as an id source. Ids come from authored data, counters, or hashes of deterministic inputs.
- `np.random.default_rng()` called *directly* from sim code. Only `rng/tree.py` is allowed to construct generators. Everywhere else derives through an `RngTree` instance.
- `set()` iteration where order matters for events or decisions — sort explicitly when iteration order is observable.

**Required:**

- Every function that makes a stochastic decision takes an `rng: np.random.Generator` parameter. Never a seed. Never a bare `Optional[int]`. The caller is responsible for deriving.
- Label paths for `rng_tree.derive(...)` should be stable and semantic: `derive("match", match_id, "round", round_num, "player", player_id, "shot", shot_idx)`. Avoid ad-hoc strings. If a new label segment is needed, add it to the label-path doc block at the top of `rng/tree.py`.
- When adding a new stochastic call site, add a determinism test: run twice with the same seed, assert byte-identical events.

---

## Pydantic / typing rules

- Every new model: `model_config = ConfigDict(extra="forbid")`. Frozen (`frozen=True`) for immutable value objects (definitions, registries, agents, weapons, map callouts). Mutable state (Player, Team, MatchState, RoundState) may be non-frozen.
- Enum fields use `StrEnum` imported from `esports_sim._compat` — **not** `from enum import StrEnum` directly. The compat shim keeps 3.10 working; once we drop 3.10 support we'll flip it globally in one PR.
- No `dict[str, Any]` at a module or public-API boundary. If data is free-form, define a Pydantic model; if it truly must be opaque, annotate as `dict[str, JsonValue]` and justify in a comment.
- No `Optional[X]` where the field has a meaningful default — use the default. `Optional` means "genuinely unknown / not-yet-set", not "lazy about providing a value".
- Discriminated unions for polymorphic types (see `schemas/events.py`). Adding a new event/action subclass requires adding it to the `EventUnion` / `ActionUnion` annotation.
- Validators over comments: if a field has a constraint ("must be between 0 and 100"), use `Field(ge=0, le=100)` not a docstring.

---

## Data-driven design rules

**Valorant ground truth lives in `data/`, not Python.** Agents, abilities, weapons, maps, callouts, adjacency, sightlines, teams, players — all YAML.

- Hardcoded agent ids, weapon ids, or map ids in sim code are a **red flag**. If logic needs to dispatch on "is this a rifle?", read it from the weapon's `weapon_class`, not by checking `weapon_id == "phantom"`.
- If a rule needs configuration (e.g., "how much does tilt reduce aim?"), put the parameter in a YAML config file under `data/` or a `config/` subdir, not as a Python constant mid-module.
- Schemas strict by default: `extra="forbid"` means a typo in YAML blows up at load time. Do not relax this. If a YAML file needs a new field, add it to the schema first.
- Authoring rule: a new attribute, agent, weapon, or map is a **YAML change + test**, not a code change. If you find yourself editing Python to add a Valorant entity, stop and ask whether the registry should own it instead.

---

## Attribute system rules

- The canonical list lives in `data/attributes.yaml`. Adding an attribute is a one-line YAML edit.
- Sim code reads attributes by id with a default: `player.attr("clutch_factor", default=50.0)`. Never access `player.attributes["clutch_factor"]` directly — missing keys must not raise in the hot path.
- When a heuristic/policy starts reading a new attribute, that attribute must exist in `data/attributes.yaml` first. The registry-load test (`test_player_attributes_all_registered`) guards the other direction.
- No hidden magic numbers tied to attributes. If aim_precision 80 means "first-bullet accuracy at 0.85", that mapping lives in a documented config, not inline.

---

## Policy / observation / action rules

- Every decision inside a match goes through `PlayerPolicy.decide(obs, legal, rng) -> Action`. Do not reach around it.
- The match engine constructs `PlayerObservation` per player, per decision. Observations are designed to become partial/fog-of-war later; never pass the full `MatchState` into a policy.
- Heuristic decision logic lives in **one** module — the forthcoming `policy/heuristic.py`. Do not sprinkle `if player.aim_precision > 80: ...` into engine files. Policies read attributes; the engine resolves.
- `Action` is a typed Pydantic model. Fields beyond `type` are action-specific and validated by the engine. Adding a new `ActionType` requires updating `policy/base.py` and handling it in the engine.

---

## Event log rules

- Every state mutation in the sim emits a typed Event. If no event is emitted, the mutation didn't happen as far as replay / UI / narrative are concerned.
- Adding a new event type:
  1. Define a new Pydantic model subclassing `Event` in `schemas/events.py` with a `Literal["dotted.type"]` discriminator.
  2. Add it to the `EventUnion` annotation at the bottom of that file.
  3. Write a test that appends an instance and reloads it via `EventLog.load()`.
- Events are append-only. No mutation after emission. If you need to "correct" an event, emit a new one that supersedes it.
- Event field types: primitive values, strings, and tuples of strings. No nested Pydantic models inside events (flatten instead) unless there's a strong reason — keeps JSONL round-trips simple and human-readable.

---

## Match engine rules

- Spatial unit is the **callout**, not pixels. Players occupy callouts and transit along `Map.adjacency` edges. Sightlines are a separate concept (you can walk somewhere you can't see into).
- Tick = 100ms of sim time, fixed. No wall-clock dependencies. No "sleep for realism" — the viewer handles pacing.
- Round lifecycle: `BUY -> ROUND -> (optional) POST_PLANT -> END`. Phase transitions emit events.
- Utility effects (smokes blocking sight, flashes blinding a callout) are resolved at the callout/sightline level. Don't introduce pixel-level LOS checks.
- First to 13 + OT, side swap at round 12. Deviations from real Valorant ruleset must be flagged and justified.

---

## Testing rules

- New stochastic code path → new determinism test.
- New Pydantic model with `extra="forbid"` → at least one test that constructs a valid instance and one that asserts invalid input raises `ValidationError`.
- New YAML data file → a load test in `test_registry.py` (or equivalent) that asserts structural invariants, not just "it parses".
- The north-star test `tests/test_determinism.py::test_match_determinism_identical_seed_identical_events` is `xfail(strict=True)`. When the match engine is ready, un-xfail it — strict mode will fail the suite if it ever silently stops asserting. Do not relax the strict flag.
- `pytest` must pass clean. An `xfailed` test is fine; an `xpassed` test is a bug.

---

## Anti-patterns to watch for (common LLM failure modes)

When reviewing Claude-generated code or generating it yourself, scan for these:

- **Silent non-determinism.** Calls to `random.random()`, `random.choice()`, `random.shuffle()`, `time.time()`, `datetime.now()`, `uuid.uuid4()` anywhere under `src/esports_sim/`. One slipped call corrupts replay forever.
- **Dict drift.** `def foo(state: dict):` or `-> dict` in a function signature inside the sim. Replace with a Pydantic model.
- **Hardcoded Valorant names.** `if agent_id == "jett":` branches in engine code. The behavior should come from `Agent.role` or an ability flag, not from a name check.
- **Invented agents / weapons / abilities.** LLMs will cheerfully add "Chamber" or "Vandal Pro" that don't exist in your YAML. Every referenced id must be in `data/`.
- **Magic numbers.** Literal floats in sim code with no comment or config backing. If it's a tuning knob, it belongs in YAML.
- **Happy-path Pydantic.** Models without `extra="forbid"`, or using `model_config = ConfigDict()` without configuring anything — ship it strict.
- **Mutable default args.** `def foo(xs: list = []):` — classic Python footgun, and LLMs love it. Use `Field(default_factory=list)` or `xs: list | None = None`.
- **Ad-hoc JSON writing.** Using `json.dumps(obj.dict())` or `json.dump(model.model_dump())` instead of `model.model_dump_json()`. The latter is the only determinism-safe serializer for Pydantic v2.
- **Logic sprawl.** A decision that "sort of fits" in two places (policy + engine) — if you're tempted, it goes in the policy. The engine resolves; it does not decide.
- **Test that asserts nothing.** `assert result is not None` is not a test. Assert specific values, specific event counts, specific types.
- **Skipping the rng parameter.** A stochastic function that takes no `rng` argument is an inevitable bug. If randomness is involved, an `rng: np.random.Generator` parameter is mandatory.
- **Renaming attributes.** "I renamed `aim_precision` to `precision` for brevity" — no. Attribute ids are stable contracts, authored in YAML, referenced across data + sim + UI. Renames are a migration, not a convenience.
- **Emitting events after the fact.** "I'll emit the KillEvent at the end of the round once I know" — no. Emit in temporal order as things happen. The log is a stream, not a summary.

---

## Quick grep sweeps

Run these before declaring done — anything that lights up is suspect.

```bash
# Hidden randomness
grep -rnE '\b(random|uuid|time\.time|datetime\.now|perf_counter)\b' src/esports_sim/

# Direct RNG construction outside the sanctioned spot
grep -rn 'default_rng\|np.random.RandomState\|PCG64' src/esports_sim/ \
  | grep -v 'src/esports_sim/rng/tree.py'

# Dict at the boundary
grep -rnE 'def .+\(.*: dict[^\[]|-> dict[^\[]' src/esports_sim/

# Hardcoded Valorant ids in sim code
grep -rnE '"(jett|raze|omen|sova|killjoy|vandal|phantom|operator|haven|bind|ascent)"' \
  src/esports_sim/ | grep -v schemas/ | grep -v _compat

# StrEnum imported the wrong way
grep -rn 'from enum import StrEnum' src/esports_sim/

# Pydantic without extra=forbid
grep -rn 'ConfigDict(' src/esports_sim/ | grep -v 'extra=' 
```

---

## Pre-submit checklist

Before declaring any sim-touching task done, walk this list. If any line fails, the task is not done.

1. `pytest` runs clean — all green or xfail-strict. No warnings escalated to errors.
2. No new `import random`, `time.time()`, `uuid.uuid4()`, or direct `np.random.default_rng()` call under `src/esports_sim/`.
3. Every new or modified stochastic function takes `rng: np.random.Generator` and uses it for 100% of randomness.
4. Every new Pydantic model has `model_config = ConfigDict(extra="forbid")` (and `frozen=True` if value-object).
5. No hardcoded Valorant agent / weapon / map / ability id in sim code — all references come from loaded data.
6. If you added a stochastic code path: you added a determinism test that runs it twice with the same seed and asserts identical output.
7. If you added an event type: it's in `EventUnion`, and it round-trips through JSONL in a test.
8. If you added an attribute: it's in `data/attributes.yaml` **and** the registry test still passes.
9. If you added an action type: the engine validates it and the legal-actions set includes it where appropriate.
10. The north-star test (`test_match_determinism_identical_seed_identical_events`) is still `xfail(strict=True)` — or, if you made it pass, it's been un-xfailed.
11. `git diff` reviewed for the anti-patterns above. Read the diff as a skeptic, not as the author.

---

## When in doubt

Ask rather than guess. The project's design choices are deliberate — if something feels awkward to implement, it's often because the proposed shape violates an invariant, not because the invariant is wrong. Surface the tension and let the human pick the fork.
