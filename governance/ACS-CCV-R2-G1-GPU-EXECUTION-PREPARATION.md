# ACS-CCV-R2-G1 — GPU Execution Preparation

> Task ID: `ACS-CCV-R2-G1-GPU-EXECUTION-PREPARATION`
>
> Date: `2026-08-15`
>
> Parent checkpoint: `0376ee3c5b7a4c78735a04578a9a12fa1df6c2a2`
>
> Decision: `OWNER AUTHORIZED / AUTOMATIC PRE-GPU COMPLETION`
>
> Execution boundary: `READ-ONLY HOST PREFLIGHT + OFFLINE PROMPT MATERIALIZATION / NO GPU`
>
> Production Ready: `NO`

## 1. Authorization

The Project Lead instructed automation to complete all work before GPU execution
without another review window. This checkpoint authorizes bounded, fail-closed
preparation only. It does not authorize a ComfyUI queue submission, model load, CUDA
execution, image generation, production integration or validation acceptance.

CCV-R2-G0 is frozen and closed at
`0376ee3c5b7a4c78735a04578a9a12fa1df6c2a2`. Its 3-arm, 5-shot,
3-seed matrix contains exactly 45 planned runs.

## 2. Allowed work

G1 may:

1. read and hash the frozen model, input, custody and manifest bytes;
2. inspect Git commits and read-only environment metadata;
3. extract ComfyUI prompt JSON from the three designated historical PNGs;
4. normalize the extracted graphs to the frozen G0 parameters;
5. materialize three base graphs and exactly 45 per-run prompt payloads in a new,
   repository-external preparation directory;
6. validate unique run IDs, blind labels, output prefixes, seeds, paths and payload
   digests;
7. issue an execution-readiness receipt;
8. provide an inert future runner that remains fail-closed without an explicit,
   receipt-bound GPU authorization document.

All writes must be confined to a newly created CCV-R2 preparation directory. The
historical G2-R1 evidence and archive roots are immutable inputs.

## 3. Prohibited work

G1 must not:

- start or restart ComfyUI;
- send HTTP requests to `/prompt`, open a websocket or enqueue any job;
- import or initialize CUDA frameworks;
- load a checkpoint, IPAdapter, CLIP Vision or ControlNet model;
- create or modify an image output;
- modify the G2-R1 evidence root or its six-volume archive;
- alter product code, schemas, migrations, APIs, DTOs, routes, handlers, workers,
  frontend code or existing production tests;
- declare the historical CCV-R1 result validated;
- issue `FEATURE ACCEPTED` or `PRODUCTION READY`.

## 4. Frozen experiment matrix

- Arms: `A0_TEXT_BASELINE`, `A1_FACE_IDENTITY`, `A2_FACE_OPENPOSE`
- Shots: `01_medium_front`, `02_closeup_side`, `03_full_walking`,
  `04_back_turning`, `05_sitting_high`
- Seeds: `123456`, `223456`, `323456`
- Planned runs: `3 × 5 × 3 = 45`
- Resolution: `1024 × 1024`
- Sampler: `euler / normal / 20 steps / CFG 7.0`
- A1 identity weight: `0.6 / linear`
- A2 identity weight: `0.6 / linear`
- A2 OpenPose strength: `0.8 / start 0.0 / end 1.0`
- Maximum retry: `1`, explicitly ledgered; silent retry forbidden.

## 5. Frozen runtime inputs

The preflight must verify exact size and SHA-256 for the SDXL checkpoint, IPAdapter,
CLIP Vision, OpenPose ControlNet, two reference images and five pose inputs declared by
the preparation tool. Any missing or changed byte fails closed.

The local OpenPose file is a historical converted artifact whose exact upstream byte
chain remains partial. The local CLIP Vision packaging chain is also partial. Their
fixed bytes may be used for this synthetic forward experiment, but the readiness
receipt must preserve those provenance limitations and must not claim production
licensing clearance.

## 6. Repository allowlist

G1 implementation is limited to:

- `experiments/ccv-r2/README.md`
- `experiments/ccv-r2/preflight/prepare_gpu_execution.py`
- `experiments/ccv-r2/preflight/validate_preparation.py`
- `experiments/ccv-r2/preflight/execution-readiness.schema.json`
- `experiments/ccv-r2/preflight/execution-readiness.template.json`
- `experiments/ccv-r2/scripts/run_gpu_experiment.py`

In addition, only the five governance surfaces changed by this checkpoint may be
updated: this record, root `AGENTS.md`, the System Master Plan,
`CURRENT_MILESTONE.md` and root `README.md`.

## 7. Required readiness result

The stage can close only when all of the following are true:

- repository static validation passes;
- all 45 run-register rows map one-to-one to 45 payloads;
- all configured runtime inputs pass exact byte verification;
- the three historical prompt sources pass exact digest verification and semantic
  arm classification;
- ComfyUI and custom-node commit identities are recorded;
- preparation directory file inventory and receipt digests are emitted;
- validator reports `CCV_R2_G1_PREPARATION=PASS`;
- no ComfyUI process, prompt queue, CUDA execution or new image generation was started.

The next state is `GPU_READY_PREPARATION_COMPLETE / AWAIT EXPLICIT GPU EXECUTION
CHECKPOINT`. G1 itself grants no GPU execution authority.
