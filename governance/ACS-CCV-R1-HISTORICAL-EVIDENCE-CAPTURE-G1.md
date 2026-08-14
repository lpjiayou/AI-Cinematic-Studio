# ACS-CCV-R1 Historical Evidence Capture G1

## 1. Record

| Field | Value |
| --- | --- |
| Task | `ACS-CCV-R1-HISTORICAL-EVIDENCE-CAPTURE-G1` |
| Date | `2026-08-14` |
| Decision | `EXPERIMENT-EVIDENCE TOOLING CLOSURE AUTHORIZED` |
| Execution mode | `MANUAL / BOUNDED / FAIL-CLOSED` |
| Authorized base | `9094a46615f2be9ca45f95418ac441326d326315` |
| Authorized base tree | `d372581f0f0f434e10df78542ef4ac9bbefbfb51` |
| Base status | `G0 OWNER ACCEPTED / REMOTE-VERIFIED / PR #5 CI PASS` |

The Project Lead directly accepted G0 and separately authorized G1. G1 closes only
the three experiment-evidence tooling blockers recorded by G0. It does not start the
external GPU host, collect any external byte, rerun ComfyUI or accept the experiment.

## 2. Required closures

### CCV-CAPTURE-001

Replace the hardcoded historical-script recovery claim with a value derived from the
three exact historical-script records. Custody and historical usage remain separate.

### CCV-CAPTURE-002

Normalize the complete 27-record G0 inventory, including references, crop lineage,
environment, model source and license state. Recovered, missing and ambiguous evidence
must be distinguishable without guessing.

### CCV-CAPTURE-003

Define a normalized failure/retry/exclusion ledger linked to the frozen 50-run
register and supporting evidence references. Failed historical attempts must not be
silently collapsed into successful output rows.

## 3. Governance checkpoint allowlist

```text
AGENTS.md
AI_CINEMATIC_STUDIO_SYSTEM_MASTER_PLAN.md
CURRENT_MILESTONE.md
README.md
governance/ACS-CCV-R1-HISTORICAL-EVIDENCE-CAPTURE-G1.md
```

This governance-only checkpoint must be committed, non-force published and remotely
verified before the tooling paths below are edited.

## 4. Tooling implementation allowlist

```text
experiments/ccv-r1/capture/README.md
experiments/ccv-r1/capture/historical-capture.schema.json
experiments/ccv-r1/capture/finalize_historical_capture.py
experiments/ccv-r1/experiment-manifest.schema.json
experiments/ccv-r1/scripts/evidence_common.py
experiments/ccv-r1/validation/validate_capture_plan.py
experiments/ccv-r1/validation/validate_capture_tooling.py
```

No other implementation path is authorized.

## 5. Required behavior

- the G0 pending plan remains immutable and continues to describe a powered-off host;
- the future collection input covers exactly the 27 registered non-output records and
  all 50 run IDs;
- every recovered file is positive-size, SHA-256 verified and path-confined beneath
  an explicitly supplied read-only evidence root;
- model records reuse actual safetensors architecture inspection and reject zero-byte,
  malformed and SD1.5/SDXL mismatched files;
- the face-crop record requires explicit lineage to the full-body reference record;
- recovered models require explicit source and license state;
- capture-time environment state is not represented as historical state without a
  verified usage link;
- the three historical-script records alone derive
  `historicalScriptBytesRecovered`;
- failures, retries and exclusions use unique event IDs and evidence references;
- a partial recovery is labelled partial and can never claim full capture;
- every output and seed remains linked to an exact frozen run ID;
- no raw image, model, log, workflow or external script byte is committed to Git.

## 6. Validation

- all CLI entry points pass `--help` without GPU dependencies;
- no-GPU fixtures prove complete, partial, zero-byte, traversal, script-derivation,
  crop-lineage, source/license and failure-ledger behavior;
- the frozen `10 / 25 / 15 = 50` register remains exact;
- existing Core regression remains `464/464`;
- product, application and existing `tests/` blobs remain unchanged;
- Markdown, documentation links, Python AST, secret scan and `git diff --check` pass;
- commit, non-force publication, Local SHA = Remote SHA, `0/0`, clean worktree,
  Draft PR and Repository Validation pass.

## 7. Prohibitions

- no external GPU start, snapshot, SSH or provider action;
- no real evidence collection or image regeneration;
- no `services/`, `apps/` or `tests/` modification;
- no product Schema, Migration, DDL, HTTP/API, Auth/RBAC or Frontend change;
- no M6-P4+, M7-M19, CCV-R2-G0 or Character Visual Identity implementation;
- no claim that CCV-R1 is independently reproduced or validation accepted.

## 8. Stop state

```text
ACS-CCV-R1-HISTORICAL-EVIDENCE-CAPTURE-G1 CHECKPOINT CANDIDATE
EXTERNAL GPU COLLECTION NOT STARTED
EXTERNAL COLLECTION G2 REQUIRES SEPARATE AUTHORIZATION
CCV-R2-G0 NOT AUTHORIZED
PRODUCTION READY: NO
```
