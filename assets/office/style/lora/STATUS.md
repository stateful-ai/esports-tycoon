# esports-sim-diorama LoRA — training status

**Status: TRAINED (2026-07-09).** After the plan upgrade the staged
train call was accepted immediately and the job completed:
`model_5ZuAoQQnRSMSeykEwaHjBKwm` now reports `status: trained`
(FLUX.2 Dev base, 16-image captioned corpus, trigger phrase
`esports-sim-diorama`, concept scale 0.8).

**Open item — API sampling.** Every generation attempt against the
trained model returns a bare 500 from Scenario
(`POST /v1/models/<id>/inferences` with `{"parameters": {"type":
"txt2img", ...}}`, and `POST /v1/generate/txt2img` — both exist, both
500; retried for ~15 minutes post-training, so not deployment lag).
The legacy inference path likely does not serve `flux.2-dev-lora` on
this plan/API generation. The model itself is healthy and can be used
from the Scenario web UI (app.scenario.com -> esports-sim-diorama ->
Generate, prefix prompts with the trigger phrase). The agreed
validation prompt: "esports-sim-diorama style, isometric esports team
office lounge with couches and trophy shelf, dark navy background" —
save a good result to `assets/office/style/lora/sample.png`. Finding
the correct current-generation API route is a small research task for
a future session.

---

Original staging notes below (historical).

## What exists on the account

- Model: `model_5ZuAoQQnRSMSeykEwaHjBKwm` — name `esports-sim-diorama`,
  type `flux.2-dev-lora` (FLUX.2 Dev base), status `new` (draft).
- Project: `proj_FqPB7iKvwuMBkYHAojra45cE` (team `team_BNAyn8xCxEe9XFAWaQ9Br5B3`).
- 16 training images uploaded and captioned (caption = asset
  `description`, each prefixed with the trigger phrase
  `esports-sim-diorama style`).

## The blocker (verbatim)

`PUT /v1/models/<id>/train` returned:

```json
{"reason": "You have reached your plan's limit. Please upgrade your plan
 to continue using this feature.",
 "name": "PlanLimitReachedError",
 "details": {"actionLimit": 0, "actionName": "parallel-training",
             "actionValue": 0, "limitScope": "team"}}
```

`GET /v1/teams` shows the team plan is **`cu-basic`**, whose
parallel-training limit is 0 — model training is not included in the
current plan at all (no job was holding the slot; all account models are
`trained` or `new`). The May 2026 trainings ran under a different tier.
**No credits were spent**: model creation and image upload were free,
and the train call was rejected before charging (no
estimatedCreativeUnits was ever returned).

## How to resume (after plan upgrade / training entitlement)

One call (Basic auth = base64 of `SCENARIO_API_KEY:SCENARIO_SECRET_KEY`
from `.env`):

```
PUT https://api.cloud.scenario.com/v1/models/model_5ZuAoQQnRSMSeykEwaHjBKwm/train?projectId=proj_FqPB7iKvwuMBkYHAojra45cE
Content-Type: application/json

{"parameters": {"conceptPrompt": "esports-sim-diorama",
                "learningRate": 0.00005, "rank": 64, "batchSize": 1,
                "nbEpochs": 10, "nbRepeats": 20}}
```

Then poll `GET /v1/models/model_5ZuAoQQnRSMSeykEwaHjBKwm` (~30 s
interval) until `status` is `trained` (path: `draft/new → training →
trained|failed`). Validation sample prompt agreed with the owner:
"esports-sim-diorama style, isometric esports team office lounge with
couches and trophy shelf, dark navy background" → save to
`assets/office/style/lora/sample.png`.

Gotchas learned this run:

- `conceptPrompt` max 20 characters ("esports-sim-diorama" = 19 fits;
  "... style" = 25 was rejected with a Musubi validation error).
- The `caption` field on the training-image upload body is silently
  ignored; Scenario auto-captions into the asset `description`.
  Overwrite captions with `PUT /v1/assets/<assetId>?projectId=<proj>`
  body `{"description": "<caption>"}` (verified persisted).
- `GET /models/<id>/training-images` is 403 for API keys; the upload
  responses are the source of asset ids.

## Corpus (16 images, short side upscaled to 1024 with LANCZOS)

| Asset id | File | Source |
|---|---|---|
| asset_uwAC9eaNAgeirKG3Jw2MZsLP | office_shell.png | assets/office/painted/shell.webp |
| asset_jzCACh8ZX5rNmtbaUGGkuhdv | office_base_v3.png | assets/office/style/base_painted_v3.png |
| asset_9Ua2d18fB86rqQeapMnwLnyw | office_base_alt1.png | assets/office/style/candidates/base_alt1.png |
| asset_kDNdQxuVVq1kHYAyMXifMkSG | office_base_alt2.png | assets/office/style/candidates/base_alt2.png |
| asset_HEvYTMMfx8Sxog7ZcfuXq2mD | office_shell_alt1.png | assets/office/style/candidates/shell_alt1.png |
| asset_cCx5eDSSP76G812X85HninMo | office_shell_alt2.png | assets/office/style/candidates/shell_alt2.png |
| asset_dUaJKnafSCEnA2EhzuyPx7t7 | map_ascent.png | assets/maps/painted/ascent.webp |
| asset_nHAJjwmAEa25HVPpdVVmiBxJ | map_bind.png | assets/maps/painted/bind.webp |
| asset_QFRn5JN8xFBeLtgXj3Lkqj8S | map_haven.png | assets/maps/painted/haven.webp |
| asset_51S2nUYYcx5b9XnVRS1rG2xK | map_lotus.png | assets/maps/painted/lotus.webp |
| asset_nsSsyjrbwrFKXi1dXc7KrXwW | map_split.png | assets/maps/painted/split.webp |
| asset_RHngrpKjLQT6gdahz9DwoCbL | map_ascent_alt.png | assets/maps/style/candidates/ascent_alt.png |
| asset_iyrgchw1LezSNsSPQN6hYMp5 | map_bind_alt.png | assets/maps/style/candidates/bind_alt.png |
| asset_cQL9cuMKMcZ1jQGARgPdUds3 | map_haven_alt.png | assets/maps/style/candidates/haven_alt.png |
| asset_LVK38J83BrV4e7dLFtaiUSKx | map_lotus_alt.png | assets/maps/style/candidates/lotus_alt.png |
| asset_aFWhvdvy3sEWc7z7f1YZRffo | map_split_alt.png | assets/maps/style/candidates/split_alt.png |

Captions follow the pattern
`esports-sim-diorama style, isometric <esports office interior|{theme}
map diorama>, <concrete contents>, <teal/amber lighting note>, dark navy
surround/void`. Full caption text lives in each asset's `description`
on Scenario (and in the session scratchpad `corpus/manifest.json`).

## Full API recipe validated this session

1. `GET /v1/models?pageSize=100` — duplicate check (Basic auth).
2. `POST /v1/models?projectId=<proj>` body
   `{"name": "esports-sim-diorama", "type": "flux.2-dev-lora"}` → 200,
   `model.id`.
3. Per image: `POST /v1/models/<modelId>/training-images?projectId=<proj>`
   body `{"name": "<file>.png", "data": "data:image/png;base64,<b64>"}`
   → 200 with asset id + auto-caption.
4. Per image: `PUT /v1/assets/<assetId>?projectId=<proj>` body
   `{"description": "<caption with trigger phrase>"}` → 200.
5. `PUT /v1/models/<modelId>/train?projectId=<proj>` with the parameters
   block above → **429 PlanLimitReachedError on cu-basic**.
