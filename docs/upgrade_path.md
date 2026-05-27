# Upgrade path

How we handle schema changes without breaking saved state or golden
fixtures.

## Saved state
Every save (or fixture, or event log) carries a schema version stamp.
When the schema changes, add a migration function that reads the old
shape and emits the new. Never overwrite the original — keep the old
loader paths until you're sure no users are still on the old version.

## Tests
Golden fixtures are not regenerated casually. If a determinism test
fails after a refactor, the test was right — re-examine the change.

## Communication
Schema changes get a one-paragraph entry in CHANGELOG.md explaining
what migration is needed.
