"""Find audible audio that carries no annotation.

The check answers one question: is there anything you can hear in a stretch the
annotation says is empty?

The reference level is the clip's OWN labelled speech, not a fixed threshold.
A constant cannot work across recordings whose noise floors differ by ten or
more decibels, and a per-clip median does not work either because the median of
a mostly-speech recording IS speech level. Both mistakes were made and are
documented in docs/CHECKS_THAT_WERE_WRONG.md.

Usage:
    python -m checks.audio_coverage export.json --audio-dir ./wav --config schema.json
"""
from __future__ import annotations
import argparse
import os
import sys

import numpy as np

from .common import Finding, gaps, load_json, read_wav_mono, rms_dbfs
from .label_studio import regions


def analyse(task, wav_path, speaker_labels, span_labels, tolerance_db, min_gap):
    """Return (reference dBFS, duration, findings) for one clip."""
    samples, rate = read_wav_mono(wav_path)
    duration = len(samples) / rate
    regs = regions(task)

    speech = [
        samples[int(g["start"] * rate):int(g["end"] * rate)]
        for _, g in regs
        if g.get("label") in speaker_labels and g.get("start") is not None
    ]
    if not speech:
        return None, duration, [Finding("no reference", os.path.basename(wav_path), "clip has no speaker regions to calibrate against")]
    reference = rms_dbfs(np.concatenate(speech))

    covered = [
        (g["start"], g["end"])
        for _, g in regs
        if g.get("label") in span_labels and g.get("start") is not None
    ]

    findings = []
    for start, end in gaps(covered, duration):
        if end - start < min_gap:
            continue
        level = rms_dbfs(samples[int(start * rate):int(end * rate)])
        if level > reference - tolerance_db:
            findings.append(Finding(
                "audible unlabelled gap",
                f"{os.path.basename(wav_path)} {start:.2f}-{end:.2f}",
                f"{end - start:.2f}s at {level:.1f} dBFS, clip speech is {reference:.1f} dBFS",
            ))
    return reference, duration, findings


def silence_inside(task, wav_path, speaker_labels, quiet_db, min_run):
    """Continuous silence inside a region that claims someone is speaking."""
    samples, rate = read_wav_mono(wav_path)
    regs = regions(task)
    speech = [samples[int(g["start"] * rate):int(g["end"] * rate)]
              for _, g in regs if g.get("label") in speaker_labels and g.get("start") is not None]
    if not speech:
        return []
    reference = rms_dbfs(np.concatenate(speech))

    hop = int(0.05 * rate)
    findings = []
    for rid, g in regs:
        if g.get("label") not in speaker_labels or g.get("start") is None:
            continue
        block = samples[int(g["start"] * rate):int(g["end"] * rate)]
        n = len(block) // hop
        if n < 2:
            continue
        frames = block[:n * hop].reshape(-1, hop)
        quiet = np.array([rms_dbfs(f) < reference - quiet_db for f in frames])
        run = 0
        for k in range(len(quiet) + 1):
            is_quiet = quiet[k] if k < len(quiet) else False
            if is_quiet:
                run += 1
                continue
            if run * 0.05 >= min_run:
                a = g["start"] + (k - run) * 0.05
                findings.append(Finding(
                    "silence inside a speaker region",
                    f"{os.path.basename(wav_path)} {rid} {g['start']:.2f}-{g['end']:.2f}",
                    f"{run * 0.05:.2f}s of silence from {a:.2f}",
                ))
            run = 0
    return findings


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Find audible audio with no annotation on it.")
    ap.add_argument("export")
    ap.add_argument("--audio-dir", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--tolerance-db", type=float, default=10.0,
                    help="flag a gap within this many dB of the clip's own speech level (default 10)")
    ap.add_argument("--min-gap", type=float, default=0.30, help="ignore gaps shorter than this (default 0.30s)")
    ap.add_argument("--quiet-db", type=float, default=30.0, help="silence is this far below speech level (default 30)")
    ap.add_argument("--min-silence-run", type=float, default=1.5, help="report silence runs at least this long (default 1.5s)")
    args = ap.parse_args(argv)

    cfg = load_json(args.config)
    speaker_labels = set(cfg["speaker_labels"])
    span_labels = set(cfg.get("coverage_labels") or cfg["scope"].keys())

    findings, checked = [], 0
    for task in sorted(load_json(args.export), key=lambda t: t.get("id", 0)):
        upload = str(task.get("file_upload") or "")
        wav = None
        for candidate in os.listdir(args.audio_dir):
            if candidate.endswith(".wav") and (candidate in upload or upload.endswith(candidate)):
                wav = os.path.join(args.audio_dir, candidate)
                break
        if wav is None:
            print(f"  no wav matched for task {task.get('id')} ({upload})", file=sys.stderr)
            continue
        checked += 1
        ref, dur, f = analyse(task, wav, speaker_labels, span_labels, args.tolerance_db, args.min_gap)
        findings += f
        findings += silence_inside(task, wav, speaker_labels, args.quiet_db, args.min_silence_run)
        if ref is not None:
            print(f"  {os.path.basename(wav):<34} {dur:6.2f}s  speech {ref:6.1f} dBFS  findings {len(f)}")

    print(f"\n{checked} clips checked, {len(findings)} findings")
    for f in findings:
        print(f"   {f.kind}: {f.where} — {f.detail}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
