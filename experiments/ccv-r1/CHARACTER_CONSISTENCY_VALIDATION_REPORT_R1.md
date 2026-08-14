# Character Consistency GPU Experiment Report — Evidence-Hardened Revision R1

> Status: `EXPERIMENT REPORTED / INDEPENDENT REPRODUCTION NOT POSSIBLE`
>
> Classification: `EXPERIMENT EVIDENCE / NOT PRODUCTION CODE / NOT A MILESTONE DELIVERABLE`
>
> Rights: `SYNTHETIC_TEST_ONLY / NOT FOR PRODUCTION`
>
> Historical execution date: `2026-08-14`
>
> Report revision date: `2026-08-14`
>
> Core baseline checked by the original report: `e172cc7c9bfca04066153d9edad70d9074bb37e5`
>
> Original report SHA-256: `02adacedaf2d24488d3718bfb71732006de5f3f40364d329818ee01d8ac2f008`

This revision corrects the narrative record and establishes a verifiable evidence
contract. It does not assert that the historical GPU execution has been reproduced,
does not accept any schema direction, and authorizes no production implementation.

## 1. Evidence boundary

The original GPU host is powered off and billed by the hour. Its scripts, workflows,
models, inputs, outputs and logs are not available in this repository. Consequently:

- the experiment is reported, not independently reproduced;
- observations remain feasibility signals limited to one synthetic character and
  five shot descriptions;
- exact historical script bytes and seeds not recorded in the original report remain
  unknown;
- the checked-in scripts are hardened successors for future evidence collection, not
  the recovered historical script bytes;
- no image, model or other binary is committed.

## 2. Reported environment

The following values come from the original narrative and are not yet backed by an
environment capture manifest:

| Item | Reported value | Evidence state |
| --- | --- | --- |
| GPU | NVIDIA A100-PCIE-40GB | pending raw capture |
| Driver | 560.35.03 | pending raw capture |
| CUDA | 12.6 | pending raw capture |
| Python | 3.12.7 | pending raw capture |
| PyTorch | 2.13.0+cu126 | pending raw capture |
| ComfyUI | 0.28.0 | exact commit pending |
| Custom node | ComfyUI_IPAdapter_plus | exact commit pending |

Reported models were `sd_xl_base_1.0.safetensors`,
`ip-adapter-plus-face_sdxl_vit-h.safetensors`,
`CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors` and
`controlnet-openpose-sdxl.safetensors`. Their exact bytes, SHA-256, sources and
license states are pending.

## 3. Frozen reported prompts and shots

Reported character prompt:

```text
a young woman, 20 years old, long straight black hair,
brown eyes, red leather jacket, white t-shirt, blue jeans
```

Reported negative prompt:

```text
lowres, bad anatomy, bad hands, blurry, watermark, text, deformed face
```

| Shot | Reported description |
| --- | --- |
| `01_medium_front` | medium shot, standing, facing camera, neutral background |
| `02_closeup_side` | close-up portrait, side profile view, soft lighting |
| `03_full_walking` | full body shot, walking on a street, wide angle |
| `04_back_turning` | from behind, turning head back over shoulder |
| `05_sitting_high` | sitting on a chair, high angle shot, looking up |

The original report says these prompts were held byte-identical. That assertion must
be checked against recovered scripts/workflows before it becomes independent evidence.

## 4. Corrected run accounting

The original report incorrectly said `40` total generations. The declared matrices
expand to:

| Round | Matrix | Count |
| --- | --- | ---: |
| R1 | fixed seed: 5 shots; varying seeds: 5 shots | 10 |
| R2a | 3 IPAdapter weights × 5 shots | 15 |
| R2b | 2 IPAdapter weights × 5 shots | 10 |
| R3 | 3 ControlNet strengths × 5 shots | 15 |
| **Total** |  | **50** |

The phrase “15 images per sub-round” is withdrawn because it is false for R2b. Every
expected output is individually listed in `experiment-manifest.pending.json`. The
actual external directory has not yet been compared to those 50 expected entries; a
missing or additional file must be reported, not silently excluded.

## 5. Bounded observations

### 5.1 Round 1 — text only

The report describes 10 outputs at 512×768, with one five-shot fixed-seed schedule
and one five-shot varying-seed schedule. It reports visible identity and wardrobe
variation across changed shot prompts. This supports a bounded observation that text
description plus fixed seed was not reliable in this tested configuration.

It does not prove that every text-only technique fails universally.

### 5.2 Round 2 — face identity conditioning

R2a reportedly used a full-body reference at weights `0.5 / 0.7 / 0.9` and produced
15 outputs. The report describes reduced face drift but reference-pose, background and
wardrobe contamination.

R2b reportedly used a 512×512 face crop at weights `0.6 / 0.8` and produced 10
outputs. It describes reduced scene/wardrobe coupling while the back-facing shot
remained unsuccessful.

These are subjective observations pending the exact reference files, crop lineage,
workflows, seeds, all output hashes and independent scoring.

### 5.3 Round 3 — face conditioning plus OpenPose

Round 3 reportedly used IPAdapter weight `0.6`, OpenPose ControlNet strengths
`0.6 / 0.8 / 1.0`, five COCO-18 skeletons and 15 outputs. The narrative reports a
successful back-facing result at strength `0.6` and increasing scene/wardrobe
degradation at higher strengths.

The strongest supportable conclusion is:

```text
FEASIBLE IN THE TESTED SINGLE-CHARACTER FIVE-SHOT CONFIGURATION
```

“Identity solved”, “Verified” and any general production-readiness conclusion are
withdrawn. No second character, multi-seed repeat, frozen threshold, blind review or
automated identity/pose metric was captured.

## 6. Failure evidence and fail-closed requirements

The historical report records two faults:

1. an SD1.5 OpenPose ControlNet with `768` conditioning dimension was selected for an
   SDXL workflow using `2048`, producing a matrix-shape error;
2. a ControlNet file was zero bytes after a failed download and remained unnoticed
   for roughly three weeks.

The hardened scripts therefore require exact byte size and SHA-256 for every model
and artifact, reject zero-byte files, and reject declared model-family or
conditioning-dimension disagreement. Finalization additionally parses role-specific
conditioning tensors from the actual safetensors header, derives `768` or `2048`,
and binds the resulting header evidence to the full model SHA-256. Arbitrary bytes,
unknown tensor layouts and declaration-only compatibility are rejected. Filename
substring matching is not accepted.

Round 3 registers its five COCO-18 skeleton images as five independent artifacts.
Each run identifies the exact skeleton logical name used for its shot; each skeleton
must receive its own positive size and SHA-256 before finalization.

The original failed invocations, full stack traces and selection chronology remain
pending external collection. They must be included rather than discarded as noise.

## 7. M6 facts and architecture boundary

### 7.1 Existing IdentityBinding boundary

The original report incorrectly described M6 visual identity as only prose and
`visualConstraints`. Current Core already contains:

- `CharacterContinuityVersion.identityBindings[]`;
- allowed binding fields `identityBindingRef`, `identityRef`,
  `identityVersionRef`, `identityDigest` and `rightsGrantRef`;
- the `IdentityAuthorizationPort` protocol;
- default fail-closed behavior for non-empty bindings in the bounded current M6
  implementation;
- a reserved `IdentityBindingChanged` event contract for a future accepted identity
  authority;
- an M6 consumer that currently excludes `identityBindings`.

These facts do not mean an identity authority is accepted or implemented. The binding
to a concrete `characterRef`, AssetVersion/rights validation chain and consumer
projection remain unresolved. `M6 ≠ V5 Identity Lock` remains in force.

### 7.2 No schema safety claim

The previous statement that additive fields would not affect the existing 464 tests
is withdrawn. At most, old inputs may continue through current permissive normalization.
Effects on canonical digest, outbox payload, staleness, consumer projection,
CharacterContinuityVersion compatibility, SQLite roundtrip and InMemory/SQLite parity
have not been validated.

No schema, migration, DDL or production change is authorized by this report.

### 7.3 Execution parameters do not belong to M6 Character facts

The proposal to store `identityMethod` and `identityStrength` directly on an M6
Character is withdrawn. Model-, adapter-, checkpoint-, workflow-, weight-, strength-
and seed-specific values are execution parameters belonging to future M10 generation
requests and/or V4 execution policy, subject to separate architecture acceptance.

Stable semantic Character facts remain M6 concerns. Future identity-profile authority,
AssetVersion/rights/provenance ownership, Shot pose ownership and execution-policy
composition remain undecided and require a separate ADR after stronger evidence.

Frontend prototype presentation models do not establish Core schema authority.

## 8. Performance boundary

The reported Round 3 average was `7.3 s/image` for a 1024×1024 image on one A100. It
does not include multiple candidates, retries, local regeneration, validation,
video/audio generation or concurrent users.

The only accepted wording is:

```text
Single A100 is sufficient for the current bounded image-validation workload.
```

This does not prove a production queue or scheduler is unnecessary. It only leaves
such infrastructure unauthorized until measured demand exists.

## 9. Pending evidence required for independent review

Independent reproduction remains impossible until all of the following are collected:

1. exact historical bytes and SHA-256 of all three original scripts;
2. three ComfyUI API workflow JSON files and SHA-256;
3. full-body reference, face crop and crop-derivation evidence;
4. five COCO-18 skeleton files and generation source;
5. all 50 outputs with exact byte size and SHA-256;
6. all seeds, including the five varying Round 1 seeds;
7. all model and encoder sizes, SHA-256, sources and license status;
8. exact ComfyUI and custom-node commits;
9. raw environment capture and complete logs;
10. all failures, retries and exclusions;
11. any blind-review records or automated metrics.

All recovered material remains `SYNTHETIC_TEST_ONLY / NOT FOR PRODUCTION`. Binary
files stay outside this repository.

## 10. Review finding disposition

| Finding | R1 disposition |
| --- | --- |
| F-001 | Corrected total `40 → 50`; exact `10/15/10/15`; removed the invalid R2 sub-round statement; pending manifest lists all 50 outputs. |
| F-002 | Status downgraded; missing scripts/workflows/hashes/seeds/logs/metrics explicitly registered; hardened successors are not mislabelled as historical bytes. |
| F-003 | Replaced solved/verified claims with `FEASIBLE IN THE TESTED SINGLE-CHARACTER FIVE-SHOT CONFIGURATION`. |
| F-004 | Added existing `identityBindings[]`, five binding fields, `IdentityAuthorizationPort`, reserved event, consumer exclusion and fail-closed facts. |
| F-005 | Withdrew M6 `identityMethod`/`identityStrength`; assigned execution parameters to future M10/V4 subject to separate authorization. |
| F-006 | Records that future reference evidence must use exact immutable AssetVersion/digest/rights/provenance lineage; no schema is proposed here. |
| F-007 | Withdraws an unversioned wardrobe-list solution; applicability/version/staleness remain ADR questions. |
| F-008 | Clarifies Frontend prototype fields are experience hypotheses, not Core schema authority. |
| F-009 | Withdraws the “464 tests unaffected” claim and names the unvalidated digest/outbox/parity impacts. |
| F-010 | Limits performance wording to the bounded single-A100 image-validation workload. |
| F-011 | Replaces cumulative state-drift wording with increasing outlier risk over a broader independent-shot distribution. |

### 10.1 Evidence-validator Owner Review remediation

The first evidence-hardening candidate was held at Owner Review. Its bounded R1
correction addresses three independently reproduced gaps:

| Review gap | R1 handling |
| --- | --- |
| Declaration-only model compatibility | Actual safetensors headers are parsed; recognized conditioning tensor shapes derive the architecture dimension and are tied to model/header SHA-256. |
| Captured schema allowed null evidence | Captured status conditionally requires finalized model/artifact/output digests, integer seeds, captured run state and exact frozen run counts; runtime consistency checks mirror those rules. |
| Round 3 aggregate skeleton placeholder | Replaced by five per-shot artifact records, each independently hashed and referenced by every applicable run. |

This correction improves future evidence collection only. It does not recover the
historical external evidence and does not change the report status.

## 11. Stop state

```text
EXPERIMENT REPORTED
INDEPENDENT REPRODUCTION NOT POSSIBLE
FORMAL CHARACTER CONSISTENCY VALIDATION: NOT PASSED
M6 SCHEMA CHANGE: NOT AUTHORIZED
CCV-R2: NOT AUTHORIZED / NOT STARTED
PRODUCTION READY: NO
```
