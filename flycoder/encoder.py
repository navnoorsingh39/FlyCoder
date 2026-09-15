"""Webpage state → voltage on real MaleCNS visual projection neurons.

EXPERIMENTAL INTERFACE. The neuron types are real (LC4, LPLC2, LPLC1, LC10a)
and are the same populations `flybrain.eyes.FeatureDetectors` drives for SSH
Fighter. The assignment of CSS geometry onto those types is ours: it does not
claim that a fly sees a div.

Mapping
-------
TARGET_LEFT     horizontal error < 0 (square left of center)
                → LC10a left   (courtship-tracking / chase, ipsilateral)

TARGET_RIGHT    horizontal error > 0
                → LC10a right

TARGET_UP       vertical error < 0 (square above center)
                → LPLC1 left   (small approaching objects; experimental vertical channel)

TARGET_DOWN     vertical error > 0
                → LPLC1 right

CENTERED_X      |horizontal error| ≤ tolerance
                → weak bilateral LC10a (cancels laterality when X is solved)

CENTERED_Y      |vertical error| ≤ tolerance
                → weak bilateral LPLC1

ERROR_MAGNITUDE distance from center, 0..1
                → LC4 + LPLC2 both sides (looming / fast-looming, intensity)

PREVIOUS_REWARD used on the experiment side (selector). A negative reward also
                adds a little extra LC4 drive so a setback reads as "more loom".
                Positive reward is not injected into unnamed neurons.

All drive is passed to FlyBrain.step(inject=[(indices, amount), ...]).
Connectome weights are never written.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import config as C
from .coder_env import EnvState

# Documented sensory map: FlyCoder signal → MaleCNS cell types + side.
SENSORY_MAP = {
    "TARGET_LEFT": {"types": ["LC10a"], "side": "L",
                    "role": "chase / courtship tracking, left visual field"},
    "TARGET_RIGHT": {"types": ["LC10a"], "side": "R",
                     "role": "chase / courtship tracking, right visual field"},
    "TARGET_UP": {"types": ["LPLC1"], "side": "L",
                  "role": "experimental vertical channel (small-object detectors, left)"},
    "TARGET_DOWN": {"types": ["LPLC1"], "side": "R",
                    "role": "experimental vertical channel (small-object detectors, right)"},
    "CENTERED_X": {"types": ["LC10a"], "side": None,
                   "role": "weak bilateral chase when X is already centered"},
    "CENTERED_Y": {"types": ["LPLC1"], "side": None,
                   "role": "weak bilateral small-object drive when Y is already centered"},
    "ERROR_MAGNITUDE": {"types": ["LC4", "LPLC2"], "side": None,
                        "role": "looming intensity from distance-to-center"},
    "PREVIOUS_REWARD": {"types": ["LC4"], "side": None,
                        "role": "experimental: extra looming after a negative reward"},
}


def _clip(v: float, cap: float = C.ENCODER_CAP) -> float:
    return float(np.clip(v, 0.0, cap))


@dataclass
class Encoded:
    inject: list[tuple[np.ndarray, float]]
    drive: dict[str, float]
    events: list[str]


class CoderEncoder:
    """Build (neuron-index, voltage) pairs from an EnvState, using brain.cells()."""

    def __init__(self, brain):
        self.brain = brain
        self.cells = {
            "LC10a": {s: brain.cells(["LC10a"], s) for s in "LR"},
            "LPLC1": {s: brain.cells(["LPLC1"], s) for s in "LR"},
            "LC4": {s: brain.cells(["LC4"], s) for s in "LR"},
            "LPLC2": {s: brain.cells(["LPLC2"], s) for s in "LR"},
        }
        missing = [f"{t}{s}" for t, sides in self.cells.items() for s, idx in sides.items() if len(idx) == 0]
        if missing:
            raise RuntimeError(f"MaleCNS annotations missing expected visual types: {missing}")

    def encode(self, state: EnvState) -> Encoded:
        drive = {k: 0.0 for k in (
            "lc10aL", "lc10aR", "lplc1L", "lplc1R", "lc4L", "lc4R", "lplc2L", "lplc2R",
            "TARGET_LEFT", "TARGET_RIGHT", "TARGET_UP", "TARGET_DOWN",
            "CENTERED_X", "CENTERED_Y", "ERROR_MAGNITUDE", "PREVIOUS_REWARD",
        )}
        events: list[str] = []
        inject: list[tuple[np.ndarray, float]] = []

        hx = max(state.viewport_width / 2.0, 1.0)
        hy = max(state.viewport_height / 2.0, 1.0)
        mag = float(np.clip(state.distance_from_center / max(state.max_distance, 1.0), 0.0, 1.0))
        tol = C.CENTER_TOLERANCE_PX

        # --- horizontal: LC10a laterality (known chase pathway) ---
        if state.horizontal_error < -tol:
            amt = _clip(C.CHASE_BASE + C.CHASE_GAIN * abs(state.horizontal_error) / hx)
            drive["TARGET_LEFT"] = amt
            drive["lc10aL"] = amt
            inject.append((self.cells["LC10a"]["L"], amt))
            events.append("VISUAL STIMULUS → LEFT")
            events.append(f"LC10a L +{amt:.2f} (target left of center)")
        elif state.horizontal_error > tol:
            amt = _clip(C.CHASE_BASE + C.CHASE_GAIN * abs(state.horizontal_error) / hx)
            drive["TARGET_RIGHT"] = amt
            drive["lc10aR"] = amt
            inject.append((self.cells["LC10a"]["R"], amt))
            events.append("VISUAL STIMULUS → RIGHT")
            events.append(f"LC10a R +{amt:.2f} (target right of center)")
        else:
            drive["CENTERED_X"] = C.CENTERED_DRIVE
            drive["lc10aL"] = C.CENTERED_DRIVE
            drive["lc10aR"] = C.CENTERED_DRIVE
            inject.append((self.cells["LC10a"]["L"], C.CENTERED_DRIVE))
            inject.append((self.cells["LC10a"]["R"], C.CENTERED_DRIVE))
            events.append("CENTERED_X → weak bilateral LC10a")

        # --- vertical: LPLC1 laterality (experimental; no up/down in the 1-D eye) ---
        if state.vertical_error < -tol:
            amt = _clip(C.SMALL_OBJECT_GAIN * abs(state.vertical_error) / hy)
            drive["TARGET_UP"] = amt
            drive["lplc1L"] = amt
            inject.append((self.cells["LPLC1"]["L"], amt))
            events.append("VISUAL STIMULUS → UP")
            events.append(f"LPLC1 L +{amt:.2f} (experimental vertical)")
        elif state.vertical_error > tol:
            amt = _clip(C.SMALL_OBJECT_GAIN * abs(state.vertical_error) / hy)
            drive["TARGET_DOWN"] = amt
            drive["lplc1R"] = amt
            inject.append((self.cells["LPLC1"]["R"], amt))
            events.append("VISUAL STIMULUS → DOWN")
            events.append(f"LPLC1 R +{amt:.2f} (experimental vertical)")
        else:
            drive["CENTERED_Y"] = C.CENTERED_DRIVE
            drive["lplc1L"] = C.CENTERED_DRIVE
            drive["lplc1R"] = C.CENTERED_DRIVE
            inject.append((self.cells["LPLC1"]["L"], C.CENTERED_DRIVE))
            inject.append((self.cells["LPLC1"]["R"], C.CENTERED_DRIVE))
            events.append("CENTERED_Y → weak bilateral LPLC1")

        # --- distance: looming detectors, both sides ---
        loom = _clip(C.LOOM_GAIN * mag)
        drive["ERROR_MAGNITUDE"] = loom
        if loom > 0.02:
            for side in "LR":
                drive[f"lc4{side}"] = loom
                drive[f"lplc2{side}"] = loom
                inject.append((self.cells["LC4"][side], loom))
                inject.append((self.cells["LPLC2"][side], loom))
            events.append(f"ERROR_MAGNITUDE → LC4+LPLC2 {loom:.2f}")

        # --- previous reward: experimental extra loom after a setback ---
        # EnvState.reward is the score of the last committed action (0 on the first cycle).
        prev_r = state.reward
        if prev_r < -0.02:
            extra = _clip(abs(prev_r) * C.REWARD_LOOM, cap=0.3)
            drive["PREVIOUS_REWARD"] = -abs(prev_r)
            for side in "LR":
                drive[f"lc4{side}"] = min(C.ENCODER_CAP, drive[f"lc4{side}"] + extra)
                inject.append((self.cells["LC4"][side], extra))
            events.append(f"PREVIOUS_REWARD {prev_r:+.2f} → extra LC4 {extra:.2f}")
        elif prev_r > 0.02:
            drive["PREVIOUS_REWARD"] = prev_r
            events.append(f"PREVIOUS_REWARD {prev_r:+.2f} (selector bias only)")

        return Encoded(inject=inject, drive=drive, events=events)
