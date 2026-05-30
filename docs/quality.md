# Quality

What we mean by a 'good' contribution here.

## A good PR
- Single concern. Easy to review.
- Has tests for new behavior (or explains why not).
- Updates docs that get out of sync.
- CHANGELOG.md gets a one-line bullet.

## A good test
- Pins behavior, not implementation.
- One clear assertion. If you need three, write three tests.
- Doesn't depend on wall-clock time or network — uses seams.

## A good commit message
- Subject line is imperative, under 70 chars, no period.
- Body explains *why*, not what.

## A good docstring
- One short paragraph about the *contract*.
- 'Note:' for non-obvious tradeoffs.
