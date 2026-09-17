"""Structural checks for a CVAT video export, and a cross-format agreement check.

Two independent serializations of the same work should agree on the number of
annotations. When they do not, one of them is lying and you do not yet know
which.

Usage:
    python -m checks.cvat_video annotations.xml [--datumaro default.json] [--frames 300]
"""
from __future__ import annotations
import argparse
import collections
import sys
import xml.etree.ElementTree as ET

from .common import Finding, load_json


def parse(xml_path: str):
    root = ET.parse(xml_path).getroot()
    meta = root.find("meta/task")
    size = meta.find("original_size")
    width, height = float(size.find("width").text), float(size.find("height").text)
    frames = int(meta.find("size").text)

    schema = {}
    for label in meta.findall("labels/label"):
        schema[label.find("name").text] = {
            attr.find("name").text: set(attr.find("values").text.split("\n"))
            for attr in label.findall("attributes/attribute")
        }

    tracks = []
    for tr in root.findall("track"):
        boxes = []
        for b in tr.findall("box"):
            boxes.append(dict(
                frame=int(b.get("frame")),
                outside=b.get("outside") == "1",
                occluded=b.get("occluded") == "1",
                x1=float(b.get("xtl")), y1=float(b.get("ytl")),
                x2=float(b.get("xbr")), y2=float(b.get("ybr")),
                attrs={a.get("name"): a.text for a in b.findall("attribute")},
            ))
        tracks.append((tr.get("id"), tr.get("label"), sorted(boxes, key=lambda z: z["frame"])))
    return width, height, frames, schema, tracks


def check(width, height, frames, schema, tracks, jump_px, size_ratio):
    findings: list[Finding] = []
    for tid, label, boxes in tracks:
        seen = set()
        for b in boxes:
            where = f"track {tid} frame {b['frame']}"
            if b["frame"] in seen:
                findings.append(Finding("duplicate frame in track", where, "two boxes on one frame"))
            seen.add(b["frame"])
            if not 0 <= b["frame"] < frames:
                findings.append(Finding("frame out of range", where, f"clip has {frames} frames"))
            if b["outside"]:
                continue
            if b["x2"] <= b["x1"] or b["y2"] <= b["y1"]:
                findings.append(Finding("zero or inverted box", where, f"{b['x1']:.1f},{b['y1']:.1f},{b['x2']:.1f},{b['y2']:.1f}"))
            if b["x1"] < -0.01 or b["y1"] < -0.01 or b["x2"] > width + 0.01 or b["y2"] > height + 0.01:
                findings.append(Finding("box outside frame", where, f"frame is {width:.0f}x{height:.0f}"))

            expected = set(schema.get(label, {}))
            if set(b["attrs"]) != expected:
                findings.append(Finding("attribute scope", where,
                                        f"missing={sorted(expected - set(b['attrs']))} extra={sorted(set(b['attrs']) - expected)}"))
            for k, v in b["attrs"].items():
                allowed = schema.get(label, {}).get(k)
                if allowed and v not in allowed:
                    findings.append(Finding("unknown attribute value", where, f"{k}={v!r}"))

        # motion sanity, but only between consecutive visible frames
        for prev, cur in zip(boxes, boxes[1:]):
            if prev["outside"] or cur["outside"] or cur["frame"] != prev["frame"] + 1:
                continue
            dx = abs((prev["x1"] + prev["x2"]) / 2 - (cur["x1"] + cur["x2"]) / 2)
            dy = abs((prev["y1"] + prev["y2"]) / 2 - (cur["y1"] + cur["y2"]) / 2)
            if max(dx, dy) > jump_px:
                findings.append(Finding("centre jump", f"track {tid} {prev['frame']}->{cur['frame']}", f"{dx:.0f},{dy:.0f} px in one frame"))
            pw, ph = prev["x2"] - prev["x1"], prev["y2"] - prev["y1"]
            cw, ch = cur["x2"] - cur["x1"], cur["y2"] - cur["y1"]
            if pw > 0 and ph > 0 and (max(cw / pw, pw / cw) > size_ratio or max(ch / ph, ph / ch) > size_ratio):
                findings.append(Finding(
                    "size jump", f"track {tid} {prev['frame']}->{cur['frame']}",
                    f"w {pw:.0f}->{cw:.0f} h {ph:.0f}->{ch:.0f}. CHECK THE ATTRIBUTES AND THE FRAME EDGE "
                    "BEFORE CALLING THIS AN ERROR: an occlusion or an exit looks exactly like this",
                ))
    return findings


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Checks for a CVAT video export.")
    ap.add_argument("xml", help="CVAT for video 1.1 annotations.xml")
    ap.add_argument("--datumaro", help="Datumaro default.json exported from the same task")
    ap.add_argument("--jump-px", type=float, default=60.0)
    ap.add_argument("--size-ratio", type=float, default=1.8)
    args = ap.parse_args(argv)

    width, height, frames, schema, tracks = parse(args.xml)
    visible = sum(1 for _, _, boxes in tracks for b in boxes if not b["outside"])
    records = sum(len(boxes) for _, _, boxes in tracks)
    print(f"{len(tracks)} tracks, {records} box records, {visible} visible, {frames} frames, {width:.0f}x{height:.0f}")
    for tid, label, boxes in tracks:
        vis = [b for b in boxes if not b["outside"]]
        print(f"  track {tid:<3} {label:<16} {len(boxes):4d} records {len(vis):4d} visible  frames {boxes[0]['frame']}-{boxes[-1]['frame']}")

    findings = check(width, height, frames, schema, tracks, args.jump_px, args.size_ratio)

    if args.datumaro:
        dm = load_json(args.datumaro)
        dm_count = sum(len(item.get("annotations", [])) for item in dm.get("items", []))
        print(f"\ncross-format: CVAT visible {visible} vs Datumaro {dm_count}")
        if dm_count != visible:
            findings.append(Finding("cross-format disagreement", "CVAT XML vs Datumaro", f"{visible} vs {dm_count} annotations"))

    unused = [name for name in schema if not any(label == name for _, label, _ in tracks)]
    if unused:
        print(f"\nlabels declared and never used: {', '.join(unused)}  (not an error, but say why in your docs)")

    print(f"\n{len(findings)} findings")
    for f in findings:
        print(f"   {f.kind}: {f.where} — {f.detail}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
