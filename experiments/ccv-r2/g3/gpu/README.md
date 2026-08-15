# CCV-R2 G3-G2 GPU execution

This directory contains the fail-closed executor and independent validator for the
51 opaque requests frozen by G3-G1.

## Frozen controls

- readiness SHA-256:
  `e39ac4a8c3ddbf1f26571b295bcb00da7ff6b499acd49e8ad47291726bbbc5e4`;
- preparation inventory SHA-256:
  `20878b06608af6310cc1e60648d5b5e59a05cc6aa43475feb9ff3f9ae1e62845`;
- maximum queue count: `51`;
- maximum in flight: `1`;
- automatic retry: `false`.

## Static validation

```bash
python3 -m py_compile \
  experiments/ccv-r2/g3/gpu/execute_g3_gpu_experiment.py \
  experiments/ccv-r2/g3/gpu/validate_g3_gpu_results.py
python3 -m unittest -v experiments/ccv-r2/g3/gpu/test_g3_gpu_execution.py
```

## Authorized host execution

Run only from the repository root after the Project Lead authorization is present:

```bash
python3 experiments/ccv-r2/g3/preflight/validate_g3_preparation.py \
  /data/ccv-r2-2026-08-15-preparation-g3-g1

python3 experiments/ccv-r2/g3/gpu/execute_g3_gpu_experiment.py \
  /data/ccv-r2-2026-08-15-preparation-g3-g1 \
  --authorization /data/ccv-r2-g3-g2-execution-authorization.json

python3 experiments/ccv-r2/g3/gpu/validate_g3_gpu_results.py \
  /data/ccv-r2-2026-08-15-results-g3-g2
```

A successful technical run still leaves `validationAccepted=false` and
`productionReady=false`; independent blind visual review is the next gate.

