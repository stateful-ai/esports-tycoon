# UI review driver — captures the esports-sim web UI with Playwright.
# Usage: .venv-win/Scripts/python.exe scripts/ui_review.py [--out DIR] [--tabs t1,t2] [--width W] [--height H]
#        .venv-win/Scripts/python.exe scripts/ui_review.py --gate [--tabs t1,t2]
# Gate mode: exit 1 if unnamedFocusable > 0 OR tinyTextUnder11px > 0 OR any
# pageerror/console.error is captured (excluding benign 404s for painted map
# assets under /assets/maps/painted/, which the viewer probes by design).
import argparse, asyncio, json, sys
from pathlib import Path

TABS = ["dashboard", "inbox", "tactics", "club", "facilities", "season", "market", "stats", "company"]

def _is_benign_painted_map_404(msg):
    return "404" in msg and "/assets/maps/painted/" in msg

async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="runs/ui-review")
    ap.add_argument("--tabs", default=",".join(TABS))
    ap.add_argument("--width", type=int, default=1600)
    ap.add_argument("--height", type=int, default=950)
    ap.add_argument("--gate", action="store_true", help="exit 1 on a11y/console regressions")
    args = ap.parse_args()

    out = Path(args.out); out.mkdir(parents=True, exist_ok=True)
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": args.width, "height": args.height})
        errors = []
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        def _on_console(m):
            if m.type == "error":
                errors.append(f"console.{m.type}: {m.text}")
        page.on("console", _on_console)
        def _on_response(r):
            if r.status >= 400:
                errors.append(f"http.{r.status}: {r.url}")
        page.on("response", _on_response)

        await page.goto("http://localhost:8420/", wait_until="networkidle")
        await page.screenshot(path=out / "00_landing.png")

        # Lobby may be open (no campaign loaded) — start/resume a campaign
        state = await page.evaluate("() => ({lobby: !document.getElementById('newgame').classList.contains('hidden'), resume: document.getElementById('lobby-resume') && !document.getElementById('lobby-resume').classList.contains('hidden')})")
        if state["lobby"]:
            if state["resume"]:
                await page.click("#resume-list .resume-world button >> nth=0", timeout=3000)
            else:
                await page.click("#mode-solo")
                await page.wait_for_selector("#ng-teams button.team-pick:not([disabled])", timeout=8000)
                await page.click("#ng-teams button.team-pick:not([disabled]) >> nth=0")
            await page.wait_for_load_state("networkidle")
            await page.wait_for_timeout(800)
        await page.screenshot(path=out / "01_after_load.png")

        # The first-week help overlay auto-opens on a fresh profile (season 1
        # week 1) and intercepts all pointer events. Dismiss it so tab clicks
        # work; this mirrors a real user closing the guide.
        await page.evaluate(
            "const h = document.getElementById('help'); if (h) { h.classList.add('hidden'); h.setAttribute('aria-hidden','true'); }"
        )

        for tab in [t.strip() for t in args.tabs.split(",") if t.strip()]:
            try:
                await page.click(f'nav#tabs [data-tab="{tab}"]', timeout=3000)
                await page.wait_for_timeout(700)
                await page.screenshot(path=out / f"tab_{tab}.png", full_page=True)
            except Exception as e:
                errors.append(f"tab {tab}: {e}")

        # Extra states worth reviewing
        try:
            await page.click('nav#tabs [data-tab="dashboard"]')
            await page.wait_for_timeout(500)
            # help overlay
            await page.evaluate("document.getElementById('help').classList.remove('hidden')")
            await page.screenshot(path=out / "overlay_help.png")
            await page.evaluate("document.getElementById('help').classList.add('hidden')")
        except Exception as e:
            errors.append(f"overlays: {e}")

        # player profile overlay (click first player name on Club > Squad)
        try:
            await page.click('nav#tabs [data-tab="club"]')
            await page.wait_for_timeout(700)
            await page.click("#view [data-pid] >> nth=0", timeout=4000)
            await page.wait_for_timeout(800)
            await page.screenshot(path=out / "overlay_player_profile.png", full_page=False)
            await page.keyboard.press("Escape")
            await page.evaluate("document.querySelectorAll('.overlay').forEach(o => o.classList.add('hidden'))")
        except Exception as e:
            errors.append(f"profile: {e}")

        # mobile viewport — dashboard responsiveness
        try:
            await page.set_viewport_size({"width": 390, "height": 844})
            await page.click('nav#tabs [data-tab="dashboard"]', timeout=4000)
            await page.wait_for_timeout(700)
            await page.screenshot(path=out / "mobile_dashboard.png", full_page=True)
            await page.click('nav#tabs [data-tab="club"]', timeout=4000)
            await page.wait_for_timeout(700)
            await page.screenshot(path=out / "mobile_club.png", full_page=True)
            await page.set_viewport_size({"width": args.width, "height": args.height})
        except Exception as e:
            errors.append(f"mobile: {e}")

        # a11y quick scan: focusable count, images without alt, contrast-ish (computed font sizes < 11px)
        audit = await page.evaluate("""() => {
          const els = [...document.querySelectorAll('button, a, input, select, [tabindex]')];
          const unnamed = els.filter(e => !e.textContent.trim() && !e.getAttribute('title') && !e.getAttribute('aria-label')).length;
          const smallText = [...document.querySelectorAll('#view *')].filter(e => {
            const fs = parseFloat(getComputedStyle(e).fontSize);
            return fs < 11 && e.textContent.trim() && e.children.length === 0;
          }).length;
          const onclick = document.querySelectorAll('[onclick]').length;
          return {focusable: els.length, unnamedFocusable: unnamed, tinyTextUnder11px: smallText, inlineOnclick: onclick};
        }""")
        (out / "audit.json").write_text(json.dumps({"audit": audit, "errors": errors}, indent=2))
        await browser.close()
        print(json.dumps({"out": str(out), "audit": audit, "errors": errors[:20]}, indent=2))

        if args.gate:
            real_errors = [e for e in errors if not _is_benign_painted_map_404(e)]
            fail = audit["unnamedFocusable"] > 0 or audit["tinyTextUnder11px"] > 0 or len(real_errors) > 0
            if fail:
                print(f"GATE FAIL: unnamedFocusable={audit['unnamedFocusable']} tinyTextUnder11px={audit['tinyTextUnder11px']} errors={len(real_errors)}")
                if real_errors:
                    print("  first errors:")
                    for e in real_errors[:10]:
                        print(f"    {e}")
                sys.exit(1)
            else:
                print("GATE PASS: unnamedFocusable=0 tinyTextUnder11px=0 errors=0")

asyncio.run(main())
