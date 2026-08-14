# CCV-R2 G1 GPU Preparation

This directory contains the frozen G0 design and the bounded G1 preparation tools.
G1 does not authorize or start GPU execution.

## Host preparation

Run from the repository root on the attached FunHPC host:

```bash
python3 experiments/ccv-r2/preflight/prepare_gpu_execution.py
python3 experiments/ccv-r2/preflight/validate_preparation.py \
  /data/ccv-r2-2026-08-15-preparation-g1
python3 experiments/ccv-r2/scripts/run_gpu_experiment.py \
  /data/ccv-r2-2026-08-15-preparation-g1
```

The third command is validation-only unless `--execute` is supplied. Even with
`--execute`, the G1 runner refuses queue submission: a later G2 governance checkpoint,
receipt-bound authorization document and result-ledger implementation are required.

## Expected result

Preparation succeeds only after exact SHA-256 verification of four model artifacts,
seven inputs, two immutable controls and three historical prompt sources. It derives
three base graphs and exactly 45 per-run request payloads, then emits an inventory and
`execution-readiness.json` in the repository-external preparation directory.

No tool in G1 starts ComfyUI, imports torch, loads a model, enqueues a prompt or creates
an image. The G2-R1 evidence and archive roots are read-only.
