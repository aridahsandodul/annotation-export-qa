"""Structural checks for a Label Studio JSON export.

Written against audio segment and text span projects, but the schema rules are
driven entirely by the SCOPE and VALUES dicts you pass in, so it generalises to
any project whose regions carry per-region attribute controls.

Usage:
    python -m checks.label_studio export.json --config myschema.json
"""
from __future__ import annotations
import argparse
import collections
import sys

from .common import Finding, load_json


def regions(task: dict) -> list[tuple[str, dict]]:
    """Group a task's result records into regions keyed by region id.

    Label Studio emits one record per region per control. The record carrying
    `from_name == region_key` holds the geometry and the label; the rest each
    carry one attribute. Grouping by `id` is what reassembles them.
    """
    grouped: "collections.OrderedDict[str, dict]" = collections.OrderedDict()
    for rec in task["annotations"][0]["result"]:
        g = grouped.setdefault(rec["id"], {"attrs": {}, "parent": rec.get("parentID")})
        if rec.get("parentID"):
            g["parent"] = rec["parentID"]
        value = rec["value"]
        if "labels" in value:
            g["labels"] = value["labels"]
            g["label"] = value["labels"][0] if value["labels"] else None
            g["start"] = value.get("start")
            g["end"] = value.get("end")
            g["text"] = value.get("text")
        else:
            key = next((k for k in ("choices", "taxonomy", "rating") if k in value), None)
            if key:
                g["attrs"][rec["from_name"]] = value[key]
    return sorted(grouped.items(), key=lambda kv: (kv[1].get("start") or 0, kv[1].get("end") or 0))


def check_task(task_id, name, regs, scope, values, findings):
    if not regs:
        findings.append(Finding("empty annotation", name, "submitted with zero regions"))
        return

    ids = [rid for rid, _ in regs]
    if len(set(ids)) != len(ids):
        findings.append(Finding("repeated region id", name, "a region id appears twice"))

    seen_spans = {}
    for rid, g in regs:
        where = f"{name} {rid} {g.get('label')} {g.get('start')}-{g.get('end')}"
        if "label" not in g:
            findings.append(Finding("attributes with no region", where, "attribute records exist but no labelled region carries this id"))
            continue
        if len(g.get("labels") or []) != 1:
            findings.append(Finding("multi-label region", where, f"{len(g.get('labels') or [])} labels on one region"))

        expected = scope.get(g["label"])
        if expected is None:
            findings.append(Finding("unknown label", where, f"{g['label']!r} is not in the schema"))
        else:
            missing, extra = set(expected) - set(g["attrs"]), set(g["attrs"]) - set(expected)
            if missing or extra:
                findings.append(Finding("attribute scope", where, f"missing={sorted(missing)} extra={sorted(extra)}"))

        for control, chosen in g["attrs"].items():
            if len(chosen) != 1:
                findings.append(Finding("multi-value choice", where, f"{control}={chosen}"))
            elif control in values and chosen[0] not in values[control]:
                findings.append(Finding("unknown value", where, f"{control}={chosen[0]!r}"))

        if g["parent"]:
            findings.append(Finding("parentID", where, f"nested under {g['parent']} — Label Studio does this by accident when a region is selected while you draw"))

        s, e = g.get("start"), g.get("end")
        if s is not None and e is not None:
            if e <= s:
                findings.append(Finding("zero or negative length", where, f"{s} to {e}"))
            if s < 0:
                findings.append(Finding("negative start", where, str(s)))
            key = (s, e)
            if key in seen_spans:
                findings.append(Finding("duplicate offsets", where, f"same span as {seen_spans[key]}"))
            seen_spans[key] = rid


def check_overlaps(name, regs, speaker_labels, exclusive_labels, findings):
    """Relationship checks between regions that share a timeline.

    `speaker_labels`  regions that identify who produced the sound.
    `exclusive_labels` regions that cannot coexist with a speaker region at the
                       same instant, such as a non-speech sound.
    """
    speakers = [(i, g) for i, g in regs if g.get("label") in speaker_labels and g.get("start") is not None]

    for k, (i, a) in enumerate(speakers):
        for j, b in speakers[k + 1:]:
            overlap = min(a["end"], b["end"]) - max(a["start"], b["start"])
            if overlap > 5e-4 and a["label"] == b["label"]:
                findings.append(Finding("same-speaker self-overlap", f"{name} {i} vs {j}", f"{overlap:.3f}s — one speaker cannot be in two places"))

    for i, g in [(i, g) for i, g in regs if g.get("label") in exclusive_labels and g.get("start") is not None]:
        for j, sp in speakers:
            overlap = min(g["end"], sp["end"]) - max(g["start"], sp["start"])
            if overlap > 5e-4:
                findings.append(Finding("exclusive label over a speaker", f"{name} {i} x {j}", f"{overlap:.3f}s — either someone is talking or they are not"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Structural checks for a Label Studio export.")
    ap.add_argument("export", help="Label Studio JSON export")
    ap.add_argument("--config", required=True, help="JSON: {scope, values, speaker_labels, exclusive_labels}")
    ap.add_argument("--quiet", action="store_true", help="print only the finding count")
    args = ap.parse_args(argv)

    cfg = load_json(args.config)
    scope = {k: set(v) for k, v in cfg["scope"].items()}
    values = {k: set(v) for k, v in cfg.get("values", {}).items()}
    speaker_labels = set(cfg.get("speaker_labels", []))
    exclusive_labels = set(cfg.get("exclusive_labels", []))

    findings: list[Finding] = []
    tasks = load_json(args.export)
    total_regions = 0
    for task in sorted(tasks, key=lambda t: t.get("id", 0)):
        name = str(task.get("file_upload") or task.get("id"))
        regs = regions(task)
        total_regions += len(regs)
        check_task(task.get("id"), name, regs, scope, values, findings)
        if speaker_labels:
            check_overlaps(name, regs, speaker_labels, exclusive_labels, findings)

    print(f"{len(tasks)} tasks, {total_regions} regions, {len(findings)} findings")
    if not args.quiet:
        by_kind = collections.Counter(f.kind for f in findings)
        for kind, n in by_kind.most_common():
            print(f"\n{kind.upper()}  ({n})")
            for f in findings:
                if f.kind == kind:
                    print(f"   {f.where} — {f.detail}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
