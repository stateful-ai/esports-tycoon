# Q&A

Placeholder for recurring questions. Append as they come up.

## Q: What does this project deliberately not do?
See docs/non_goals.md.

## Q: How is determinism enforced?
See docs/determinism_contract.md or the equivalent — every adaptive
feature must reduce to a byte-identical replay under fixed inputs.

## Q: How do I run tests?
Activate the venv (or use the project's Makefile if present): `pytest`.

## Q: Where do design decisions live?
Under docs/decisions.md (append-only log).
