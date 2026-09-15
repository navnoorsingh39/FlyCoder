# Contributing to FlyCoder

FlyCoder is a small scientific demo. Useful contributions keep the neural
pipeline honest and the interface understandable.

## Setup

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m flybrain download
python -m flycoder --headless --seed 64
python -m flycoder
```

Dashboard: http://127.0.0.1:8788/

## Rules that are not optional

- Do **not** fabricate neuron identities, spatial coordinates, synaptic edges,
  spike values, or decisions.
- Do **not** change MaleCNS / FlyBrain weights, mappings, selector destinations,
  reward math, or the decision sequence unless the change is a documented bug
  fix with a before/after headless result.
- Visualization may interpolate, glow, or animate, but it must be driven by
  real FlyCoder signals.
- README claims must match running code. If you change `GRAPH_NODES`, update
  the docs in the same change.

## How to test

```powershell
python -m flycoder --headless --seed 64
```

Expected on the frozen seed used in the public demo: the div centers, reward
is `+1.0`, and the action/CSS stack is unchanged unless you intentionally
changed the experiment.

For dashboard work: Recording Mode (`R`), 1920×1080, no page scroll, no
browser console errors.

## Pull requests

1. One concern per PR.
2. Say what is real vs experimental if the change touches the interface.
3. Include the headless one-liner result if the loop changed.

Open an issue first for architecture or mapping changes.
