# Vendored frontend modules

`app.js` and `profile.js` used to `import` preact and htm straight from
`https://esm.sh/...` at page load. That made a third-party CDN a hard runtime
dependency of the game: with no internet (an offline session, a locked-down
CI box, a LAN party on a hotel Wi-Fi that eats esm.sh) the module graph never
resolved and the UI rendered as an empty shell — chrome and tabs painted, the
`#view` root stayed blank, and the only clue was a console error.

These files are the untouched npm ESM builds, fetched from registry.npmjs.org:

| file                | package        | source in the tarball        |
|---------------------|----------------|------------------------------|
| `preact.mjs`        | preact@10.19.2 | `dist/preact.mjs`            |
| `preact-hooks.mjs`  | preact@10.19.2 | `hooks/dist/hooks.mjs`       |
| `htm.mjs`           | htm@3.1.1      | `dist/htm.mjs`               |

The one edit is in `preact-hooks.mjs`: its `import {options} from "preact"` is
a bare specifier, which a browser cannot resolve without an import map, so it
is rewritten to `./preact.mjs`. Nothing else is changed.

Refresh with `scripts/vendor_frontend_deps.py` (it re-downloads the pinned
versions and re-applies that one rewrite). `tests/test_web_assets.py` guards
the invariant: no file under `web/static/` may reference an external host.
