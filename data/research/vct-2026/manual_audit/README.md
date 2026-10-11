# Browser audit

All **662 field comparisons pass**, across **ten live VLR URLs** and eleven
screenshots. The screenshots were opened and visually inspected; expected
values were transcribed independently of the collection parser and CSV output.
Chromium opened the live public pages through Playwright with verified TLS.

`observations.json` holds the independent observations, page URLs, screenshot
paths, and review timestamp. `checks.csv` contains each expected and actual
value. `result.json` records the result and hashes of the checked CSVs and
observations; each check includes its screenshot hash.

| Example | What was checked |
| --- | --- |
| Gentle Mates–EDward Gaming, Santiago Haven | 13–11, 24 scored rounds, all ten player box scores |
| T1–Team Liquid, Santiago Split | 13–15, 28 scored rounds including overtime, all ten player box scores |
| Shopify Rebellion Black–ROSE, NA Stage 2 Breeze | 13–7, 20 scored rounds, all ten tier-2 box scores |
| QoR–Evictix, NA Stage 1 Pearl | 13–8, K/D/A present, optional stat fields blank |
| ACE–ODG, China Pro Division Pearl | 13–10, empty ACE lineup, five ODG names with blank stats |
| Santiago event statistics | Visible aggregate fields for marteen, eeiu, trent, and iZu; All/Both, minimum rounds zero |
| Bilibili Gaming–TYLOO, China Stage 1 Pearl | 13–3 and all ten box scores, investigating a round-denominator discrepancy |
| China Stage 1 event statistics | slowly's 517 rounds and nephh's 259 rounds confirmed; both exceed collected scoreline totals by one |
| Marved and FNS/FiNESSE profiles | Real names, current-team listing absence, and past-team/current-team distinction |

Missing source cells are checked as empty CSV values, not zero. The China
Pro Division example retains its scoreline and available names but is excluded
from the lineup model. China Stage 1 aggregate/map denominator differences
remain in `validation.json`; no unverified correction is applied.

Wait for page presentation animations to settle before capturing a screenshot;
early screenshots can have partially clipped digits. Two initial transcription
differences (CHAROD's opening counts and Racoone's spelling) were resolved by
re-reading the screenshots. The collected values were correct.

Recheck with:

```sh
python scripts/check_vlr_manual_audit.py
```

This is a purposive spot check of important edge cases. It does not establish
a dataset-wide error rate or complete worldwide coverage. A new snapshot needs
new browser observations; do not regenerate expected values from the CSV.
