# CCV-R2 Reproducible GPU Experiment

This directory contains the frozen G0 design, bounded G1 preparation tools and the
G2 receipt-bound execution tooling. G2 is authorized only for the exact 45-request
matrix prepared under:

- preparation root: \`/data/ccv-r2-2026-08-15-preparation-g1\`;
- receipt SHA-256:
  \`995035ee1169b7335d7c0707ea6adc31e36cd342c2a281f475fd66b7f4952c05\`;
- result root: \`/data/ccv-r2-2026-08-15-results-g2\`.

## G1 host preparation

Run from the repository root on the attached FunHPC host:

\`\`\`bash
python3 experiments/ccv-r2/preflight/prepare_gpu_execution.py
python3 experiments/ccv-r2/preflight/validate_preparation.py \
  /data/ccv-r2-2026-08-15-preparation-g1
python3 experiments/ccv-r2/scripts/run_gpu_experiment.py \
  /data/ccv-r2-2026-08-15-preparation-g1
\`\`\`

The legacy G1 runner remains validation-only and never queues a prompt.

## G2 execution

Copy the frozen authorization template to a host-local file, then verify that the
local ComfyUI server is running on \`127.0.0.1:8188\`. Do not change the receipt,
inventory, matrix, concurrency, retry or result-root fields.

\`\`\`bash
cp experiments/ccv-r2/gpu/execution-authorization.template.json \
  /data/ccv-r2-g2-execution-authorization.json

python3 experiments/ccv-r2/gpu/execute_gpu_experiment.py \
  /data/ccv-r2-2026-08-15-preparation-g1 \
  --authorization /data/ccv-r2-g2-execution-authorization.json

python3 experiments/ccv-r2/gpu/validate_gpu_results.py \
  /data/ccv-r2-2026-08-15-results-g2
\`\`\`

The executor submits one prompt at a time. A terminal failure is written to both
ledgers and stops the run; automatic retry is prohibited. Safe resume verifies every
completed output and refuses any in-flight, failed or digest-conflicting state.

Successful result validation proves generation completeness only. It leaves
\`validationAccepted=false\` and \`productionReady=false\`, and stops for independent
blind visual review.

## Static execution tests

\`\`\`bash
python3 -m unittest -v experiments/ccv-r2/gpu/test_gpu_execution.py
\`\`\`

The tests use a mock ComfyUI client and synthetic one-pixel PNGs. They verify 45-run
sequential execution, terminal failure stop, no automatic retry, digest-bearing result
validation and resume without requeue.
