"""Shared helpers for annotation export checks.

Nothing here is specific to one project. Every function takes a parsed export
and returns findings; none of them print, so they compose.
"""
from __future__ import annotations
import collections
import json
import math
import wave

import numpy as np


class Finding(collections.namedtuple("Finding", "kind where detail")):
    """One defect. `kind` groups them, `where` locates it, `detail` explains it."""

    def __str__(self) -> str:
        return f"{self.kind}: {self.where} — {self.detail}"


def rms_dbfs(samples: np.ndarray) -> float:
    """RMS of a sample block, in dBFS.

    Averaging happens in the POWER domain and the conversion to decibels happens
    once, at the end. Averaging decibel values instead is a real and easy mistake:
    decibels are logarithmic, so a handful of near-silent frames drags the mean
    down by tens of dB and hides loud content sitting next to them. See
    docs/CHECKS_THAT_WERE_WRONG.md.
    """
    if samples.size == 0:
        return -math.inf
    return 20.0 * math.log10(math.sqrt(float((samples.astype(np.float64) ** 2).mean())) + 1e-12)


def read_wav_mono(path: str) -> tuple[np.ndarray, int]:
    """16-bit mono WAV to float samples in [-1, 1], plus the sample rate."""
    with wave.open(path) as w:
        if w.getsampwidth() != 2:
            raise ValueError(f"{path}: expected 16-bit PCM, got {w.getsampwidth() * 8}-bit")
        if w.getnchannels() != 1:
            raise ValueError(f"{path}: expected mono, got {w.getnchannels()} channels")
        raw = w.readframes(w.getnframes())
        return np.frombuffer(raw, dtype=np.int16).astype(np.float64) / 32768.0, w.getframerate()


def merge_intervals(spans: list[tuple[float, float]]) -> list[list[float]]:
    """Merge overlapping or touching [start, end) spans."""
    out: list[list[float]] = []
    for s, e in sorted(spans):
        if out and s <= out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return out


def gaps(covered: list[tuple[float, float]], duration: float, floor: float = 1e-3):
    """Stretches of [0, duration) that no span covers."""
    prev, holes = 0.0, []
    for s, e in merge_intervals(covered):
        if s - prev > floor:
            holes.append((prev, s))
        prev = e
    if duration - prev > floor:
        holes.append((prev, duration))
    return holes


def load_json(path: str):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
