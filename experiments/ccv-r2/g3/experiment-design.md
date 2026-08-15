# CCV-R2 G3 Reference Contamination Remediation Design

## Status

| Field | Value |
| --- | --- |
| Protocol | `g3-rcr-v1` |
| State | `G0_FROZEN_NO_GPU` |
| Parent | `6fa0388c86e3720e83fe2db183cc9a2615baf2f6` |
| Main requests | `45` |
| Additional back-turning requests | `6` |
| Total unique GPU requests | `51` |
| GPU execution | `NOT AUTHORIZED` |
| Validation accepted | `false` |
| Production ready | `false` |

## Main inference

The primary paired comparison is M0 versus M1. M0 retains the exact contaminated G2
face-reference bytes. M1 substitutes only a collar-free crop derived from the exact
same fixed identity source. Checkpoint, workflow topology, five pose inputs, prompt,
negative prompt, sampling parameters, seeds and output dimensions remain identical.

The external P0 reference is deliberately present only as a mechanism probe. Because
it was generated independently and does not prove lineage to the original target, it
is excluded from the main hypothesis and every acceptance calculation.

## Matrix

| Arm | Reference | Role | Runs |
| --- | --- | --- | ---: |
| `G3_M0_G2_REFERENCE_CONTROL` | exact `reference_face.png` | primary control | 15 |
| `G3_M1_SAME_IDENTITY_COLLAR_FREE` | exact G1-bound crop of `reference_character.png` | primary remediation | 15 |
| `G3_P0_EXTERNAL_REFERENCE_PROBE` | exact external `reference_face_v2.png` | non-acceptance probe | 15 |

Each arm uses five shots and seeds `123456`, `223456`, `323456`.

The secondary `04_back_turning` sweep evaluates M1 at IP-Adapter weights `0.30`,
`0.45` and `0.60`, with ControlNet fixed at `0.80`. Its three `0.60` rows are the
existing M1 rows; only six new rows are generated.

## Fixed inputs

The G2 A2 model and pose digests remain authoritative. G1 must recompute them from the
host; path existence alone is insufficient. M0 is bound to SHA-256
`12147633703cbef0fcd1f521265f535c6fc4b97666e7d6dc0e322f38d7162905`.
The M1 source is bound to SHA-256
`68b3e5232718c7e4ca0582db8e9430dd7fc2862d84e11c094655ed1a19110177`.
P0 is bound to SHA-256
`407656b3c56560103171b57d286b1392b306d548e236136f7648446eabb92aba`.

M1 output bytes are intentionally pending G1 derivation and custody binding. No GPU
authorization may be issued while that digest is null.

## Review boundary

Opaque labels and the mapping are created before execution. Three reviewers score
identity continuity, shot/pose adherence, anatomy/artifact freedom and reference
contamination control. P0 scores may be reported descriptively but cannot satisfy the
primary thresholds.

The R4/R5 package remains `EXTERNAL_PRE_G3_EVIDENCE /
NOT_VALIDATION_ACCEPTED`. It informed this design but is not upgraded into sealed G3
evidence.

