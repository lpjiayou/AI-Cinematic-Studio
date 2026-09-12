# SH09 R3 — Exact offline binding and runtime seam candidate

Status: IMPLEMENTATION CANDIDATE / OWNER REVIEW PENDING.

Task: `ACS-SH09-EXACT-OFFLINE-BINDING-AND-RUNTIME-SEAM-R3-20260913`.
Base: `3e5b8d08d3eef26506a69be99c42c90f38826cc0`;
tree: `a644acd1bfc9f1304e1389d5d442acc96d5251a2`.

The Project Lead authorized A01—A06 and the narrow [ADR-0022 §5.7](../../governance/ADR-0022-generation-dispatch-grant.md#57-v14-r3-原图历史前像和完整编码增量)
increment. No R2/F01 or Package 1/2/3 acceptance is reopened.

Three supplied original archives are available. The offline explicit-input builder
checks archive/member SHA and safe membership, compares the full original and new
16-node graph, and records only `/20/inputs/text` as the Camera revision. Output
node 41 and omitted CLIPLoader device are preserved. Original archives are not
rewritten or executed. Private source data and candidate prompts stay outside Git.

Profile/compiler/runtime/request and complete encoding use explicit new versions.
Historical argv/model preimages remain distinct from contract digests and current
observations. Model metadata is not proof that weight bytes were checked locally.
CRF16, medium, movflags=0, threads=1, tool identities and frame mapping are bound
before sending and checked against derivation evidence. The omitted historical
defaults and single-thread delta remain explicit candidate choices for review.

Tests use the original V5 assembly, Job/Attempt, temporary SQLite and fixture-owned
loopback with synthetic media. They are not SH09 generation or live GPU evidence.
Exact test commands, raw logs, candidate commit/tree, patch and SHA list are in the
external candidate delivery; no count or acceptance is predicted here.

- Camera prompt: PROPOSED_PENDING_OWNER_ACCEPTANCE.
- Exact offline binding Owner acceptance: PENDING.
- Live runtime currentness: NOT_CHECKED; systemRuntimeBound=false.
- Prompt submission authorized: false; Spike-0 executed: false; readiness: BLOCKED.
- Publication, deployment, formal database/Grant, GPU/SSH and B—G: NOT AUTHORIZED.

HISTORICAL_PATH_NOT_EXECUTION_AUTHORITY=true. This record is evidence of a bounded
local candidate, not an approval bundle, deployment file or production completion.
