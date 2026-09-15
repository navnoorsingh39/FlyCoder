"""FlyCoder closed loop: CSS env → encoder → FlyBrain → decoder → selector → env.

The brain is the repository's `flybrain.FlyBrain`. Weights stay frozen.
Dashboard extras (sampled soma graph, staged telemetry) are display-only.
"""
from __future__ import annotations

import sys
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flybrain import FlyBrain

from . import config as C
from .coder_env import ACTION_LABELS, CoderEnv
from .decoder import DescendingDecoder
from .encoder import CoderEncoder
from .selector import ActionSelector

STAGES = ("OBSERVE", "STIMULATE", "PROPAGATE", "READOUT", "ACTION", "EVALUATE")

HUMOR = (
    "CSS competency: inconclusive",
    "Neuron budget: excessive",
    "Flexbox hypothesis detected",
    "Fruit fly refuses Grid",
)

KIND = {
    "bg": 0,
    "lc10a": 1,
    "lplc1": 2,
    "loom": 3,
    "steer": 4,
    "commit": 5,
    "reject": 6,
}

ACTION_SHORT = {
    "DISPLAY_BLOCK": "BLOCK",
    "DISPLAY_FLEX": "FLEX",
    "TEXT_ALIGN_CENTER": "TEXT ALIGN",
    "MARGIN_AUTO": "MARGIN AUTO",
    "JUSTIFY_CENTER": "JUSTIFY CENTER",
    "ALIGN_CENTER": "ALIGN CENTER",
    "DELETE_LAST": "DELETE",
    "RUN": "RUN",
}


def _centroid3(xs, ys, zs):
    if not xs:
        return 0.0, 0.0, 0.0
    n = len(xs)
    return sum(xs) / n, sum(ys) / n, sum(zs) / n


def neuron_map(brain) -> dict:
    """Static dashboard payload: real soma coordinates + sparse real synapses.

    Positions are MaleCNS soma (or to-soma) locations in EM voxels, preserved
    in 3D. This is a spatial connectome visualization, not neuron morphology.
    """
    empty = {
        "neurons": int(brain.n),
        "connections": int(len(brain.indices)),
        "mapped": 0,
        "vis": {"x": [], "y": [], "z": [], "kind": [], "id": [], "edges": [], "density": []},
        "labels": [],
        "pos_index": None,
        "brain_to_vis": {},
        "spatial": True,
        "morphology": False,
    }
    if brain.positions is None:
        return empty
    ok = ~np.isnan(brain.positions).any(axis=1)
    pos_index = np.full(brain.n, -1, np.int32)
    pos_index[ok] = np.arange(ok.sum(), dtype=np.int32)
    xyz = brain.positions[ok].copy()
    side = brain.side[ok]
    if (side == "R").any() and (side == "L").any():
        if np.nanmean(xyz[side == "R", 0]) < np.nanmean(xyz[side == "L", 0]):
            xyz[:, 0] = -xyz[:, 0]
    lo, hi = np.percentile(xyz, 0.4, axis=0), np.percentile(xyz, 99.6, axis=0)
    center = (lo + hi) / 2.0
    scale = float((hi - lo).max()) or 1.0
    norm = (xyz - center) / scale

    kind_of: dict[int, int] = {}

    def mark(idx, kind):
        for i in np.asarray(idx, dtype=np.int64).ravel():
            if 0 <= i < brain.n and pos_index[i] >= 0:
                kind_of[int(i)] = kind

    for s in "LR":
        mark(brain.cells(["LC10a"], s), KIND["lc10a"])
        mark(brain.cells(["LPLC1"], s), KIND["lplc1"])
        mark(brain.cells(["LC4"], s), KIND["loom"])
        mark(brain.cells(["LPLC2"], s), KIND["loom"])
    for g, k in (
        ("steer_L", KIND["steer"]), ("steer_R", KIND["steer"]),
        ("escape_L", KIND["commit"]), ("escape_R", KIND["commit"]),
        ("forward_L", KIND["commit"]), ("forward_R", KIND["commit"]),
        ("backward_L", KIND["reject"]), ("backward_R", KIND["reject"]),
    ):
        if g in brain.groups:
            mark(brain.groups[g], k)

    priority = np.fromiter(kind_of.keys(), dtype=np.int64, count=len(kind_of))
    mapped = np.flatnonzero(pos_index >= 0)
    need = max(0, C.GRAPH_NODES - len(priority))
    if need and len(mapped):
        taken = np.zeros(brain.n, dtype=bool)
        if len(priority):
            taken[priority] = True
        remaining = mapped[~taken[mapped]]
        if len(remaining):
            mi = pos_index[remaining]
            bins = np.clip(((norm[mi] + 0.5) * 16).astype(np.int32), 0, 15)
            code = bins[:, 0] * 256 + bins[:, 1] * 16 + bins[:, 2]
            rem = remaining[np.argsort(code, kind="stable")]
            step = max(1, len(rem) // need)
            fill = rem[::step][:need]
            for i in fill:
                kind_of.setdefault(int(i), KIND["bg"])

    vis_brain = np.fromiter(kind_of.keys(), dtype=np.int64, count=len(kind_of))
    vis_x, vis_y, vis_z, vis_kind, vis_id = [], [], [], [], []
    brain_to_vis: dict[int, int] = {}
    for slot, b in enumerate(vis_brain):
        mi = int(pos_index[b])
        vis_x.append(round(float(norm[mi, 0]), 4))
        vis_y.append(round(float(norm[mi, 1]), 4))
        vis_z.append(round(float(norm[mi, 2]), 4))
        vis_kind.append(int(kind_of[int(b)]))
        vis_id.append(int(b))
        brain_to_vis[int(b)] = slot

    edges = []
    indptr, indices = brain.indptr, brain.indices
    for pre, slot in brain_to_vis.items():
        a, b = int(indptr[pre]), int(indptr[pre + 1])
        found = 0
        for e in range(a, b):
            post = int(indices[e])
            dst = brain_to_vis.get(post)
            if dst is None or dst == slot:
                continue
            edges.append([slot, dst])
            found += 1
            if found >= 2:
                break
        if len(edges) >= C.GRAPH_EDGES:
            break

    g = 16
    cell = np.clip(((norm + 0.5) * g).astype(np.int32), 0, g - 1)
    counts = np.zeros((g, g, g), np.int32)
    for ix, iy, iz in cell:
        counts[ix, iy, iz] += 1
    nz = counts[counts > 0]
    thresh = max(2, int(np.percentile(nz, 25))) if len(nz) else 2
    density = []
    for ix in range(g):
        for iy in range(g):
            for iz in range(g):
                n = int(counts[ix, iy, iz])
                if n >= thresh:
                    density.append([
                        round((ix + 0.5) / g - 0.5, 4),
                        round((iy + 0.5) / g - 0.5, 4),
                        round((iz + 0.5) / g - 0.5, 4),
                        n,
                    ])

    def kind_centroid(k):
        xs = [vis_x[i] for i, kk in enumerate(vis_kind) if kk == k]
        ys = [vis_y[i] for i, kk in enumerate(vis_kind) if kk == k]
        zs = [vis_z[i] for i, kk in enumerate(vis_kind) if kk == k]
        return _centroid3(xs, ys, zs)

    labels = [
        {"id": "lc10a", "title": "LC10a", "role": "SENSORY", "kind": KIND["lc10a"],
         "x": kind_centroid(KIND["lc10a"])[0], "y": kind_centroid(KIND["lc10a"])[1], "z": kind_centroid(KIND["lc10a"])[2]},
        {"id": "lplc1", "title": "LPLC1", "role": "SENSORY", "kind": KIND["lplc1"],
         "x": kind_centroid(KIND["lplc1"])[0], "y": kind_centroid(KIND["lplc1"])[1], "z": kind_centroid(KIND["lplc1"])[2]},
        {"id": "loom", "title": "LC4 / LPLC2", "role": "SENSORY", "kind": KIND["loom"],
         "x": kind_centroid(KIND["loom"])[0], "y": kind_centroid(KIND["loom"])[1], "z": kind_centroid(KIND["loom"])[2]},
        {"id": "steer", "title": "DNa02", "role": "DESCENDING", "kind": KIND["steer"],
         "x": kind_centroid(KIND["steer"])[0], "y": kind_centroid(KIND["steer"])[1], "z": kind_centroid(KIND["steer"])[2]},
        {"id": "commit", "title": "DNp01 / DNg100", "role": "DESCENDING", "kind": KIND["commit"],
         "x": kind_centroid(KIND["commit"])[0], "y": kind_centroid(KIND["commit"])[1], "z": kind_centroid(KIND["commit"])[2]},
        {"id": "reject", "title": "MDN", "role": "DESCENDING", "kind": KIND["reject"],
         "x": kind_centroid(KIND["reject"])[0], "y": kind_centroid(KIND["reject"])[1], "z": kind_centroid(KIND["reject"])[2]},
    ]

    return {
        "neurons": int(brain.n),
        "connections": int(len(brain.indices)),
        "mapped": int(ok.sum()),
        "vis": {
            "x": vis_x, "y": vis_y, "z": vis_z, "kind": vis_kind, "id": vis_id,
            "edges": edges, "density": density,
        },
        "labels": labels,
        "pos_index": pos_index,
        "brain_to_vis": brain_to_vis,
        "spatial": True,
        "morphology": False,
    }


class FlyCoderExperiment:
    def __init__(self, device: str | None = None, seed: int = C.SEED):
        self.device = device or C.DEVICE
        self.seed = int(seed)
        self.env = CoderEnv()
        self.selector = ActionSelector()
        self.brain = None
        self.encoder = None
        self.decoder = None
        self.static = None
        self.pos_index = None
        self.brain_to_vis: dict[int, int] = {}
        self.rng = np.random.default_rng(0)

        self.lock = threading.Lock()
        self.ready = False
        self.running = False
        self.speed = 1
        self.cinematic = True
        self.load_error: str | None = None
        self.attempts = 0
        self.cumulative_reward = 0.0
        self.started_at: float | None = None
        self.elapsed = 0.0
        self._elapsed_anchor: float | None = None
        self.step_ms = 0.0
        self.frame_spikes = np.empty(0, np.int64)
        self.last_spikes_total = 0
        self.last_drive: dict[str, float] = {}
        self.last_signals = {"left": 0.0, "right": 0.0, "commit": 0.0, "reject": 0.0}
        self.last_source = "none"
        self.typed_line = ""
        self.last_action: str | None = None
        self.stage = "OBSERVE"
        self.pulse: str | None = None
        self.best_error = 0.0
        self.reward_history: deque[float] = deque(maxlen=C.REWARD_HISTORY)
        self.events: deque[dict] = deque(maxlen=C.TELEMETRY_EVENTS)
        self.telemetry: deque[str] = deque(maxlen=C.TELEMETRY_LINES)
        self.finished = False
        self.finish_stats: dict | None = None
        self.sim_finished = False
        self.show_overlay = False
        self.success_banner = False
        self.present_epoch = 0
        self.layout_note = ""
        self.eval_note = ""
        self.cursor_from = 0
        self.present_kind = "OBSERVE"
        self.control_mode = "SCANNING"
        self.timeline: list[dict] = []
        self.event_id = 0
        self.last_event: dict | None = None
        self._seq = 0
        self._payload: dict | None = None
        self.cond = threading.Condition()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def log(self, line: str) -> None:
        self.telemetry.appendleft(line)

    def emit(self, kind: str, msg: str) -> None:
        now = datetime.now()
        stamp = now.strftime("%H:%M:%S.") + f"{int(now.microsecond / 1000):03d}"
        self.events.appendleft({"t": stamp, "kind": kind, "msg": msg})
        self.log(f"{stamp}  {kind}  {msg}")

    def load(self) -> None:
        print("loading connectome...", flush=True)
        try:
            brain = FlyBrain(device=self.device, seed=self.seed)
        except Exception as e:
            self.load_error = str(e)
            print(f"FlyCoder: failed to load FlyBrain: {e}", flush=True)
            self._publish()
            return
        self.brain = brain
        self.encoder = CoderEncoder(brain)
        self.decoder = DescendingDecoder(brain)
        raw = neuron_map(brain)
        self.pos_index = raw.pop("pos_index", None)
        self.brain_to_vis = raw.pop("brain_to_vis", {})
        self.static = raw
        self._warmup()
        self.ready = True
        self.best_error = self.env.distance_from_center
        self.emit("BRAIN", f"connectome online  {brain.n:,} neurons  {len(brain.indices):,} connections")
        print(
            f"brain ready: {brain.n:,} neurons, {len(brain.indices):,} connections on {brain.device}",
            flush=True,
        )
        self._publish()

    def _warmup(self) -> None:
        assert self.brain is not None and self.decoder is not None
        for _ in range(C.WARMUP_STEPS):
            fired = self.brain.step()
            self.decoder.observe(fired)
        self.decoder.reset()

    def reset(self, seed: int | None = None) -> None:
        with self.lock:
            self.running = False
            if seed is not None:
                self.seed = int(seed)
            self.env.reset()
            self.selector.reset()
            if self.brain is not None:
                self.brain.reset(self.seed)
                self.decoder.reset()
                self._warmup()
            self.attempts = 0
            self.cumulative_reward = 0.0
            self.started_at = None
            self.elapsed = 0.0
            self._elapsed_anchor = None
            self.finished = False
            self.finish_stats = None
            self.sim_finished = False
            self.show_overlay = False
            self.success_banner = False
            self.present_epoch += 1
            self.layout_note = ""
            self.eval_note = ""
            self.cursor_from = 0
            self.present_kind = "OBSERVE"
            self.control_mode = "SCANNING"
            self.timeline = []
            self.event_id = 0
            self.last_event = None
            self.typed_line = ""
            self.last_action = None
            self.last_source = "none"
            self.stage = "OBSERVE"
            self.pulse = None
            self.frame_spikes = np.empty(0, np.int64)
            self.last_spikes_total = 0
            self.reward_history.clear()
            self.events.clear()
            self.telemetry.clear()
            self.best_error = self.env.distance_from_center
            if self.brain is not None:
                self.emit("BRAIN", f"reset  seed={self.seed}  warmup steps={self.brain.steps}")
            self._publish()

    def start(self) -> None:
        with self.lock:
            if not self.ready or self.finished:
                return
            if not self.running:
                self.running = True
                now = time.time()
                if self.started_at is None:
                    self.started_at = now
                self._elapsed_anchor = now
                self.emit("BRAIN", "experiment start")
                self._publish()

    def pause(self) -> None:
        with self.lock:
            if self.running:
                self._accrue_elapsed()
                self.running = False
                self._elapsed_anchor = None
                self.emit("BRAIN", "pause")
                if self.sim_finished:
                    self.finished = True
                    self.show_overlay = True
                    self.success_banner = False
                    self.control_mode = "EXPERIMENT COMPLETE"
                self._publish()

    def set_speed(self, speed: int) -> None:
        with self.lock:
            self.speed = int(speed) if int(speed) in (1, 2, 4) else 1
            self._publish()

    def set_cinematic(self, on: bool) -> None:
        with self.lock:
            self.cinematic = bool(on)
            if not self.cinematic and self.sim_finished:
                self.finished = True
                self.show_overlay = True
                self.success_banner = False
                self.running = False
            self._publish()

    def _accrue_elapsed(self) -> None:
        if self._elapsed_anchor is not None:
            self.elapsed += time.time() - self._elapsed_anchor
            self._elapsed_anchor = time.time()

    def _sim_elapsed(self) -> float:
        if self.brain is None:
            return 0.0
        return max(0.0, (self.brain.steps - C.WARMUP_STEPS) * self.brain.dt)

    def _mark_event(self, kind: str, **extra) -> None:
        self.event_id += 1
        self.last_event = {"id": self.event_id, "kind": kind, **extra}

    def _group_mean(self, *names: str) -> float:
        if self.decoder is None:
            return 0.0
        counts = self.decoder.snapshot()
        total = 0.0
        n = 0
        for g in names:
            total += float(counts.get(g, 0.0))
            n += int(self.decoder.sizes.get(g, 1))
        return total / max(n, 1)

    def _clip01(self, v: float) -> float:
        return float(max(0.0, min(1.0, v)))

    def _control_label(self, mode: str, left: float, right: float) -> str:
        if mode == "STEERING RIGHT":
            return "MOVE RIGHT"
        if mode == "STEERING LEFT":
            return "MOVE LEFT"
        if mode == "COMMITTING":
            return "CONTROL COMMIT"
        if mode == "REJECTING":
            return "REJECT / BACK"
        if mode == "EVALUATING RESULT":
            return "EVALUATE"
        if mode in ("TARGET CENTERED", "EXPERIMENT COMPLETE"):
            return mode
        if right > left:
            return "SCANNING"
        return "SCANNING"

    def _refresh_control(self, action: str | None = None) -> None:
        left = float(self.last_signals.get("left") or 0)
        right = float(self.last_signals.get("right") or 0)
        commit = float(self.last_signals.get("commit") or 0)
        reject = float(self.last_signals.get("reject") or 0)
        if self.finished:
            self.control_mode = "EXPERIMENT COMPLETE"
        elif self.sim_finished:
            self.control_mode = "TARGET CENTERED"
        elif action == "DELETE_LAST" or (reject >= C.REJECT_THRESHOLD and reject >= commit):
            self.control_mode = "REJECTING"
        elif action is not None or commit >= C.COMMIT_THRESHOLD:
            self.control_mode = "COMMITTING"
        elif right > left + C.STEER_MARGIN:
            self.control_mode = "STEERING RIGHT"
        elif left > right + C.STEER_MARGIN:
            self.control_mode = "STEERING LEFT"
        elif self.eval_note:
            self.control_mode = "EVALUATING RESULT"
        else:
            self.control_mode = "SCANNING"

    def _channels(self) -> dict:
        drive = self.last_drive or {}
        sensory = {
            "lc10aL": round(float(drive.get("lc10aL") or 0), 4),
            "lc10aR": round(float(drive.get("lc10aR") or 0), 4),
            "lplc1L": round(float(drive.get("lplc1L") or 0), 4),
            "lplc1R": round(float(drive.get("lplc1R") or 0), 4),
            "lc4": round(max(float(drive.get("lc4L") or 0), float(drive.get("lc4R") or 0)), 4),
            "lplc2": round(max(float(drive.get("lplc2L") or 0), float(drive.get("lplc2R") or 0)), 4),
            "error": round(float(drive.get("ERROR_MAGNITUDE") or 0), 4),
        }
        sensory_norm = {k: round(self._clip01(v / C.ENCODER_CAP), 3) for k, v in sensory.items()}
        dna02_l = round(self._group_mean("steer_L"), 4) if self.decoder else round(float(self.last_signals.get("left") or 0), 4)
        dna02_r = round(self._group_mean("steer_R"), 4) if self.decoder else round(float(self.last_signals.get("right") or 0), 4)
        dnp01 = round(self._group_mean("escape_L", "escape_R"), 4)
        dng100 = round(self._group_mean("forward_L", "forward_R"), 4)
        mdn = round(self._group_mean("backward_L", "backward_R"), 4)
        descending = {
            "dna02L": dna02_l,
            "dna02R": dna02_r,
            "dnp01": dnp01,
            "dng100": dng100,
            "mdn": mdn,
        }
        descending_norm = {
            "dna02L": round(self._clip01(dna02_l / 0.55), 3),
            "dna02R": round(self._clip01(dna02_r / 0.55), 3),
            "dnp01": round(self._clip01(dnp01 / 0.45), 3),
            "dng100": round(self._clip01(dng100 / 0.45), 3),
            "mdn": round(self._clip01(mdn / 0.80), 3),
        }
        left = float(self.last_signals.get("left") or 0)
        right = float(self.last_signals.get("right") or 0)
        steer = max(-1.0, min(1.0, (right - left) / 0.40))
        control = {
            "left": round(left, 4),
            "right": round(right, 4),
            "commit": round(float(self.last_signals.get("commit") or 0), 4),
            "reject": round(float(self.last_signals.get("reject") or 0), 4),
            "steer": round(steer, 4),
            "mode": self.control_mode,
            "label": self._control_label(self.control_mode, left, right),
        }
        return {
            "sensory": sensory,
            "sensory_norm": sensory_norm,
            "descending": descending,
            "descending_norm": descending_norm,
            "control": control,
        }

    def _live_snapshot(self) -> dict:
        env = self.env.to_dict()
        brain_steps = int(self.brain.steps) if self.brain is not None else 0
        vis_spikes = []
        if self.brain_to_vis and len(self.frame_spikes):
            for i in self.frame_spikes:
                slot = self.brain_to_vis.get(int(i))
                if slot is not None:
                    vis_spikes.append(slot)
            if len(vis_spikes) > C.MAX_SPIKES:
                vis_spikes = self.rng.choice(vis_spikes, C.MAX_SPIKES, replace=False).tolist()
        sim_hz = 0.0
        if self.step_ms > 0:
            sim_hz = round(C.BRAIN_STEPS_PER_ACTION * 1000.0 / self.step_ms, 1)
        mapped = 0
        if self.static is not None:
            mapped = int(self.static.get("mapped") or 0)
        sim_elapsed = self._sim_elapsed()
        present_elapsed = self.elapsed
        if self.running and self._elapsed_anchor is not None:
            present_elapsed += time.time() - self._elapsed_anchor
        return {
            "ready": self.ready,
            "running": self.running,
            "finished": self.finished,
            "show_overlay": self.show_overlay,
            "sim_finished": self.sim_finished,
            "speed": self.speed,
            "cinematic": self.cinematic,
            "load_error": self.load_error,
            "neurons": int(self.brain.n) if self.brain is not None else C.SOURCE_NEURONS,
            "connections": int(len(self.brain.indices)) if self.brain is not None else C.SOURCE_CONNECTIONS,
            "mapped": mapped,
            "malecns": C.MALECNS_VERSION,
            "device": None if self.brain is None else self.brain.device,
            "weights": "FROZEN",
            "mapping": "EXPERIMENTAL",
            "brain_steps": brain_steps,
            "active": self.last_spikes_total,
            "vis_spikes": vis_spikes,
            "ms": round(self.step_ms, 1),
            "sim_hz": sim_hz,
            "env": env,
            "actions": list(C.ACTIONS),
            "cursor": self.selector.cursor,
            "cursor_from": self.cursor_from,
            "highlighted": C.ACTIONS[self.selector.cursor],
            "q": [round(float(x), 3) for x in self.selector.q],
            "typed_line": self.typed_line,
            "last_action": self.last_action,
            "drive": {k: round(float(v), 3) for k, v in self.last_drive.items()},
            "signals": self.last_signals,
            "counts": self.decoder.snapshot() if self.decoder is not None else {},
            "source": self.last_source,
            "stage": self.stage,
            "pulse": self.pulse,
            "present_kind": self.present_kind,
            "layout_note": self.layout_note,
            "eval_note": self.eval_note,
            "attempts": self.attempts,
            "cumulative_reward": round(self.cumulative_reward, 4),
            "reward_history": [round(x, 4) for x in self.reward_history],
            "best_error": round(self.best_error, 1),
            "elapsed": round(sim_elapsed, 2),
            "present_elapsed": round(present_elapsed, 2),
            "events": list(self.events),
            "telemetry": list(self.telemetry),
            "finish": self.finish_stats,
            "success_banner": self.success_banner,
            "control_mode": self.control_mode,
            "timeline": list(self.timeline),
            "discrete": self.last_event,
            "event_id": self.event_id,
            "selector": {
                "index": self.selector.cursor,
                "action": C.ACTIONS[self.selector.cursor],
                "from": self.cursor_from,
            },
            **self._channels(),
        }

    def _beat(self, kind: str, stage: str | None = None, pulse: str | None = False, action: str | None = None) -> None:
        """Publish live dashboard state. Never sleeps; the browser interpolates."""
        self.present_kind = kind
        if stage is not None:
            self.stage = stage
        if pulse is not False:
            self.pulse = pulse
        self._refresh_control(action)
        self._publish()

    def _present_wait(self, lo: int, hi: int, epoch: int) -> bool:
        """Readable gap between real cycles. Dashboard keeps interpolating last spikes."""
        ms = int(self.rng.integers(lo, hi + 1))
        end = time.time() + (ms / 1000.0) / max(self.speed, 1)
        last_pub = 0.0
        while time.time() < end:
            if self._stop.is_set() or not self.running or epoch != self.present_epoch:
                return False
            now = time.time()
            if now - last_pub > 0.22:
                self._publish()
                last_pub = now
            time.sleep(0.03)
        return epoch == self.present_epoch and self.running

    def cycle(self) -> dict:
        """One observation: encode → BRAIN_STEPS_PER_ACTION → decode → maybe act."""
        assert self.brain is not None and self.encoder is not None and self.decoder is not None
        env_state = self.env.state()
        self.pulse = None
        self.layout_note = ""
        self.eval_note = ""
        prev_hx, prev_hy = env_state.horizontal_error, env_state.vertical_error

        self.present_kind = "OBSERVE"
        self.stage = "OBSERVE"
        hx, hy = env_state.horizontal_error, env_state.vertical_error
        htxt = "left" if hx < -C.CENTER_TOLERANCE_PX else ("right" if hx > C.CENTER_TOLERANCE_PX else "x centered")
        vtxt = "above" if hy < -C.CENTER_TOLERANCE_PX else ("below" if hy > C.CENTER_TOLERANCE_PX else "y centered")
        self.emit("OBSERVATION", f"target {htxt} / {vtxt}  err {env_state.distance_from_center:.0f} px")
        self._beat("OBSERVE", stage="OBSERVE", pulse=None)

        encoded = self.encoder.encode(env_state)
        self.last_drive = encoded.drive
        bits = []
        if encoded.drive.get("TARGET_LEFT"):
            bits.append("LC10a-L ↑")
        if encoded.drive.get("TARGET_RIGHT"):
            bits.append("LC10a-R ↑")
        if encoded.drive.get("TARGET_UP"):
            bits.append("LPLC1-L ↑")
        if encoded.drive.get("TARGET_DOWN"):
            bits.append("LPLC1-R ↑")
        if encoded.drive.get("ERROR_MAGNITUDE", 0) > 0.02:
            bits.append("LC4/LPLC2 ↑")
        self.emit("INPUT", "  ".join(bits) if bits else "weak bilateral hold")
        self._beat("INPUT", stage="STIMULATE", pulse="stimulus")

        t0 = time.perf_counter()
        fired_parts = []
        self.decoder.reset()
        for _ in range(C.BRAIN_STEPS_PER_ACTION):
            fired = self.brain.step(inject=encoded.inject)
            self.decoder.observe(fired)
            fired_parts.append(fired)
        self.step_ms = 0.9 * self.step_ms + 0.1 * (time.perf_counter() - t0) * 1000
        self.frame_spikes = (
            np.unique(np.concatenate(fired_parts)) if fired_parts else np.empty(0, np.int64)
        )
        self.last_spikes_total = int(len(self.frame_spikes))
        self.emit("BRAIN", f"step {self.brain.steps:05d} / active {self.last_spikes_total:,}")
        self._beat("PROPAGATE", stage="PROPAGATE", pulse="stimulus")

        signals = self.decoder.signals()
        self.last_signals = {
            "left": round(signals.left, 4),
            "right": round(signals.right, 4),
            "commit": round(signals.commit, 4),
            "reject": round(signals.reject, 4),
        }
        if signals.left > signals.right + C.STEER_MARGIN:
            self.emit("READOUT", "DNa02-L > DNa02-R")
        elif signals.right > signals.left + C.STEER_MARGIN:
            self.emit("READOUT", "DNa02-R > DNa02-L")
        else:
            self.emit("READOUT", "DNa02 laterality tied")
        if signals.commit >= C.COMMIT_THRESHOLD:
            self.emit("READOUT", "DNp01 / DNg100 commit threshold")
        if signals.reject >= C.REJECT_THRESHOLD:
            self.emit("READOUT", "MDN reject threshold")
        self._beat("READOUT", stage="READOUT", pulse=None)

        cursor_before = self.selector.cursor
        decision = self.selector.decide(signals)
        self.cursor_from = cursor_before
        self.last_source = decision.source
        for line in decision.events:
            self.emit("CONTROL", line)
        if decision.cursor != cursor_before:
            self._mark_event("CURSOR", from_index=cursor_before, to_index=decision.cursor)
            self._beat("CURSOR_MOVE", stage="ACTION", pulse=None)

        self.last_action = decision.action
        if decision.action == "DELETE_LAST" or decision.source == "reject":
            commit_pulse = "reject"
        elif decision.action is not None:
            commit_pulse = "commit"
        else:
            commit_pulse = None

        if decision.action is not None:
            self._mark_event("ACTION_COMMITTED", action=decision.action, source=decision.source)
            self._beat("COMMIT", stage="ACTION", pulse=commit_pulse, action=decision.action)
            state = self.env.apply(decision.action)
            self.attempts += 1
            self.cumulative_reward += state.reward
            self.selector.update_reward(decision.action, state.reward)
            self.typed_line = ACTION_LABELS.get(decision.action, decision.action)
            self.emit("ACTION", self.typed_line)
            if decision.action == "DISPLAY_FLEX":
                self.layout_note = "FLEX LAYOUT ACTIVE"
                self.emit("CONTROL", "CONTROL STRATEGY CHANGED")
                self.emit("CONTROL", "FLEX LAYOUT ACTIVE")
            self.best_error = min(self.best_error, state.distance_from_center)
            self.reward_history.append(float(state.reward))
            self.timeline.append({
                "n": self.attempts,
                "action": decision.action,
                "label": ACTION_SHORT.get(decision.action, decision.action),
                "css": self.typed_line,
                "reward": round(float(state.reward), 3),
            })
            self._mark_event("CSS_CHANGED", action=decision.action, css=self.typed_line)
            self._beat("ACTION", stage="ACTION", pulse=commit_pulse, action=decision.action)

            dx = abs(state.horizontal_error) - abs(prev_hx)
            dy = abs(state.vertical_error) - abs(prev_hy)
            xpart = "X improved" if dx < -1 else ("X worse" if dx > 1 else "X unchanged")
            ypart = "Y improved" if dy < -1 else ("Y worse" if dy > 1 else "Y unchanged")
            self.eval_note = f"{xpart} · {ypart}"
            self.emit("EVALUATE", self.eval_note)
            reward_pulse = "reward" if state.reward > 0.2 else commit_pulse
            self._beat("EVALUATE", stage="EVALUATE", pulse=reward_pulse, action=decision.action)
            self.emit("REWARD", f"{state.reward:+.3f}  dist {state.distance_from_center:.0f} px")
            self._mark_event("REWARD", action=decision.action, reward=round(float(state.reward), 4))
            if self.attempts % 7 == 0 and not state.centered:
                self.emit("HUMOR", HUMOR[(self.attempts // 7 - 1) % len(HUMOR)])
            self._beat("REWARD", stage="EVALUATE", pulse=reward_pulse, action=decision.action)
            if state.centered:
                self._finish()
        else:
            self.typed_line = ""
            self.stage = "EVALUATE"
            self.emit("REWARD", "no commit this observation")
            self._beat("EVALUATE", stage="EVALUATE", pulse=None)

        self._publish()
        return self.snapshot()

    def _finish(self) -> None:
        self._accrue_elapsed()
        self.sim_finished = True
        self.success_banner = True
        self.pulse = "success"
        self.stage = "EVALUATE"
        self.control_mode = "TARGET CENTERED"
        sim_elapsed = self._sim_elapsed()
        self.finish_stats = {
            "attempts": self.attempts,
            "brain_steps": int(self.brain.steps) if self.brain is not None else 0,
            "elapsed": round(sim_elapsed, 2),
            "final_reward": round(self.cumulative_reward, 4),
            "best_error": round(self.best_error, 2),
        }
        self.emit("SUCCESS", "TARGET CENTERED")
        self.emit("REWARD", f"REWARD {self.cumulative_reward:+.3f}")
        self.emit("SUCCESS", "EXPERIMENT COMPLETE")
        self._mark_event("SUCCESS", reward=round(self.cumulative_reward, 4))
        self._beat("SUCCESS", stage="EVALUATE", pulse="success")
        if not self.cinematic:
            self.running = False
            self.finished = True
            self.show_overlay = True
            self.success_banner = False
            self.control_mode = "EXPERIMENT COMPLETE"
            self._publish()

    def snapshot(self) -> dict:
        return self._live_snapshot()

    def _publish(self) -> None:
        payload = self.snapshot()
        with self.cond:
            self._payload = payload
            self._seq += 1
            self.cond.notify_all()

    def wait_payload(self, seen: int, timeout: float = 15.0) -> tuple[int, dict | None, bool]:
        with self.cond:
            fresh = self.cond.wait_for(lambda: self._seq != seen, timeout=timeout)
            return self._seq, self._payload, fresh

    def loop_forever(self) -> None:
        while not self._stop.is_set():
            epoch = self.present_epoch
            if self.running and not self.sim_finished and self.ready:
                self.cycle()
                if self.cinematic and self.running and not self.sim_finished and epoch == self.present_epoch:
                    self._present_wait(*C.CYCLE_PRESENT_MS, epoch)
                elif not self.cinematic and self.running and not self.sim_finished:
                    delay = max(
                        0.0,
                        (C.DT * C.BRAIN_STEPS_PER_ACTION) / max(self.speed, 1) - self.step_ms / 1000.0,
                    )
                    if delay > 0:
                        time.sleep(delay)
                continue
            if self.running and self.sim_finished:
                hold = C.SUCCESS_HOLD_MS if self.cinematic else (350, 450)
                self._present_wait(*hold, epoch)
                if epoch != self.present_epoch:
                    continue
                self.running = False
                self.finished = True
                self.show_overlay = True
                self.success_banner = False
                self.control_mode = "EXPERIMENT COMPLETE"
                self._publish()
                continue
            time.sleep(0.05)

    def spawn(self) -> None:
        self._thread = threading.Thread(target=self.loop_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()


def run_headless(max_cycles: int = 400, seed: int = C.SEED, device: str | None = None) -> dict:
    """Run until the div is centered or `max_cycles` actions, no dashboard."""
    exp = FlyCoderExperiment(device=device, seed=seed)
    exp.load()
    exp.cinematic = False
    exp.running = True
    exp.started_at = time.time()
    exp._elapsed_anchor = exp.started_at
    cycles = 0
    while cycles < max_cycles and not exp.env.centered:
        exp.cycle()
        cycles += 1
    snap = exp.snapshot()
    snap["cycles"] = cycles
    return snap
