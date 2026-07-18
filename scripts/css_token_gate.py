# CSS token gate: web/static stylesheets must reference colors through
# --es-* design tokens (ui/design-system/tokens.css), never raw hex.
# Exit 1 = fail. Mirrors the other repo gates (balance/pacing/floor).
import re, sys
from pathlib import Path

STATIC = Path("src/esports_sim/web/static")
ALLOWED = {
    # viewer/map-studio paint scenes use literal colors for SVG map art that
    # intentionally matches the painted assets; keep the allowlist narrow.
    "viewer.js",
}
HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")

bad = []
for css in sorted(STATIC.glob("*.css")):
    for i, line in enumerate(css.read_text(encoding="utf-8").splitlines(), 1):
        # skip comments
        code = line.split("/*")[0]
        for h in HEX.findall(code):
            bad.append(f"{css.name}:{i}: {h}  {line.strip()[:80]}")

if bad:
    print("FAIL: raw hex colors in web CSS (use --es-* tokens):")
    print("\n".join(bad[:60]))
    sys.exit(1)
print("OK: no raw hex colors in web/static CSS")
