# Retained original receipts

These are safe original files copied from the acceptance run after PR review identified that its local `runs/` references were not available to remote readers. No new gameplay, report rerun or acceptance happened during publication. `raw-git-mapping.json` maps the original paths to published paths and lists their exact byte lengths, SHA256 values and Git blob IDs. `-text -whitespace` attributes apply only to this evidence folder. The first fix commit was `b5ca3ce000b07ee9c92711bc220a6c818afeec5c`.

The original CSV is unchanged byte for byte. Its old references resolve as follows:

| CSV step | Original evidence reference | Published original |
| --- | --- | --- |
| 1 | `runs/playtests/2026-10-11-away-recap/01-dashboard.txt` | [01-dashboard.txt](01-dashboard.txt) |
| 2 | `runs/playtests/2026-10-11-away-recap/02-readback.txt` | [02-readback.txt](02-readback.txt) |
| 3 | `runs/playtests/2026-10-11-away-recap/03-readback.txt` | [03-readback.txt](03-readback.txt) |
| 4 | `runs/playtests/2026-10-11-away-recap/04-public.txt` | [04-public.txt](04-public.txt) |
| 5 | `runs/playtests/2026-10-11-away-recap/audit.json;telemetry-report.txt;usage-report.txt` | [audit.json](audit.json), [telemetry-report.txt](telemetry-report.txt), [usage-report.txt](usage-report.txt) |

The CSV analytics references to `audit.json` and `usage-retained.json` refer to their originals in this folder. `original-comparison.json` retains the read-only comparison against the parent's original reproduction: fixture and accepted decisions107:110 match. Original discovery/reproduction credit remains with that parent session.

`03-plan.txt` and `05-save.txt` retain actual 200 response receipts. `02-prep.txt` retains CLI echoed execution code, but its console calls did not appear in stdout; do not treat it as retained response text. `02-readback.txt`, saved decision107 and retained request13/result200 independently support preparation acceptance. `04-public.txt` retains independently recovered DOM and public state/report/usage readbacks after the single Advance. The saved fixture reports Nordic Frost3 / Team Nexus13 and Ghost1.63. The Dashboard visible text says13-3 win.

Observer limitations remain visible. `04-advance.js` awaited the wrong `/api/advance` route; the observer was interrupted and no `04-advance.txt` response stdout was retained. `04-readback.txt` is the original timeout for literal `NEWS`, which the interface uppercases with CSS. Neither observer error initiated a second advance. No absent response or exit stdout has been invented.

There are multiple bounded usage snapshots: `audit.json` and `usage-retained.json` captured36 events; the later `usage-report.txt` counted38 world events; the copied original `usage.0.jsonl` is the retained sidecar at publication. All are original bytes captured at different times. All four observed mutation requests have paired200 outcomes. Browser `session_id` values in usage are non-authentication telemetry IDs; none match the privately restored membership ID. These bounded receipts do not prove complete funnels, complete duration or exact attention.

`telemetry-report.txt` reports1 campaign save and110 recorded actions; it also reports skipping copied metadata and membership files because they are not GameState saves. Historical action totals belong to the inherited campaign; only the three indices in `audit.json` are new acceptance decisions. Individual report process exit receipts were not retained: the original grouped PowerShell tool call exited0, but its pipeline does not prove each subprocess exit code. Do not infer a gate pass. No tests or expensive gates ran.

`flywheel-before.json` is the original inherited findings snapshot. `flywheel-after.json` retains only original appended record IDs0222 through0224, not the full appended record stdout. No record text was reconstructed for publication.

`source-manifest.json` is the original425 tracked src/data Windows-file SHA256 freeze, recorded with base20273 and a dirty narrative edit. It excludes scripts/tests/untracked sources. `tested-source-git-mapping.json` is a new read-only publication audit, mapping that original freeze to b5ca3ce Git bytes/blobs using Git filters. It verifies unchanged working files and filter equivalence, not that the gameplay ran on a clean final HEAD. CRLF versus LF hashes are explicitly separate. The final evidence commit retains the same narrative Git blob.

`server-running.json` is the original public startup receipt: timestamp, owned PID/port8539, cwd/imported package path, copied fixture hash and425-source count. It contains no command, save contents, cookie or membership inputs. The original fixture SHA and import identity remain independently readable without publishing the private launcher.

Excluded private material: saves, membership/cookies, full launch or identity setup inputs, and launch harness. Public source hashes and local-path provenance are included, but no credential or membership identifiers are published. The original server/browser were stopped before publication.
