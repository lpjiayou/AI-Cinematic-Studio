# ACS-CCV-R1 Historical Evidence Capture G2

## 1. Record

| Field | Value |
| --- | --- |
| Task | `ACS-CCV-R1-HISTORICAL-EVIDENCE-CAPTURE-G2` |
| Date | `2026-08-14` |
| Decision | `ONE-WINDOW EXTERNAL HISTORICAL EVIDENCE COLLECTION AUTHORIZED` |
| Execution mode | `MANUAL / READ-ONLY SOURCE / FAIL-CLOSED` |
| Authorized base | `af34ac074cb8bfbf334e4f56aad0c0d479b741be` |
| Authorized base tree | `0cec29c8de8777c5c3dbb824b2a7f421d9cb9c36` |
| Base evidence | `G1 REMOTE-VERIFIED / PR #6 DRAFT / REPOSITORY VALIDATION PASS / 464/464` |

The Project Lead separately authorized G2 after the G1 tooling checkpoint was
non-force published and remotely verified. G2 is an evidence-custody operation. It
does not rerun the experiment, accept CCV-R1, authorize CCV-R2 or change a product
schema.

## 2. Authorized collection

G2 may perform one bounded access window against the already-started external GPU
host to recover or explicitly mark unavailable:

- the exact 27 non-output records frozen by G0 and normalized by G1;
- all 50 historical output files and exact per-run seeds;
- failure, retry and exclusion evidence linked to the frozen run register;
- source size and SHA-256, custody location, usage-link state, license state and
  required face-crop lineage;
- an immutable provider snapshot reference when available without altering the
  source filesystem.

The G1 finalizer and schemas are the only authority for record count, run IDs,
accepted evidence states, path confinement, positive-size checks and model
architecture/dimension validation.

## 3. Read-only boundary

Historical source bytes are read-only. The collector may list metadata, read and hash
files, and copy bytes into a newly created restricted collection destination outside
the historical source directories. It must not:

- start ComfyUI, a worker, model server or generation script;
- regenerate, repair, convert, crop, rename, touch, chmod or rewrite a source file;
- install or upgrade a package, node or model;
- infer a seed, workflow, usage link, license or missing byte from narrative memory;
- treat current environment state as historical without a verified usage link;
- follow a symlink outside the explicit evidence root;
- expose raw log, credential, token, private key or provider response in Git or chat.

If source and destination cannot be separated, collection stops. A missing,
zero-byte, ambiguous or unlinked item remains explicit and is never recreated.

## 4. External custody layout

Raw bytes remain outside Git in access-controlled storage under a dedicated root:

```text
ccv-r1-2026-08-14-evidence/
├─ raw/
├─ inventory/
├─ manifests/
└─ custody/
```

The destination may contain copied scripts, workflows, references, skeletons, logs,
outputs and environment records. Model bytes may remain in an immutable snapshot or
restricted object store, but the independent reviewer must retain access to the bytes
behind every model digest.

## 5. Governance checkpoint allowlist

```text
AGENTS.md
AI_CINEMATIC_STUDIO_SYSTEM_MASTER_PLAN.md
CURRENT_MILESTONE.md
README.md
governance/ACS-CCV-R1-HISTORICAL-EVIDENCE-CAPTURE-G2.md
```

This authorization checkpoint must be committed, non-force published and remotely
verified before evidence bytes are read.

## 6. Collection outputs

The external collection window may write only outside the repository:

```text
capture-input.json
historical-evidence-manifest.json
inventory/source-inventory.json
inventory/source-inventory.sha256
inventory/custody-copy-inventory.json
inventory/custody-copy-inventory.sha256
custody/collection-receipt.json
```

The two inventories must independently agree on every copied byte's size and digest
before the source host is shut down. Normalized manifests remain
`COLLECTION_INPUT_NOT_REVIEWED` or partial until a later independent review.

No collected raw byte or generated image is added to the repository in G2. A later
review package requires separate scope if sanitized manifest facts are to be
committed.

## 7. Gates

- governance checkpoint Local SHA equals Remote SHA, ahead/behind `0/0`, clean;
- source access is read-only and the destination is isolated;
- exact 27-record and 50-run registers are preserved;
- every recovered file is positive-size and SHA-256 verified;
- models pass actual safetensors architecture and SDXL dimension checks;
- all unavailable or usage-unverified evidence remains explicit;
- two independent inventories agree before host shutdown;
- normalized inputs pass the G1 finalizer without GPU execution;
- no raw secret or external binary enters Git;
- production, application and existing test blobs remain unchanged;
- full Core regression remains `464/464`.

## 8. Prohibitions and stop state

No `services/`, `apps/`, `tests/`, Schema, Migration, DDL, HTTP/API, Auth/RBAC,
Frontend, M6-P4+, M7-M19, CCV-R2 or Character Visual Identity implementation is
authorized.

After capture and offline validation:

```text
ACS-CCV-R1-HISTORICAL-EVIDENCE-CAPTURE-G2 CHECKPOINT CANDIDATE
EXTERNAL EVIDENCE COLLECTED OR EXPLICITLY MARKED UNAVAILABLE
INDEPENDENT REVIEW REQUIRED
CCV-R2-G0 NOT AUTHORIZED
PRODUCTION READY: NO
```
