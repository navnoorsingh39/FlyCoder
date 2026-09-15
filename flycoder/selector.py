"""Stateful action cursor driven by descending-neuron control channels.

The connectome does not emit CSS tokens. It wiggles an interface:

    neural LEFT   → move action cursor left
    neural RIGHT  → move action cursor right
    neural COMMIT → execute the highlighted action
    neural REJECT → delete last rule (escape)

A lightweight Q table (experimental, outside the brain) tracks which actions
recently reduced distance-to-center. On a neural laterality *tie*, the cursor
takes one step toward an untried action or a higher-Q action. That is a bounded
explore/reward bias so the experiment can finish in a sitting; it is not a
prewritten CSS sequence, and it never runs unless the fly's own DNa02 signals
are tied.

Connectome weights are never updated.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from . import config as C
from .coder_env import ACTION_LABELS
from .decoder import ControlSignals


@dataclass
class Decision:
    action: str | None
    cursor: int
    events: list[str]
    q: list[float]
    source: str           # "neural" | "idle" | "reject" | "none"


class ActionSelector:
    def __init__(self, actions: tuple[str, ...] = C.ACTIONS):
        self.actions = actions
        self.n = len(actions)
        self.cursor = 0
        self.q = np.zeros(self.n, dtype=np.float32)
        self.tried: set[str] = set()
        self.idle_cycles = 0
        self.last_committed: str | None = None
        self.last_reward = 0.0

    def reset(self) -> None:
        self.cursor = 0
        self.q[:] = 0
        self.tried.clear()
        self.idle_cycles = 0
        self.last_committed = None
        self.last_reward = 0.0

    def _step_toward(self, target: int) -> None:
        if target == self.cursor:
            return
        n = self.n
        forward = (target - self.cursor) % n
        back = (self.cursor - target) % n
        self.cursor = (self.cursor + (1 if forward <= back else -1)) % n

    def decide(self, signals: ControlSignals) -> Decision:
        events: list[str] = []
        moved = False

        hold = self.last_reward > 0.02
        if hold:
            events.append("HOLD CURSOR (positive reward, experimental)")
        elif signals.left > signals.right + C.STEER_MARGIN:
            self.cursor = (self.cursor - 1) % self.n
            moved = True
            events.append(f"ACTION CURSOR → {self.actions[self.cursor]}")
        elif signals.right > signals.left + C.STEER_MARGIN:
            self.cursor = (self.cursor + 1) % self.n
            moved = True
            events.append(f"ACTION CURSOR → {self.actions[self.cursor]}")
        elif C.Q_TIE_BIAS:
            untried = [i for i, a in enumerate(self.actions)
                       if a not in self.tried and a not in ("RUN",)]
            if untried:
                self._step_toward(untried[0])
                moved = True
                events.append(f"EXPLORE UNTRIED → {self.actions[self.cursor]} (experimental)")
            elif float(np.max(self.q)) > 0.04:
                self._step_toward(int(np.argmax(self.q)))
                moved = True
                events.append(f"Q-BIAS CURSOR → {self.actions[self.cursor]} (experimental)")

        if not moved:
            events.append(f"ACTION CURSOR → {self.actions[self.cursor]}")

        action = None
        source = "none"
        # Stronger of reject vs commit wins when both fire.
        if signals.reject >= C.REJECT_THRESHOLD and signals.reject >= signals.commit:
            action = "DELETE_LAST"
            source = "reject"
            events.append("REJECT SIGNAL")
            events.append(ACTION_LABELS["DELETE_LAST"])
            self.idle_cycles = 0
        elif signals.commit >= C.COMMIT_THRESHOLD:
            action = self.actions[self.cursor]
            source = "neural"
            events.append("COMMIT SIGNAL")
            events.append(ACTION_LABELS.get(action, action))
            self.idle_cycles = 0
        else:
            self.idle_cycles += 1
            if self.idle_cycles >= C.IDLE_COMMIT_CYCLES:
                action = self.actions[self.cursor]
                source = "idle"
                events.append("IDLE COMMIT (experimental; descending commit channel quiet)")
                events.append(ACTION_LABELS.get(action, action))
                self.idle_cycles = 0

        if action is not None and action not in ("DELETE_LAST", "RUN"):
            self.tried.add(action)
        self.last_committed = action
        return Decision(
            action=action,
            cursor=self.cursor,
            events=events,
            q=[float(x) for x in self.q],
            source=source,
        )

    def update_reward(self, action: str, reward: float) -> None:
        """Experimental readout: EMA of reward per action. Not the connectome."""
        if action not in self.actions:
            return
        i = self.actions.index(action)
        self.q[i] += np.float32(C.Q_LEARNING_RATE) * np.float32(reward - self.q[i])
        self.last_reward = float(reward)
