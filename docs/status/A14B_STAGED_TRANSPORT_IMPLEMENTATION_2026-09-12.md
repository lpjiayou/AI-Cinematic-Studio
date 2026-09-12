# A14B Compatibility and Staged Transport — R2 Implementation Candidate

Status: `IMPLEMENTATION_CANDIDATE / OWNER_REVIEW_PENDING`

Date: `2026-09-12`

Task: `ACS-A14B-CONTRACT-COMPATIBILITY-AND-STAGED-TRANSPORT-R2-20260912`

Base commit: `ad7349ff493baaa1e0bc831810ea28b3dd2b2dce`

Base tree: `a1f0f68ad69ea90d9c9cd96c2ed2ae33df4b2c93`

Branch: `feature/a14b-staged-transport-r2`

HISTORICAL_PATH_NOT_EXECUTION_AUTHORITY=true

## Authority and immutable history

The Project Lead explicitly authorized the [ADR-0022](../../governance/ADR-0022-generation-dispatch-grant.md)
v1.3 narrow compatibility increment and local staged-transport engineering. The R2
task package SHA-256 is `f534853983be877de027d959ed33ba96e7db915f7ea1a3f12f52a3b1e3370b6b`.
It does not change Grant/Terminal approval, revocation, CAS, coordination, lease,
slot, at-most-once or original Job/Attempt authority. Prior Package 1/2/3 acceptance
records and exact old three-model validation remain independent historical facts.

## Bounded implementation

The new profile, compiler and runtime schemas distinguish six explicit model roles,
paired expert/LoRA stages, exact input contracts and a fixed 49-PNG output topology.
The engineering template is `TEST_ONLY`; it cannot establish SH09 exact binding.
Its backend class is restricted to fixture-owned loopback, not a live GPU endpoint.
The approved prompt is distinct from the original Script action and receives no
implicit camera suffix. Original upstream lineage is still read at L1 and L2.

The explicit transport factory has no import/constructor/open network effects.
The spent, in-process Capability authorizes one bounded write inside L2. Response,
history, downloads and postprocessing occur outside that gate. Network uncertainty
is preserved without retry, redirect, fallback or a second Attempt. A local sealed
submission identity is independent of the provider prompt identifier.

Native PNG content hashes and ordered indices are retained separately from the
derived MP4 hash. CPU postprocessing selects indices 0–47 and drops index 48, then
fresh ffprobe checks 704×1280, 48 frames, 24 fps and two seconds. The result boundary
uses the original artifact commit intent and durable replace. Unobserved provider
GPU usage and cost remain UNKNOWN, never Fake `false` or zero-cost evidence.

## Validation evidence and limits

The external candidate archive contains exact commands, failed and corrected raw
logs, scoped regression results, file hashes, the complete patch and a machine
manifest tied to its final local commit/tree. Tests use temporary SQLite databases,
synthetic media and HTTP servers created and held by the test fixtures. Existing
services, port 8188, SSH tunnels and formal data are not used. The local Linux CPU
runner exercises real fcntl/flock and FFmpeg; it is not an M12 build-host approval.
No full Core suite or GitHub CI is claimed by this bounded evidence.

One bounded search did not find the three required original frozen packages.
`A13=NOT_RUN_MISSING_ORIGINAL_EVIDENCE`; no synthetic skipped test substitutes for it.
The external intake record preserves the roots, names and results of that search.

```text
SH09_EXACT_BINDING=BLOCKED_MISSING_ORIGINAL_EVIDENCE
OWNER_ACCEPTANCE=PENDING
PUBLICATION=NOT_AUTHORIZED
REAL_COMFYUI_CONNECTIONS=0
REAL_PROMPT_SUBMISSIONS=0
GPU_EXECUTIONS=0
FORMAL_DATABASE_ACCESSES=0
NEW_PAID_OPERATIONS_STARTED=0
SYSTEM_RUNTIME_BOUND=false
PROMPT_SUBMISSION_AUTHORIZED=false
SPIKE_0_READINESS=BLOCKED
```

Final independent review, publication, trusted original binding, deployment and any
single real generation each retain their separate authorization gates. This record
is not an Owner signature, a live Grant, a runtime attestation or production approval.
