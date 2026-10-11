# Development first-observation browser session — PR #398

Question: can a player distinguish a promoted player's first season observation from measured flat growth while seeing last week's gains?

Actual browser session on clean `7bee7d747dd1bf651ac4e38b55336be0a4db9847`, `fix/first-development-baseline-clarity`, isolated loopback 8536 and CLI browser `development-398-first`. Trusted task model/effort: gpt-6.1-sol / medium. No local automated tests, syntax checks, native acceptance helpers, simulation gates, or analytics report commands were executed. Logging and direct receipt reconciliation are observational bookkeeping, not test passes.

The copied synthetic `26UHC` seed2038 save starts and ends at S2 W5 with 120 accepted decisions and 27 manager snapshots. Fixture import/identity restoration is harness setup, not gameplay or a newly observed Advance. Private bootstrap, cookies, sessions, and authentication configuration are excluded from the publication allowlist. The copied save has SHA256 699C475C39B34CFC49748D0FE774F0EA8E753AC675CD36FC3EA5D82D27E8996F.

## Player observations

Six 21-column shard rows are retained in actions.csv. Step 1 is the CUA harness failure and was registered retrospectively with that limitation explicitly preserved; steps 2–6 have timestamped pre-action intentions. No root/canonical history was appended or rewritten.

- Step 2: copied world reload opens Team Nexus S2W5; pending Nightsurge content moment visible.
- Step 3: Club → Development visibly shows Nightsurge `First observation · W4`, `No earlier comparison`, and `First observation — no earlier skill comparison`, with stored52.2 rating in Start/Now. Latest-week Practice+0.31OVR, Bench scrims+0.01OVR, Tactical/light,0maps remain visible. Tooltip/source data retain game_sense+.67, positioning+.85, utility_usage+1.56; scrim+.03game_sense/+.03positioning. Actual screenshot is evidence/development-report.png. Independent `/api/roster/team_nexus`200 confirms comparison_available=false, overall_delta=null, first_observation, tracked_points1. Hollowlock/Slyblade still show measured0.0 with their5tracked points; summary6compared,3grown,0regressed,3steady,1first observation. Positive-growth rows remain visible.
- Step 4: identity cell in report opens Nightsurge `team_kraken_unit_p0` profile. Public `/api/players/team_kraken_unit_p0/profile`200 independently confirms bench, Tactical/light, mentorApex. Profile has separate remaining gap: Development says `CA52.2 to52.2 over1weeks`; it does not expose the Club latest-week gains. Profile's3season matches are a separate time scope from the Club latest-week0senior maps. This is a partial player outcome, not parity acceptance.
- Step 5: exactly one visible Advance click produces POST `/api/actions/advance`409. Response/UI directs Dashboard → Needs you → Team moment. No flavor choice, retry, or accepted Advance. Independent public readback remains S2W5; Nightsurge stays1point; defaultfive apex,vortex,ghost,fa_13,echo unchanged. The now-two-point transition is UNVERIFIED.
- Step 6: explicit Save produces POST `/api/actions/save`200 and `World saved.` Saved decisions, manager snapshots, development history, and every top-level semantic field equal copied baseline. No new accepted decisions. Raw save byte identity is separately recorded in manifest and is not inferred from semantic equality.

## Reconciliation and limitations

Saved action-log coverage:120/120 preexisting decision entries retained identically,0new entries,27/27snapshots identical. One rejected gameplay attempt is correctly outside accepted decisions. All six CSV rows are decision-log `not_instrumented` for their specific navigation/setup/rejection/persistence scope; none imply a missing accepted choice. Preserve usage coverage separately.

Raw usage baseline 10 events is an exact prefix of end 28 events. End world-scoped retained stream has 2 attempts, 2 results, 5 views, 16 visible-time slices, 2 session_start and 1 session_end. Both action-endpoint attempts have matching results: request 13 advance 409/http_error; request 14 save 200/success. Views retain lobby, dashboard, club/squad and club/development. Profile identity/navigation has no dedicated view hook; the HTTP200 is independent public readback, not invented usage. Raw streams are bounded/best-effort; visible time does not prove attention or exact session duration. These counts describe retained capture only.

Harness failures/corrections remain durable: CUA Chrome unavailable and inventory apps[]/browsers[]; initial baseline accidentally counted the telemetry object as1 (corrected per-manager27 in import-baseline-correction.json); independent readback guessed `/api/team/team_nexus` and received404 (corrected using actual `/api/roster/team_nexus`200); CLI skill's documented `network` command is unsupported by installed CLI (raw failed output retained). Actual wire and usage streams, rather than that unsupported command, support Advance/Save evidence. Initial console404 and rejected Advance409 are retained in browser console snapshots.

Source before/after: same clean head7bee; raw Windows CRLF SHA256 values and Git-normalized blob IDs are separately recorded for both source changes and the unrun regression file. Working Git blobs equal head blobs and full tracked Git status is clean. No source/test/primary/PR-head/shared-ref edits. Owned server parent 39284 / listener 19360 relationship and command verified before stopping; only named CLI development-398-first was closed. Ports8421/8538 untouched.

Scope of observed acceptance: Club Development first-observation distinction, genuine-flat distinction, preserved weekly attribution, compared-only coverage, identity readback, and explicit persistence on exact 398 head. No two-point transition, legacy-save attribute-gap runtime exercise, fresh campaign, broad layout/device coverage, balance/determinism gate, or unit acceptance claimed. Screenshot was actually inspected and shows the distinction with readable gain chips; minor plural text `1 first observations` remains cosmetic.

## Flywheel

Inherited 8 local esports-playtest findings before browser play. Recorded two learnings and one pain point in local Agora flywheel: esports-playtest-0240,0241,0242. Actual receipts are evidence/flywheel-before.json and flywheel-after.json. Remaining player-profile comparison gap is handed to root for separate GPT-6.1-sol/medium ownership; no scope expansion to this fix.

