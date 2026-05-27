# Process notes

How we work on this codebase.

## Small diffs by default
A PR should ideally fit on one screen. If it doesn't, the change is
probably doing two things; split it.

## Tests are the contract
When you break a test you didn't expect to, the test is right until
proven otherwise. The bug is in the change, not the test.

## CHANGELOG.md as the running narrative
Every visible change gets one bullet under `## [Unreleased]`. The
release_engineer agent picks these up at release time.

## No magic numbers in code
Constants live in named places; ratios get a name.
