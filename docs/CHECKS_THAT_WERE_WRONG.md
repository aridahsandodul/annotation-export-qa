# Checks that were wrong

**Five checks in this toolkit's history produced confident output and were wrong. Three were deleted. Two were rebuilt.**

This document exists because the checks are the easy part. **Auditing your own checks is the part nobody does**, and every failure below was caught by a person disputing a result, never by the tooling noticing itself.

---

## 1. A fixed threshold where a per-recording measurement belonged

**The check:** flag any unlabelled stretch louder than −45 dBFS.

**Why it failed:** the recordings' noise floors ranged from −29 to −42 dBFS. A single constant is above the floor in one file and below it in another. **It produced five false positives out of six flags**, and the annotator, who had listened, was told his ear was wrong.

**The fix:** compare against the recording's own reference level. `audio_coverage.py` calibrates on the clip's labelled speech.

**The general shape:** a constant standing in for a measurement. It is convenient, it looks principled, and it silently assumes every input is the same.

---

## 2. Averaging decibels

**The check, after the first fix:** average the per-frame dBFS values over a stretch and compare that to the clip median.

**Why it failed, and this is the worst one.** Decibels are logarithmic. **Averaging them does not average energy.** These recordings are gated, with long runs of exact digital zeros, and a zero frame evaluates to about −240 dBFS. A handful of them drags the mean down by tens of decibels.

**It reported a stretch as −39.0 dBFS that actually measures −19.9 dBFS, louder than the average labelled speech in the same clip.** It hid **23 audible unlabelled stretches** for three days and produced a clean all-clear that was reported as fact.

**The fix:** average in the power domain, convert to decibels once, at the end. That is the whole of `rms_dbfs()` in `common.py`:

```python
20 * log10(sqrt(mean(samples ** 2)) + 1e-12)
```

**The tell:** the peaks disagreed with the means. A stretch reported at −39 dBFS had a sample peak of 0.65, which is 65% of full scale. **A mean and a peak that far apart is either a very bursty signal or a broken mean.** It was the second.

---

## 3. Region loudness against the clip median

**The check:** flag any labelled region quieter than its clip's median frame level minus 8 dB, on the theory that a near-silent region is mislabelled.

**Why it failed:** the median frame of a mostly-speech recording **is speech level**. Anything quieter than average speech got flagged, so the check reported **69 findings including entire correct speaker turns.**

**The fix:** deleted. There was no threshold that made it useful.

**The general shape:** a statistic chosen because it was easy to compute rather than because it answered the question.

---

## 4. Crisp boundary followed by a level rise

**The check:** a region whose boundary is marked `crisp` should be followed by a drop in level, so flag the ones followed by a rise.

**Why it failed:** in a conversation, a crisp ending is usually the other person starting immediately. **43 findings, all of them normal turn-taking.**

**The fix:** deleted.

**The general shape:** a rule inferred from what the label sounds like it should mean, rather than from what the data does.

---

## 5. Containment instead of intersection

**The check:** a non-speech region must not sit inside a speaker region. Implemented as `a.start >= b.start and a.end <= b.end`.

**Why it failed:** it only caught full containment. **A region overlapping by 0.58 seconds at one edge passed.** A second reviewer found it by hand.

**The fix:** test any intersection, `min(ends) - max(starts) > 0`. It is in `label_studio.py` as `check_overlaps`.

**The general shape:** the easy case implemented, the general case assumed to be the same.

---

## What this cost, stated plainly

**One false all-clear delivered as fact.** On one day the annotator was told five flagged stretches were room tone and that his listening had beaten the tool. Two of them were content, louder than the surrounding speech. **The tool was wrong and the person was right**, and the tool said so with numbers attached.

---

## The rule that came out of it

**A check that has never been wrong has never been tested.**

Concretely, before trusting any check:

- **Run it against data you know is bad.** All three checkers here were regression-tested against exports whose defects were already found by hand, and they reproduce them exactly.
- **Run it against data you know is clean** and confirm it says nothing.
- **Look for the internal contradiction.** A file cannot lack both "ships SAM2" and "ClickSEG"; one of them has to be there. **When a search returns zero hits for every term, that is a failed read, not a pass.** A partial page render once returned exactly that and was nearly believed.
- **When a person who has looked at the raw data disagrees with the tool, the tool is the more likely suspect.** That happened twice here. Both times the person was right.
