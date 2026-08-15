# ACS-CCV-R2-G3 Reference Contamination Remediation

Status: `OWNER AUTHORIZED / G0 GOVERNANCE FREEZE / NO GPU`

Date: `2026-08-15`

Parent checkpoint: `6fa0388c86e3720e83fe2db183cc9a2615baf2f6`

## 1. Decision and authority

The Project Lead directed the project to start the next gate after formal G2
closeout. The standing authorization to complete bounded GPU-preparation work without
repeated review applies only to this listed wave:

```text
G3-G0 DESIGN FREEZE
→ REMOTE VERIFY
→ G3-G1 NO-GPU PREPARATION TOOLING
→ STATIC AND HOST READINESS VALIDATION
→ STOP BEFORE GPU
```

This record does not authorize ComfyUI queue submission, model loading, CUDA work,
image generation, product integration, schema or migration work, release, merge or a
Production Ready claim.

## 2. Preserved G2 decision

G2 remains closed as `PASS_WITH_REMEDIATION_REQUIRED`. Its 45 outputs and sealed
result inventory are immutable. `A2_FACE_OPENPOSE` is a technical base only;
`validationAccepted=false` and `productionReady=false` remain unchanged.

The G3 parent bindings are:

- G2 closeout commit: `6fa0388c86e3720e83fe2db183cc9a2615baf2f6`;
- G2 result inventory SHA-256:
  `704451a5133c00b29e73eeb756e738646a812ab71ce7f77d0a17ccc20f7705f9`;
- G2 authorization SHA-256:
  `3a63a2234c2c18fde58d46c1aa3f02bb991c9730d915e61719d5fded1dbb1958`;
- G2 formal-closeout manifest SHA-256:
  `2736472ad7279179f793924349372d4066ca2e6746bd18e412c976bf0e245272`.

The missing original G2 technical-lock and cohort-score-lock bytes remain a recorded
custody gap. G3 must create and preserve new original locks; it must not reconstruct
or relabel the missing G2 locks.

## 3. Research boundary

Primary question:

> Does replacing only the contaminated G2 face-reference bytes with a collar-free
> crop derived from the same fixed identity source reduce reference contamination
> without materially degrading identity continuity or pose adherence?

The primary attribution compares only:

- `G3_M0_G2_REFERENCE_CONTROL`: exact G2 `reference_face.png` bytes;
- `G3_M1_SAME_IDENTITY_COLLAR_FREE`: a new face-only crop derived from the exact G2
  `reference_character.png` bytes and bound before any GPU request.

Every other main-comparison input and parameter is fixed to the G2 A2 technical base.

`G3_P0_EXTERNAL_REFERENCE_PROBE` uses the external `reference_face_v2.png` bytes only
as a separately labelled mechanism probe. Its identity lineage to the original CCV
target is unproven. It cannot pass the primary hypothesis, replace the canonical
identity input, support validation acceptance or establish production readiness.

## 4. Frozen matrix

### Main reference matrix

```text
3 reference arms × 5 shots × 3 common seeds = 45 requests
```

The main comparison is the paired 30-request M0/M1 subset. The 15 P0 requests are
secondary and excluded from primary acceptance.

### Back-turning identity-strength sweep

The difficult `04_back_turning` shot receives a separate, preregistered IP-Adapter
weight sweep under M1 only:

```text
weights 0.30 / 0.45 / 0.60 × 3 common seeds
```

The three `0.60` rows are reused from the main M1 matrix and must not be regenerated.
Only six additional GPU requests are added for `0.30` and `0.45`. ControlNet remains
fixed at `0.80`; checkpoint, reference, seed, prompt and skeleton remain fixed.

Total unique planned GPU requests: `51`.

## 5. Fixed technical controls

- checkpoint: `sd_xl_base_1.0.safetensors`;
- IP-Adapter: `ip-adapter-plus-face_sdxl_vit-h.safetensors`;
- CLIP Vision: `CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors`;
- pose model: `controlnet-openpose-sdxl.safetensors`;
- IP-Adapter main weight: `0.60`, linear;
- ControlNet strength: `0.80`, start `0.0`, end `1.0`;
- resolution: `1024 × 1024`;
- steps: `25`;
- CFG: `7.0`;
- sampler: `dpmpp_2m`;
- scheduler: `karras`;
- seeds: `123456`, `223456`, `323456`;
- one request in flight;
- automatic retry prohibited.

RealVisXL and Juggernaut are excluded from the primary G3 attribution. Their external
R4 observations may inform later anatomy work but may not enter this matrix.

## 6. Same-identity crop binding

G1 must bind exact bytes before materializing requests. The M1 reference must:

1. derive only from the fixed `reference_character.png` source whose SHA-256 is
   `68b3e5232718c7e4ca0582db8e9430dd7fc2862d84e11c094655ed1a19110177`;
2. record the integer crop rectangle, source dimensions, output dimensions, resize
   algorithm, software version, output byte SHA-256 and decoded RGB-pixel SHA-256;
3. contain the face region while excluding collar, jacket, torso and background as
   far as the rectangular crop permits;
4. use no generation, inpainting, face restoration, face swap, color adjustment,
   retouching or hidden post-processing;
5. be frozen before the first queue submission.

G0 does not guess crop coordinates. A G1 receipt that lacks the exact derivation
record fails closed.

## 7. Review and acceptance

All 51 unique outputs receive opaque labels before execution. The technical mapping
and score rows must be locked as original digest-bearing files before unblinding.

Three independent reviewers use the existing four G2 criteria and 1–5 scale. The
primary M1 arm passes only if all of the following hold:

- median identity continuity `>= 4.0`;
- median shot/pose adherence `>= 4.0`;
- median contamination control `>= 4.0`;
- median weighted composite `>= 4.0`;
- fraction of outputs with every criterion `>= 3` is `>= 0.80`;
- M1 contamination-control median improves over M0 by `>= 1.0`;
- M1 identity median is no more than `0.25` below M0;
- terminal failure rate `<= 0.10`.

For the back-turning sweep, a weight is eligible only if all three seeds achieve
median pose adherence `>= 3.5` and median identity continuity `>= 3.0`. Selection is
deterministic: highest pose median, then highest identity median, then lower weight.
Failure to select an eligible weight is a G3 remediation failure, not a reason to
change ControlNet post hoc.

Review completion does not automatically set `validationAccepted=true` or
`productionReady=true`.

## 8. G1 authorized paths

After this governance checkpoint is remotely verified, G1 may add or update only:

- `experiments/ccv-r2/g3/README.md`;
- `experiments/ccv-r2/g3/preflight/g3-readiness.schema.json`;
- `experiments/ccv-r2/g3/preflight/prepare_g3_execution.py`;
- `experiments/ccv-r2/g3/preflight/validate_g3_preparation.py`;
- `experiments/ccv-r2/g3/tests/test_g3_preparation.py`;
- `CURRENT_MILESTONE.md` and `AGENTS.md` for exact checkpoint state.

G1 may read the G2 preparation and result roots but may write only to a new G3
preparation root. Existing G2 outputs, ledgers, inventories, locks, archives and
closeout records are read-only.

## 9. Fail-closed stop conditions

Stop before GPU if any required byte, digest, lineage record, crop receipt, workflow,
request, opaque label, technical mapping, rubric or free-space gate is missing or
ambiguous; if the unique request count is not exactly 51; if a G2 path would be
overwritten; or if any queue/model/CUDA/image operation is attempted by G1.

The next GPU gate requires a separate Project Lead authorization bound to the final
G3-G1 preparation receipt.

