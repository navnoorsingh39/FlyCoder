"""Export the brain for a browser: `flybrain export --web <folder>`.

Writes two gzipped files a web page can fetch and run without Python. They are named .bin, not
.bin.gz, because dev servers send .gz files with Content-Encoding: gzip and the browser then
unpacks them itself; readers should check for the gzip magic bytes (1f 8b) instead.

weights.N.bin  one gzip stream split into parts of at most 40 MB (GitHub warns above 50 MB);
  join the parts listed in brain.json in order, then decompress. The stream holds
  the connectome as CSC columns (presynaptic neuron -> its postsynaptic targets)
  header   "FLYW", version, n, nnz (uint32 each), ln_min (float32)
  degree   n varints: how many targets each presynaptic neuron has
  targets  nnz varints: postsynaptic index gaps within each column (first one absolute)
  weights  nnz bytes: top bit = inhibitory, low 7 bits = round(127 * ln(|w| / w_min) / -ln(w_min))
           so |w| = exp(ln_min * (1 - q/127)); log steps of about 9%, which keeps the count-1
           synapses that linear 8-bit would round to zero

meta.bin  per-neuron labels
  header   "FLYM", version, n (uint32), then a uint32 length + UTF-8 JSON
           {"types": [...], "superclasses": [...], "params": {...}, "sensory_input": bool}
  type     n uint16 indices into types
  class    n uint8 indices into superclasses
  side     n uint8: 0 unknown, 1 left, 2 right

Synapses onto sensory neurons are dropped unless sensory_input=True, as in FlyBrain(sensory_input=False).
"""
from __future__ import annotations

import gzip
import io
import json
import struct
from pathlib import Path

import numpy as np
from scipy import sparse

from .brain import FlyBrain
from .data import ensure_data

VERSION = 1
PART_BYTES = 40_000_000


def _varints(values: np.ndarray) -> bytes:
    """LEB128 unsigned varints for a non-negative integer array, vectorised by byte length."""
    v = values.astype(np.uint64)
    length = np.ones(len(v), np.int64)
    for k in range(1, 5):
        length += v >= (1 << (7 * k))
    out = np.zeros(int(length.sum()), np.uint8)
    start = np.concatenate([[0], np.cumsum(length)[:-1]])
    for k in range(5):
        on = length > k
        byte = (v[on] >> np.uint64(7 * k)) & np.uint64(0x7F)
        more = (length[on] > k + 1).astype(np.uint64) << np.uint64(7)
        out[start[on] + k] = (byte | more).astype(np.uint8)
    return out.tobytes()


def export_web(out: Path | str, data: Path | str | None = None, sensory_input: bool = False) -> dict:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    data = ensure_data(data)
    meta = np.load(data / "brain.npz")
    W = sparse.load_npz(data / "weights.npz").tocsr()   # rows = postsynaptic
    superclass = meta["superclass"].astype(str)
    if not sensory_input:
        sensory = np.char.find(superclass, "sensory") >= 0
        W = sparse.diags((~sensory).astype(np.float32)) @ W
    W = W.tocsc()
    W.eliminate_zeros()
    W.sort_indices()
    n, nnz = W.shape[0], int(W.nnz)

    mag = np.abs(W.data).astype(np.float64)
    ln_min = float(np.log(mag.min()))
    q = np.clip(np.rint(127 * (np.log(mag) - ln_min) / -ln_min), 0, 127).astype(np.uint8)
    q |= (W.data < 0).astype(np.uint8) << 7

    degree = np.diff(W.indptr).astype(np.int64)
    gaps = W.indices.astype(np.int64).copy()
    first = W.indptr[:-1][degree > 0]
    inner = np.ones(nnz, bool)
    inner[first] = False
    gaps[inner] = np.diff(W.indices.astype(np.int64))[inner[1:]]

    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=9, mtime=0) as f:
        f.write(b"FLYW" + struct.pack("<IIIf", VERSION, n, nnz, ln_min))
        f.write(_varints(degree))
        f.write(_varints(gaps))
        f.write(q.tobytes())
    blob = buf.getvalue()
    parts = []
    for start in range(0, len(blob), PART_BYTES):
        parts.append(f"weights.{len(parts)}.bin")
        (out / parts[-1]).write_bytes(blob[start:start + PART_BYTES])
    for old in out.glob("weights*.bin"):
        if old.name not in parts:
            old.unlink()

    cell_type = meta["cell_type"].astype(str)
    types, type_idx = np.unique(cell_type, return_inverse=True)
    classes, class_idx = np.unique(superclass, return_inverse=True)
    side = np.select([meta["side"].astype(str) == "L", meta["side"].astype(str) == "R"], [1, 2], 0).astype(np.uint8)
    header = json.dumps({
        "types": types.tolist(), "superclasses": classes.tolist(), "sensory_input": sensory_input,
        "params": {k: getattr(FlyBrain, k) for k in ("dt", "tau", "gain", "tonic", "noise_hz", "noise_amp")},
    }).encode()
    with gzip.open(out / "meta.bin", "wb", compresslevel=9) as f:
        f.write(b"FLYM" + struct.pack("<III", VERSION, n, len(header)) + header)
        f.write(type_idx.astype(np.uint16).tobytes())
        f.write(class_idx.astype(np.uint8).tobytes())
        f.write(side.tobytes())

    # how much the 8-bit log code moves the weights
    back = np.exp(ln_min * (1 - (q & 0x7F) / 127.0))
    err = np.abs(back - mag) / mag
    info = {"neurons": n, "connections": nnz, "ln_min": ln_min,
            "weights_mb": round(len(blob) / 1e6, 1), "parts": parts,
            "meta_mb": round((out / "meta.bin").stat().st_size / 1e6, 2),
            "weight_error_mean": round(float(err.mean()), 4), "weight_error_max": round(float(err.max()), 4)}
    (out / "brain.json").write_text(json.dumps(info, indent=2))
    return info
