# Perf notes

Place to track performance observations that aren't bugs but might
bite later. Add a section when you notice something; resolve a section
when it's actually addressed.

## Status
No perf hot-spots known today. The deterministic core is intentionally
simple; the test suite runs in single-digit seconds.

## What to watch
- Test suite duration if it climbs past ~10s.
- Cold-start time of the local LLM-backed adapters (if any).

## Profiling cheat-sheet
`python -m cProfile -o /tmp/p.prof scripts/<thing>.py` and then
`snakeviz /tmp/p.prof` (or `python -m pstats /tmp/p.prof`).
