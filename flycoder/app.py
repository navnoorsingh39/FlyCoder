"""FlyCoder: 166,700 MaleCNS neurons trying to center a div.

    python -m flycoder
    python flycoder/app.py
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flycoder import config as C
from flycoder.experiment import FlyCoderExperiment, run_headless

DASH = Path(__file__).resolve().parent / "dashboard"


def _handler(exp: FlyCoderExperiment):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, body: bytes, ctype: str, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _file(self, name: str, ctype: str) -> None:
            path = (DASH / name).resolve()
            if DASH.resolve() not in path.parents and path != DASH.resolve():
                return self.send_error(404)
            if not path.is_file():
                return self.send_error(404)
            return self._send(path.read_bytes(), ctype)

        def do_GET(self):
            path = urlparse(self.path).path
            files = {
                "/": ("index.html", "text/html; charset=utf-8"),
                "/index.html": ("index.html", "text/html; charset=utf-8"),
                "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                "/styles.css": ("styles.css", "text/css; charset=utf-8"),
                "/cns3d.js": ("cns3d.js", "text/javascript; charset=utf-8"),
                "/fly_motion.js": ("fly_motion.js", "text/javascript; charset=utf-8"),
                "/fly3d.js": ("fly3d.js", "text/javascript; charset=utf-8"),
                "/vendor/three.min.js": ("vendor/three.min.js", "text/javascript; charset=utf-8"),
                "/favicon.ico": ("favicon.ico", "image/x-icon"),
                "/favicon-16x16.png": ("favicon-16x16.png", "image/png"),
                "/favicon-32x32.png": ("favicon-32x32.png", "image/png"),
                "/apple-touch-icon.png": ("apple-touch-icon.png", "image/png"),
                "/flycoder-icon.svg": ("flycoder-icon.svg", "image/svg+xml; charset=utf-8"),
                "/flycoder-icon-512.png": ("flycoder-icon-512.png", "image/png"),
            }
            if path in files:
                return self._file(*files[path])
            if path == "/static.json":
                if exp.static is None:
                    return self._send(b'{"ready":false}', "application/json", 503)
                return self._send(json.dumps(exp.static).encode(), "application/json")
            if path == "/state":
                return self._send(json.dumps(exp.snapshot()).encode(), "application/json")
            if path != "/events":
                return self.send_error(404)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            seen = -1
            try:
                while True:
                    seen, data, fresh = exp.wait_payload(seen, timeout=15)
                    if fresh and data is not None:
                        self.wfile.write(f"data: {json.dumps(data)}\n\n".encode())
                    else:
                        self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
            except OSError:
                return

        def do_POST(self):
            if urlparse(self.path).path != "/control":
                return self.send_error(404)
            n = int(self.headers.get("Content-Length") or 0)
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
            except json.JSONDecodeError:
                return self._send(b'{"ok":false}', "application/json", 400)
            cmd = body.get("cmd")
            if cmd == "start":
                exp.start()
            elif cmd == "pause":
                exp.pause()
            elif cmd == "reset":
                exp.reset()
            elif cmd == "speed":
                exp.set_speed(int(body.get("value", 1)))
            elif cmd == "cinematic":
                exp.set_cinematic(bool(body.get("value")))
            else:
                return self._send(b'{"ok":false}', "application/json", 400)
            return self._send(b'{"ok":true}', "application/json")

    return Handler


def serve(exp: FlyCoderExperiment, port: int, open_browser: bool) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), _handler(exp))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}/"
    print(f"dashboard: {url}", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        print("\nstopping", flush=True)
        exp.stop()


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="FlyCoder: MaleCNS connectome centering a div.")
    p.add_argument("--port", type=int, default=C.PORT)
    p.add_argument("--device", default=C.DEVICE, help="cpu, cuda, or auto")
    p.add_argument("--seed", type=int, default=C.SEED)
    p.add_argument("--no-browser", action="store_true")
    p.add_argument("--headless", action="store_true", help="run until centered, no dashboard")
    p.add_argument("--max-cycles", type=int, default=500)
    args = p.parse_args(argv)

    if args.headless:
        snap = run_headless(max_cycles=args.max_cycles, seed=args.seed, device=args.device)
        env = snap["env"]
        print(
            f"centered={env['centered']}  cycles={snap['cycles']}  attempts={snap['attempts']}  "
            f"brain_steps={snap['brain_steps']}  reward={snap['cumulative_reward']}  "
            f"dist={env['distance_from_center']}",
            flush=True,
        )
        print(env["css_text"], flush=True)
        if not env["centered"]:
            raise SystemExit(2)
        return

    mimetypes.add_type("text/javascript", ".js")
    exp = FlyCoderExperiment(device=args.device, seed=args.seed)
    loader = threading.Thread(target=exp.load, daemon=True)
    loader.start()
    exp.spawn()
    serve(exp, args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
