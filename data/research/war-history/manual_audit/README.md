# Independent browser audit

Expected values in `observations.json` were transcribed after viewing live
VLR pages in Playwright Chromium and inspecting screenshots with `view_image`.
The browser session does not call the collector/parser or generate expected
values from CSV rows. Comparison keys identify the corresponding records;
expected stats, scores, banks and categories come from browser evidence.

The 2026 sample covers Gen.G–ZETA Pacific Stage 2 performance and Team
Liquid–Paper Rex Champions overview/economy, including blank versus displayed
zero, clutch counts, objective stats, both sides and every played round of
the sampled Champions map. Separate attack/defend toggle samples verify
player-side stats and exposure. An academy/parent-tag sample verifies the
logo/agent recovery rule. Historical samples are described in the final
observations file, including the winners, sides and cumulative scores of all
eight overtime rounds in 2025 NRG–EDward Gaming Abyss. The final
forfeit sample confirms the 13–0 administrative scoreline, ten blank player
rows and explicit forfeit header; it verifies exclusion from WAR. The final
`result.json` records the actual page, screenshot and
field-check counts and hashes of the checked CSV files.
An additional rendered performance sample confirms three negative ECON
values as source anomalies and checks that they remain flagged for review.

Initial transcription errors in side colors, the last buy categories, and
the invy/f0rsakeN rows were corrected after enlarged browser screenshots and
browser text review. Historical values were also checked against the
independent browser's visible-text log retained in this folder, including
d4v41's opening-duel counts. The collected values were correct. These corrections
are not claimed as data-collection errors. No screenshot expectation was
changed just to agree with a CSV.

The sample is purposive, not an estimate of the full dataset's error rate.
Full structural validation separately checks grain, keys, joins, provenance,
map/round reconciliation, missingness and eligibility. CSV hashes in this
audit must be refreshed after collection is finished, not while streaming
tables are still growing.
