"""Capture real FlyCoder release screenshots and a Recording Mode video.

Requires a running dashboard (python -m flycoder --no-browser --port 8788)
and Playwright Chromium:

    pip install playwright
    python -m playwright install chromium

    python scripts/capture_release_media.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
MEDIA = ROOT / "docs" / "media"
URL = "http://127.0.0.1:8788/"
VIEW = {"width": 1920, "height": 1080}


def _ffmpeg() -> str | None:
    return shutil.which("ffmpeg")


def wait_ready(page) -> None:
    page.wait_for_selector("#btn-start", timeout=180_000)
    reset = page.locator("#btn-reset")
    if reset.count():
        try:
            if not reset.is_disabled():
                reset.click()
                page.wait_for_timeout(600)
        except Exception:
            pass
    page.wait_for_selector("#btn-start:not([disabled])", timeout=180_000)
    page.wait_for_timeout(800)


def shot(page, name: str) -> None:
    path = MEDIA / name
    page.screenshot(path=str(path), type="png")
    print("wrote", path, flush=True)


def crop(page, selector: str, name: str) -> None:
    loc = page.locator(selector)
    loc.screenshot(path=str(MEDIA / name))
    print("wrote", MEDIA / name, flush=True)


def to_gif(mp4: Path, gif: Path) -> None:
    ff = _ffmpeg()
    if not ff or not mp4.exists():
        return
    pal = MEDIA / "_palette.png"
    # Short, readable preview (~12s @ 10fps, half width) so GitHub stays cloneable.
    vf_in = "fps=10,scale=960:-1:flags=lanczos"
    subprocess.run(
        [ff, "-y", "-ss", "8", "-t", "12", "-i", str(mp4), "-vf", f"{vf_in},palettegen", str(pal)],
        check=False,
        capture_output=True,
    )
    subprocess.run(
        [ff, "-y", "-ss", "8", "-t", "12", "-i", str(mp4), "-i", str(pal),
         "-filter_complex", f"{vf_in}[x];[x][1:v]paletteuse", str(gif)],
        check=False,
        capture_output=True,
    )
    pal.unlink(missing_ok=True)
    if gif.exists():
        print("wrote", gif, gif.stat().st_size, "bytes", flush=True)


def compress_mp4(src: Path, dest: Path) -> None:
    ff = _ffmpeg()
    if not ff:
        if src != dest:
            shutil.copyfile(src, dest)
        return
    subprocess.run(
        [ff, "-y", "-i", str(src), "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-crf", "28", "-preset", "medium", "-movflags", "+faststart",
         "-vf", "scale=1920:1080:flags=lanczos", str(dest)],
        check=False,
    )
    print("wrote", dest, dest.stat().st_size if dest.exists() else 0, "bytes", flush=True)


def main() -> int:
    MEDIA.mkdir(parents=True, exist_ok=True)
    raw_dir = MEDIA / "_raw"
    if raw_dir.exists():
        shutil.rmtree(raw_dir)
    raw_dir.mkdir()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport=VIEW,
            device_scale_factor=1,
            record_video_dir=str(raw_dir),
            record_video_size=VIEW,
        )
        page = context.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda exc: errors.append(f"pageerror {exc}"))
        page.on("console", lambda msg: errors.append(f"console.{msg.type} {msg.text}") if msg.type == "error" else None)

        page.goto(URL, wait_until="domcontentloaded")
        wait_ready(page)
        fav = page.evaluate("() => !!document.querySelector('link[rel=\"icon\"]')")
        print("favicon link", fav, flush=True)

        # Confirm WebGL views have drawn something non-black.
        page.wait_for_timeout(1200)
        gl_ok = page.evaluate(
            """() => {
              const fly = document.getElementById('fly3d');
              const brain = document.getElementById('brain');
              return !!(fly && brain && fly.width > 8 && brain.width > 8 &&
                        typeof THREE !== 'undefined' && typeof FlyView === 'function' && typeof CNSView === 'function');
            }"""
        )
        print("webgl canvases", gl_ok, flush=True)

        rec = page.locator("#btn-record")
        if rec.count() and "on" not in (rec.get_attribute("class") or ""):
            rec.click()
            page.wait_for_timeout(200)

        reset = page.locator("#btn-reset")
        if reset.count() and not reset.is_disabled():
            reset.click()
            page.wait_for_timeout(800)
            wait_ready(page)

        page.click("#btn-start")
        # Intro + first cycles in Recording Mode. Prefer live /state (authoritative).
        deadline = time.time() + 40
        while time.time() < deadline:
            try:
                st = json.loads(urlopen("http://127.0.0.1:8788/state", timeout=5).read())
                if (st.get("attempts") or 0) >= 1:
                    break
            except Exception:
                pass
            page.wait_for_timeout(400)
        page.wait_for_timeout(1800)
        shot(page, "flycoder-running.png")
        crop(page, "#brainwrap", "flycoder-connectome.png")
        crop(page, "#flywrap", "flycoder-3d-fly.png")

        deadline = time.time() + 70
        while time.time() < deadline:
            try:
                st = json.loads(urlopen("http://127.0.0.1:8788/state", timeout=5).read())
                if st.get("finished") or st.get("show_overlay") or (st.get("env") or {}).get("centered"):
                    break
            except Exception:
                pass
            page.wait_for_timeout(500)
        page.wait_for_timeout(1600)
        shot(page, "flycoder-success.png")
        shot(page, "flycoder-hero.png")

        video_path = page.video.path() if page.video else None
        context.close()
        browser.close()
        print("console/page errors:", errors[:12], flush=True)

    if video_path:
        src = Path(video_path)
        dest = MEDIA / "flycoder-demo.mp4"
        compress_mp4(src, dest)
        to_gif(dest, MEDIA / "flycoder-demo.gif")
    shutil.rmtree(raw_dir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
