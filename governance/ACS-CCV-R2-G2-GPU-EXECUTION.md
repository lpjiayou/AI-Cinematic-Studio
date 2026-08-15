# ACS-CCV-R2-G2 — GPU Execution

> Task ID: `ACS-CCV-R2-G2-GPU-EXECUTION`
>
> Date: `2026-08-15`
>
> Parent checkpoint: `93b04842f4987f84db7a5b41a77b36ea1280cd5b`
>
> Decision: `PROJECT LEAD AUTHORIZED / ACTIVE`
>
> Execution boundary: `RECEIPT-BOUND 45-RUN SYNTHETIC GPU GENERATION / FAIL-CLOSED`
>
> Production Ready: `NO`

## 1. Authorization

The Project Lead explicitly authorizes entry into
`ACS-CCV-R2-G2-GPU-EXECUTION`. This authority is limited to the frozen CCV-R2
experiment prepared and validated by G1. It does not authorize any product, schema,
migration, API, worker, deployment, release or Production Ready change.

Execution is cryptographically bound to the G1 preparation receipt:

```text
PREPARATION_ROOT=/data/ccv-r2-2026-08-15-preparation-g1
PREPARATION_RECEIPT_SHA256=995035ee1169b7335d7c0707ea6adc31e36cd342c2a281f475fd66b7f4952c05
PREPARATION_INVENTORY_SHA256=95e1257003b28aced87719d31b4caba2eabc5a18995d2d9b98dbfb20157db40a
EXPECTED_RUN_COUNT=45
RESULT_ROOT=/data/ccv-r2-2026-08-15-results-g2
```

A changed receipt, request payload, model, input, count, run identifier, blind label,
output path or execution policy invalidates this authorization and must fail closed.

## 2. Frozen execution matrix

G2 may execute exactly the G0/G1 matrix:

- arms: `A0_TEXT_BASELINE`, `A1_FACE_IDENTITY`, `A2_FACE_OPENPOSE`;
- shots: five frozen shot IDs;
- seeds: `123456`, `223456`, `323456`;
- initial queue submissions: maximum `45`;
- concurrency: maximum `1` in-flight prompt;
- dimensions: `1024 × 1024`;
- sampling: `25 steps / CFG 7 / dpmpp_2m / karras`;
- IPAdapter: `0.6 / linear`;
- OpenPose: strength `0.8 / start 0 / end 1`.

The G0 protocol permits at most one explicitly governed retry, but this G2 activation
authorizes no automatic retry. A failed run must be recorded and execution must stop.
Any retry requires a separate, run-specific authorization record and must retain the
original failure relation.

## 3. Allowed host actions

G2 may:

1. revalidate the immutable G1 preparation and exact receipt;
2. create a new isolated result root;
3. start or reuse a local ComfyUI server on the attached FunHPC host;
4. load only the four frozen model bytes verified by G1;
5. submit the 45 frozen request payloads sequentially to local ComfyUI;
6. wait for each prompt to reach a terminal state before any next submission;
7. copy the single generated PNG for each run to its canonical result path;
8. record prompt ID, timestamps, duration, output size, SHA-256 and embedded
   `ccvR2` metadata binding;
9. atomically update the result ledger and failure ledger after every terminal event;
10. resume only by verifying already completed result bytes before skipping them;
11. independently validate the complete result set and create a review packet inventory.

No raw generated image or model byte may be committed to Git.

## 4. Repository allowlist

The G2 governance activation commit may change only:

- `AGENTS.md`;
- `AI_CINEMATIC_STUDIO_SYSTEM_MASTER_PLAN.md`;
- `CURRENT_MILESTONE.md`;
- `README.md`;
- this governance record.

The following implementation commit may add or update only:

- `experiments/ccv-r2/README.md`;
- `experiments/ccv-r2/gpu/execution-authorization.schema.json`;
- `experiments/ccv-r2/gpu/execution-authorization.template.json`;
- `experiments/ccv-r2/gpu/result-ledger.schema.json`;
- `experiments/ccv-r2/gpu/execute_gpu_experiment.py`;
- `experiments/ccv-r2/gpu/validate_gpu_results.py`;
- `experiments/ccv-r2/gpu/test_gpu_execution.py`.

Product code, existing tests, schemas, migrations, HTTP/API contracts, services, apps,
workers and frontend paths must have zero diff.

## 5. Mandatory fail-closed gates

Before the first queue submission, the runner must prove:

- G1 validator returns `PASS`;
- the receipt SHA-256 is the authorized digest;
- the authorization document names this checkpoint and the exact result root;
- `gpuExecutionAuthorized=true`, `expectedRunCount=45`,
  `maximumQueueCount=45`, `maximumInFlight=1` and
  `automaticRetryAuthorized=false`;
- the result root is new or contains only a valid resumable G2 ledger;
- ComfyUI is reachable through the configured local endpoint;
- every request still matches its registered size and SHA-256.

The runner must stop immediately on queue rejection, history timeout, ComfyUI terminal
failure, missing or multiple image outputs, path escape, zero-byte output, PNG metadata
mismatch, digest conflict, count overflow or ledger inconsistency. It may not silently
retry, skip or reinterpret a failed run.

## 6. Required result surfaces

The isolated result root must contain:

- `execution-authorization.json`;
- `result-ledger.json`;
- `failure-ledger.json`;
- `outputs/` with exactly one canonical PNG per successful run;
- `execution-receipt.json` after all 45 outputs validate;
- `result-inventory.json` and `result-inventory.sha256`;
- `review-package.json` with blind-label mappings and digest references.

Every mutation must use an atomic replacement. Completed rows are immutable unless a
separate governed retry exists.

## 7. Completion and stop state

Generation completion requires 45/45 successful, unique, positive-size PNGs whose
digests and embedded metadata bind to the frozen request records. It is not a visual
quality decision.

After execution and independent result validation:

```text
ACS-CCV-R2-G2 GPU GENERATION COMPLETE OR FAIL-CLOSED
STOP FOR INDEPENDENT BLIND VISUAL REVIEW
VALIDATION ACCEPTED: NO
PRODUCTION READY: NO
NO PRODUCT / SCHEMA / MIGRATION / PRODUCTION AUTHORITY
```

G2 may not score, unblind, accept or productionize the result automatically. A separate
review checkpoint is required.
