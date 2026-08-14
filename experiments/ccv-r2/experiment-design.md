# CCV-R2 Reproducible Experiment Design

## 1. Status

| Field | Value |
| --- | --- |
| Experiment | `acs-ccv-r2` |
| Protocol | `g0-v1` |
| State | `FROZEN DESIGN / NOT EXECUTED` |
| Parent closeout | `4132458d7f92e02dbd2e4be93476294aab825db6` |
| Rights boundary | `SYNTHETIC_TEST_ONLY / NOT FOR PRODUCTION` |
| Expected runs | `45` |
| GPU execution | `NOT AUTHORIZED BY THIS DESIGN FILE` |

This is a new forward-looking controlled experiment. It does not reconstruct the
unavailable historical workflows and does not convert the G2-R1 partial manifest into
historical validation acceptance.

## 2. Research question

Does exact face identity conditioning plus exact OpenPose conditioning improve both
identity continuity and shot/pose adherence over text-only and face-only controls when
all arms use the same five shots, three seeds and fixed SDXL sampling parameters?

The primary arm is `A2_FACE_OPENPOSE`. The controls are:

- `A0_TEXT_BASELINE`: text prompt only;
- `A1_FACE_IDENTITY`: exact face-reference bytes with IP-Adapter at `0.6`;
- `A2_FACE_OPENPOSE`: the same face conditioning plus exact per-shot COCO-18
  skeleton bytes and ControlNet strength `0.8`.

Weights `0.6` and `0.8` are frozen engineering baselines selected before R2
execution. They are not described as historically validated optima.

## 3. Factorial boundary

```text
3 arms
x 5 shots
x 3 common integer seeds
= 45 planned first attempts
```

Seeds are `123456`, `223456` and `323456`. Every arm receives every shot/seed
combination exactly once. Common seeds reduce nuisance variation when comparing arms.
Boolean seeds, implicit random seeds and post-hoc seed replacement are forbidden.

The five shots are medium-front, close-up-side, full-body-walking, back-turning and
high-angle-sitting. The back-turning shot is a declared difficult case and may not be
removed after execution.

## 4. Frozen generation parameters

All arms use:

- SDXL base model;
- `1024 x 1024`;
- `25` steps;
- CFG `7.0`;
- sampler `dpmpp_2m`;
- scheduler `karras`;
- batch size `1`;
- one declared positive prompt and one declared negative prompt.

A1 and A2 use the same exact face-reference bytes and IP-Adapter configuration. A2
alone adds the declared per-shot skeleton and OpenPose model. No refiner, LoRA,
upscaler, face restoration, inpainting or hidden post-processing is permitted.

## 5. Fixed byte inputs

The manifest freezes four model digests, seven input digests and their expected
runtime paths. Before execution, a read-only host preflight must recompute every size
and SHA-256. A missing path, zero-byte file or mismatch blocks all runs.

The face reference remains explicitly
`AMBIGUOUS_HISTORICAL_CROP_LINEAGE_BYTES_FIXED_FOR_FORWARD_TEST`. R2 uses the exact
bytes as a new synthetic test input; it does not claim the historical crop operation
was recovered.

The separately downloaded `z_image_turbo_bf16.safetensors` is excluded from this
protocol and must not be discovered or loaded by an R2 workflow.

## 6. Model source and license boundary

- SDXL base: fixed digest matches the Stability AI published checkpoint; upstream
  license is CreativeML Open RAIL++-M.
- IP-Adapter face: fixed digest matches the h94/IP-Adapter published file; upstream
  license is Apache-2.0.
- CLIP ViT-H: upstream logical model card identifies MIT, but the exact repackaged
  safetensors source chain remains partial.
- OpenPose SDXL: upstream model family card identifies OpenRAIL++, but the exact
  2.5 GB converted byte source remains partial.

Because the latter two byte provenance chains are incomplete, every R2 artifact is
restricted to internal synthetic evaluation and not commercial or production use.
This protocol does not erase that limitation.

## 7. Workflow freezing

Execution preparation must produce exactly three ComfyUI API JSON files, one for each
arm. Before any queue call:

1. each workflow must parse as JSON;
2. node types must exist in the live ComfyUI `/object_info` inventory;
3. all model and input names must resolve to the frozen files;
4. each workflow's byte size and SHA-256 must be inserted into the execution manifest;
5. the workflow may vary only seed, shot prompt, pose input and output prefix per run;
6. a rendered prompt payload receipt must be retained for every run.

A workflow hash change invalidates the preparation receipt and requires a new
governance checkpoint.

## 8. Run register and retries

`run-register.template.json` is the complete 45-run first-attempt register. Run IDs,
output paths and blind labels are unique. Output paths are relative and confined.

A maximum of one explicit retry is allowed per planned run. The original attempt stays
in the ledger. Retries receive new IDs, reference the original and never overwrite an
output. Silent retry, silent exclusion and deletion of a failed attempt are forbidden.

## 9. Review and acceptance

Three reviewers score only opaque blind labels. They must not see arm, seed, workflow
or label mapping until all reviews are submitted. Each criterion uses a frozen 1-5
scale. Medians decide the result; criteria may not be dropped after execution.

The primary arm passes only if every threshold in
`review-rubric.template.json` passes. Missing outputs count in terminal failure rate.
The difficult back-turning shot has its own frozen pose threshold.

No successful image, attractive montage or subjective narrative can override a failed
declared threshold.

## 10. Evidence and custody

For every run retain:

- resolved prompt/API JSON and SHA-256;
- environment receipt;
- queue/prompt identifier and timestamps;
- output PNG size and SHA-256;
- embedded prompt/workflow metadata digest;
- failure/retry/exclusion relation;
- blind review rows and final aggregation.

The evidence root must use source and custody inventories, deterministic bounded
archive volumes, a volume index and a later cross-instance reattach verification. Raw
images and model bytes remain outside Git.

## 11. Stop conditions

Preparation stops before GPU execution if any of these is true:

- required byte missing, zero or digest-mismatched;
- model architecture mismatch;
- required ComfyUI node or commit unavailable;
- workflow JSON unresolved or node-invalid;
- run count is not exactly `45`;
- duplicate run ID, output path or blind label;
- review mapping or failure ledger invalid;
- output root overlaps a frozen G2-R1 custody/archive root;
- free space cannot preserve outputs plus evidence and archive headroom;
- any product, schema, migration or production path changes.

## 12. G0 completion claim

G0 completion means only that the protocol, register, rubric and failure policy are
internally consistent and frozen before execution. It does not mean GPU readiness,
experiment success, validation acceptance or Production Ready.
