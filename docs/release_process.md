# Release process

Releases are founder-cut, not autonomous. The release_engineer agent
drafts notes; the founder reviews and tags.

## Versioning
We follow SemVer (MAJOR.MINOR.PATCH).

## Cutting a release
1. Founder reviews the candidate notes drafted by release_engineer.
2. Founder edits CHANGELOG.md and commits.
3. Tag: `git tag -a vX.Y.Z -m 'release notes summary'`.
4. Push tag: `git push origin vX.Y.Z`.

## Hotfixes
Branch from the tag, fix, tag with the next PATCH.
