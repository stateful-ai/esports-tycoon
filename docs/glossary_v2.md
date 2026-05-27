# Glossary (deep)

Companion to docs/glossary.md. Where the short version gives a sentence,
this gives a paragraph and why the term matters in this codebase.

## Determinism
Byte-identical replay under (recipe, seed, ticks). The harshest
invariant in the project — every adaptive feature has to be reducible
to this. When a test fails on a fixture, the question is always 'did I
change behaviour I didn't mean to?'

## Adaptation
The system's response to observed patterns in player or game state.
Adaptation here is *re-ordering* and *emphasis*, not generation; the
content surface stays authored, only its sequencing moves.
