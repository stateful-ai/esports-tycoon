# release_engineer brief

Stateful's release_engineer agent (added to company-os tonight) helps
cut a release for this project. The pipeline:

1. When the founder asks for a release draft, the agent reads
   CHANGELOG.md, recent merged PRs, and the commit log since the last
   tag.
2. It writes a release-notes draft as docs/release_notes_vX.Y.Z.md.
3. It flags whether the changes warrant MAJOR/MINOR/PATCH per SemVer.
4. The founder reviews and cuts the tag manually. The agent does NOT
   push tags or publish releases.

See company-os agents/release_engineer/instructions.md for details.
