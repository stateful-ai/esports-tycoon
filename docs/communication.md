# Communication

How we write the artifacts that outlast the conversation.

## Commit subject line
Imperative ('Add foo', not 'Added foo'). Under 70 chars. No period.

## Commit body
Explain the *why*. The diff already shows the *what*. Include any
non-obvious tradeoffs.

## PR description
Three sections, in order:
- **Summary** — one paragraph: what changed and why.
- **Test plan** — concrete bullets for what was verified.
- **Notes for review** — risk areas, design alternatives considered.

## Reviewer voice
Address the diff, not the author. 'This branch is over-fitting to one
case' beats 'You over-fit to one case.'
