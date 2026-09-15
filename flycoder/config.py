"""Central FlyCoder configuration.

REAL (frozen MaleCNS / FlyBrain):
    connectome weights, neuron identities, connectivity, simulated firing.

EXPERIMENTAL (this file and the FlyCoder interface):
    webpage encoding, CSS action semantics, reward, dashboard, action selector.
"""
from __future__ import annotations

# --- brain / loop -----------------------------------------------------------------
BRAIN_STEPS_PER_ACTION = 10          # neural timesteps per environment observation
WARMUP_STEPS = 80                    # settle spontaneous activity before the first action
DEVICE = "auto"                      # FlyBrain device: "cpu", "cuda", or "auto"
SEED = 64
DT = 0.020                           # FlyBrain default; do not change the connectome

# --- environment ------------------------------------------------------------------
VIEWPORT_WIDTH = 1920
VIEWPORT_HEIGHT = 1080
TARGET_WIDTH = 120
TARGET_HEIGHT = 120
CENTER_TOLERANCE_PX = 2.0

ACTIONS = (
    "DISPLAY_BLOCK",
    "DISPLAY_FLEX",
    "TEXT_ALIGN_CENTER",
    "MARGIN_AUTO",
    "JUSTIFY_CENTER",
    "ALIGN_CENTER",
    "DELETE_LAST",
    "RUN",
)

# --- encoder (experimental mapping onto real visual projection neurons) -----------
# Amounts are voltages added via FlyBrain.step(inject=...), same route as flybrain.eyes.
ENCODER_CAP = 0.8
CHASE_BASE = 0.55          # LC10a, matching the SSH Fighter chase channel scale
CHASE_GAIN = 0.30
LOOM_GAIN = 0.80           # LC4 + LPLC2; error magnitude → looming intensity
SMALL_OBJECT_GAIN = 0.70   # LPLC1; experimental vertical-error channel
CENTERED_DRIVE = 0.08      # weak bilateral drive when an axis is already centered
REWARD_LOOM = 0.35         # extra LC4 drive after a negative reward (experimental)

# --- decoder / selector (experimental control interface on real DNs) --------------
STEER_MARGIN = 0.04        # mean spikes/neuron/window, left vs right DNa02
COMMIT_THRESHOLD = 0.20    # mean spikes/neuron/window on DNp01 (+ DNg100)
REJECT_THRESHOLD = 0.55    # mean spikes/neuron/window on MDN (above ~1 Hz rest)
IDLE_COMMIT_CYCLES = 8     # experimental: commit current cursor if DNs stay quiet
Q_LEARNING_RATE = 0.25     # experimental lightweight readout; NOT connectome weights
Q_TIE_BIAS = True          # on neural laterality ties, step toward untried / higher Q

# --- dashboard --------------------------------------------------------------------
PORT = 8788
MAX_SPIKES = 400           # vis-local active nodes sent per update (not the full connectome)
TELEMETRY_EVENTS = 22      # latest structured events shown in the dashboard
TELEMETRY_LINES = 48
PUBLISH_HZ_CAP = 20
GRAPH_NODES = 8000         # sampled real soma positions in the 3D spatial connectome
GRAPH_EDGES = 6000         # sparse real synapses among those sampled neurons
REWARD_HISTORY = 24

# Recording mode: readable pacing BETWEEN real observation cycles.
# The brain still computes at full speed; the dashboard interpolates live.
# ~18 cycles × ~1.8 s ≈ 32 s visible experiment, plus intro / residual.
CYCLE_PRESENT_MS = (2400, 2900)
SUCCESS_HOLD_MS = (3500, 4500)
USEFUL_ACTIONS = ("DISPLAY_FLEX", "JUSTIFY_CENTER", "ALIGN_CENTER")
TYPE_MS_PER_CHAR = (25, 45)

# MaleCNS v1.0 expected size (also read live from the loaded FlyBrain when present)
SOURCE_NEURONS = 166_700
SOURCE_CONNECTIONS = 25_582_938
MALECNS_VERSION = "MaleCNS v1.0"
