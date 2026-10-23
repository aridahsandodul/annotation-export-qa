# annotation-export-qa

**Checks that read an annotation export and tell you what is wrong with it, plus an honest record of the checks that were wrong themselves.**

Annotation quality is usually judged by looking at the tool. These read the file the tool produced, which is the thing a downstream team actually receives.

---

## What it checks

### `checks/label_studio.py` — structure and relationships

Reads a Label Studio JSON export, regroups the flat result records back into regions, and reports:

- **Attribute scope per label.** Every label declares which controls apply to it. A region missing one, or carrying one it should not, is a defect the interface will not show you.
- **Values outside the declared set**, multi-value choices, multi-label regions.
- **Geometry**: zero-length and negative spans, negative starts, duplicate offsets.
- **Accidental nesting.** Label Studio writes a `parentID` when a region is drawn while another is selected. It is invisible in the editor and visible only in the export, and it asserts a relationship that does not exist.
- **Same-speaker self-overlap.** One speaker cannot be in two places.
- **Exclusive labels over speaker regions.** Either someone is talking or they are not.

### `checks/audio_coverage.py` — is anything audible unlabelled

Finds stretches the annotation says are empty but the waveform is not, and silence sitting inside a region that claims someone is speaking.

**The reference level is the recording's own labelled speech, never a fixed number.** Two earlier versions of this check used a constant and then a median. Both were wrong, and both are documented in [docs/CHECKS_THAT_WERE_WRONG.md](docs/CHECKS_THAT_WERE_WRONG.md).

### `checks/cvat_video.py` — tracking structure and cross-format agreement

Box geometry, frame ranges, attribute scope and values, and per-frame motion sanity. Also compares the CVAT XML against the Datumaro export of the same task: **two serializations of one piece of work should agree on the count, and when they do not, one is lying and you do not yet know which.**

**The motion checks deliberately refuse to call a jump an error.** A box halving in height looks identical whether it is a tracking failure, an occlusion, or an animal leaving the frame. The check reports it and tells you to read the attributes and the frame edge before deciding. Two such jumps in the sample data turned out to be one occlusion and one exit.

---

## The part worth reading

**[docs/CHECKS_THAT_WERE_WRONG.md](docs/CHECKS_THAT_WERE_WRONG.md)** — five checks that produced confident, wrong output. A fixed threshold across recordings with different noise floors. Averaging decibel values, which are logarithmic, and hiding 23 real findings for three days. A statistic chosen for convenience that flagged 69 correct regions. A rule inferred from what a label sounds like it means. Containment where intersection was needed.

**Three were deleted. Two were rebuilt. Every one was caught by a person disputing the result, never by the tooling noticing itself.**

---

## Use

Requires Python 3.9+ and numpy.

```bash
python -m checks.label_studio export.json --config examples/schema_audio_conversation.json

python -m checks.audio_coverage export.json \
    --audio-dir ./wav --config examples/schema_audio_conversation.json

python -m checks.cvat_video annotations.xml --datumaro default.json
```

Each exits non-zero when it finds something, so they drop into a pre-delivery script.

**The schema lives in a JSON config, not in the code.** `examples/schema_audio_conversation.json` is the one these were written against; replace it with your own label-to-control map and value lists.

---

## Where this came from

Built this while auditing a four-modality annotation portfolio. The image work covers 10 images across CVAT, Supervisely, Label Studio, and Labelbox, plus a 5-image subset of polygon and mask annotations in Roboflow. The portfolio also includes a 300-frame CVAT tracking run, 22 text documents, and 12 conversational audio clips totaling about 36 minutes. The portfolio itself is at [fish-annotation-portfolio](https://github.com/aridahsandodul/fish-annotation-portfolio).

**All three checkers were regression-tested both ways**: against exports whose defects had already been found by hand, where they reproduce them exactly, and against the final clean exports, where they report nothing.

---

## What this is not

- **Not an accuracy measure.** These check whether an export is internally consistent and complete. **Whether the right label was applied is a question about the data, and nothing here can answer it.**
- **Not a substitute for listening or looking.** The audio check finds stretches worth your attention. It cannot tell you what is in them.
- **Not tool-agnostic.** Label Studio and CVAT export shapes are assumed. The ideas transfer; the parsers do not.

MIT licensed.
