# K2-002 EP01 SH12 R5 anchor-only control runner

This directory implements one isolated `TECHNICAL_EVIDENCE_ONLY` experiment:
`K2-002-EP01-SH12-R5-ANCHOR-ONLY`.

It does not change the normal EP01 runner. The default contract remains
`ANCHOR_DERIVED`, where `seed = int(startAnchorSha256[:13], 16)`. The separate
`FIXED_BASELINE_SEED` path is available only for the pinned SH12 experiment,
with both acknowledgements, one shot, one attempt, no batch, no publication
and zero canonical mutations.

## Commands

```bash
export K2_EP01_I2V_ACK=TECHNICAL_EVIDENCE_ONLY
export K2_EP01_EXPERIMENT_ACK=ANCHOR_ONLY_FIXED_BASELINE_SEED

python3 run_controlled_experiment.py \
  experiments/EP01_SH12_R5_ANCHOR_ONLY.json --dry-run

python3 run_controlled_experiment.py \
  experiments/EP01_SH12_R5_ANCHOR_ONLY.json --execute
```

`--dry-run` reads and hashes the current frozen baseline and model files, checks
the derived anchor provenance/readiness record, writes an isolated variant
workflow and receipt, and performs no network call, input staging or run-lock
mutation.

`--execute` is intentionally a separate one-shot path. It repeats the full
validation immediately before submission, atomically consumes the single run
attempt, stages the digest-pinned image and sends exactly one loopback ComfyUI
`POST /prompt`. There is no retry, force, unlock, seed override, shot selector
or batch option.

## Mandatory 23 gates

1. `K2_EP01_I2V_ACK=TECHNICAL_EVIDENCE_ONLY`.
2. `K2_EP01_EXPERIMENT_ACK=ANCHOR_ONLY_FIXED_BASELINE_SEED`.
3. `authorityState=TECHNICAL_EVIDENCE_ONLY`.
4. `publicationAllowed=false`.
5. `canonicalMutations=0`.
6. `shotId=EP01_SH12`.
7. `changedVariable=START_ANCHOR_ONLY`.
8. `maxRuns=1`.
9. Frozen `shots.json` SHA-256 matches the code-pinned R5 trust root.
10. Frozen workflow raw and canonical SHA-256 values match.
11. Frozen anchor bytes and dimensions match.
12. Variant anchor SHA-256 differs from the frozen anchor.
13. Variant seed equals the frozen baseline seed.
14. Positive and negative prompt hashes match.
15. KSampler, shift, dimensions, frames and fps match.
16. UNET, text encoder and VAE byte hashes match.
17. Structured workflow diff is exactly `/12/inputs/image`.
18. The CLI has no batch path and permits one fixed shot only.
19. The atomic run-count lock permits at most one attempt.
20. A valid `COMPLETE` receipt must not already exist.
21. The frozen materialized workflow remains read-only and unchanged.
22. Frozen `shots.json` remains read-only and unchanged.
23. Every failure before submission records zero GPU/provider calls; no retry is
    made after an ambiguous or failed submission.

The experiment manifest contains prompt digests only. Prompt text is read from
the frozen R3 materialized workflow and is never restated as a new authority.

## ComfyUI worktree attestation

The fixed ComfyUI checkout must remain at commit
`feca51a8544511dd73d43602f387def0cc601a9d` on branch `master`, with no
tracked changes. Five untracked `api_workflows` files were present before the
R3 video: their observed file mtime was 2026-07-24, while the R3 video mtime
was 2026-08-28. They are not under ComfyUI's automatically loaded
`custom_nodes` path, and this runner never imports or executes them.

They are admitted only as this exact code-pinned path-and-SHA-256 closed set:

| Path | SHA-256 |
|---|---|
| `api_workflows/R5C-1-GPU-OpenPose-ControlNet-Closeout.md` | `1371589bfc191274e467b53ba475cc8e15129f4961c5164bed9889f592e22dfc` |
| `api_workflows/r5c1_openpose_runner.py` | `df018bb287c1d1025eab9bcab79e084a2f498271dc3e0a9e1e82ce394652de33` |
| `api_workflows/r5c1_sd15_openpose_api.json` | `e76bd44d2818be1b8e57c4e856cdd41d3046a62f433001608d492e659757052b` |
| `api_workflows/run_openpose_api.py` | `4d20be5f720bd31bb3e87b314e033cba10399a886299afaf65e7bfc80bade6fc` |
| `api_workflows/run_openpose_api_flexible.py` | `df018bb287c1d1025eab9bcab79e084a2f498271dc3e0a9e1e82ce394652de33` |

Missing, additional, symlinked, non-regular or digest-changed files fail the
run. The complete untracked set is checked before and after hashing, and the
receipt records every attested path and digest. This is not a directory-level
exception: any sixth untracked path, including another `api_workflows` file,
is rejected.

## Tests

Run only the focused CPU tests in this directory:

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

These tests do not contact ComfyUI and do not use a GPU.

## Batch-r3 convergence record

See batch-r3/RUNBOOK_BATCH_R3.md for the authorized 14-shot execution snapshot, evidence index, visual status matrix, and non-canonical EP01 baseline draft.
