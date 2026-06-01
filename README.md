# esports-tycoon

## Status

- Phase: alpha
- Stack: Python (>=3.12,<3.13)

A management sim where the soul of the game is **persistent player
personalities** — their memories of past matches, their relationships, and a
public social feed where they react to everything that happens. You manage the
humans, not the matches.

**M0** is a one-week vertical slice on a hand-authored *Week-6-of-8* canned save,
proving the core taste-reaction: *the game remembered something.* Tone is dry
mockumentary; the game is **Vector Strike**, a fictional Valorant-flavored 5v5.
See `docs/scope-m0.md` (CompanyOS) for the full scope.

## Quick Start

- `git clone` this repository and `cd esports-tycoon`.
- `pip install -e .[dev,web]` — core deps plus the test + web extras (see `pyproject.toml`).
- `make test` — runs the full suite (templated zero-API backend, no GPU).
- `python -m esports_tycoon play` — serves the slice at http://127.0.0.1:8765.
- See `docs/` for the founder briefs, scope, and design notes.

## Zero-API quickstart

Fresh clone, **no API key, no network, no GPU** — the slice is built to run that
way by default. Two commands and you are playing the Week 6 (of 8) fixture:

```bash
pip install -e .[web]               # core deps + Flask for the local web app
python -m esports_tycoon play       # serves http://127.0.0.1:8765
```

The web app picks practice → match → fallout for the Week-6 must-win, including
an optional focused training rep for one starter. It writes the screenshot-ready
recap to `runs/<slice_id>/` and never opens an outbound connection. The match
resolver is seeded from the save (`seed: 6`), so the same inputs land in the
same `runs/<slice_id>/` folder with byte-identical artifacts.

Headless equivalent (no Flask, no browser — the same engine, same artifacts):

```bash
pip install -e .                                       # PyYAML + pydantic only
python -m esports_tycoon.runner --opponent apex_foundry # week 6 fixture
```

To play through the remaining slate of Weeks 6 → 7 → 8, re-run the headless
runner against the rivals in turn (their ids are listed in
`saves/week6.yaml` under `rivals:`):

```bash
python -m esports_tycoon.runner --opponent apex_foundry --seed 6     # week 6
python -m esports_tycoon.runner --opponent sovereign    --seed 7     # week 7
python -m esports_tycoon.runner --opponent last_light   --seed 8     # week 8
```

The opt-in `vllm` backend (a local OpenAI-compatible Qwen server) is documented
below — it is *never* required to play. The templated backend is the default
because the whole slice runs end-to-end without it.

The on-disk shape of the save is documented field-by-field in
[`saves/SCHEMA.md`](saves/SCHEMA.md).

## What's here (M0.0 — tone + cast lock)

- **`docs/tone_and_cast_lock.md`** — the 1-pager pinning the voice, the fiction,
  the 5-starter cast with explicit clash pairs, and the 6 rival archetypes.
- **`saves/week6.yaml`** — the canned Week-6-of-8 save (the canonical save
  root, shipped as package data through the `saves` package): 5 starters, 8
  clash pairs, 6 rival archetypes, 37 precedent memory entries with stable
  `mem:<player>:<event>` IDs, and last week's scoreline + Chirper feed.
- **`esports_tycoon/cast_lock/`** — the acceptance-bar validator and the founder's
  single batched approve/reject gate.
- **`saves/week6.approval.yaml`** — the recorded founder decision, bound to a
  content digest of the batch.
- **`esports_tycoon/schema.py`** — the typed game schema (pydantic): `Player`,
  `MemoryEntry`, `Relationship`, `WorldState`, plus the resolver/adapter outputs
  `WhyRecord` and `GeneratedContent`. Enforces stable `mem:…` cite IDs and the
  no-dangling-cites grounding contract.
- **`esports_tycoon/canned/loader.py`** — `loader.load()` → a validated
  `WorldState` from the packaged save. The save and the typed schema round-trip
  losslessly, and the save carries its own RNG `seed` (the seed-in-save contract),
  so the resolver replays it bit-for-bit by default.
- **`saves/SCHEMA.md`** — the human-facing field reference for the save format.
  Every field accepted by the loader appears here with a one-line description
  and the load-time invariants; the loader links it as the companion to the
  typed schema.

```bash
python -m esports_tycoon inspect             # load the canned save, print a summary
python -m esports_tycoon resolve <cite-id>   # resolve a cite ID to its memory entry
```

## Content adapter (templated default + opt-in LLM)

All rendered prose goes through one seam,
`esports_tycoon.content.generate_content(kind, ctx) -> GeneratedContent`, for the
three M0 kinds: `chirper_post`, `narration`, `halftime_ack`. A single config flag
picks the backend:

- **`templated`** — deterministic, zero-API. **The default**: the whole slice
  runs with no network, no keys, and no cost. Every cite it emits is pulled from
  the canned log, so grounding is always `ok`.
- **`vllm`** — the gaming-pack `game_llm` client against any OpenAI-compatible
  endpoint (a local vLLM in dev, a cheap hosted Qwen in prod), configured by the
  `GAME_LLM_*` env vars in `.env.example`. Opt-in: `pip install -e .[vllm]`. The
  backend is imported lazily, only when the flag selects it, so `import
  esports_tycoon.content` and the templated default work with the extra absent.

```python
from esports_tycoon.canned import loader
from esports_tycoon import resolver
from esports_tycoon.schema import Decisions
from esports_tycoon.content import generate_content, GenerationContext

world = loader.load()
decisions = Decisions(opponent="northwind", map="Helix")
why = resolver.run(world, decisions)          # seed defaults to the save's own seed
# why = resolver.run(world, decisions, seed=7)  # ...or override it to explore the spread
post = generate_content("chirper_post", GenerationContext(world=world, why=why, author="vex"))
```

The backend is selected by `ESPORTS_TYCOON_CONTENT_BACKEND` (`templated` |
`vllm`), defaulting to `templated`. The resolver never imports the adapter:
narration consumes the resolver's finished `WhyRecord`, never the other way
round.

## Play the slice (local web app + auto-recap)

One playable week — **practice → match → fallout** — served as a local web app on
`127.0.0.1`, with a screenshot-ready recap written every run. Templated (zero-API)
mode by default, so it runs with no network, no keys, and no cost.

```bash
pip install -e .[web]            # Flask is an opt-in extra
python -m esports_tycoon play    # serves http://127.0.0.1:8765
# or: python -m esports_tycoon.web --port 8765 --opponent apex_foundry --seed 6
```

The default port is **8765** (not 8000): a local `GAME_LLM_*` server, an LLM
router, and a Stable Diffusion UI commonly hold 8000/8001/7860 on a dev box, so
the slice would fail to bind there. Pass `--port` to override; if the chosen port
is busy the app exits with a clear message rather than a raw traceback.

The app serves the **manager view** and the in-universe **Chirper feed** in one
process. The week's decision surface is practice focus, an optional focused rep
that spends a small training budget on one starter, then two open-text moments:
a private pre-match team talk and a public post-match Chirper post — each capped
at 120 characters.

Focused reps are not just receipts. The canonical `vex_aim` rep changes Vex's
same-seed local outcome from `came_apart` to `carried`, improves her morale, and
surfaces a deterministic Vex ↔ Pixie relationship fallout line in `/match`,
`/recap`, the saved recap artifact, and the Chirper feed. The follow-on fork is
now playable too: `pixie_flash_repair` spends the same 4 TP on the seeded
Vex/Pixie flash review, steadies Pixie, cools the relationship fallout to
`working review`, and posts a distinct Pixie fallout receipt. The choice is a
visible tradeoff between more carry power and repairing the system around it.
That fork now carries forward into a run-local **review-room trust** resource:
Vex reps drop trust and create a late-retake follow-up scrim problem, while
flash repair raises trust and sets up a cleaner second-contact scrim. Branch
runs also export `week7_setup.json` with the chosen branch, fallout state, trust
delta, hook id, hook prompt, and recommended next focus. The `/week7` page then
consumes that setup and asks the player to lock `contain_fallout` or
`prove_ceiling`; following or ignoring the recommended focus writes a deterministic
`week7_focus.json` pressure artifact. `/week7/result` now consumes the setup and
focus receipts, resolves the Tuesday scrim pressure block, and writes
`week7_pressure.json` with the outcome id, scrim result, review-room beat,
public signal, and deltas. `/week8` then consumes all three Week-7 receipts and
asks the manager to lock a prep response: patch the exposed break or double down
on identity. That writes `week8_prep.json`, turning the pressure result into the
next durable manager problem without simulating another match. `/week8/scrim`
then consumes that prep response and writes `week8_scrim.json`, making the prep
choice alter the next scrim modifier, opening state, and locked tactical call.
`/week8/match` now consumes the scrim and writes `week8_match_plan.json`, a
match-preview plan lock that names the opponent attack, team edge, risk level,
and the final prep call before any full match resolver exists.
`/week8/match/result` then consumes that plan and writes
`week8_match_result.json`, resolving the plan into one deterministic result,
public read, pressure beat, and Week 9 hook without adding a broader media,
sponsor, or roster system. `/week9` consumes that result and writes
`week9_setup.json`, turning the Week 8 fallout into the next manager response
posture. `/week9/prep` then consumes that posture and writes `week9_prep.json`,
locking the first Week 9 tactical prep lane. `/week9/scrim` consumes that prep
and writes `week9_scrim.json`, turning the lane into a room/public/tactical
read. `/week9/match` consumes that read and writes `week9_match_plan.json`,
locking the match-week plan while still deferring match resolution.

On completion the slice writes its artifact to `runs/<slice_id>/`:

- **`recap.md`** — the week written up: fixture, your decisions, the match and its
  key moments, morale fallout, the Chirper feed, and *what the room remembered*
  (every cited memory resolved back to the canned log).
- **`feed.snapshot.html`** — a standalone Chirper page, exactly what `/feed` serves.
- **`week7_setup.json`** — written only for the repair-vs-reps fork, exporting
  the deterministic next-week hook without adding persistence.
- **`week7_focus.json`** — written when `/week7` locks the next block focus,
  including whether the choice followed the recommendation and any ignored-read
  consequence.
- **`week7_pressure.json`** — written by `/week7/result`, consuming the setup
  and focus receipts into a deterministic four-outcome pressure payoff.
- **`week8_prep.json`** — written by `/week8`, recording the post-pressure
  management response, tradeoff deltas, exposed problem, and next hook.
- **`week8_scrim.json`** — written by `/week8/scrim`, turning the prep response
  into the next scrim setup and tactical call without resolving a full match.
- **`week8_match_plan.json`** — written by `/week8/match`, consuming the scrim
  setup into a deterministic opponent-read, team-edge, risk, and match-plan
  lock while still deferring the match result.
- **`week8_match_result.json`** — written by `/week8/match/result`, resolving
  the match plan into a deterministic outcome, scoreline, fallout beat, and
  Week 9 hook.
- **`week9_setup.json`** — written by `/week9`, consuming the Week 8 result into
  a Week 9 problem, recommendation, selected response posture, and next prep
  hook.
- **`week9_prep.json`** — written by `/week9/prep`, turning the response posture
  into a deterministic prep lane, combined prep deltas, match-read alignment,
  and `week9_scrim.json` hook.
- **`week9_scrim.json`** — written by `/week9/scrim`, consuming setup + prep
  into exactly three deterministic scrim reads and a `week9_match_plan.json`
  handoff without creating the match plan or result.
- **`week9_match_plan.json`** — written by `/week9/match`, consuming setup,
  prep, and scrim reads into exactly three deterministic match-plan options and
  a `week9_match_result.json` handoff without resolving the result.

`slice_id` is content-addressed (a hash of the save, seed, and every decision), so
**re-running with the same seed in templated mode reproduces a byte-identical
recap**. The headless runner is the no-browser path (and how the determinism is
checked in CI):

```bash
python -m esports_tycoon.runner --seed 6 --practice defaults \
    --training-drill pixie_flash_repair \
    --team-talk "no heroes. run the default." \
    --fallout "week 6: held the line. on to week 7."
```

The web app is a thin shell over `esports_tycoon.runner`: the engine, the recap
artifact, and the determinism contract all live in the runner and are tested with
no web dependency.

## Deploy the backend to Cloudflare Containers

The repo includes a Cloudflare Containers wrapper for the Flask backend:

- `Dockerfile` builds the Python 3.12 web app in templated mode.
- `cloudflare/worker.ts` routes Worker requests to a single named container
  Durable Object, keeping Flask session signing stable.
- `wrangler.jsonc` binds that Durable Object and tells Wrangler to build the
  container image from the local Dockerfile.

```bash
npm install
npm run typecheck
npm run cf:deploy
```

`wrangler deploy` builds the image locally with Docker, pushes it to the
Cloudflare-managed registry, and deploys the Worker wrapper. Docker or a
Docker-compatible engine must be running and accessible to the current user.
After deploy:

```bash
npm run cf:containers
npm run cf:images
curl https://esports-tycoon-backend.<your-subdomain>.workers.dev/healthz
```

## The render-time gate (grounding + safety + cost)

Every generated piece flows through one gate, `esports_tycoon.gate.render`,
before it reaches the feed or the recap. It composes the three red-team rules
into a single regen loop:

- **Grounding** (`esports_tycoon.grounding`) — LLM cites are parsed as
  `mem:<player>:<slug>`, resolved against the canned log, regenerated up to
  `N=2`, then any still-unresolvable cites are **dropped** and the
  `grounding_status` (`ok` | `regen` | `dropped`) is stamped. No hallucinated
  history.
- **Safety** (`esports_tycoon.safety`) — the same screener pre-filters the
  manager's open-text (an unsafe input is rejected before it reaches the model)
  and post-filters every completion; output that can't be made safe within the
  regen budget is withheld. It blocks slurs, real-person impersonation / real-IP
  leakage, and targeted harassment, and is obfuscation-resistant (leetspeak,
  spacing, character-stretching). `ADVERSARIAL_SEED_CORPUS` is the seed corpus it
  is held against.
- **Cost** (`esports_tycoon.cost`) — one `CostMeter` per slice meters every
  attempt (regens included); a per-slice ceiling breach raises
  `CostCeilingExceeded`, which halts the run. The M0 local-vLLM model is free, so
  a real slice spends `$0` well under the ceiling; the guard bites the moment a
  paid model is configured behind the same adapter.

```python
from esports_tycoon import gate
from esports_tycoon.cost import CostMeter
from esports_tycoon.content import llm

meter = CostMeter()  # one per slice run
result = gate.render(
    lambda: llm.generate("chirper_post", ctx, client=client),
    world=world, meter=meter,
)
# result.content is final (safe, grounded, priced); result.grounding / .safety /
# .cost carry the per-piece bookkeeping.
```

`esports_tycoon.recap` aggregates those results across a slice and writes the
per-slice **grounding-rate** and **drop-rate** (plus safety and cost lines) into
`recap.md`.

Later tickets add the in-universe Chirper feed model that consumes this gate.

## The cast-lock gate

```bash
python -m esports_tycoon.cast_lock review     # one-screen batch summary
python -m esports_tycoon.cast_lock validate   # acceptance-bar checklist
python -m esports_tycoon.cast_lock status     # decision vs. current content
python -m esports_tycoon.cast_lock approve --approver <you> [--reason ...]
python -m esports_tycoon.cast_lock reject  --approver <you>  --reason ...
```

A batch that fails validation cannot be approved; any edit to either file
invalidates the recorded approval until the gate is re-run.

## Run vLLM (local bring-up)

To exercise `vllm` mode for real you need a local, OpenAI-compatible Qwen 7B/8B
server at `http://localhost:8000/v1` — the endpoint `.env.example` already points
at. `scripts/vllm_serve.sh` is the one-command bring-up: on a CUDA GPU host it
`pip install`s vLLM if missing and runs `vllm serve Qwen/Qwen2.5-7B-Instruct`,
which downloads the weights from the Hugging Face Hub on first boot (cached
thereafter). Critically, it passes `--served-model-name qwen2.5-7b-instruct`, so
clients (and the `curl` below) reach the model under that short name rather than
the full `Qwen/Qwen2.5-7B-Instruct` repo id — which is why it matches
`GAME_LLM_MODEL` out of the box. Override the repo or served name with
`VLLM_MODEL` / `VLLM_SERVED_NAME` (keep the latter equal to `GAME_LLM_MODEL`).

`vllm serve` is a long-running foreground process, so the bring-up spans **two
terminals**: serve in one, smoke from another. Do the one-time setup first, then:

```bash
# One-time setup
cp .env.example .env        # GAME_LLM_* already target localhost:8000
pip install -e .[vllm]      # the openai client the game + smoke use

# Terminal 1 — serve (stays running; first boot downloads the weights)
scripts/vllm_serve.sh       # GPU host: installs vLLM if missing, then `vllm serve`
                            # wait for: "Application startup complete"

# Terminal 2 — smoke the live endpoint once it's up
python -m esports_tycoon.vllm_demo smoke   # up + structured + warm under 5s? (exit 0 = yes)

# raw equivalent of the smoke's round-trip:
curl -s http://localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"qwen2.5-7b-instruct","messages":[{"role":"user","content":"reply with a short json object {\"ready\":true}"}],"max_tokens":64}'
```

A green smoke means the endpoint is up, returns parseable JSON, and answers
within a warm latency budget (default 5s) — the prerequisite for the demo gate
below. The check runs one structured round-trip through the game's own client and
prints its verdict (illustrative — the timings vary by host and load; the GPU run
is the operational acceptance check, since CI has no GPU):

```text
======================================================================
 vLLM ENDPOINT SMOKE TEST
======================================================================
 Model    : qwen2.5-7b-instruct
 Warm-up  : 2.314s (untimed; absorbs first-request load)
 Reachable: ✓
 Structured: ✓ reply={'ready': True, 'note': 'up'}
 Warm call: ✓ 0.412s (budget 5.000s)
======================================================================
✓ SMOKE PASSED — endpoint is up, structured, and warm under budget.
```

## The vLLM-mode demo gate

Before any **vLLM-mode** screenshot is taken or shared, it must clear one gate:
the slice runs end-to-end through the adapter in `vllm` mode against the local
Qwen endpoint, latency is measured and recorded, the adversarial-seed safety
corpus passes, and the founder signs off in writing on the exact output.

```bash
# 1. Run the whole slice in vllm mode against the live local Qwen endpoint
#    (GAME_LLM_* env; needs `pip install -e .[vllm]`). Measures latency, screens
#    the adversarial corpus + the run's own output, writes the bundle.
python -m esports_tycoon.vllm_demo preflight --seed 6 [--max-latency <secs>]
# 2. The founder reviews artifacts/vllm_demo/{recap.md,feed.snapshot.html} and signs off.
python -m esports_tycoon.vllm_demo sign-off --approver <founder> [--reason ...]
python -m esports_tycoon.vllm_demo status      # may a screenshot be shared? (exit 0 = yes)
```

The preflight bundles its evidence into a content digest over the *exact* recap +
feed the founder will screenshot. A preflight whose automated gate failed (a
safety leak, unsafe generated output, or a blown `--max-latency` budget) **cannot
be signed off**, and because vLLM output is non-deterministic, any re-generation
produces a new digest that makes a prior sign-off `stale` — so an approval
authorises one reviewed output, never a future one. The digest binds to the
actual screenshot surface: `status` re-hashes the `recap.md`/`feed.snapshot.html`
on disk, so editing either file out-of-band flips the gate back to `BLOCKED`.
Local vLLM is free, so cost is not gated here; latency is *measured and
recorded*, and only fails the gate against a founder-supplied budget.

## Tests

`make test` is the canonical entrypoint and is what CI runs from a clean clone
on every push and pull request (`.github/workflows/ci.yml`). It needs no API
key, no network, and no GPU — the whole suite runs against the templated
zero-API backend, and the golden + round-trip tests
(`tests/test_golden_determinism.py`) fail the build the moment the committed
bytes under `tests/golden/` drift from what the engine produces.

```bash
make install        # one-time: pip install -e .[dev,web]
make test           # full suite (golden + round-trip enforced)
make test-golden    # just the determinism tests
make golden-update  # intended-change escape hatch: re-emit committed goldens, review the diff
```

Direct invocations still work if you'd rather skip `make`:

```bash
python -m unittest discover -s tests     # stdlib runner (no extra deps)
# or, with pytest installed:
pytest
```

Requires Python 3.12 (pinned for byte-identity reproducibility — see
`constraints.txt`) and the deps it locks (pydantic, PyYAML). `make install`
installs from the lock; do the same on a fresh checkout to reproduce the
committed `saves/week6.yaml` byte-for-byte.
