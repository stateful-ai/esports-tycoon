# Combined-eight gate evidence correction

Offline audit on the completed frozen eight-fix source, checkout3ac34df3a476543d9e79dc4dc03bb381c04e397d with reviewed tree833ae36edda98357c6f88b012a6fdfbba94104e0. Root model/effort unknown (not exposed), game0.0.1, identified test world26UHC/seed2038/S1W2. The correction row's expectation precedes re-verification; it does not backdate the original helper failure.

The first artifact-preservation helper exited1 before writing because it compared raw Windows working-file digests from result.source_sha256 against Git-filtered blob digests from manifest.source_sha256. The actual full pytest result was already successful:1225passed6240.22s, exit0/source_unchangedtrue. Corrected verification compares raw hashes to manifest.working_file_sha256, then independently verifies each current Git-filtered file identity and blob digest against the reviewed tree. All fifteen paths pass both comparisons.

Startup, full stdout, terminal result and the failed-verifier clarification are preserved under the sibling 2026-10-08-eight-gap-validation/evidence/full-gate directory. Original nineteen player observations remain byte-identical. No test run restarted, source changed, game action executed or browser interaction emitted. This offline correction expects zero new accepted decisions and is not instrumented by either game telemetry stream. The earlier browser session and its pre/post flywheel already preserve gameplay findings; this is supplemental validation evidence, with no duplicate flywheel publication.

This combined-eight gate does not validate the later dashboard/current-roster fixes or final actual-main CI. Their ten-fix gate remains separate.
