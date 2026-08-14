# ACS-CCV-R1 Historical Evidence Capture G0

## 1. Record

| Field | Value |
| --- | --- |
| Task | `ACS-CCV-R1-HISTORICAL-EVIDENCE-CAPTURE-G0` |
| Date | `2026-08-14` |
| Decision | `CAPTURE PREPARATION AUTHORIZED / NO EXTERNAL COLLECTION IN G0` |
| Execution mode | `MANUAL / GOVERNANCE + EVIDENCE TOOLING / FAIL-CLOSED` |
| Accepted base | `main 9c13e8f8d7ccef079dd382fe11b1d173fdef13d7` |
| Accepted base tree | `8ee5c3ba7ef214bfa3e56ca97cee0b73a3666bb4` |
| Base evidence | `CCV-R1 OWNER ACCEPTED / PR #4 REBASE AND MERGE / 464/464 / MAIN CI PASS` |

The Project Lead directly accepted the CCV-R1 seed-type correction and authorized
this G0 preparation package. G0 prepares a one-window, read-only recovery of existing
historical bytes from the powered-off external GPU host. It does not power on that
host, rerun ComfyUI, regenerate an output or accept the experiment.

## 2. Purpose

G0 must make the next external collection deterministic before hourly GPU billing
resumes. It freezes:

1. the exact categories to recover;
2. the existing 50-run register and `10 / 25 / 15` round counts;
3. custody, usage-link, rights and missing-evidence states;
4. a no-GPU validator for the pending capture plan;
5. the stop conditions that must be closed before collection starts.

## 3. Evidence boundary

Every recovered item remains:

```text
EXPERIMENT EVIDENCE
NOT PRODUCTION CODE
NOT A MILESTONE DELIVERABLE
SYNTHETIC_TEST_ONLY
NOT FOR PRODUCTION
```

Finding bytes on the historical host proves present-day custody only. Claiming that
those bytes participated in the `2026-08-14` run additionally requires an exact
workflow, log, ComfyUI history or embedded-output-metadata usage link. Unlinked bytes
must remain `RECOVERED / USAGE LINK UNVERIFIED`.

## 4. Frozen collection categories

The next collection window must recover or explicitly mark missing:

- three original historical scripts;
- three ComfyUI API workflow JSON files;
- exact base, IPAdapter, image-encoder and OpenPose model bytes, sizes and SHA-256;
- Round 2 full-body reference, Round 2/3 face crop and crop lineage;
- five separately registered COCO-18 pose skeletons;
- all per-run seeds for the 50-run register;
- three raw round logs plus failure, retry and exclusion evidence;
- all 50 outputs with size and SHA-256;
- ComfyUI/custom-node commits and raw environment capture;
- model source and license records.

Unknown or ambiguous evidence stays pending. It must not be regenerated, inferred
from filenames or reconstructed from narrative memory.

## 5. G0 tooling blockers

G0 records three blockers that must be closed in a separately authorized G1 before
the external host is started:

1. `historicalScriptBytesRecovered` is currently emitted as constant `false`, so
   recovered original scripts cannot yet be represented without contradiction;
2. collection configuration must include references, crop lineage, environment and
   model source/license evidence in addition to the seven short-form categories;
3. recovered failures, retries and exclusions need a normalized ledger rather than
   being silently collapsed into 50 successful output rows.

These are experiment-evidence tooling gaps, not product schema gaps.

## 6. Exact G0 allowlist

```text
AGENTS.md
AI_CINEMATIC_STUDIO_SYSTEM_MASTER_PLAN.md
CURRENT_MILESTONE.md
README.md
governance/ACS-CCV-R1-HISTORICAL-EVIDENCE-CAPTURE-G0.md
experiments/ccv-r1/capture/README.md
experiments/ccv-r1/capture/capture-plan.schema.json
experiments/ccv-r1/capture/capture-plan.pending.json
experiments/ccv-r1/validation/validate_capture_plan.py
```

Production, application and existing test blobs must remain unchanged.

## 7. Prohibitions

- no GPU host start, snapshot action or external file access in G0;
- no ComfyUI execution or image regeneration;
- no generated image, model or raw log committed to Git;
- no product Schema, Migration, DDL, HTTP/API, Auth/RBAC or Frontend change;
- no M6-P4+, M7-M19, CCV-R2-G0 or Character Visual Identity implementation;
- no validation, feasibility or production-readiness claim.

## 8. G0 acceptance gates

- capture plan validates without GPU;
- existing run register remains exactly `10 / 25 / 15 = 50` with unique run/output IDs;
- required script/workflow/model/reference/skeleton/log/environment groups are exact;
- all external paths, sizes and digests remain null in the pending plan;
- full Core regression remains `464/464`;
- protected production/application/test blobs remain exact;
- commit, non-force publication, remote equality, Draft PR and CI pass.

## 9. Stop state

```text
ACS-CCV-R1-HISTORICAL-EVIDENCE-CAPTURE-G0 CHECKPOINT CANDIDATE
EXTERNAL GPU COLLECTION NOT STARTED
G1 TOOLING-CLOSURE AUTHORIZATION REQUIRED BEFORE HOST START
CCV-R2-G0 NOT AUTHORIZED
PRODUCTION READY: NO
```
