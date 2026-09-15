"""Descending-neuron activity → FlyCoder control channels.

EXPERIMENTAL INTERFACE. The populations are real MaleCNS descending neurons
exposed as `FlyBrain.groups` (built in flybrain/build.py MOTOR_TYPES):

    steer    DNa02     walking-steering command neurons
    escape   DNp01     giant fiber (escape take-off)
    forward  DNg100    forward walking
    backward MDN       moonwalker (backward walking)

They are used as *control channels into an action-selection UI*, not as
CSS vocabulary:

    DNa02 L vs R  → move the action cursor left / right
    DNp01 + DNg100 → COMMIT (execute the highlighted action)
    MDN            → REJECT (delete / escape)

This is the same readout style as sshfighter/fly_fighter.py Decoder:
count spikes of identified groups over a short window. Nothing here writes
connectome weights, and nothing claims "DNa02 means display:flex".
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

from . import config as C

# Control-channel map: FlyCoder signal → brain.groups keys → cell types.
CONTROL_CHANNELS = {
    "left": {
        "groups": ("steer_L",),
        "types": ["DNa02"],
        "role": "cursor left (steering laterality)",
    },
    "right": {
        "groups": ("steer_R",),
        "types": ["DNa02"],
        "role": "cursor right (steering laterality)",
    },
    "commit": {
        "groups": ("escape_L", "escape_R", "forward_L", "forward_R"),
        "types": ["DNp01", "DNg100"],
        "role": "execute highlighted action (escape + forward walking)",
    },
    "reject": {
        "groups": ("backward_L", "backward_R"),
        "types": ["MDN"],
        "role": "delete last / reject (moonwalker / backward walking)",
    },
}


@dataclass
class ControlSignals:
    left: float
    right: float
    commit: float
    reject: float
    counts: dict[str, float]
    events: list[str]


class DescendingDecoder:
    """Observe `brain.step()` spike indices and read DN control channels."""

    def __init__(self, brain):
        groups = brain.groups
        missing = [g for ch in CONTROL_CHANNELS.values() for g in ch["groups"] if g not in groups]
        if missing:
            raise RuntimeError(f"brain.groups missing descending populations: {missing}")
        empty = [g for g, idx in groups.items() if g in {x for ch in CONTROL_CHANNELS.values() for x in ch["groups"]} and len(idx) == 0]
        if empty:
            raise RuntimeError(f"descending groups resolved to zero neurons: {empty}")
        self.names = list(groups)
        self.col = {g: i for i, g in enumerate(self.names)}
        self.groups = groups
        self.sizes = {g: max(len(idx), 1) for g, idx in groups.items()}
        self.history: deque[np.ndarray] = deque(maxlen=C.BRAIN_STEPS_PER_ACTION)
        self.mask = np.zeros(brain.n, dtype=bool)

    def reset(self) -> None:
        self.history.clear()

    def observe(self, fired: np.ndarray) -> None:
        self.mask[:] = False
        if len(fired):
            self.mask[fired] = True
        counts = np.zeros(len(self.names), dtype=np.float32)
        for g, idx in self.groups.items():
            counts[self.col[g]] = float(self.mask[idx].sum())
        self.history.append(counts)

    def _mean(self, *group_names: str) -> float:
        """Mean spikes per neuron over the current window."""
        if not self.history:
            return 0.0
        recent = np.sum(list(self.history), axis=0)
        total = 0.0
        n = 0
        for g in group_names:
            total += float(recent[self.col[g]])
            n += self.sizes[g]
        return total / max(n, 1)

    def snapshot(self) -> dict[str, float]:
        if not self.history:
            return {g: 0.0 for g in self.names}
        recent = np.sum(list(self.history), axis=0)
        return {g: float(recent[self.col[g]]) for g in self.names}

    def signals(self) -> ControlSignals:
        left = self._mean(*CONTROL_CHANNELS["left"]["groups"])
        right = self._mean(*CONTROL_CHANNELS["right"]["groups"])
        commit = self._mean(*CONTROL_CHANNELS["commit"]["groups"])
        reject = self._mean(*CONTROL_CHANNELS["reject"]["groups"])
        events = []
        if left > right + C.STEER_MARGIN:
            events.append("descending laterality → LEFT")
        elif right > left + C.STEER_MARGIN:
            events.append("descending laterality → RIGHT")
        if commit >= C.COMMIT_THRESHOLD:
            events.append("descending activity detected (COMMIT channel)")
        if reject >= C.REJECT_THRESHOLD:
            events.append("descending activity detected (REJECT channel)")
        return ControlSignals(
            left=left, right=right, commit=commit, reject=reject,
            counts=self.snapshot(), events=events,
        )
