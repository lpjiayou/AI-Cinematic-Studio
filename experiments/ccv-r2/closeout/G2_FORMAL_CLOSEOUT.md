# CCV-R2 G2 Formal Closeout

Date: `2026-08-15`

## Decision

`ACS-CCV-R2-G2-GPU-EXECUTION` is closed as:

```text
G2_GPU_EXECUTION=PASS
G2_RESULT_INTEGRITY=PASS
G2_BLIND_REVIEW=COMPLETE_WITH_ORIGINAL_LOCK_CUSTODY_GAP
G2_HYPOTHESIS=PARTIAL_PASS
SELECTED_TECHNICAL_BASE=A2_FACE_OPENPOSE
G2_CLOSEOUT=PASS_WITH_REMEDIATION_REQUIRED
VALIDATION_ACCEPTED=false
PRODUCTION_READY=false
NEXT_GATE=ACS-CCV-R2-G3-REFERENCE-CONTAMINATION-REMEDIATION
```

This decision does not authorize production use, release, merge, API or schema
changes, or a Production Ready claim. Pull request #7 remains Draft.

## Execution and integrity evidence

The accepted matrix was executed exactly as `3 arms × 5 shots × 3 seeds = 45`
outputs. The official result validator was rerun after the post-G2 external
experiments and reverified all 45 output bytes successfully.

| Control | Value |
| --- | --- |
| Result inventory SHA-256 | `704451a5133c00b29e73eeb756e738646a812ab71ce7f77d0a17ccc20f7705f9` |
| Execution authorization SHA-256 | `3a63a2234c2c18fde58d46c1aa3f02bb991c9730d915e61719d5fded1dbb1958` |
| Blind review archive SHA-256 | `a6ae805df744e2e87276de6d1585739b49eee8ad7f36d40ef89d6cf3b7a0c7d3` |
| Formal closeout manifest SHA-256 | `2736472ad7279179f793924349372d4066ca2e6746bd18e412c976bf0e245272` |
| G2 custody inventory SHA-256 | `36d980f2be829568bc9a392fa231b563d6f761e9d7b12274507f67663df4545d` |
| Formal closeout archive SHA-256 | `03c3ea8bb5a3e9a523a2e3c7f4d3f3048697e8185e4147286ac20962598b5f90` |
| Formal closeout archive bytes | `106647445` |

The archive is held at:

```text
/data/ccv-r2-2026-08-15-formal-closeout-g2-archive/ccv-r2-g2-formal-closeout.tar.gz
```

The repository stores only the custody record and digests. It does not store the
binary output or archive.

## Blind review decision

The blind review selected `A2_FACE_OPENPOSE` as the technical base, not as an
accepted production configuration.

| Arm | Cohort | Total | Identity | Pose | Anatomy | Contamination control | High-risk items |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `a0_text_baseline` | `C2` | 67.0 | 50 | 70 | 88 | 84 | 1/15 |
| `a1_face_identity` | `C1` | 69.4 | 92 | 58 | 56 | 40 | 4/15 |
| `a2_face_openpose` | `C3` | 77.0 | 90 | 90 | 50 | 40 | 6/15 |

The immutable result package still reports
`AWAITING_INDEPENDENT_BLIND_VISUAL_REVIEW=true` because that field records the state
when the result package was finalized. The package was not rewritten after review.
This closeout record binds the later review decision without mutating the sealed
result root.

## Custody gaps

The original technical-lock and cohort-score-lock files were not present on the
reattached GPU volume. Their expected digests remain recorded:

```text
technical lock: f75956bb81a8ef8dcf482f0defadf26975852941f06115da4571759cf09bf6db
score lock:     48d0159109431d242836c5bb8ba88f8e7121f374a4a396800708aa306b44c08c
```

A reconstructed closeout review record was created with SHA-256
`3c10e5e1deb3d940f42a68944602cdc0df4df69fa2b11b174d387f72b7f99e20`.
It transparently records the missing original bytes and must not be represented as
the original lock artefact.

The GPU-side tooling snapshot also lacked `.git` metadata. It is bound as a source
snapshot labelled `4d2e3732`; no local Git repository or commit identity was
fabricated. The remote governance parent is the verified PR head
`4d2e3732d2f96eac418b216c0d470971e0d1af66`.

## Post-G2 external experiments

Two experiments performed after unblinding are registered separately as external
pre-G3 design input. They are not part of the sealed G2 protocol and do not change
the G2 acceptance flags.

The external evidence package is bound by:

```text
archive SHA-256: e106864ed035d1b32d6b31c71113184df7bce203da010194950dec00975d9f5f
archive bytes:   11080721
intake SHA-256:  4ebe17ba6cd0aca4ebe48a465ad57201e5332b1629b30a9f755c1607c1749b38
inventory SHA:   c73fb2a8c0b759072ff6838d9a30f68388ef627b0be88ab433899ddcf226ab10
```

Classification:

```text
EXTERNAL_PRE_G3_EVIDENCE
TWO_VARIABLES_CONFOUNDED
NOT_SINGLE_VARIABLE_ATTRIBUTION
NOT_VALIDATION_ACCEPTED
```

The offered `reference_face_v2.png` may be used as a mechanism-probe candidate. Its
identity lineage to the original CCV target is unproven, so it cannot close the
original-character identity lock or replace the canonical identity asset without a
separate identity decision.

## Next gate

G3 must retain a single-variable reference-contamination comparison for its main
acceptance matrix. Any shot-level IPAdapter adjustment for `04_back_turning` is a
separate preregistered sub-experiment, with ControlNet held fixed during the first
weight sweep.

