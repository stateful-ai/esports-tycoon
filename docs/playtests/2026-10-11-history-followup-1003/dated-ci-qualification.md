# CI qualification added after the immutable 994-row summary

Prepared on 2026-10-11. The earlier `../2026-10-11-reviewed-history-and-analytics.md` remains an exact timestamped report. This addendum qualifies subsequent source/CI information without rewriting its earlier observations.

PR388's prior Python3.13 [remote run38121115590](https://github.com/stateful-ai/esports-tycoon/actions/runs/38121115590) reported **1 failed,1289 passed,4 skipped in5462.76 seconds**; the Python3.12 job was cancelled. The failure exposed a read-only finance serialization mutation. The source-only correction is `fa6e33b1f04e63120d17df8e34686f0b9b3421cd`, authored by the GPT-6.1-sol/medium owner. Root independently reviewed it in review5482703355. See the original [PR388 CI read-only correction report](https://github.com/stateful-ai/esports-tycoon/blob/fa6e33b1f04e63120d17df8e34686f0b9b3421cd/docs/playtests/2026-10-11-gap39-sponsor-runrate/ci-readonly-correction.md).

The correction report explicitly records unrun local regressions and no new browser session. Source diagnosis and root review do not establish passing current-head CI. This draft introduces no browser acceptance claims for PR388 or PR395, and no local tests or gates were run under the user's instruction. Fresh exact-head remote CI and independent root review remain required.
