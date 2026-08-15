# CCV-R2 G3 no-GPU preparation

G3 tests whether a collar-free reference derived from the same fixed identity source
reduces the reference contamination observed in G2. The external clean reference is
materialized only as a non-acceptance mechanism probe.

This directory is preparation-only. None of its programs contacts ComfyUI, imports
Torch, loads a model, queues a prompt or generates an image.

## Required host inputs

- frozen G2 preparation root:
  `/data/ccv-r2-2026-08-15-preparation-g1`;
- frozen G2 result root: `/data/ccv-r2-2026-08-15-results-g2`;
- exact G2 references and pose inputs at their frozen runtime paths;
- external probe `/data/ccv-r5-clean-reference/reference_face_v2.png`;
- same-identity collar-free crop at
  `/data/coding/apps/ComfyUI/input/ccv-r2-g3-reference-face-collar-free.png`;
- its derivation receipt at the same path with suffix `.derivation.json`.

The crop receipt must record the exact integer crop rectangle and prove, using decoded
RGB pixels, that the output is only a crop-and-resize of the fixed G2
`reference_character.png`. A human/operator attestation that collar, jacket and torso
are excluded is required; the tool does not infer that semantic fact from filenames.

If the crop has not yet been created, inspect the fixed source image, choose an exact
collar-free rectangle, and let the preparation tool create both the PNG and receipt:

```bash
python3 experiments/ccv-r2/g3/preflight/prepare_g3_execution.py \
  --derive-crop-box LEFT TOP RIGHT BOTTOM \
  --attest-collar-excluded
```

The command refuses to overwrite either file. The attestation flag means the selected
rectangle was visually checked to exclude collar, jacket and torso; it must not be
supplied for an unreviewed rectangle.

## Prepare and validate

Run from the repository root on the reattached FunHPC host:

```bash
python3 experiments/ccv-r2/g3/preflight/prepare_g3_execution.py
python3 experiments/ccv-r2/g3/preflight/validate_g3_preparation.py \
  /data/ccv-r2-2026-08-15-preparation-g3-g1
```

Expected terminal claims:

```text
CCV_R2_G3_G1_PREPARATION=PASS
REQUEST_COUNT=51
GPU_EXECUTION_STARTED=false
COMFYUI_QUEUE_TOUCHED=false
```

Stop after validation. G3 GPU execution requires a separate Project Lead
authorization bound to the final readiness receipt SHA-256.

## Static tests

```bash
python3 -m unittest -v experiments/ccv-r2/g3/tests/test_g3_preparation.py
```
