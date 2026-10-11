# PR 387 remote-CI read-purity repair

This is source-only follow-up to head `33e789c1ba05c1a993f76bd9f1d7c0eac914bf2c`. It does not extend or recreate the browser acceptance recorded under the five gap40 session folders. Their CSV rows, raw receipts, freezes, manifests and historical build qualifications remain unchanged.

GitHub Actions run `38124501142`, Python 3.13 job `114425988784`, completed against that exact head with **3 failed, 1290 passed, 4 skipped in 4264.34s (1:11:04)**. All three failures were `tests/test_web_advance_transition.py::test_state_exposes_next_transition_without_mutating_campaign` for regular, playoffs and offseason. Python 3.12 was canceled. Full finalized job output was retrieved read-only through REST `repos/stateful-ai/esports-tycoon/actions/jobs/114425988784/logs`; the local private capture is `runs/387-ci-failed-job-final.log`.

The assertion diff skips an identical leading JSON prefix and shows two changed fields: `scout_progress_by` and `sponsor_slots_by`, each changing from `{}` to `{"team_nexus":{}}`. Source inspection traced them to dashboard reads through the mutable `GameState.scout_progress` and `GameState.sponsor_slots` convenience properties. Those properties intentionally use `setdefault` for write callers. The repair changes only the dashboard scouting-progress lookup and `_objectives_hub` sponsor iteration to read the existing per-manager maps with `.get`. Missing buckets still render the same zero/empty defaults; stored values remain visible. The objectives helper now uses its explicit team argument.

The whole-GameState purity regression and its transition-copy assertions remain intact. Mutable state properties, simulation, readiness/retry/restart handling, and loading/transition wording are unchanged. No PR 388 finance repair was imported.

**Validation:** source inspection and remote-log inspection only. No local tests, simulations, gates, native syntax checks or browser acceptance ran for this repair under the user's explicit override. Fresh remote CI on the pushed repair head and independent root review are required before merge. Prior browser acceptance proves only its recorded builds.

Private finalized log: 2846751 bytes; SHA256 a24b5595f0f6bad79f0e160c071ce31b0fcb6c67511787aa0188f0fe5148ba59.
