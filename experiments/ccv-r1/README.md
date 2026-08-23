# ACS CCV-R1 Evidence Package

> `EXPERIMENT EVIDENCE / NOT PRODUCTION CODE / NOT A MILESTONE DELIVERABLE`
>
> `SYNTHETIC_TEST_ONLY / NOT FOR PRODUCTION`
>
> Status: `EXPERIMENT REPORTED / INDEPENDENT REPRODUCTION NOT POSSIBLE`

This directory hardens the evidence contract for the three Character Consistency
rounds reported on `2026-08-14`. It does not claim that the historical run has been
independently reproduced, does not authorize a schema change, and does not contain
generated images, models or recovered historical logs.

## Historical evidence limitation

The GPU machine is off. The original script bytes, ComfyUI API workflows, input
images, skeleton images, model files, logs and generated images remain external. The
three scripts in [`scripts/`](scripts/) are hardened successor entrypoints, not a
claim that the exact historical bytes were recovered.

Unknown historical values remain `null` or `PENDING_*`. They must never be inferred
from filenames or narrative prose.

## Structure

```text
experiments/ccv-r1/
├─ README.md
├─ CHARACTER_CONSISTENCY_VALIDATION_REPORT_R1.md
├─ experiment-manifest.schema.json
├─ experiment-manifest.pending.json
├─ configs/
│  ├─ round-1.json
│  ├─ round-2.json
│  └─ round-3.json
├─ scripts/
│  ├─ evidence_common.py
│  ├─ character_consistency_test.py
│  ├─ ipadapter_face_test.py
│  └─ ipadapter_pose_test.py
├─ validation/
│  └─ validate_fail_closed.py
├─ workflows/
│  └─ README.md
└─ evidence/
   └─ README.md
```

Generated images and other binaries must not be committed. Their logical filenames,
byte sizes and SHA-256 values belong in a finalized manifest.

## No-GPU validation

Run from the repository root:

```bash
python experiments/ccv-r1/scripts/character_consistency_test.py --help
python experiments/ccv-r1/scripts/ipadapter_face_test.py --help
python experiments/ccv-r1/scripts/ipadapter_pose_test.py --help

python experiments/ccv-r1/scripts/character_consistency_test.py --validate-only
python experiments/ccv-r1/scripts/ipadapter_face_test.py --validate-only
python experiments/ccv-r1/scripts/ipadapter_pose_test.py --validate-only

python experiments/ccv-r1/validation/validate_fail_closed.py
```

The final command proves, without GPU dependencies, that:

- the frozen matrix expands to `10 + 25 + 15 = 50` expected outputs;
- Round 3 registers five separate skeleton files and links each run to its exact
  skeleton logical name;
- a zero-byte model file is rejected;
- arbitrary bytes and unrecognized safetensors architectures are rejected;
- conditioning width is derived from role-specific tensors in the actual
  safetensors header, so an SD1.5 `768` file cannot masquerade as declared SDXL
  `2048` metadata;
- architecture evidence records both the full model SHA-256 and safetensors-header
  SHA-256;
- a captured manifest cannot retain null size, digest or seed evidence, and its
  declared count must match the frozen per-round matrix;
- a non-empty file must match both its recorded byte size and SHA-256.

Pending configuration validation compares explicit declarations because model bytes
are not yet available. Finalization does not trust those declarations alone: it
parses actual safetensors tensor shapes, derives `768` or `2048`, compares that result
to the declaration and writes digest-tied `architectureEvidence`. Filename matching
is never accepted as architecture evidence.

## Pending and finalized manifests

The checked-in pending manifest is generated from the three configs and lists every
expected output individually. It deliberately contains null historical seeds and
digests that were not preserved in the report.

To regenerate one round's pending manifest:

```bash
python experiments/ccv-r1/scripts/character_consistency_test.py \
  --write-pending-manifest \
  --manifest-out /tmp/ccv-r1-round-1.pending.json
```

Finalization is fail closed. Before `--finalize-manifest`, replace all pending model,
artifact and seed fields with values recovered from the external GPU machine. The
command verifies model/artifact size and SHA-256, verifies actual safetensors
architecture, verifies exact output count, requires every captured seed and digest,
rejects missing or zero-byte outputs, and writes an evidence manifest automatically.
Round 3 requires five independently hashed skeleton files rather than one directory
or aggregate placeholder:

```bash
python experiments/ccv-r1/scripts/ipadapter_pose_test.py \
  --finalize-manifest \
  --output-root /external/ccv-r1 \
  --manifest-out /external/ccv-r1/round-3/experiment-manifest.json
```

Writing a manifest changes evidence state only. It does not mean technical validation
passed and does not authorize CCV-R2, M6 schema work or production use.

## Rights and governance

Every input, intermediate and output is governed as:

```text
SYNTHETIC_TEST_ONLY
NOT FOR PRODUCTION
```

Source, license status, provenance and human approval remain pending until explicitly
collected. Unclear rights or license status is a hard stop.
