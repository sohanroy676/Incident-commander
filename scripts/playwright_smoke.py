"""Dev-only browser smoke test for the hub page. Not part of CI, the tests or the runtime.

Setup (outside requirements*.txt on purpose):
    pip install playwright
    playwright install chromium
Run:
    python scripts/playwright_smoke.py [--headed]

It starts a hub on a free local port, drives the real page and exits 1 on the first failed check.
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ic_hub.server import make_server

TIMEOUT_MS = 30_000


def check(ok: bool, what: str) -> None:
    print(("PASS " if ok else "FAIL ") + what)
    if not ok:
        raise SystemExit(1)


def main(headed: bool) -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright is not installed: pip install playwright && playwright install chromium")
        raise SystemExit(2) from None

    server = make_server(0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    problems: list[str] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=not headed)
            page = browser.new_page()
            page.on("console", lambda m: problems.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: problems.append(str(e)))
            page.goto(f"http://127.0.0.1:{server.port}/")

            page.wait_for_selector("#alerts tbody tr", timeout=TIMEOUT_MS)
            check(page.title() == "Incident Commander hub", "page loads and lists alerts")
            check(page.locator("#metrics li").count() > 0, "metrics strip is filled")

            row = page.locator("#alerts tbody tr", has_text="ALRT-9003")
            row.get_by_role("button", name="Run").click()
            # a locator wait, not wait_for_function: the page CSP forbids string evaluation
            page.locator("#decisions", has_text="DECISION").wait_for(timeout=TIMEOUT_MS)
            check("ALRT-9003" in page.inner_text("#decisions"), "run ends with DECISION lines")
            check("Live updates" in page.inner_text("#stream-status"), "stream status is shown")

            before = page.evaluate("document.documentElement.dataset.theme")
            page.click("#theme-btn")
            after = page.evaluate("document.documentElement.dataset.theme")
            check(after in ("dark", "light") and after != before, "theme button switches theme")
            page.keyboard.press("t")
            back = page.evaluate("document.documentElement.dataset.theme")
            check(back != after, "t shortcut switches theme back")
            page.keyboard.press("?")
            check(page.locator("#shortcuts").evaluate("e => e.open"), "? opens the shortcut list")

            page.click("#am-btn")
            page.wait_for_selector("#alerts tbody tr:has-text('AM-')", timeout=TIMEOUT_MS)
            check("AM-" in page.inner_text("#am-ok"), "Alertmanager intake adds an alert")
            check(
                page.locator("#alerts tbody tr", has_text="AM-").locator("td").nth(3).inner_text()
                == "intake",
                "intake alert is marked as intake",
            )

            page.fill("#am-json", "{ not json")
            page.click("#am-btn")
            check("not valid JSON" in page.inner_text("#am-errors"), "bad JSON shows an error")
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
    check(not problems, f"no console errors {problems}")
    print("smoke test passed")


if __name__ == "__main__":
    main("--headed" in sys.argv)
