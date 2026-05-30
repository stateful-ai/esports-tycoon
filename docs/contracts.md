# Contracts

Promises the code makes that aren't in the type system but are
enforced by tests and by convention.

## Determinism
Same inputs, same outputs. Always.

## No silent failures
Any path that swallows an exception must log it loudly at WARNING.

## One reason per function
Public functions do one thing. Tests pin the thing they do.

## Backwards compat for one minor version
When we change a public surface, the old shape works for at least
one more minor release with a deprecation note in CHANGELOG.

## Tests own behavior
When a test fails after a refactor, the test was right.
