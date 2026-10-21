"""Dev-only: record the README hero GIF from a real hub run. Not part of CI, the tests or the runtime.

Setup (outside requirements*.txt on purpose):
    pip install playwright pillow
    playwright install chromium
Run:
    python scripts/record_hero_gif.py [--out docs/media/hero.gif]

It starts `python -m ic_hub --data-dir <temp>` on a free port, drives the real page (ALRT-9001 in "me, in
this page" mode, approved with Shift+A), takes a screenshot per step and encodes them as a small GIF.
"""

from __future__ import annotations

import argparse
import io
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TIMEOUT_MS = 30_000
WIDTH = 900
COLOURS = 96


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def encode(frames: list[tuple[bytes, int]], out: Path) -> None:
    from PIL import Image

    images = []
    for png, _ in frames:
        img = Image.open(io.BytesIO(png)).convert("RGB")
        height = round(img.height * WIDTH / img.width)
        img = img.resize((WIDTH, height), Image.Resampling.LANCZOS)
        images.append(
            img.quantize(colors=COLOURS, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    images[0].save(
        out,
        save_all=True,
        append_images=images[1:],
        duration=[ms for _, ms in frames],
        loop=0,
        optimize=True,
    )


def record(url: str) -> list[tuple[bytes, int]]:
    from playwright.sync_api import sync_playwright

    frames: list[tuple[bytes, int]] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1100, "height": 700})

        def snap(ms: int) -> None:
            frames.append((page.screenshot(), ms))

        page.goto(url)
        page.wait_for_selector("#alerts tbody tr", timeout=TIMEOUT_MS)
        snap(1500)

        page.select_option("#mode", "web")
        page.fill("#deadline", "20")
        snap(1200)
        page.locator("#alerts tbody tr", has_text="ALRT-9001").get_by_role(
            "button", name="Run"
        ).click()
        page.locator("#approval").wait_for(state="visible", timeout=TIMEOUT_MS)
        page.locator("#approval").scroll_into_view_if_needed()
        snap(1800)
        page.keyboard.press("Shift+A")
        page.locator("#decisions", has_text="DECISION").wait_for(timeout=TIMEOUT_MS)
        page.locator("#decisions").scroll_into_view_if_needed()
        snap(2200)

        page.locator("#chart").scroll_into_view_if_needed()
        snap(2200)
        page.locator("#history-on").wait_for(state="visible", timeout=TIMEOUT_MS)
        page.locator("#history").scroll_into_view_if_needed()
        snap(1800)

        page.click("#theme-btn")
        snap(1800)

        page.locator("#am-btn").scroll_into_view_if_needed()
        page.click("#am-btn")
        page.wait_for_selector("#alerts tbody tr:has-text('AM-')", timeout=TIMEOUT_MS)
        page.locator("#alerts tbody tr", has_text="AM-").first.scroll_into_view_if_needed()
        snap(2500)
        browser.close()
    return frames


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "media" / "hero.gif")
    args = parser.parse_args()
    try:
        import PIL  # noqa: F401
        import playwright  # noqa: F401
    except ImportError:
        print(
            "needs playwright and pillow: pip install playwright pillow && playwright install chromium"
        )
        return 2

    port = free_port()
    with tempfile.TemporaryDirectory() as data_dir:
        hub = subprocess.Popen(
            [sys.executable, "-m", "ic_hub", "--port", str(port), "--data-dir", data_dir],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
        )
        try:
            time.sleep(1.5)
            frames = record(f"http://127.0.0.1:{port}/")
        finally:
            hub.terminate()
            hub.wait(timeout=10)
    encode(frames, args.out)
    print(f"wrote {args.out} ({args.out.stat().st_size / 1024:.0f} KiB, {len(frames)} frames)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
