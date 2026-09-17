# Examples

`schema_audio_conversation.json` is the schema the checks were written against: a
five-label conversational audio project with three per-region attribute controls.

**Replace it with your own.** The keys are:

| Key | Meaning |
|---|---|
| `scope` | label → the controls that apply to it. A region missing one, or carrying an extra, is a defect |
| `values` | control → its allowed values. Anything else is flagged |
| `speaker_labels` | labels that identify who produced the sound. Used for self-overlap and for the acoustic reference level |
| `exclusive_labels` | labels that cannot coexist with a speaker region at the same instant |
| `coverage_labels` | labels that count as covering the timeline. Defaults to every label in `scope` |

**No sample export or audio is included.** The recordings these were built against are
from a corpus that is not redistributed here, and the annotations are portfolio
evidence that lives in its own repository.
