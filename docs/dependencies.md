# Dependencies

We try to stay lean. Every dependency added is a future maintenance cost.

## Runtime
- Python ≥ 3.10 (or whatever pyproject.toml pins).
- See pyproject.toml for the canonical list.

## Dev
- pytest for tests.
- Optional: ruff for linting (no commitment to a specific version).

## When we add a dependency
Open a PR with a short note in the description explaining what it
unlocks that we can't reasonably do with stdlib. Bias toward small
single-purpose packages over kitchen-sink frameworks.
