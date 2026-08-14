# ACS-CCV-R1 Evidence Hardening

## 1. Record

| Field | Value |
| --- | --- |
| Task | `ACS-CCV-R1-EVIDENCE-HARDENING` |
| Date | `2026-08-14` |
| Decision | `BOUNDED EXPERIMENT-EVIDENCE HARDENING AUTHORIZED` |
| Execution mode | `MANUAL / BOUNDED / FAIL-CLOSED` |
| Accepted parent checkpoint | `ACS-GOV-POST-M6-P3-G1-CLOSEOUT / 20207e7f2d2123468698f453c70ce725a293976a` |
| Accepted parent tree | `e3638838dd0c79201a1962bb247ec7c773b62ffa` |
| Production and test diff | `ZERO REQUIRED` |
| Final stop | `AFTER COMMIT / NON-FORCE PUSH / REMOTE VERIFY / DRAFT PR / CI / OWNER REVIEW REQUIRED` |

This checkpoint converts the `2026-08-14` Character Consistency narrative into a
bounded evidence structure. The external GPU machine is off; no rerun is required and
missing historical evidence must remain explicit.

## 2. Classification

Every CCV-R1 artifact is classified:

```text
EXPERIMENT EVIDENCE
NOT PRODUCTION CODE
NOT A MILESTONE DELIVERABLE
SYNTHETIC_TEST_ONLY
NOT FOR PRODUCTION
```

The report status is:

```text
EXPERIMENT REPORTED / INDEPENDENT REPRODUCTION NOT POSSIBLE
```

No validation acceptance or schema authority follows from this checkpoint.

## 3. Evidence rules

1. The corrected expected count is `50`: R1 `10`, R2a `15`, R2b `10`, R3 `15`.
2. Each expected output receives its own manifest row.
3. Unknown historical seeds, hashes and commits stay null/pending.
4. Every model/artifact requires a positive byte size and SHA-256 before finalization.
5. SD1.5/SDXL family or `768/2048` conditioning mismatch fails closed.
6. Missing, zero-byte or digest-mismatched outputs fail closed.
7. Failures, retries and exclusions are explicit manifest facts.
8. Generated images and model binaries never enter this repository.

## 4. Architecture boundary

M6 already has `identityBindings[]`, the five accepted binding fields and
`IdentityAuthorizationPort`; current non-empty bindings fail closed. This evidence
record neither activates that boundary nor changes its consumer behavior.

Provider/model/workflow parameters belong to future M10/V4 execution concerns, not
M6 Character facts. That ownership statement prevents a known wrong direction; it
does not authorize M10 or V4 implementation.

## 5. Exact allowlist

This checkpoint may change only:

```text
AGENTS.md
AI_CINEMATIC_STUDIO_SYSTEM_MASTER_PLAN.md
CURRENT_MILESTONE.md
README.md
governance/ACS-GOV-POST-M6-P3-G1-CLOSEOUT.md
governance/ACS-CCV-R1-EVIDENCE-HARDENING.md
experiments/ccv-r1/README.md
experiments/ccv-r1/CHARACTER_CONSISTENCY_VALIDATION_REPORT_R1.md
experiments/ccv-r1/experiment-manifest.schema.json
experiments/ccv-r1/experiment-manifest.pending.json
experiments/ccv-r1/configs/round-1.json
experiments/ccv-r1/configs/round-2.json
experiments/ccv-r1/configs/round-3.json
experiments/ccv-r1/scripts/evidence_common.py
experiments/ccv-r1/scripts/character_consistency_test.py
experiments/ccv-r1/scripts/ipadapter_face_test.py
experiments/ccv-r1/scripts/ipadapter_pose_test.py
experiments/ccv-r1/validation/validate_fail_closed.py
experiments/ccv-r1/workflows/README.md
experiments/ccv-r1/evidence/README.md
```

Any `services/`, `apps/` or `tests/` diff is a hard stop.

## 6. Prohibitions

- no Schema, Migration or DDL;
- no M6-P4+, M7/M8/M9/M10 implementation;
- no HTTP/API, Auth/RBAC or Frontend;
- no production GPU, Worker or ComfyUI integration;
- no generated image or model binary;
- no claim that the experiment passed validation;
- no CCV-R2 or Character Visual Identity ADR entry.

## 7. Stop state

After all gates, commit, non-force publication, Draft PR, CI and remote equality:

```text
ACS-CCV-R1-EVIDENCE-HARDENING CHECKPOINT CANDIDATE
PROJECT LEAD OWNER REVIEW REQUIRED
CCV-R2 / SCHEMA WORK NOT AUTHORIZED
PRODUCTION READY: NO
```
