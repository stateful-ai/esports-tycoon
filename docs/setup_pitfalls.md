# Setup pitfalls

Things that bite contributors on day 1. If one of these snags you,
add a new one — that's the whole point of the file.

## venv not activated
If `pytest` is not found, you probably forgot to activate your
venv (`source .venv/bin/activate`) or you're using a different
Python. The repo's pinned Python version is in `pyproject.toml`.

## Stale dev deps
`pip install -e .[dev]` once after pulling new changes that touch
pyproject.toml or you'll get import errors on freshly-added deps.

## Cached test fixtures
`pytest --cache-clear` if a determinism test fails right after a
branch swap — pytest's cached previously-passed list can mislead.
